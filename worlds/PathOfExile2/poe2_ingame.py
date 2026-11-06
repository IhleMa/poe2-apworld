"""In-game chat output for the PathOfExile2 Client: reloading the loot filter and whispering messages to yourself.

PoE2 has no API for this, so - like the Path of Exile 1 Archipelago client - the client types into the game's chat:
Enter, paste the line, Enter. Rules that keep this from getting in your way:

* It only types while Path of Exile 2 is the window in front (so it never types into another program).
* Timing "instant" (default): messages go out right away, gathered for a moment so bursts become one batch, and
  rate-limited so chat isn't flooded. Timing "zone": only right after a zone has loaded.
* Every message category is whispered unless you hide it (see CATEGORIES). Repeated filter reloads collapse into one.
* Your clipboard is restored afterwards.

Supported: Windows (native) and Linux with xdotool (Steam/Proton). Not supported on macOS.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
import typing

from CommonClient import logger

if typing.TYPE_CHECKING:
    from .poe2_client import PoE2Integration

WINDOW_TITLE = "Path of Exile 2"
MAX_LINE = 200                 # characters per chat line (PoE's limit is a bit higher)
MAX_LINES_PER_BATCH = 5
BATCH_DELAY = 0.15             # instant mode: gather messages arriving together into one batch
BURST_LINES = 6                # instant mode rate limit: up to 6 lines at once ...
REFILL_SECONDS = 1.0           # ... then one more line per second
ZONE_SETTLE_SECONDS = 3.0      # zone mode: wait after the last zone-load line before typing
SEND_WINDOW_SECONDS = 15.0     # zone mode: only send this long after a zone change
LINE_GAP = 0.06                # lets the game read the pasted line before the clipboard changes

# Whisper categories: name -> (description, shown by default). Everything is shown unless hidden.
CATEGORIES: dict[str, tuple[str, bool]] = {
    "my_items":       ("items you receive, and items you find for others", True),
    "hints":          ("hints about your items or locations", True),
    "chat":           ("chat from other players and the server", True),
    "progress":       ("goals, releases, collects and countdowns", True),
    "pickups":        ("Ctrl+C feedback: already checked, can't equip yet", True),
    "warnings":       ("client warnings: DeathLink, out of logic", True),
    "other":          ("any other server message", True),
    "other_items":    ("items moving between other players", False),
    "other_hints":    ("hints between other players", False),
    "join_leave":     ("players joining or leaving, tag changes", False),
    "server_replies": ("replies to client commands, tutorial text", False),
    "client_info":    ("client status: zone/level checks sent, filter updates", False),
}
DEFAULT_HIDDEN = sorted(name for name, (_, shown) in CATEGORIES.items() if not shown)


# ---------------------------------------------------------------- platform input
class _Keyboard:
    available = False
    reason = "unsupported operating system"

    def foreground_is_game(self) -> bool:
        return is_game_title(self.foreground_title())

    def foreground_title(self) -> str:
        return ""

    def send_line(self) -> None:
        """Open chat, paste the clipboard, send. The clipboard is set by the caller beforehand."""
        raise NotImplementedError


def _windows_input_types():
    """ctypes structures for user32.SendInput (correct sizes on 32- and 64-bit Python)."""
    import ctypes
    WORD, DWORD, LONG = ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int32   # fixed widths, same as Windows' types

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                    ("time", DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
                    ("dwFlags", DWORD), ("time", DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", DWORD), ("u", _U)]

    return INPUT, KEYBDINPUT


class _WindowsKeyboard(_Keyboard):
    VK_RETURN, VK_CONTROL, VK_SHIFT, VK_MENU, VK_V = 0x0D, 0x11, 0x10, 0x12, 0x56
    KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    def __init__(self):
        import ctypes
        self.ctypes = ctypes
        self.user32 = ctypes.windll.user32
        self.INPUT, self.KEYBDINPUT = _windows_input_types()
        # Enter, Ctrl+V, Enter as one atomic batch: nothing the player presses can land in between
        seq = [(vk, True) for vk in (self.VK_SHIFT, self.VK_CONTROL, self.VK_MENU)]   # release held modifiers
        seq += [(self.VK_RETURN, False), (self.VK_RETURN, True),
                (self.VK_CONTROL, False), (self.VK_V, False), (self.VK_V, True), (self.VK_CONTROL, True),
                (self.VK_RETURN, False), (self.VK_RETURN, True)]
        self.batch = (self.INPUT * len(seq))(*[self._input(vk, up) for vk, up in seq])
        self.available = True
        self.reason = ""

    def _input(self, vk: int, up: bool):
        ki = self.KEYBDINPUT(wVk=vk, wScan=self.user32.MapVirtualKeyW(vk, 0),
                             dwFlags=self.KEYUP if up else 0, time=0, dwExtraInfo=0)
        return self.INPUT(type=self.INPUT_KEYBOARD, ki=ki)

    def foreground_title(self) -> str:
        hwnd = self.user32.GetForegroundWindow()
        length = self.user32.GetWindowTextLengthW(hwnd)
        buf = self.ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()

    def send_line(self):
        sent = self.user32.SendInput(len(self.batch), self.batch, self.ctypes.sizeof(self.INPUT))
        if sent != len(self.batch):
            raise OSError("Windows blocked the key presses (is Path of Exile 2 running as administrator? "
                          "Then run Archipelago as administrator too)")


class _XdotoolKeyboard(_Keyboard):
    def __init__(self):
        self.xdotool = shutil.which("xdotool")
        self.available = bool(self.xdotool)
        self.reason = "" if self.available else "install xdotool to use in-game chat on Linux"

    def _run(self, *args) -> str:
        return subprocess.run([self.xdotool, *args], capture_output=True, text=True, timeout=3).stdout.strip()

    def foreground_title(self) -> str:
        try:
            return self._run("getactivewindow", "getwindowname")
        except Exception:
            return ""

    def send_line(self):
        # one xdotool call for the whole sequence
        self._run("key", "--clearmodifiers", "--delay", "8", "Return", "ctrl+v", "Return")


def is_game_title(title: str) -> bool:
    return title.strip().startswith(WINDOW_TITLE)


def make_keyboard() -> _Keyboard:
    try:
        if sys.platform == "win32":
            return _WindowsKeyboard()
        if sys.platform.startswith("linux"):
            return _XdotoolKeyboard()
    except Exception as e:  # pragma: no cover - platform specific
        kb = _Keyboard()
        kb.reason = f"keyboard input unavailable ({e})"
        return kb
    return _Keyboard()


# ---------------------------------------------------------------- chat queue
def clean(text: str) -> str:
    text = " ".join(text.replace("\r", " ").split())
    return text.lstrip("/@#$%&~!") if text[:1] in "/@#$%&~" else text


def split_message(text: str, limit: int) -> list[str]:
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        if len(w) > limit:
            w = w[:limit - 1] + "…"
        if cur and len(cur) + 1 + len(w) > limit:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        lines.append(cur)
    return lines


class InGameChat:
    def __init__(self, integration: "PoE2Integration", keyboard: _Keyboard | None = None):
        self.integ = integration
        self.kb = keyboard or make_keyboard()
        self.whispers: list[str] = []
        self.reload_filter = False
        self.zone_entered_at = 0.0
        self.last_zone_event = "none yet"
        self.last_result = "nothing sent yet"
        self._pending_since = 0.0
        self._tokens = float(BURST_LINES)
        self._tokens_at = time.time()
        self._sending = False
        self._warned_unavailable = False

    # ---------- settings
    @property
    def enabled(self) -> bool:
        return bool(self.integ.settings.get("whispers", True))

    @property
    def timing(self) -> str:
        return self.integ.settings.get("chat_timing", "instant")

    @property
    def hidden(self) -> set[str]:
        stored = self.integ.settings.get("whisper_hidden")
        return set(DEFAULT_HIDDEN if stored is None else stored)

    # ---------- what gets queued
    def queue_whisper(self, text: str, category: str):
        if not self.enabled or category in self.hidden:
            return
        text = clean(text)
        if text:
            self._mark_pending()
            self.whispers.append(text)
            del self.whispers[:-60]   # never let a backlog grow without bound

    def queue_filter_reload(self):
        if self.integ.settings.get("auto_reload_filter", True):
            self._mark_pending()
            self.reload_filter = True

    def _mark_pending(self):
        if not self.pending():
            self._pending_since = time.time()

    def on_zone_entered(self, what: str = "zone change"):
        self.zone_entered_at = time.time()
        self.last_zone_event = f"{what} at {time.strftime('%H:%M:%S')}"

    def debug_lines(self) -> list[str]:
        title = self.kb.foreground_title() if self.kb.available else ""
        return [
            self.status_line(),
            f"Keyboard input: {'available' if self.kb.available else 'unavailable - ' + self.kb.reason}",
            f"Character to whisper: {self.integ.settings.get('character') or '(unknown - level up or /poe2_character <name>)'}",
            f"Last zone change seen in Client.txt: {self.last_zone_event}",
            f"Window in front right now: {title!r} ({'Path of Exile 2' if is_game_title(title) else 'not the game'})",
            f"Queued: {len(self.whispers)} whispers, filter reload {'yes' if self.reload_filter else 'no'}",
            f"Last attempt: {self.last_result}",
        ]

    def status_line(self) -> str:
        if not self.kb.available:
            return f"In-game chat: unavailable - {self.kb.reason}"
        s = self.integ.settings
        when = "instantly" if self.timing == "instant" else "after each zone change"
        hidden = ", ".join(sorted(self.hidden)) or "nothing"
        return (f"In-game chat: filter auto-reload {'on' if s.get('auto_reload_filter', True) else 'off'}, "
                f"whispers {'on' if self.enabled else 'off'} ({when}, while PoE2 is in front; hidden: {hidden})")

    # ---------- sending
    def pending(self) -> bool:
        return self.reload_filter or bool(self.whispers)

    def _refill(self):
        now = time.time()
        self._tokens = min(BURST_LINES, self._tokens + (now - self._tokens_at) / REFILL_SECONDS)
        self._tokens_at = now

    def _build_lines(self, budget: int) -> list[str]:
        lines = []
        if self.reload_filter and budget > 0:
            from .poe2_client import FILTER_NAME
            lines.append(f"/itemfilter {FILTER_NAME}")
        name = self.integ.settings.get("character")
        if self.whispers and name:
            prefix = f"@{name} "
            room = budget - len(lines)
            text_lines: list[str] = []
            while self.whispers and len(text_lines) < room:
                parts = split_message(self.whispers[0], MAX_LINE - len(prefix))
                if len(text_lines) + len(parts) > room and text_lines:
                    break
                text_lines += parts[:room - len(text_lines)]
                self.whispers.pop(0)
            lines += [prefix + t for t in text_lines]
        return lines

    def _ready(self) -> bool:
        now = time.time()
        if self.timing == "zone":
            return ZONE_SETTLE_SECONDS <= now - self.zone_entered_at <= SEND_WINDOW_SECONDS
        return now - self._pending_since >= BATCH_DELAY

    async def tick(self):
        if self._sending or not self.pending() or not self._ready():
            return
        if not self.kb.available:
            if not self._warned_unavailable:
                self._warned_unavailable = True
                logger.warning(f"[PoE2] In-game chat is unavailable: {self.kb.reason}.",
                               extra={"poe2_no_whisper": True})
            self.whispers.clear()
            self.reload_filter = False
            return
        if self.whispers and not self.integ.settings.get("character"):
            if not self._warned_unavailable:
                self._warned_unavailable = True
                logger.warning("[PoE2] Can't whisper you yet: your character name isn't known. Level up once or use "
                               "/poe2_character <name>.", extra={"poe2_no_whisper": True})
            self.whispers.clear()
            if not self.pending():
                return
        self._refill()
        budget = min(MAX_LINES_PER_BATCH, int(self._tokens)) if self.timing == "instant" else MAX_LINES_PER_BATCH
        if budget < 1:
            return
        title = await asyncio.to_thread(self.kb.foreground_title)
        if not is_game_title(title):
            self.last_result = f"waiting at {time.strftime('%H:%M:%S')}: window in front was {title!r}"
            if self.timing == "zone":
                self.zone_entered_at = 0.0   # try again after the next zone change
            return   # instant mode: tries again as soon as the game is in front
        self._sending = True
        try:
            lines = self._build_lines(budget)
            self.reload_filter = False
            if lines:
                started = time.perf_counter()
                self.last_result = ""
                sent = await self._type_lines(lines)
                self._tokens -= sent
                if not self.last_result:
                    self.last_result = (f"typed {sent} line(s) in {time.perf_counter() - started:.2f}s "
                                        f"at {time.strftime('%H:%M:%S')}")
        finally:
            self._sending = False
            if self.pending():
                self._pending_since = time.time() - BATCH_DELAY   # the rest goes out when the rate limit allows
        if self.timing == "zone":
            self.zone_entered_at = 0.0   # one batch per zone change

    async def _type_lines(self, lines: list[str]) -> int:
        # clipboard access stays on the client's main thread; only the keystrokes run in a worker thread
        clip = self.integ.clipboard
        previous = clip.read()
        sent = 0
        try:
            for line in lines:
                if not is_game_title(await asyncio.to_thread(self.kb.foreground_title)):
                    break
                clip.write(line)
                await asyncio.to_thread(self.kb.send_line)
                sent += 1
                await asyncio.sleep(LINE_GAP)
        except OSError as e:
            self.last_result = str(e)
            logger.warning(f"[PoE2] In-game chat: {e}", extra={"poe2_no_whisper": True})
        finally:
            await asyncio.sleep(LINE_GAP)
            clip.write(previous or "")
            self.integ.ignore_clipboard(previous or "")
        if sent < len(lines):
            # put what wasn't typed back at the front of the queue
            for line in reversed(lines[sent:]):
                if line.startswith("/itemfilter"):
                    self.reload_filter = True
                else:
                    self.whispers.insert(0, line.split(" ", 1)[1])
        return sent
