from typing import Optional, Any
from BaseClasses import MultiWorld

# Returning None falls through to Manual's normal (category / yaml_option) checks.


def before_is_category_enabled(multiworld: MultiWorld, player: int, category_name: str) -> Optional[bool]:
    return None


def before_is_item_enabled(multiworld: MultiWorld, player: int, item: dict[str, Any]) -> Optional[bool]:
    # Item counts are adjusted in hooks/World.py:before_create_items_all
    return None


def before_is_location_enabled(multiworld: MultiWorld, player: int, location: dict[str, Any]) -> Optional[bool]:
    from . import poe2
    from ..Helpers import get_option_value

    if location.get("victory"):
        return None
    world = multiworld.worlds[player]

    region = poe2.REGION_INDEX.get(location.get("region", ""), 0)
    if region > poe2.max_region(world):
        return False

    if "Pinnacle Bosses" in location.get("category", []) and \
            get_option_value(multiworld, player, "goal") != poe2.GOAL_PINNACLE:
        return False

    level = poe2.LEVEL_OF_LOCATION.get(location["name"])
    if level is not None and level > get_option_value(multiworld, player, "max_level_location"):
        return False
    return None


def before_is_event_enabled(multiworld: MultiWorld, player: int, event: dict[str, Any]) -> Optional[bool]:
    return None
