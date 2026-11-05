# Path of Exile 2 hooks for the Manual framework.
from typing import Any
from worlds.AutoWorld import World
from BaseClasses import MultiWorld, CollectionState, Item, ItemClassification

from ..Items import ManualItem
from ..Locations import ManualLocation
from ..Data import game_table, item_table, location_table, region_table
from ..Helpers import is_option_enabled, get_option_value, format_state_prog_items_key, ProgItemsCat, remove_specific_item

from . import poe2

import logging
logger = logging.getLogger("PoE2")


def hook_get_filler_item_name(world: World, multiworld: MultiWorld, player: int) -> list[str] | str | bool:
    return False


def before_generate_early(world: World, multiworld: MultiWorld, player: int) -> None:
    passthrough = getattr(multiworld, "re_gen_passthrough", {}).get(world.game, {})
    if passthrough.get("poe2_class"):
        world.poe2_class = passthrough["poe2_class"]
    poe2.chosen_class(world)


def before_create_regions(world: World, multiworld: MultiWorld, player: int):
    pass


def after_create_regions(world: World, multiworld: MultiWorld, player: int):
    pass


def before_create_items_all(item_config: dict[str, int | dict], world: World, multiworld: MultiWorld, player: int) -> dict[str, int | dict]:
    cls = poe2.chosen_class(world)
    goal = get_option_value(multiworld, player, "goal")

    # Character class: only the chosen one exists, and you start with it.
    for c in poe2.CLASSES:
        item_config[f"Class - {c}"] = 1 if c == cls else 0

    # Ascendancy
    asc_on = is_option_enabled(multiworld, player, "include_ascendancy")
    for c, data in poe2.CLASSES.items():
        for a in data["ascendancies"]:
            item_config[f"Ascendancy - {a}"] = 1 if (asc_on and c == cls) else 0
    if not asc_on:
        item_config["Progressive Ascendancy Trial"] = 0

    # Supports: one item per lineage unless progressive
    if not is_option_enabled(multiworld, player, "progressive_support_gems"):
        for name in poe2.SUPPORTS:
            if name in item_config:
                item_config[name] = 1

    # Passive points
    passives = get_option_value(multiworld, player, "passive_points_in_pool")
    item_config["Passive Skill Point"] = passives
    if passives == 0:
        item_config["Weapon Set Passive Points"] = 0

    # Pinnacle trophies only for that goal
    if goal != poe2.GOAL_PINNACLE:
        item_config["Pinnacle Boss Trophy"] = 0
    return item_config


def before_create_items_place_items(item_pool: list, world: World, multiworld: MultiWorld, player: int) -> list:
    return item_pool


def _take(item_pool: list, name: str):
    for item in item_pool:
        if item.name == name:
            remove_specific_item(item_pool, item)
            return item
    return None


def before_create_items_starting(item_pool: list, world: World, multiworld: MultiWorld, player: int) -> list:
    cls = poe2.chosen_class(world)
    data = poe2.CLASSES[cls]
    start: list[Item] = []

    item = _take(item_pool, f"Class - {cls}")
    if item:
        start.append(item)

    if is_option_enabled(multiworld, player, "usable_starting_gear"):
        for name in (f"Progressive {data['weapon']}", "Life Flask Slot", "Mana Flask Slot"):
            item = _take(item_pool, name)
            if item:
                start.append(item)

    if is_option_enabled(multiworld, player, "starting_skill_gem"):
        options = sorted(n for n, g in poe2.SKILL_GEMS.items()
                         if g["tier"] == 1 and data["gem_group"] in g["groups"]
                         and (not g["weapons"] or data["weapon"] in g["weapons"]))
        in_pool = [n for n in options if any(i.name == n for i in item_pool)]
        if in_pool:
            item = _take(item_pool, world.random.choice(in_pool))
            if item:
                start.append(item)

    for item in start:
        multiworld.push_precollected(item)
    world.poe2_start = [i.name for i in start]
    return item_pool


def before_create_items_filler(item_pool: list, world: World, multiworld: MultiWorld, player: int) -> list:
    """Trim the pool to fit the enabled locations, removing the least important items first."""
    unfilled = len(multiworld.get_unfilled_locations(player=player))
    excess = len(item_pool) - unfilled
    if excess <= 0:
        return item_pool

    rng = world.random
    top = poe2.max_region(world)
    tier_cap = poe2.GEM_TIER_CAP[top]
    support_cap = poe2.SUPPORT_TIER_CAP[top]
    cls = poe2.chosen_class(world)
    cls_data = poe2.CLASSES[cls]
    progressive_supports = is_option_enabled(multiworld, player, "progressive_support_gems")

    def support_tier_of_copy(name: str, index: int) -> int:
        tiers = poe2.SUPPORTS[name]["tiers"]
        return tiers[min(index, len(tiers) - 1)] if progressive_supports else tiers[0]

    def remove(candidates: list, keep: int = 0):
        nonlocal excess
        rng.shuffle(candidates)
        removable = max(len(candidates) - keep, 0)
        for item in candidates[:removable]:
            if excess <= 0:
                return
            remove_specific_item(item_pool, item)
            excess -= 1

    def pool_items(pred):
        return [i for i in item_pool if pred(i.name)]

    # 1. gems that can't be used before the goal
    remove(pool_items(lambda n: n in poe2.GEMS and poe2.GEMS[n]["tier"] > tier_cap))
    # 2. support levels above what the goal reaches (highest copies first)
    if excess > 0:
        seen: dict[str, int] = {}
        high = []
        for i in item_pool:
            if i.name in poe2.SUPPORTS:
                idx = seen.get(i.name, 0)
                seen[i.name] = idx + 1
                if support_tier_of_copy(i.name, idx) > support_cap:
                    high.append(i)
        remove(high)
    # 3. plain filler / useful extras
    remove(pool_items(lambda n: n in ("A Pile of Gold", "Weapon Set Passive Points")))
    remove(pool_items(lambda n: n in poe2.OTHER_GEMS))
    # 4. supports beyond what logic needs (+ buffer)
    remove(pool_items(lambda n: n in poe2.SUPPORTS), keep=poe2.PINNACLE["supports"] + 10)
    # 5. skill gems for other weapon/spell groups (+ buffer)
    remove(pool_items(lambda n: n in poe2.SKILL_GEMS and cls_data["gem_group"] not in poe2.SKILL_GEMS[n]["groups"]),
           keep=10)
    # 6. passive points beyond the highest requirement (+ buffer)
    remove(pool_items(lambda n: n == "Passive Skill Point"), keep=70)
    # 7. unique-tier copies of gear for weapons/off-hands the class doesn't start with
    if excess > 0:
        for name in poe2.GEAR_ITEMS:
            if name == f"Progressive {cls_data['weapon']}" or name in poe2.ARMOUR_ITEMS:
                continue
            copies = pool_items(lambda n, name=name: n == name)
            if copies and excess > 0:
                remove_specific_item(item_pool, copies[0])
                excess -= 1
    # 8. small location pools: keep shrinking. Logic requirements scale down to what remains
    #    (see poe2.requirements_for), so the seed stays beatable - it just has fewer unlocks.
    remove(pool_items(lambda n: n in poe2.SUPPORTS), keep=poe2.SUPPORTS_NEEDED[top] + 2)
    remove(pool_items(lambda n: n in poe2.SKILL_GEMS and cls_data["gem_group"] not in poe2.SKILL_GEMS[n]["groups"]))
    remove(pool_items(lambda n: n == "Passive Skill Point"), keep=20)
    remove(pool_items(lambda n: n in poe2.SKILL_GEMS and poe2.SKILL_GEMS[n]["tier"] > 1), keep=poe2.SKILLS_NEEDED[top] + 2)
    if excess > 0:
        # highest rarity tiers of every gear slot first (copies beyond Normal)
        for keep_copies in (3, 2, 1):
            for name in poe2.GEAR_ITEMS:
                copies = pool_items(lambda n, name=name: n == name)
                while len(copies) > keep_copies and excess > 0:
                    remove_specific_item(item_pool, copies.pop())
                    excess -= 1
    remove(pool_items(lambda n: n == "Passive Skill Point"))
    remove(pool_items(lambda n: n in poe2.SUPPORTS))
    remove(pool_items(lambda n: n in ("Progressive Charm Slot", "Progressive Support Socket", "Progressive Ascendancy Trial")))
    remove(pool_items(lambda n: n in poe2.GEAR_ITEMS and n != f"Progressive {cls_data['weapon']}"), keep=4)
    remove(pool_items(lambda n: n in poe2.SKILL_GEMS), keep=2)

    if excess > 0:
        raise Exception(
            f"[Path of Exile 2 - {multiworld.player_name[player]}] Not enough locations for the item pool "
            f"({excess} too many items). Enable more location types (zones, bosses, levels, item bases), "
            f"raise max_level_location, lower passive_points_in_pool, or choose a later goal.")
    return item_pool


def after_create_items(item_pool: list, world: World, multiworld: MultiWorld, player: int) -> list:
    names = [i.name for i in item_pool] + [i.name for i in multiworld.precollected_items[player]]
    poe2.compute_availability(world, names)
    return item_pool


def before_set_rules(world: World, multiworld: MultiWorld, player: int):
    pass


def after_set_rules(world: World, multiworld: MultiWorld, player: int):
    pass


def before_create_item(item_name: str, world: World, multiworld: MultiWorld, player: int) -> str:
    return item_name


def after_create_item(item: ManualItem, world: World, multiworld: MultiWorld, player: int) -> ManualItem:
    return item


def before_generate_basic(world: World, multiworld: MultiWorld, player: int):
    pass


def after_collect_item(world: World, state: CollectionState, Changed: bool, item: Item):
    pass


def after_remove_item(world: World, state: CollectionState, Changed: bool, item: Item):
    pass


def before_fill_slot_data(slot_data: dict, world: World, multiworld: MultiWorld, player: int) -> dict:
    return slot_data


def after_fill_slot_data(slot_data: dict, world: World, multiworld: MultiWorld, player: int) -> dict:
    slot_data["poe2_class"] = poe2.chosen_class(world)
    slot_data["poe2_progressive_supports"] = bool(is_option_enabled(multiworld, player, "progressive_support_gems"))
    return slot_data


def before_write_spoiler(world: World, multiworld: MultiWorld, spoiler_handle) -> None:
    spoiler_handle.write(f"\nPath of Exile 2 ({multiworld.player_name[world.player]}): class {poe2.chosen_class(world)}, "
                         f"starting with {', '.join(getattr(world, 'poe2_start', []))}\n")


def before_extend_hint_information(hint_data: dict[int, dict[int, str]], world: World, multiworld: MultiWorld, player: int) -> None:
    pass


def after_extend_hint_information(hint_data: dict[int, dict[int, str]], world: World, multiworld: MultiWorld, player: int) -> None:
    pass


def hook_interpret_slot_data(world: World, player: int, slot_data: dict[str, Any]) -> dict[str, Any]:
    return slot_data
