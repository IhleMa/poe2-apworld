#!/usr/bin/env python3
"""Generate the Manual-format data files for the Path of Exile 2 Archipelago world.

Source: the repoe-fork/poe2 game-data export (https://github.com/repoe-fork/poe2).
Usage:  python tools/build_data.py <path-to-repoe-poe2-checkout> worlds/manual_pathofexile2_community
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SRC = Path(sys.argv[1]) / "data"
OUT = Path(sys.argv[2]) / "data"
SCHEMA = "https://github.com/ManualForArchipelago/Manual/raw/main/schemas/Manual.{}.schema.json"

def load(name):
    return json.loads((SRC / name).read_text(encoding="utf-8"))

base_items = load("base_items.json")
skill_gems = load("skill_gems.json")
world_areas = load("world_areas.json")

# ---------------------------------------------------------------------------
# Progression regions (index matters: hooks use it)
# ---------------------------------------------------------------------------
REGIONS = [
    "Act 1 - The Riverbank",   # 0  sphere-0 start, no requirements
    "Act 1",                   # 1
    "Act 2",                   # 2
    "Act 3",                   # 3
    "Act 4",                   # 4
    "Interludes",              # 5
    "Endgame",                 # 6  maps / atlas
]
# Highest monster / item level a region is considered to cover.
REGION_MAX_LEVEL = [2, 15, 32, 45, 53, 57, 100]
# Character level reached while in each region (for "Reach Level N" placement).
REGION_MAX_CHAR_LEVEL = [3, 15, 31, 44, 53, 59, 100]

def region_for_drop_level(lvl):
    for i, mx in enumerate(REGION_MAX_LEVEL):
        if lvl <= mx:
            return i
    return len(REGIONS) - 1

def region_for_char_level(lvl):
    for i, mx in enumerate(REGION_MAX_CHAR_LEVEL):
        if lvl <= mx:
            return i
    return len(REGIONS) - 1

# ---------------------------------------------------------------------------
# Gear / weapon types that currently exist in PoE2
# ---------------------------------------------------------------------------
WEAPON_CLASSES = {            # data item_class -> unlock name
    "One Hand Mace": "One Hand Mace",
    "Two Hand Mace": "Two Hand Mace",
    "Warstaff": "Quarterstaff",
    "Spear": "Spear",
    "Bow": "Bow",
    "Crossbow": "Crossbow",
    "Wand": "Wand",
    "Staff": "Staff",
    "Sceptre": "Sceptre",
    "Talisman": "Talisman",
}
OFFHAND_CLASSES = {"Shield": "Shield", "Buckler": "Buckler", "Focus": "Focus", "Quiver": "Quiver"}
ARMOUR_CLASSES = {"Helmet": "Helmet", "Body Armour": "Body Armour", "Gloves": "Gloves", "Boots": "Boots"}
JEWELLERY_CLASSES = {"Belt": "Belt", "Amulet": "Amulet", "Ring": "Ring"}
FLASK_CLASSES = {"LifeFlask": "Life Flask", "ManaFlask": "Mana Flask", "UtilityFlask": "Charm"}
OTHER_CLASSES = {"Jewel": "Jewel"}
# Weapon types in the game files that are not obtainable yet (swords arrive with 1.0).
NOT_YET_IN_GAME = {"Claw", "Dagger", "One Hand Sword", "Two Hand Sword", "One Hand Axe", "Two Hand Axe", "Flail"}

LOCATION_CLASSES = {**WEAPON_CLASSES, **OFFHAND_CLASSES, **ARMOUR_CLASSES, **JEWELLERY_CLASSES, **FLASK_CLASSES, **OTHER_CLASSES}

# gem "crafting_types" -> weapon unlocks that can use the attack skill
GEM_WEAPON_REQ = {
    "Mace": ["One Hand Mace", "Two Hand Mace"],
    "Bow": ["Bow"],
    "Crossbow": ["Crossbow"],
    "Spear": ["Spear"],
    "Quarterstaff": ["Quarterstaff"],
    "Primal": ["Talisman"],
}

CLASSES = {
    # class: (starting weapon unlock, gem category used for the starting skill gem, ascendancies)
    "Warrior":   ("Two Hand Mace", "Mace",         ["Titan", "Warbringer", "Smith of Kitava"]),
    "Mercenary": ("Crossbow",      "Crossbow",     ["Tactician", "Witchhunter", "Gemling Legionnaire"]),
    "Ranger":    ("Bow",           "Bow",          ["Deadeye", "Pathfinder"]),
    "Huntress":  ("Spear",         "Spear",        ["Amazon", "Spirit Walker", "Ritualist"]),
    "Monk":      ("Quarterstaff",  "Quarterstaff", ["Martial Artist", "Invoker", "Acolyte of Chayula"]),
    "Sorceress": ("Staff",         "Elemental",    ["Stormweaver", "Chronomancer", "Disciple of Varashta"]),
    "Witch":     ("Wand",          "Occult",       ["Infernalist", "Blood Mage", "Lich", "Abyssal Lich"]),
    "Druid":     ("Talisman",      "Primal",       ["Oracle", "Shaman"]),
}

BAD_PREFIX = ("[", "Runeforged ", "Runemastered ", "Coming Soon")
# Special / league / quest-only jewellery bases
EXCLUDED_BASES = {
    "Ring", "Dusk Ring", "Gloam Ring", "Penumbra Ring", "Tenebrous Ring", "Breach Ring", "Refined Breach Ring",
    "Dusk Amulet", "Gloam Amulet", "Penumbra Amulet", "Tenebrous Amulet", "Twisted Amulet", "Distorted Amulet",
}

# ---------------------------------------------------------------------------
# Base item locations
# ---------------------------------------------------------------------------
bases = {}
for key, b in base_items.items():
    cls = b.get("item_class")
    if cls not in LOCATION_CLASSES or b.get("release_state") != "released":
        continue
    name = b["name"]
    if name.startswith(BAD_PREFIX) or name in EXCLUDED_BASES:
        continue
    tags = b.get("tags", [])
    if "runeforged" in tags or "not_for_sale" in tags:
        continue
    lvl = b.get("drop_level", 1)
    if name not in bases or lvl < bases[name]["drop_level"]:
        bases[name] = {"name": name, "drop_level": lvl, "group": LOCATION_CLASSES[cls]}

GROUP_CATEGORY = {
    **{v: "Bases - Weapons" for v in WEAPON_CLASSES.values()},
    **{v: "Bases - Off-hands" for v in OFFHAND_CLASSES.values()},
    **{v: f"Bases - {v}" for v in ARMOUR_CLASSES.values()},
    **{v: "Bases - Jewellery" for v in JEWELLERY_CLASSES.values()},
    "Life Flask": "Bases - Flasks & Charms", "Mana Flask": "Bases - Flasks & Charms", "Charm": "Bases - Flasks & Charms",
    "Jewel": "Bases - Jewellery",
}

locations = []

def add_location(name, region, categories, **extra):
    loc = {"name": name, "region": REGIONS[region], "category": categories}
    loc.update(extra)
    locations.append(loc)

for b in sorted(bases.values(), key=lambda x: (x["drop_level"], x["group"], x["name"])):
    r = region_for_drop_level(b["drop_level"])
    add_location(f"Pick up {b['name']}", r, [GROUP_CATEGORY[b["group"]], "Base Items"],
                 hint_entrance=f"{b['group']} base, drops from item level {b['drop_level']}")

# ---------------------------------------------------------------------------
# Zones & bosses
# ---------------------------------------------------------------------------
ZONE_EXCLUDE = {"G2_3a", "G2_3s", "G2_8a", "G4_ship", "G4_8a", "G4_11_1a", "G1_10"}
BOSS_EXCLUDE = {"G1_10", "G2_8a", "G4_6", "P2_4"}
EARLY_ZONES = {"G1_1", "G1_town", "G1_2"}

def zone_region(aid):
    if aid in EARLY_ZONES:
        return 0
    if aid.startswith("G1"):
        return 1
    if aid.startswith("G2"):
        return 2
    if aid.startswith("G3"):
        return 3
    if aid.startswith("G4"):
        return 4
    if aid.startswith(("P1", "P2", "P3")):
        return 5
    return 6

ACT_LABEL = {0: "Act 1", 1: "Act 1", 2: "Act 2", 3: "Act 3", 4: "Act 4", 5: "Interludes", 6: "Endgame"}

campaign = [(k, a) for k, a in world_areas.items()
            if re.match(r"^(G[1-4]|P[1-3])_", k) and "WorldMap" not in k and a["name"] != "NULL"
            and not a["name"].startswith("[") and k not in ZONE_EXCLUDE]

def sort_key(item):
    k, a = item
    return (zone_region(k), a["area_level"] if not a["is_town"] else -1, k)

seen_zone_names = set()
zone_location_by_area = {}
for k, a in world_areas.items():
    if re.match(r"^(G[1-4]|P[1-3])_", k) and "WorldMap" not in k and a["name"] != "NULL" and not a["name"].startswith("["):
        zone_location_by_area[k] = f"Enter {a['name'].strip()}"
zone_location_by_area["G_Endgame_Town"] = "Enter The Ziggurat Refuge"
for k, a in sorted(campaign, key=sort_key):
    name = a["name"].strip()
    if name in seen_zone_names:
        continue
    seen_zone_names.add(name)
    r = zone_region(k)
    lbl = ACT_LABEL[r]
    add_location(f"Enter {name}", r, [f"Zones - {lbl}", "Zones"],
                 hint_entrance=f"{lbl}{' town' if a['is_town'] else ''}, area level {a['area_level']}")

seen_boss = set()
for k, a in sorted(campaign, key=sort_key):
    if not a["bosses"] or k in BOSS_EXCLUDE:
        continue
    name = a["name"].strip()
    if name in seen_boss:
        continue
    seen_boss.add(name)
    r = zone_region(k)
    lbl = ACT_LABEL[r]
    if k == "G3_10":
        loc_name = "Complete the Trial of Chaos"
    else:
        loc_name = f"Defeat the boss of {name}"
    add_location(loc_name, r, [f"Bosses - {lbl}", "Bosses"], hint_entrance=f"{lbl}, area level {a['area_level']}")

add_location("Complete the Trial of the Sekhemas", 2, ["Bosses - Act 2", "Bosses"],
             hint_entrance="Ascendancy trial, entered from The Ardura Caravan")

# The Ziggurat Refuge: first endgame zone
add_location("Enter The Ziggurat Refuge", 6, ["Zones - Endgame", "Zones"], hint_entrance="Endgame hub after the campaign")

# Pinnacle bosses: each one holds a locked "Pinnacle Boss Trophy"
PINNACLES = [
    ("MapUberBoss_Monolith", "The Burning Monolith"),
    ("MapUberBoss_IronCitadel", "The Iron Citadel"),
    ("MapUberBoss_CopperCitadel", "The Copper Citadel"),
    ("MapUberBoss_StoneCitadel", "The Stone Citadel"),
    ("MapUberBoss_FallenStar", "Ruins of Kingsmarch"),
    ("MapUberBoss_Delirium", "The Withered Willow"),
    ("MapUberBoss_Ritual", "Caer Tarth"),
    ("MapUberBoss_Divinity", "The Origin Tower"),
    ("Abyss_Pinnacle", "The Well of Souls"),
    ("ExpeditionLeagueBoss", "Kalguuran Tomb"),
]
for aid, aname in PINNACLES:
    assert world_areas[aid]["name"] == aname, (aid, world_areas[aid]["name"])
    add_location(f"Defeat the pinnacle boss of {aname}", 6, ["Pinnacle Bosses"],
                 place_item=["Pinnacle Boss Trophy"], requires="{canReachPinnacle()}",
                 hint_entrance=f"Endgame pinnacle encounter (area level {world_areas[aid]['area_level']})")

# Level ups
for lvl in range(2, 101):
    r = region_for_char_level(lvl)
    add_location(f"Reach Level {lvl}", r, ["Level Ups"], level=lvl)

# Victory locations (order = goal option values; first is the default)
VICTORIES = [
    ("Victory - Complete the Campaign", 6, "Reach The Ziggurat Refuge after Act 4 and the Interludes"),
    ("Victory - Complete Act 1", 2, "Reach Act 2 (Vastiri Outskirts)"),
    ("Victory - Complete Act 2", 3, "Reach Act 3 (Sandswept Marsh)"),
    ("Victory - Complete Act 3", 4, "Reach Act 4 (Kingsmarch)"),
    ("Victory - Complete Act 4", 5, "Reach the Interludes"),
    ("Victory - Defeat Pinnacle Bosses", 6, "Defeat the required number of pinnacle bosses"),
]
for name, r, hint in VICTORIES:
    loc = {"name": name, "region": REGIONS[r], "category": ["Goal"], "victory": True, "hint_entrance": hint}
    if "Pinnacle" in name:
        loc["requires"] = "{OptionCount(Pinnacle Boss Trophy, pinnacle_bosses_required)} and {canReachPinnacle()}"
    locations.append(loc)

# Strip the "level" helper key (kept in meta file instead)
level_of_location = {}
for loc in locations:
    if "level" in loc:
        level_of_location[loc["name"]] = loc.pop("level")

# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
items = []
gem_meta = {}  # name -> {"kind","tier","weapons"}

def clean(n):
    return n.replace(":", "").replace("|", "").strip()

for gid, g in skill_gems.items():
    name = g["base_item"]["display_name"]
    if g["crafting_level"] <= 0 or name.startswith(BAD_PREFIX) or g["base_item"].get("release_state") != "released":
        continue
    gtype = g["gem_type"]
    if gtype not in ("active", "spirit"):
        continue
    tags = set(g["tags"])
    ctypes = g["crafting_types"] or []
    if ctypes and set(ctypes) <= NOT_YET_IN_GAME | {"Axe", "Sword"}:
        continue
    if gtype == "spirit":
        kind = "Meta Gem"
    elif "minion" in tags:
        kind = "Skill Gem"
    elif "persistent" in tags:
        kind = "Spirit Gem"
    elif tags & {"buff", "curse", "mark", "warcry"} or not tags & {"attack", "spell"}:
        kind = "Utility Gem"
    else:
        kind = "Skill Gem"
    weapons = []
    if "attack" in tags and kind == "Skill Gem":
        for c in ctypes:
            weapons += GEM_WEAPON_REQ.get(c, [])
    tier = g["crafting_level"]
    gem_meta[clean(name)] = {"kind": kind, "tier": tier, "weapons": sorted(set(weapons)), "groups": ctypes}

KIND_CATEGORY = {"Skill Gem": "Skill Gems", "Spirit Gem": "Spirit Gems", "Utility Gem": "Utility Gems", "Meta Gem": "Meta Gems"}
for name, m in sorted(gem_meta.items(), key=lambda x: (x[1]["kind"], x[1]["tier"], x[0])):
    cat = KIND_CATEGORY[m["kind"]]
    item = {"name": name, "category": [cat, f"{cat} - Tier {m['tier']:02d}"]}
    if m["kind"] == "Skill Gem":
        item["progression"] = True
    else:
        item["useful"] = True
    items.append(item)

# Support gems grouped by lineage (Barbs I/II/III -> one lineage)
rx = re.compile(r"^(.*?)(?: (I|II|III|IV|V))?$")
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}
lineages = defaultdict(list)
for g in skill_gems.values():
    name = g["base_item"]["display_name"]
    if g["gem_type"] != "support" or g["crafting_level"] <= 0 or name.startswith(BAD_PREFIX):
        continue
    m = rx.match(name)
    lineages[clean(m.group(1))].append((ROMAN[m.group(2) or "I"], g["crafting_level"], clean(name)))
support_meta = {}
for root, members in sorted(lineages.items()):
    members.sort()
    item_name = f"{root} Support"
    support_meta[item_name] = {"tiers": [t for _, t, _ in members], "gems": [n for _, _, n in members]}
    items.append({
        "name": item_name,
        "category": ["Support Gems", f"Support Gems - Tier {members[0][1]}"],
        "count": len(members),       # hooks reduce this to 1 unless progressive supports are enabled
        "progression": True,
    })

# Gear
GEAR_SLOTS = (list(WEAPON_CLASSES.values()), list(OFFHAND_CLASSES.values()),
              ["Helmet", "Body Armour", "Gloves", "Boots"], ["Belt", "Amulet", "Ring (Left)", "Ring (Right)"])
for slots, cat in zip(GEAR_SLOTS, ["Weapons", "Off-hands", "Armour", "Jewellery"]):
    for s in slots:
        items.append({"name": f"Progressive {s}", "category": ["Gear", f"Gear - {cat}"], "count": 4, "progression": True})

items += [
    {"name": "Life Flask Slot", "category": ["Flasks & Charms"], "progression": True, "early": True},
    {"name": "Mana Flask Slot", "category": ["Flasks & Charms"], "progression": True},
    {"name": "Progressive Charm Slot", "category": ["Flasks & Charms"], "count": 3, "progression": True},
    {"name": "Progressive Support Socket", "category": ["Support Sockets"], "count": 3, "progression": True},
    {"name": "Passive Skill Point", "category": ["Passive Points"], "count": 123, "progression": True},
    {"name": "Weapon Set Passive Points", "category": ["Passive Points"], "count": 12, "useful": True},
    {"name": "Progressive Ascendancy Trial", "category": ["Ascendancy"], "count": 4, "progression": True},
    {"name": "Pinnacle Boss Trophy", "category": ["Goal"], "count": len(PINNACLES), "progression_skip_balancing": True},
]
for cls, (_, _, ascs) in CLASSES.items():
    for a in ascs:
        items.append({"name": f"Ascendancy - {a}", "category": ["Ascendancy", f"Ascendancy - {cls}"], "progression": True})

for cls in CLASSES:
    items.append({"name": f"Class - {cls}", "category": ["Character Class"], "progression": True})

# Filler
items.append({"name": "A Pile of Gold", "category": ["Filler"], "filler": True})

# Sanity: unique names
names = [i["name"] for i in items]
assert len(names) == len(set(names)), [n for n in names if names.count(n) > 1]
lnames = [l["name"] for l in locations]
assert len(lnames) == len(set(lnames)), [n for n in lnames if lnames.count(n) > 1]

# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------
regions = {}
for i, r in enumerate(REGIONS):
    reg = {}
    if i == 0:
        reg["starting"] = True
    else:
        reg["requires"] = f"{{canReachRegion({i})}}"
    if i + 1 < len(REGIONS):
        reg["connects_to"] = [REGIONS[i + 1]]
    regions[r] = reg

# ---------------------------------------------------------------------------
# Categories (with yaml toggles)
# ---------------------------------------------------------------------------
categories = {}
for loc in locations:
    for c in loc["category"]:
        categories.setdefault(c, {})
for c in list(categories):
    if c.startswith("Zones"):
        categories[c]["yaml_option"] = ["add_zone_locations"]
    elif c.startswith("Bosses"):
        categories[c]["yaml_option"] = ["add_boss_locations"]
    elif c == "Level Ups":
        categories[c]["yaml_option"] = ["add_level_locations"]
categories["Goal"] = {}
categories["Zones"]["hidden"] = True
categories["Bosses"]["hidden"] = True
categories["Base Items"]["hidden"] = True
categories["Base Items"]["yaml_option"] = ["add_base_item_locations"]

# ---------------------------------------------------------------------------
# Write files
# ---------------------------------------------------------------------------
def dump(fname, data, schema=None):
    if schema and isinstance(data, list):
        data = {"$schema": SCHEMA.format(schema), "data": data}
    elif schema:
        data = {"$schema": SCHEMA.format(schema), **data}
    (OUT / fname).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

dump("items.json", items, "items")
dump("locations.json", locations, "locations")
dump("regions.json", regions, "regions")
dump("categories.json", categories, "categories")
dump("events.json", [], "events")

meta = {
    "regions": REGIONS,
    "gems": gem_meta,
    "supports": support_meta,
    "classes": {k: {"weapon": w, "gem_group": g, "ascendancies": a} for k, (w, g, a) in CLASSES.items()},
    "level_of_location": level_of_location,
    "zone_location_by_area": {k: v for k, v in zone_location_by_area.items() if v in set(lnames)},
    "base_groups": {b["name"]: b["group"] for b in bases.values()},
    "source": "repoe-fork/poe2 data export",
}
(OUT / "poe2_meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")

from collections import Counter
print("items:", len(items), "instances:", sum(i.get("count", 1) for i in items))
print("locations:", len(locations))
print("locations per region:", Counter(l["region"] for l in locations))
print("gem kinds:", Counter(m["kind"] for m in gem_meta.values()))
print("support lineages:", len(support_meta), "support gems:", sum(len(s["gems"]) for s in support_meta.values()))
