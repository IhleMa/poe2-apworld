"""Path of Exile 2 specific data and logic shared by the hook files.

Logic mirrors the Path of Exile (1) Archipelago world: to enter each act you need a
number of usable skill gems (right tier + a weapon type that can use them), gear
unlocks, support gems, support sockets, passive points, flask/charm slots and,
later, ascendancy progress. Requirements are capped by what is actually in the pool.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..Helpers import load_data_file, get_option_value

if TYPE_CHECKING:
    from worlds.AutoWorld import World
    from BaseClasses import CollectionState

META = load_data_file("poe2_meta.json")
REGIONS: list[str] = META["regions"]
REGION_INDEX = {name: i for i, name in enumerate(REGIONS)}
GEMS: dict[str, dict] = META["gems"]
SUPPORTS: dict[str, dict] = META["supports"]
CLASSES: dict[str, dict] = META["classes"]
LEVEL_OF_LOCATION: dict[str, int] = META["level_of_location"]

CLASS_OPTION_ORDER = ["random", "Warrior", "Mercenary", "Ranger", "Huntress", "Monk", "Sorceress", "Witch", "Druid"]

# Goal option value -> last region whose content is played (victory order in locations.json)
GOAL_MAX_REGION = {0: 5, 1: 1, 2: 2, 3: 3, 4: 4, 5: 6}
GOAL_PINNACLE = 5

WEAPON_UNLOCKS = ["One Hand Mace", "Two Hand Mace", "Quarterstaff", "Spear", "Bow", "Crossbow",
                  "Wand", "Staff", "Sceptre", "Talisman"]
OFFHAND_UNLOCKS = ["Shield", "Buckler", "Focus", "Quiver"]
ARMOUR_UNLOCKS = ["Helmet", "Body Armour", "Gloves", "Boots", "Belt", "Amulet", "Ring (Left)", "Ring (Right)"]
GEAR_ITEMS = [f"Progressive {x}" for x in WEAPON_UNLOCKS + OFFHAND_UNLOCKS + ARMOUR_UNLOCKS]
ARMOUR_ITEMS = [f"Progressive {x}" for x in ARMOUR_UNLOCKS]

SKILL_GEMS = {n: m for n, m in GEMS.items() if m["kind"] == "Skill Gem"}
OTHER_GEMS = {n: m for n, m in GEMS.items() if m["kind"] != "Skill Gem"}

# Index = region being entered.  Values are cumulative.
SKILLS_NEEDED   = [0, 2, 4, 6, 8, 9, 10]
GEM_TIER_CAP    = [1, 3, 7, 11, 13, 14, 14]   # highest skill tier obtainable while in region i
SUPPORT_TIER_CAP = [1, 2, 3, 4, 5, 5, 5]
GEAR_NEEDED     = [0, 3, 8, 14, 20, 26, 32]
ARMOUR_SLOTS_NEEDED = [0, 2, 4, 6, 7, 8, 8]
SUPPORTS_NEEDED = [0, 1, 4, 8, 12, 15, 18]
SOCKETS_NEEDED  = [0, 0, 1, 1, 2, 2, 3]
PASSIVES_NEEDED = [0, 2, 10, 22, 32, 38, 44]   # out of 123
CHARMS_NEEDED   = [0, 0, 0, 1, 1, 2, 2]
TRIALS_NEEDED   = [0, 0, 0, 0, 1, 1, 2]

PINNACLE = {"skills": 10, "gear": 44, "armour": 8, "supports": 22, "sockets": 3, "passives": 60, "charms": 3, "trials": 3}


def chosen_class(world: "World") -> str:
    cls = getattr(world, "poe2_class", None)
    if cls:
        return cls
    value = get_option_value(world.multiworld, world.player, "starting_character")
    if value == 0:
        cls = world.random.choice(CLASS_OPTION_ORDER[1:])
    else:
        cls = CLASS_OPTION_ORDER[value]
    world.poe2_class = cls
    return cls


# The game's skill categories, in display order, and the weapon each weapon category is used with.
ALL_CATEGORIES = ["Mace", "Quarterstaff", "Spear", "Bow", "Crossbow", "Primal", "Elemental", "Occult"]
CATEGORY_WEAPON = {"Mace": "One Hand Mace", "Quarterstaff": "Quarterstaff", "Spear": "Spear", "Bow": "Bow",
                   "Crossbow": "Crossbow", "Primal": "Talisman"}


def chosen_categories(world: "World") -> list[str] | None:
    """Skill categories in the pool (class category first), or None for "All"."""
    cached = getattr(world, "poe2_categories", False)
    if cached is not False:
        return cached
    value = set(get_option_value(world.multiworld, world.player, "skill_categories") or {"Class"})
    class_cat = CLASSES[chosen_class(world)]["gem_group"]
    if "All" in value:
        result = None
    else:
        cats = {class_cat if c == "Class" else c for c in value} or {class_cat}
        result = sorted(cats, key=lambda c: (c != class_cat, ALL_CATEGORIES.index(c)))
    world.poe2_categories = result
    return result


def focus_categories(world: "World") -> set[str]:
    """Categories the build is about: the chosen ones, or the class's own when everything is in the pool."""
    cats = chosen_categories(world)
    return set(cats) if cats else {CLASSES[chosen_class(world)]["gem_group"]}


def gem_in_focus(world: "World", name: str) -> bool:
    return bool(set(GEMS[name]["groups"]) & focus_categories(world))


def starting_category_and_weapon(world: "World") -> tuple[str, str]:
    data = CLASSES[chosen_class(world)]
    focus = chosen_categories(world)
    if not focus or data["gem_group"] in focus:
        return data["gem_group"], data["weapon"]
    first = focus[0]
    return first, CATEGORY_WEAPON.get(first, data["weapon"])   # spell categories keep the class weapon


def max_region(world: "World") -> int:
    goal = get_option_value(world.multiworld, world.player, "goal")
    return GOAL_MAX_REGION.get(goal, 5)


def gem_usable_in_pool(gem: dict, weapons_available: set[str]) -> bool:
    return not gem["weapons"] or any(w in weapons_available for w in gem["weapons"])


def compute_availability(world: "World", names: list[str]) -> None:
    """Store how many of each logic-relevant thing exists (pool + start inventory)."""
    from collections import Counter
    counts = Counter(names)
    weapons = {w for w in WEAPON_UNLOCKS if counts[f"Progressive {w}"] > 0}
    avail = {"counts": counts}
    for r in range(len(REGIONS)):
        cap = GEM_TIER_CAP[max(r - 1, 0)]
        avail[f"skills_{r}"] = sum(1 for n, g in SKILL_GEMS.items()
                                   if counts[n] and g["tier"] <= cap and gem_usable_in_pool(g, weapons))
    avail["skills_any"] = sum(1 for n, g in SKILL_GEMS.items() if counts[n] and gem_usable_in_pool(g, weapons))
    avail["gear"] = sum(counts[n] for n in GEAR_ITEMS)
    avail["armour"] = sum(1 for n in ARMOUR_ITEMS if counts[n])
    avail["supports"] = sum(counts[n] for n in SUPPORTS)
    avail["sockets"] = counts["Progressive Support Socket"]
    avail["passives"] = counts["Passive Skill Point"]
    avail["charms"] = counts["Progressive Charm Slot"]
    avail["trials"] = counts["Progressive Ascendancy Trial"]
    avail["ascendancies"] = sum(counts[f"Ascendancy - {a}"] for a in CLASSES[chosen_class(world)]["ascendancies"])
    avail["life"] = counts["Life Flask Slot"]
    avail["mana"] = counts["Mana Flask Slot"]
    world.poe2_avail = avail


def _passive_scale(world: "World") -> float:
    avail = world.poe2_avail
    return avail["passives"] / 123 if avail["passives"] else 0.0


def requirements_for(world: "World", region: int) -> dict:
    a = world.poe2_avail
    scale = _passive_scale(world)
    return {
        "skills": min(SKILLS_NEEDED[region], a[f"skills_{region}"]),
        "tier": GEM_TIER_CAP[max(region - 1, 0)],
        "gear": min(GEAR_NEEDED[region], a["gear"]),
        "armour": min(ARMOUR_SLOTS_NEEDED[region], a["armour"]),
        "supports": min(SUPPORTS_NEEDED[region], a["supports"]),
        "sockets": min(SOCKETS_NEEDED[region], a["sockets"]),
        "passives": min(round(PASSIVES_NEEDED[region] * scale), a["passives"]),
        "charms": min(CHARMS_NEEDED[region], a["charms"]),
        "trials": min(TRIALS_NEEDED[region], a["trials"]),
        "ascendancy": 1 if region >= 4 and a["ascendancies"] else 0,
        "life": 1 if region >= 1 and a["life"] else 0,
        "mana": 1 if region >= 2 and a["mana"] else 0,
    }


def pinnacle_requirements(world: "World") -> dict:
    a = world.poe2_avail
    req = requirements_for(world, 6)
    req.update({
        "skills": min(PINNACLE["skills"], a["skills_any"]),
        "tier": 20,
        "gear": min(PINNACLE["gear"], a["gear"]),
        "armour": min(PINNACLE["armour"], a["armour"]),
        "supports": min(PINNACLE["supports"], a["supports"]),
        "sockets": min(PINNACLE["sockets"], a["sockets"]),
        "passives": min(round(PINNACLE["passives"] * _passive_scale(world)), a["passives"]),
        "charms": min(PINNACLE["charms"], a["charms"]),
        "trials": min(PINNACLE["trials"], a["trials"]),
    })
    return req


def meets(world: "World", state: "CollectionState", player: int, req: dict) -> bool:
    if state.count("Passive Skill Point", player) < req["passives"]:
        return False
    if req["life"] and not state.has("Life Flask Slot", player):
        return False
    if req["mana"] and not state.has("Mana Flask Slot", player):
        return False
    if state.count("Progressive Charm Slot", player) < req["charms"]:
        return False
    if state.count("Progressive Support Socket", player) < req["sockets"]:
        return False
    if state.count("Progressive Ascendancy Trial", player) < req["trials"]:
        return False
    if req["ascendancy"]:
        ascs = [f"Ascendancy - {x}" for x in CLASSES[chosen_class(world)]["ascendancies"]]
        if not state.has_any(ascs, player):
            return False
    if req["gear"] and state.count_from_list(GEAR_ITEMS, player) < req["gear"]:
        return False
    if req["armour"] and sum(1 for n in ARMOUR_ITEMS if state.has(n, player)) < req["armour"]:
        return False
    if req["supports"] and state.count_from_list(list(SUPPORTS), player) < req["supports"]:
        return False
    if req["skills"]:
        weapons = {w for w in WEAPON_UNLOCKS if state.has(f"Progressive {w}", player)}
        usable = 0
        for name, gem in SKILL_GEMS.items():
            if gem["tier"] <= req["tier"] and state.has(name, player) and gem_usable_in_pool(gem, weapons):
                usable += 1
                if usable >= req["skills"]:
                    break
        if usable < req["skills"]:
            return False
    return True
