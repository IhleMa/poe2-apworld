"""Path of Exile 2 automation for the bundled Manual client.

Everything here only *reads* game output and writes your own loot filter file - it never
touches the game process, its memory or GGG's servers:

* Client.txt watcher  - zone entries, level-ups, your deaths (DeathLink), act/campaign goals
* Loot filter writer  - ArchipelagoPoE2.filter highlights every base you still need to pick up,
                        with your normal filter appended below it
* Clipboard watcher   - hover an item in game and press Ctrl+C: its base-type check is sent,
                        and you are warned if you haven't unlocked that rarity for the slot

Boss kills are not written to Client.txt, so those checks are still clicked in the client.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import os
import re
import sys
import time
import typing
from pathlib import Path

import Utils
from CommonClient import logger

from .Helpers import load_data_file
from .poe2_character_check import OAUTH_STATUS

if typing.TYPE_CHECKING:
    from .ManualClient import ManualContext

GAME_NAME = "PathOfExile2"
FILTER_NAME = "ArchipelagoPoE2"
STEAM_APP_ID = "2694490"

META = load_data_file("poe2_meta.json")
ZONE_LOCATION_BY_AREA: dict[str, str] = META.get("zone_location_by_area", {})
BASE_GROUPS: dict[str, str] = META.get("base_groups", {})
BASES_BY_LENGTH = sorted(BASE_GROUPS, key=len, reverse=True)
GEM_NAMES: set[str] = set(META.get("gems", {}))
SUPPORT_GEM_TO_ITEM: dict[str, tuple[str, int]] = {
    gem: (item_name, idx)
    for item_name, data in META.get("supports", {}).items()
    for idx, gem in enumerate(data["gems"])
}


def PROGRESSIVE_SUPPORTS(integ) -> bool:
    return bool(integ.slot_data.get("poe2_progressive_supports"))

# ---------------------------------------------------------------- log parsing
# System lines look like "... [INFO Client 1234] : You have entered X." - chat lines have a name before the colon
# ("[INFO Client 1234] @From Name: ...", "Name: ..."), so anchoring on "] : " ignores anything typed in chat.
RE_AREA = re.compile(r'\] Generating level (\d+) area "([^"]+)"')
RE_ENTERED = re.compile(r"\] : You have entered (.+?)\.\s*$")
# PoE2 logs zone loads as "[SCENE] Set Source [Clearfell]" (PoE1's "You have entered" may not appear at all)
RE_SCENE = re.compile(r"\] \[SCENE\] Set Source \[(.+?)\]")
# the "(Class)" part is optional: PoE2 may log just "Name is now level N"
RE_LEVEL = re.compile(r"\] : ([^\s:()]+)(?: \(([^)]+)\))? is now level (\d+)\s*$")
RE_CONNECT = re.compile(r"\] Connecting to instance server.*? for character (\S+)", re.IGNORECASE)
RE_SLAIN = re.compile(r"\] : ([^\s:]+) has been slain\.\s*$")
ZONE_LOCATION_BY_NAME = {v[len("Enter "):]: v for v in ZONE_LOCATION_BY_AREA.values()}

# goal location name -> predicate on an entered area id
GOAL_AREA_TESTS: dict[str, typing.Callable[[str], bool]] = {
    "Victory - Complete Act 1": lambda a: a.startswith("G2_"),
    "Victory - Complete Act 2": lambda a: a.startswith("G3_"),
    "Victory - Complete Act 3": lambda a: a.startswith("G4_"),
    "Victory - Complete Act 4": lambda a: a.startswith(("P1_", "P2_", "P3_")),
    "Victory - Complete the Campaign": lambda a: a == "G_Endgame_Town",
}

# ---------------------------------------------------------------- clipboard items
ITEM_CLASS_TO_UNLOCKS = {
    "Helmets": ["Helmet"], "Body Armours": ["Body Armour"], "Gloves": ["Gloves"], "Boots": ["Boots"],
    "Belts": ["Belt"], "Amulets": ["Amulet"], "Rings": ["Ring (Left)", "Ring (Right)"],
    "One Hand Maces": ["One Hand Mace"], "Two Hand Maces": ["Two Hand Mace"], "Quarterstaves": ["Quarterstaff"],
    "Spears": ["Spear"], "Bows": ["Bow"], "Crossbows": ["Crossbow"], "Wands": ["Wand"], "Staves": ["Staff"],
    "Sceptres": ["Sceptre"], "Talismans": ["Talisman"], "Shields": ["Shield"], "Bucklers": ["Buckler"],
    "Foci": ["Focus"], "Quivers": ["Quiver"],
}
RARITY_TIER = {"Normal": 1, "Magic": 2, "Rare": 3, "Unique": 4}
TIER_NAME = {0: "nothing", 1: "Normal", 2: "Magic", 3: "Rare", 4: "Unique"}


def parse_item_text(text: str) -> tuple[str | None, str | None, str | None]:
    """Returns (item_class, rarity, base_type) from PoE2's Ctrl+C item text."""
    lines = [l.strip() for l in text.replace("\r", "").split("\n")]
    if not lines or not lines[0].startswith("Item Class:"):
        return None, None, None
    item_class = lines[0].split(":", 1)[1].strip()
    rarity = None
    header: list[str] = []
    for line in lines[1:]:
        if line.startswith("Rarity:"):
            rarity = line.split(":", 1)[1].strip()
            continue
        if line.startswith("--------"):
            break
        if line:
            header.append(line)
    for line in reversed(header):           # rare/unique: last header line is the base
        candidate = line.removeprefix("Superior ").strip()
        if candidate in BASE_GROUPS:
            return item_class, rarity, candidate
    for line in header:                      # magic: base is inside "Prefix Base of Suffix"
        for base in BASES_BY_LENGTH:
            if re.search(rf"(^|\s){re.escape(base)}($|\s)", line):
                return item_class, rarity, base
    return item_class, rarity, None


# ---------------------------------------------------------------- loot filter
def build_filter_text(unchecked_bases: list[str], base_filter_text: str | None, sound: bool) -> str:
    out = [
        "# Generated by the Path of Exile 2 Archipelago client - this file is rewritten automatically.",
        "# Highlighted (purple, star on minimap) = base types whose 'Pick up' check you haven't sent yet.",
        "",
    ]
    if unchecked_bases:
        quoted = " ".join(f'"{b}"' for b in sorted(unchecked_bases))
        out += [
            f"# --- Archipelago: {len(unchecked_bases)} unchecked bases ---",
            "Show",
            f"    BaseType == {quoted}",
            "    SetFontSize 45",
            "    SetTextColor 255 255 255 255",
            "    SetBorderColor 255 0 255 255",
            "    SetBackgroundColor 110 0 110 230",
            "    PlayEffect Purple",
            "    MinimapIcon 0 Purple Star",
        ]
        if sound:
            out.append("    PlayAlertSound 6 300")
        out.append("")
    if base_filter_text:
        out += ["# --- Your base filter follows ---", base_filter_text]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- path detection
def _documents_dirs() -> list[Path]:
    home = Path.home()
    dirs = [home / "Documents", home / "OneDrive" / "Documents", home / "OneDrive" / "Dokumente", home / "Dokumente"]
    for steam in (home / ".local/share/Steam", home / ".steam/steam"):
        dirs.append(steam / f"steamapps/compatdata/{STEAM_APP_ID}/pfx/drive_c/users/steamuser/Documents")
    return dirs


def detect_filter_dir() -> str | None:
    for d in _documents_dirs():
        p = d / "My Games" / "Path of Exile 2"
        if p.is_dir():
            return str(p)
    return None


def detect_client_txt() -> str | None:
    candidates = []
    if sys.platform == "win32":
        for drive in "CDEFGH":
            for sub in (r"Program Files (x86)\Grinding Gear Games\Path of Exile 2",
                        r"Program Files\Grinding Gear Games\Path of Exile 2",
                        r"Grinding Gear Games\Path of Exile 2",
                        r"Program Files (x86)\Steam\steamapps\common\Path of Exile 2",
                        r"Program Files\Steam\steamapps\common\Path of Exile 2",
                        r"SteamLibrary\steamapps\common\Path of Exile 2",
                        r"Steam\steamapps\common\Path of Exile 2",
                        r"Games\Path of Exile 2"):
                candidates.append(Path(f"{drive}:\\") / sub / "logs" / "Client.txt")
    home = Path.home()
    candidates += [home / ".local/share/Steam/steamapps/common/Path of Exile 2/logs/Client.txt",
                   home / ".steam/steam/steamapps/common/Path of Exile 2/logs/Client.txt",
                   home / "Library/Application Support/Steam/steamapps/common/Path of Exile 2/logs/Client.txt"]
    found = [c for c in candidates if c.is_file()]
    if not found:
        return None
    return str(max(found, key=lambda c: c.stat().st_mtime))


# ---------------------------------------------------------------- integration
class _Clipboard:
    @staticmethod
    def read() -> str | None:
        try:
            from kivy.core.clipboard import Clipboard
            return Clipboard.paste()
        except Exception:
            return None

    @staticmethod
    def write(text: str) -> None:
        from kivy.core.clipboard import Clipboard
        Clipboard.copy(text)


class _WhisperLogHandler(logging.Handler):
    """Forwards the client's own [PoE2] messages to in-game whispers (category from extra=, else by level)."""
    _installed: "_WhisperLogHandler | None" = None

    def __init__(self, integration):
        super().__init__(level=logging.INFO)
        self.integ = integration

    @classmethod
    def install(cls, integration):
        if cls._installed:
            logger.removeHandler(cls._installed)
        cls._installed = cls(integration)
        logger.addHandler(cls._installed)

    def emit(self, record: logging.LogRecord):
        try:
            msg = record.getMessage()
            if not msg.startswith("[PoE2]") or getattr(record, "poe2_no_whisper", False):
                return
            category = getattr(record, "poe2_category", None) or \
                ("warnings" if record.levelno >= logging.WARNING else "client_info")
            self.integ.chat.queue_whisper(msg[len("[PoE2]"):].strip(), category)
        except Exception:
            pass


class PoE2Integration:
    SETTINGS_KEY = "poe2_archipelago"

    def __init__(self, ctx: "ManualContext"):
        self.ctx = ctx
        stored = Utils.persistent_load().get(self.SETTINGS_KEY, {})
        self.settings: dict[str, typing.Any] = {
            "client_txt": stored.get("client_txt") or detect_client_txt() or "",
            "filter_dir": stored.get("filter_dir") or detect_filter_dir() or "",
            "base_filter": stored.get("base_filter", ""),
            "character": stored.get("character", ""),
            "enabled": stored.get("enabled", True),
            "filter_sound": stored.get("filter_sound", True),
            "clipboard": stored.get("clipboard", True),
            "auto_reload_filter": stored.get("auto_reload_filter", True),
            # whispers on/off (older versions stored whisper_mode off|important|all)
            "whispers": stored.get("whispers", stored.get("whisper_mode", "important") != "off"),
            "whisper_hidden": stored.get("whisper_hidden", None),
            "chat_timing": stored.get("chat_timing", "instant"),
        }
        self._log_pos: int | None = None
        self._log_path_open: str | None = None
        self._last_clip = None
        self._last_filter_key = None
        self._deathlink_received_at = 0.0
        self._announced = False
        self.slot_data: dict = {}
        from .poe2_character_check import CharacterChecker
        self.checker = CharacterChecker(self)
        from .poe2_ingame import InGameChat
        self.chat = InGameChat(self)
        self.clipboard = _Clipboard()
        _WhisperLogHandler.install(self)
        # Older versions could store a POESESSID / character id; wipe them from disk.
        for old_key in ("poesessid", "account", "character_id", "api_enabled"):
            if stored.get(old_key):
                Utils.persistent_store(self.SETTINGS_KEY, old_key, "")

    # ---------- helpers
    @property
    def active(self) -> bool:
        return bool(self.settings["enabled"]) and self.ctx.game == GAME_NAME and bool(self.ctx.server)

    def save(self, key: str, value):
        self.settings[key] = value
        Utils.persistent_store(self.SETTINGS_KEY, key, value)

    def location_id(self, name: str) -> int | None:
        return getattr(self.ctx, "location_names_to_id", {}).get(name)

    def send_location(self, name: str, reason: str) -> bool:
        loc_id = self.location_id(name)
        if loc_id is None or loc_id not in self.ctx.missing_locations or loc_id in self.ctx.locations_checked:
            return False
        self.ctx.locations_checked.append(loc_id)
        self.ctx.syncing = True
        logger.info(f"[PoE2] {reason}: sent '{name}'")
        return True

    def received_count(self, item_name: str) -> int:
        item_id = getattr(self.ctx, "item_names_to_id", {}).get(item_name)
        return sum(1 for i in self.ctx.items_received if i.item == item_id) if item_id is not None else 0

    def status_lines(self) -> list[str]:
        s = self.settings
        def flag(path, is_dir=False):
            return "OK" if path and (Path(path).is_dir() if is_dir else Path(path).is_file()) else "NOT FOUND"
        return [
            f"Automation: {'on' if s['enabled'] else 'off'}",
            f"Client.txt: {s['client_txt'] or '(not set)'} [{flag(s['client_txt'])}]",
            f"Filter folder: {s['filter_dir'] or '(not set)'} [{flag(s['filter_dir'], True)}] -> {FILTER_NAME}.filter",
            f"Base filter: {s['base_filter'] or '(none)'}",
            f"Character: {s['character'] or '(auto: first character that levels up)'}",
            f"Clipboard pickups (Ctrl+C on an item): {'on' if s['clipboard'] else 'off'}",
            self.chat.status_line(),
            f"Character API: {OAUTH_STATUS}",
        ]

    # ---------- events from the Manual client
    def on_package(self, cmd: str, args: dict):
        if self.ctx.game != GAME_NAME:
            return
        if cmd == "Connected":
            self.slot_data = args.get("slot_data") or {}
        if cmd == "Connected" and not self._announced:
            self._announced = True
            for line in self.status_lines():
                logger.info(f"[PoE2] {line}")
            logger.info("[PoE2] Type /poe2 for help. Select the 'ArchipelagoPoE2' filter in PoE2's game options.")
        if cmd in ("Connected", "RoomUpdate"):
            self.write_filter()
        if cmd == "PrintJSON":
            self.on_print_json(args)

    def on_print_json(self, args: dict):
        kind = args.get("type")
        me = self.ctx.slot
        item = args.get("item")
        involves_me = args.get("receiving") == me or getattr(item, "player", None) == me
        if kind in ("ItemSend", "ItemCheat"):
            category = "my_items" if involves_me else "other_items"
        elif kind == "Hint":
            category = "hints" if involves_me else "other_hints"
        elif kind in ("Chat", "ServerChat"):
            category = "chat"
        elif kind in ("Goal", "Release", "Collect", "Countdown"):
            category = "progress"
        elif kind in ("Join", "Part", "TagsChanged"):
            category = "join_leave"
        elif kind in ("CommandResult", "AdminCommandResult", "Tutorial"):
            category = "server_replies"
        else:
            category = "other"
        try:
            text = self.ctx.rawjsontotextparser(copy.deepcopy(args.get("data", [])))
        except Exception:
            return
        self.chat.queue_whisper(text, category)

    def on_deathlink(self, data: dict):
        if self.ctx.game == GAME_NAME:
            self._deathlink_received_at = time.time()
            logger.warning(f"[PoE2] DeathLink from {data.get('source')}! Log out to character select (PoE1 convention).")

    # ---------- loot filter
    def unchecked_bases(self) -> list[str]:
        out = []
        for base in BASE_GROUPS:
            loc_id = self.location_id(f"Pick up {base}")
            if loc_id is not None and loc_id in self.ctx.missing_locations:
                out.append(base)
        return out

    def write_filter(self, force: bool = False):
        d = self.settings["filter_dir"]
        if not d or not Path(d).is_dir() or self.ctx.game != GAME_NAME:
            return
        bases = self.unchecked_bases()
        key = (tuple(bases), self.settings["base_filter"], self.settings["filter_sound"])
        if key == self._last_filter_key and not force:
            return
        base_text = None
        bf = self.settings["base_filter"]
        if bf:
            bf_path = Path(bf) if os.path.isabs(bf) else Path(d) / bf
            if bf_path.suffix != ".filter":
                bf_path = bf_path.with_suffix(".filter")
            if bf_path.name == f"{FILTER_NAME}.filter":
                logger.warning("[PoE2] The base filter can't be the Archipelago filter itself.")
            elif bf_path.is_file():
                base_text = bf_path.read_text(encoding="utf-8-sig", errors="replace")
            else:
                logger.warning(f"[PoE2] Base filter not found: {bf_path}")
        target = Path(d) / f"{FILTER_NAME}.filter"
        tmp = target.with_suffix(".tmp")
        try:
            tmp.write_text(build_filter_text(bases, base_text, self.settings["filter_sound"]), encoding="utf-8")
            os.replace(tmp, target)
        except OSError as e:
            logger.warning(f"[PoE2] Could not write loot filter ({e}). Is the folder synced/locked by OneDrive?")
            return
        if self._last_filter_key is not None:
            logger.info(f"[PoE2] Loot filter updated ({len(bases)} bases highlighted).",
                        extra={"poe2_no_whisper": True})
        self._last_filter_key = key
        self.chat.queue_filter_reload()

    # ---------- Client.txt
    def handle_log_line(self, line: str):
        m = RE_AREA.search(line)
        if m:
            self.chat.on_zone_entered("area generated")
            self.on_area(m.group(2))
            return
        m = RE_SCENE.search(line) or RE_ENTERED.search(line)
        if m:
            zone = m.group(1).strip()
            if zone in ("(null)", "(unknown)") or re.fullmatch(r"Act \d+", zone):
                return
            self.chat.on_zone_entered(f"entered {zone}")
            loc = ZONE_LOCATION_BY_NAME.get(zone)
            if loc:
                self.send_location(loc, "Zone entered")
            return
        m = RE_CONNECT.search(line)
        if m and not self.settings["character"]:
            self.save("character", m.group(1))
            logger.info(f"[PoE2] Tracking character '{m.group(1)}'. Change with /poe2_character.")
            return
        m = RE_LEVEL.search(line)
        if m:
            name, cls, level = m.group(1), m.group(2), int(m.group(3))
            if not self.settings["character"]:
                self.save("character", name)
                logger.info(f"[PoE2] Tracking character '{name}'{f' ({cls})' if cls else ''}. "
                            "Change with /poe2_character.")
            if name == self.settings["character"]:
                for lvl in range(2, level + 1):
                    self.send_location(f"Reach Level {lvl}", f"Level {level}")
            return
        m = RE_SLAIN.search(line)
        if m and m.group(1) == self.settings["character"]:
            self.on_own_death()

    def on_area(self, area_id: str):
        loc = ZONE_LOCATION_BY_AREA.get(area_id)
        if loc:
            self.send_location(loc, "Zone entered")
        goal = getattr(self.ctx, "goal_location", None) or {}
        test = GOAL_AREA_TESTS.get(goal.get("name", ""))
        if test and test(area_id) and not self.ctx.finished_game and not self.ctx.goaled:
            logger.info(f"[PoE2] Goal reached ({goal['name']})!", extra={"poe2_category": "progress"})
            self.ctx.goaled = True
            self.ctx.syncing = True

    def on_own_death(self):
        if "DeathLink" not in self.ctx.tags:
            return
        if time.time() - self._deathlink_received_at < 15:
            return  # this death was caused by somebody else's DeathLink
        logger.info("[PoE2] You died - sending DeathLink.")
        self.ctx.deathlink_out = True
        ui = getattr(self.ctx, "ui", None)
        button = getattr(ui, "death_link_button", None) if ui else None
        if button is not None:
            button.text = "Death Link: Sent"

    def poll_log(self):
        path = self.settings["client_txt"]
        if not path or not os.path.isfile(path):
            return
        size = os.path.getsize(path)
        if self._log_path_open != path or self._log_pos is None or size < self._log_pos:
            # start at the end: only new events count (old log lines may be other characters)
            self._log_path_open, self._log_pos = path, size
            return
        if size == self._log_pos:
            return
        with open(path, "rb") as f:
            f.seek(self._log_pos)
            chunk = f.read(size - self._log_pos)
        last_nl = chunk.rfind(b"\n")
        if last_nl < 0:
            return
        self._log_pos += last_nl + 1
        for raw in chunk[:last_nl].split(b"\n"):
            self.handle_log_line(raw.decode("utf-8", errors="replace"))

    # ---------- clipboard
    def read_clipboard(self) -> str | None:
        return self.clipboard.read()

    def handle_clipboard(self, text: str):
        item_class, rarity, base = parse_item_text(text)
        if not item_class:
            return
        if base:
            if not self.send_location(f"Pick up {base}", "Item copied"):
                if self.location_id(f"Pick up {base}") is not None:
                    logger.info(f"[PoE2] {base}: already checked.", extra={"poe2_category": "pickups"})
        unlocks = ITEM_CLASS_TO_UNLOCKS.get(item_class)
        if unlocks and rarity in RARITY_TIER:
            have = max(min(self.received_count(f"Progressive {u}"), 4) for u in unlocks)
            if have < RARITY_TIER[rarity]:
                logger.warning(f"[PoE2] You can't equip this yet: {rarity} {item_class} needs "
                               f"{RARITY_TIER[rarity]} x 'Progressive {unlocks[0]}', you have {have} "
                               f"(allowed: {TIER_NAME[have]}).", extra={"poe2_category": "pickups"})

    def ignore_clipboard(self, text: str):
        """Don't treat text the client put back on the clipboard as a new Ctrl+C."""
        self._last_clip = text

    def poll_clipboard(self):
        if not self.settings["clipboard"]:
            return
        text = self.read_clipboard()
        if text is None:
            return
        if self._last_clip is None:
            self._last_clip = text   # ignore whatever was on the clipboard before we started
            return
        if text != self._last_clip:
            self._last_clip = text
            self.handle_clipboard(text)

    async def run(self):
        while not self.ctx.exit_event.is_set():
            try:
                if self.active:
                    self.poll_log()
                    self.poll_clipboard()
                    await self.chat.tick()
            except Exception as e:  # never let automation take the client down
                logger.exception(f"[PoE2] automation error: {e}")
            await asyncio.sleep(0.2)


# ---------------------------------------------------------------- client commands
def install_commands(processor_cls):
    from MultiServer import mark_raw

    def integ(self) -> PoE2Integration | None:
        i = getattr(self.ctx, "poe2", None)
        if i is None:
            self.output("PoE2 automation is not running.")
        return i

    def _cmd_poe2(self) -> bool:
        """PoE2: show automation status and the PoE2 commands."""
        i = integ(self)
        if not i:
            return False
        for line in i.status_lines():
            self.output(line)
        self.output("Commands: /poe2_log <path to Client.txt>, /poe2_filter_dir <folder>, /poe2_base_filter <name>, "
                    "/poe2_character <name>, /poe2_auto on|off, /poe2_clipboard on|off, /poe2_filter_sound on|off, "
                    "/poe2_filter (rewrite now), /poe2_filter_reload on|off, /poe2_whispers [on|off], /poe2_hide <category>, /poe2_show <category>, /poe2_chat_timing instant|zone, /poe2_chat_test, /poe2_chat_debug")
        return True

    @mark_raw
    def _cmd_poe2_log(self, path: str = "") -> bool:
        """PoE2: set the path to Path of Exile 2's logs/Client.txt (empty = auto-detect)."""
        i = integ(self)
        if not i:
            return False
        path = path.strip().strip('"') or detect_client_txt() or ""
        if not os.path.isfile(path):
            self.output(f"Not a file: {path or '(nothing auto-detected)'}")
            return False
        i.save("client_txt", path)
        i._log_pos = None
        self.output(f"Watching {path}")
        return True

    @mark_raw
    def _cmd_poe2_filter_dir(self, path: str = "") -> bool:
        """PoE2: set the folder PoE2 loads filters from (Documents/My Games/Path of Exile 2)."""
        i = integ(self)
        if not i:
            return False
        path = path.strip().strip('"') or detect_filter_dir() or ""
        if not os.path.isdir(path):
            self.output(f"Not a folder: {path or '(nothing auto-detected)'}")
            return False
        i.save("filter_dir", path)
        i.write_filter(force=True)
        self.output(f"Filter folder set; writing {FILTER_NAME}.filter there.")
        return True

    @mark_raw
    def _cmd_poe2_base_filter(self, name: str = "") -> bool:
        """PoE2: your normal filter (file name in the filter folder, or full path) to append below the AP highlights."""
        i = integ(self)
        if not i:
            return False
        i.save("base_filter", name.strip().strip('"'))
        i.write_filter(force=True)
        self.output(f"Base filter: {i.settings['base_filter'] or '(none)'}")
        return True

    @mark_raw
    def _cmd_poe2_character(self, name: str = "") -> bool:
        """PoE2: the character name whose level-ups/deaths count (empty = first one seen)."""
        i = integ(self)
        if not i:
            return False
        i.save("character", name.strip())
        self.output(f"Character: {i.settings['character'] or '(auto)'}")
        return True

    def _toggle(key, label):
        def cmd(self, value: str = "") -> bool:
            i = integ(self)
            if not i:
                return False
            new = (not i.settings[key]) if not value else value.lower() in ("on", "true", "yes", "1")
            i.save(key, new)
            if key == "filter_sound":
                i.write_filter(force=True)
            self.output(f"{label}: {'on' if new else 'off'}")
            return True
        cmd.__doc__ = f"PoE2: turn {label.lower()} on/off."
        return cmd

    def _cmd_poe2_filter(self) -> bool:
        """PoE2: rewrite the Archipelago loot filter now."""
        i = integ(self)
        if not i:
            return False
        i.write_filter(force=True)
        self.output(f"{len(i.unchecked_bases())} unchecked bases written to {FILTER_NAME}.filter.")
        return True

    @mark_raw
    def _cmd_poe2_session(self, value: str = "") -> bool:
        """PoE2: removed - session cookies are no longer supported."""
        self.output("Session-cookie (POESESSID) access was removed. If you pasted a POESESSID anywhere, log out of "
                    "pathofexile2.com / pathofexile.com to invalidate it. Tracking uses Client.txt and Ctrl+C.")
        return False

    def _cmd_poe2_whispers(self, value: str = "") -> bool:
        """PoE2: whispers on|off, or list the message categories and which ones are hidden."""
        from .poe2_ingame import CATEGORIES
        i = integ(self)
        if not i:
            return False
        value = value.strip().lower()
        if value in ("on", "off"):
            i.save("whispers", value == "on")
            if value == "off":
                i.chat.whispers.clear()
            self.output(f"Whispers: {value}")
            return True
        if value:
            self.output("Use /poe2_whispers on|off")
            return False
        hidden = i.chat.hidden
        self.output(f"Whispers: {'on' if i.chat.enabled else 'off'}, sent {i.chat.timing}. Categories:")
        for name, (desc, _) in CATEGORIES.items():
            self.output(f"  {'hidden ' if name in hidden else 'shown  '} {name}: {desc}")
        self.output("Change with /poe2_hide <category> and /poe2_show <category> ('all' works too).")
        return True

    def _set_hidden(self, value: str, hide: bool) -> bool:
        from .poe2_ingame import CATEGORIES
        i = integ(self)
        if not i:
            return False
        names = [n for n in value.lower().replace(",", " ").split() if n]
        if names == ["all"]:
            names = list(CATEGORIES)
        unknown = [n for n in names if n not in CATEGORIES]
        if not names or unknown:
            self.output(f"Unknown category {', '.join(unknown) or '(none given)'}. "
                        f"Categories: {', '.join(CATEGORIES)}, or 'all'.")
            return False
        hidden = i.chat.hidden
        hidden = hidden | set(names) if hide else hidden - set(names)
        i.save("whisper_hidden", sorted(hidden))
        self.output(f"Hidden: {', '.join(sorted(hidden)) or 'nothing'}")
        return True

    @mark_raw
    def _cmd_poe2_hide(self, value: str = "") -> bool:
        """PoE2: stop whispering a message category, e.g. /poe2_hide other_items (see /poe2_whispers)."""
        return _set_hidden(self, value, True)

    @mark_raw
    def _cmd_poe2_show(self, value: str = "") -> bool:
        """PoE2: whisper a message category again, e.g. /poe2_show join_leave (see /poe2_whispers)."""
        return _set_hidden(self, value, False)

    def _cmd_poe2_chat_timing(self, value: str = "") -> bool:
        """PoE2: when to type into game chat: instant (as messages arrive) or zone (only right after a zone loads)."""
        i = integ(self)
        if not i:
            return False
        value = value.strip().lower()
        if value not in ("instant", "zone"):
            self.output(f"Chat timing: {i.chat.timing}. Use /poe2_chat_timing instant|zone")
            return value == ""
        i.save("chat_timing", value)
        self.output(f"Chat timing: {value}")
        return True

    def _cmd_poe2_chat_debug(self) -> bool:
        """PoE2: show why in-game whispers / filter reload are or aren't being sent."""
        i = integ(self)
        if not i:
            return False
        for line in i.chat.debug_lines():
            self.output(line)
        return True

    def _cmd_poe2_chat_test(self) -> bool:
        """PoE2: queue a test whisper and a filter reload; they're sent after your next zone change."""
        i = integ(self)
        if not i:
            return False
        if not i.chat.kb.available:
            self.output(f"In-game chat is unavailable: {i.chat.kb.reason}.")
            return False
        if not i.settings.get("character"):
            self.output("Your character name isn't known yet - level up once or use /poe2_character <name>.")
            return False
        i.chat.whispers.append("Archipelago chat test - if you can read this, whispers work.")
        i.chat.reload_filter = True
        i.chat._pending_since = time.time()
        if i.chat.timing == "zone":
            self.output("Queued. Change zones in Path of Exile 2 (keep the game in front) and watch your chat.")
        else:
            self.output("Queued. Switch to Path of Exile 2 and watch your chat.")
        return True

    new_commands = {
        "poe2": _cmd_poe2,
        "poe2_log": _cmd_poe2_log,
        "poe2_filter_dir": _cmd_poe2_filter_dir,
        "poe2_base_filter": _cmd_poe2_base_filter,
        "poe2_character": _cmd_poe2_character,
        "poe2_filter": _cmd_poe2_filter,
        "poe2_auto": _toggle("enabled", "Automation"),
        "poe2_clipboard": _toggle("clipboard", "Clipboard pickups"),
        "poe2_filter_sound": _toggle("filter_sound", "Filter alert sound"),
        "poe2_filter_reload": _toggle("auto_reload_filter", "Automatic in-game filter reload"),
        "poe2_whispers": _cmd_poe2_whispers,
        "poe2_hide": _cmd_poe2_hide,
        "poe2_show": _cmd_poe2_show,
        "poe2_chat_timing": _cmd_poe2_chat_timing,
        "poe2_chat_test": _cmd_poe2_chat_test,
        "poe2_chat_debug": _cmd_poe2_chat_debug,
        "poe2_session": _cmd_poe2_session,
    }
    # CommandMeta collects commands when the class is created, so register them in both places.
    processor_cls.commands = dict(processor_cls.commands)
    for name, func in new_commands.items():
        setattr(processor_cls, f"_cmd_{name}", func)
        processor_cls.commands[name] = func
