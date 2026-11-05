"""In-game chat output for the PathOfExile2 Client: reloading the loot filter and whispering messages to yourself.

PoE2 has no API for this, so - like the Path of Exile 1 Archipelago client - the client types into the game's chat:
Enter, paste the line, Enter. Rules that keep this from getting in your way:

* It only types while Path of Exile 2 is the window in front (so it never types into another program).
* Queued lines are only sent right after a zone has loaded, never in the middle of a fight.
* At most a few lines per zone change; the rest wait for the next one. Repeated filter reloads collapse into one.
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
MAX_LINES_PER_ZONE = 4
ZONE_SETTLE_SECONDS = 1.5      # wait after "You have entered" before typing
SEND_WINDOW_SECONDS = 8.0      # only send this long after a zone change
KEY_DELAY = 0.05


# ---------------------------------------------------------------- platform input
class _Keyboard:
    available = False
    reason = "unsupported operating system"

    def foreground_is_game(self) -> bool:
        return False

    def send_line(self) -> None:
        """Open chat, paste the clipboard, send. The clipboard is set by the caller beforehand."""
        raise NotImplementedError


class _WindowsKeyboard(_Keyboard):
    VK_RETURN, VK_CONTROL, VK_SHIFT, VK_MENU, VK_V = 0x0D, 0x11, 0x10, 0x12, 0x56
    KEYUP = 0x0002

    def __init__(self):
        import ctypes
        self.user32 = ctypes.windll.user32
        self.ctypes = ctypes
        self.available = True
        self.reason = ""

    def foreground_is_game(self) -> bool:
        hwnd = self.user32.GetForegroundWindow()
        length = self.user32.GetWindowTextLengthW(hwnd)
        buf = self.ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip() == WINDOW_TITLE

    def _key(self, vk: int, up: bool = False):
        scan = self.user32.MapVirtualKeyW(vk, 0)
        self.user32.keybd_event(vk, scan, self.KEYUP if up else 0, 0)

    def send_line(self):
        for vk in (self.VK_SHIFT, self.VK_CONTROL, self.VK_MENU):   # release anything the player is holding
            self._key(vk, up=True)
        self._key(self.VK_RETURN); self._key(self.VK_RETURN, True)  # open chat
        time.sleep(KEY_DELAY * 2)
        self._key(self.VK_CONTROL); self._key(self.VK_V); self._key(self.VK_V, True); self._key(self.VK_CONTROL, True)
        time.sleep(KEY_DELAY * 2)
        self._key(self.VK_RETURN); self._key(self.VK_RETURN, True)  # send


class _XdotoolKeyboard(_Keyboard):
    def __init__(self):
        self.xdotool = shutil.which("xdotool")
        self.available = bool(self.xdotool)
        self.reason = "" if self.available else "install xdotool to use in-game chat on Linux"

    def _run(self, *args) -> str:
        return subprocess.run([self.xdotool, *args], capture_output=True, text=True, timeout=3).stdout.strip()

    def foreground_is_game(self) -> bool:
        try:
            return self._run("getactivewindow", "getwindowname") == WINDOW_TITLE
        except Exception:
            return False

    def send_line(self):
        self._run("keyup", "shift", "ctrl", "alt", "super")
        self._run("key", "--clearmodifiers", "Return")
        time.sleep(KEY_DELAY * 2)
        self._run("key", "--clearmodifiers", "ctrl+v")
        time.sleep(KEY_DELAY * 2)
        self._run("key", "--clearmodifiers", "Return")


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
        self._sending = False
        self._warned_unavailable = False

    # ---------- what gets queued
    @property
    def mode(self) -> str:
        return self.integ.settings.get("whisper_mode", "important")

    def queue_whisper(self, text: str, important: bool):
        if self.mode == "off" or (self.mode == "important" and not important):
            return
        text = clean(text)
        if text:
            self.whispers.append(text)
            del self.whispers[:-60]   # never let a backlog grow without bound

    def queue_filter_reload(self):
        if self.integ.settings.get("auto_reload_filter", True):
            self.reload_filter = True

    def on_zone_entered(self):
        self.zone_entered_at = time.time()

    def status_line(self) -> str:
        if not self.kb.available:
            return f"In-game chat: unavailable - {self.kb.reason}"
        s = self.integ.settings
        return (f"In-game chat: filter auto-reload {'on' if s.get('auto_reload_filter', True) else 'off'}, "
                f"whispers {self.mode} (sent after each zone change while PoE2 is in front)")

    # ---------- sending
    def pending(self) -> bool:
        return self.reload_filter or bool(self.whispers)

    def _build_lines(self) -> list[str]:
        lines = []
        if self.reload_filter:
            from .poe2_client import FILTER_NAME
            lines.append(f"/itemfilter {FILTER_NAME}")
        name = self.integ.settings.get("character")
        if self.whispers and name:
            prefix = f"@{name} "
            budget = MAX_LINES_PER_ZONE - len(lines)
            text_lines: list[str] = []
            while self.whispers and len(text_lines) < budget:
                msg = self.whispers[0]
                parts = split_message(msg, MAX_LINE - len(prefix))
                if len(text_lines) + len(parts) > budget and text_lines:
                    break
                text_lines += parts[:budget - len(text_lines)]
                self.whispers.pop(0)
            lines += [prefix + t for t in text_lines]
        return lines

    async def tick(self):
        if self._sending or not self.pending():
            return
        since = time.time() - self.zone_entered_at
        if not (ZONE_SETTLE_SECONDS <= since <= SEND_WINDOW_SECONDS):
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
        if not await asyncio.to_thread(self.kb.foreground_is_game):
            return   # try again after the next zone change
        self._sending = True
        try:
            lines = self._build_lines()
            self.reload_filter = False
            if lines:
                await self._type_lines(lines)
        finally:
            self._sending = False
        self.zone_entered_at = 0.0   # one batch per zone change

    async def _type_lines(self, lines: list[str]):
        # clipboard access stays on the client's main thread; only the keystrokes run in a worker thread
        clip = self.integ.clipboard
        previous = clip.read()
        sent = 0
        try:
            for line in lines:
                if not await asyncio.to_thread(self.kb.foreground_is_game):
                    break
                clip.write(line)
                await asyncio.sleep(KEY_DELAY)
                await asyncio.to_thread(self.kb.send_line)
                sent += 1
                await asyncio.sleep(0.15)
        finally:
            clip.write(previous or "")
            self.integ.ignore_clipboard(previous or "")
        if sent < len(lines):
            # put what wasn't typed back in the queue for the next zone change
            for line in reversed(lines[sent:]):
                if line.startswith("/itemfilter"):
                    self.reload_filter = True
                else:
                    self.whispers.insert(0, line.split(" ", 1)[1])
