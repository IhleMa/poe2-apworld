"""Out-of-logic checking for a PoE2 character's items.

This has no network code. It takes item records in GGG's standard item JSON format and
sends "Pick up" checks / warns about gear and gems you haven't received. It's meant to be fed by
GGG's official OAuth character API (account:characters, realm poe2) once GGG accepts new
application registrations again - see OAUTH_STATUS below.

Session-cookie (POESESSID) access was removed on purpose: pathofexile2.com protects its
account pages with browser-bound login tokens, and the client must not imitate that.
"""
from __future__ import annotations

import re
import typing

from CommonClient import logger

if typing.TYPE_CHECKING:
    from .poe2_client import PoE2Integration

OAUTH_STATUS = ("not available yet - GGG isn't accepting new API applications. Once an official OAuth app is "
                "registered, this client can read your character through it.")

RARITY_BY_FRAME = {0: "Normal", 1: "Magic", 2: "Rare", 3: "Unique"}
RARITY_TIER = {"Normal": 1, "Magic": 2, "Rare": 3, "Unique": 4}
TIER_NAME = {0: "nothing", 1: "Normal", 2: "Magic", 3: "Rare", 4: "Unique"}
BACKPACK = {"MainInventory", "ExpandedMainInventory", "Cursor", "Map", "MapDevice"}
RING_SLOT = {"Ring": "Ring (Left)", "Ring2": "Ring (Right)"}


class CharacterChecker:
    def __init__(self, integration: "PoE2Integration"):
        self.integ = integration
        self._last_violations: tuple | None = None

    def process_items(self, items: list[dict], source: str = "Character API") -> list[str]:
        from .poe2_client import BASE_GROUPS
        integ = self.integ
        violations = []
        charms_equipped = 0
        for item in items:
            base = item.get("baseType") or ""
            if base not in BASE_GROUPS:
                type_line = item.get("typeLine", "")
                base = next((b for b in BASE_GROUPS if b == type_line or b in type_line), "")
            inv = item.get("inventoryId", "")
            if base:
                integ.send_location(f"Pick up {base}", source)
            if not base or inv in BACKPACK:
                continue
            group = BASE_GROUPS[base]
            rarity = item.get("rarity") or RARITY_BY_FRAME.get(item.get("frameType"))
            if group in ("Life Flask", "Mana Flask"):
                if not integ.received_count(f"{group} Slot"):
                    violations.append(f"{base} equipped without '{group} Slot'")
            elif group == "Charm":
                charms_equipped += 1
            elif rarity in RARITY_TIER and group != "Jewel":
                unlock = RING_SLOT.get(inv, "Ring (Left)") if group == "Ring" else group
                have = min(integ.received_count(f"Progressive {unlock}"), 4)
                if have < RARITY_TIER[rarity]:
                    violations.append(f"{rarity} {base} in {unlock} (allowed: {TIER_NAME[have]})")
            violations += self.gem_violations(item)
        charm_slots = integ.received_count("Progressive Charm Slot")
        if charms_equipped > charm_slots:
            violations.append(f"{charms_equipped} charms equipped, {charm_slots} charm slot(s) received")

        key = tuple(sorted(violations))
        if key != self._last_violations:
            self._last_violations = key
            if violations:
                logger.warning("[PoE2] Out of logic - you're using things you haven't received:")
                for v in violations:
                    logger.warning(f"[PoE2]   {v}")
            else:
                logger.info("[PoE2] Everything you have equipped is unlocked.")
        return violations

    def gem_violations(self, item: dict) -> list[str]:
        """Socketed skill/support gems; skills granted by the item itself are ignored."""
        from .poe2_client import GEM_NAMES, SUPPORT_GEM_TO_ITEM, PROGRESSIVE_SUPPORTS
        out = []
        granted = set()
        for g in item.get("grantedSkills", []) or []:
            for value in g.get("values", []):
                if value and isinstance(value[0], str):
                    granted.add(re.sub(r"^Level \d+ ", "", value[0]).strip())
        for gem in item.get("socketedItems", []) or []:
            name = (gem.get("baseType") or gem.get("typeLine") or "").strip()
            if name in granted:
                continue
            if name in GEM_NAMES and not self.integ.received_count(name):
                out.append(f"skill gem '{name}' not received")
            elif name in SUPPORT_GEM_TO_ITEM:
                item_name, level_index = SUPPORT_GEM_TO_ITEM[name]
                need = level_index + 1 if PROGRESSIVE_SUPPORTS(self.integ) else 1
                if self.integ.received_count(item_name) < need:
                    out.append(f"support '{name}' needs {need} x '{item_name}'")
        return out
