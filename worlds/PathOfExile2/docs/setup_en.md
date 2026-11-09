# PathOfExile2 – Archipelago Setup Guide

This world plays Path of Exile 2 the same way the Path of Exile 1 randomizer does — you start with almost nothing and
earn your skill gems, supports, passive points, gear rarity, flask and charm slots and ascendancy as Archipelago items.
The **PathOfExile2 Client** that ships inside this `.apworld` shows what you have received, sends zone/level/pickup
checks automatically and keeps a loot filter highlighting what you still need.

The client only reads PoE2's log and your clipboard and writes a filter file. Gear and gem restrictions are not
enforced by software: **you follow the rules below yourself.**

## Requirements

- Path of Exile 2
- Archipelago 0.6.4 or newer (`.exe` installer from https://github.com/ArchipelagoMW/Archipelago/releases)
- `PathOfExile2.apworld`

## Install

1. Copy `PathOfExile2.apworld` into the `custom_worlds` folder of your Archipelago install.
   Don't extract or rename it.
2. Open `ArchipelagoLauncher.exe` → **Generate Template Options**. Your template is
   `Players/Templates/PathOfExile2.yaml`. Edit it (or use the provided example YAML).
3. The host puts everyone's YAML in `Players/`, clicks **Generate**, and hosts the archive from `output/`
   (upload it to archipelago.gg, or use **Host**). Everyone generating/hosting needs the same `.apworld` version.

## Connect

1. In the Archipelago Launcher open **PathOfExile2 Client** (it appears once the `.apworld` is installed). Room
   links from archipelago.gg for a PoE2 slot open it too.
2. Enter the server address (e.g. `archipelago.gg:38281`), click **Connect**, and enter your slot name.
3. In the **PathOfExile2** tab, the **Items** list lists everything you have received. The **Locations** tab lists checks grouped by category
   (Zones – Act 1, Bosses – Act 2, Bases – Helmet, Level Ups, …). Click a check when you complete it.
   Optional: if you also install the Universal Tracker apworld, the client colours checks that are currently in logic,
   so it doubles as a "what can I do now" tracker.

Make a **new character** of the class shown as `Class - <name>` in your Items tab. A Solo Self-Found league is
recommended; trading undermines the randomizer.

## Automatic tracking & loot filter

The client has Path of Exile 2 automation built in. It only **reads** PoE2's `Client.txt` log and your clipboard, and
**writes** one loot filter file. It never touches the game process, its memory or GGG's servers, and needs no login.

| What | How it's detected |
|---|---|
| **Enter `<zone>`** | Automatically, from Client.txt when the zone loads. |
| **Reach Level N** | Automatically, from Client.txt (all levels up to your current one). |
| **Pick up `<base>`** | Hover the item in game and press **Ctrl+C** (copies item text, like trade tools do). The client sends that base's check and warns you if the item's rarity is more than you've unlocked for that slot. |
| **Goal** (Act 1–4, Campaign) | Automatically, when you enter the next act / The Ziggurat Refuge. |
| **DeathLink** | Your deaths are sent automatically. Deaths within 15 s of a received DeathLink aren't re-sent. |
| Bosses, trials, pinnacles | Not in Client.txt — click these in the client. |

**Loot filter:** the client writes `ArchipelagoPoE2.filter` into your PoE2 filter folder. It highlights (purple, big
font, minimap star, alert sound) every base you haven't checked yet, then includes your normal filter below so
everything else looks as usual. It is rewritten whenever your checks change. In game, select **ArchipelagoPoE2** in
Options → Game → Item Filter once; after that the client reloads it in game for you (see below).

**In-game chat (filter reload and whispers):** like the Path of Exile 1 client, the client can type into PoE2's
chat for you:

- `/itemfilter ArchipelagoPoE2` whenever the filter changed, so the game reloads it by itself;
- whispers to yourself (`@YourCharacter …`) with what's happening, within about half a second: your unlocks, chat
  from other players, hints, goals, DeathLinks and warnings. Ctrl+C on an item always answers in game: the item it
  unlocked, "already checked", or "can't equip this yet".

Everything is whispered except these categories, which are hidden by default: `other_items` (items moving between
other players), `other_hints`, `join_leave`, `server_replies` and `client_info` (the client's own status lines).
`/poe2_whispers` lists all categories; `/poe2_hide <category>` and `/poe2_show <category>` change them, and
`/poe2_whispers off` turns whispers off.

It only types while Path of Exile 2 is the window in front; anything that arrives while you're tabbed out is sent as
soon as you're back. It sends Enter, pastes the line and sends Enter in one go, restores your clipboard, and limits
itself to a burst of 6 lines and then about one per second so chat isn't flooded. If you'd rather it never types
during a fight, `/poe2_chat_timing zone` only sends right after a zone has loaded. Don't have the chat box open when a
message arrives: the client's Enter would send what you were typing. Your character name is learned from your first
level-up (or set it with `/poe2_character <name>`). Turn the filter reload off with `/poe2_filter_reload off`. Use
`/poe2_chat_test` to try it; if nothing happens, `/poe2_chat_debug` shows the character name, the last zone change
the client saw and which window was in front.

This needs Windows, or Linux with `xdotool` installed (Steam/Proton). It assumes chat opens with **Enter** (the
default key). Typing into the game for you is the same thing the Path of Exile 1 client and popular trade tools do, but
it is still automated input - use it at your own discretion.

**Setup:** the client auto-detects `Client.txt` (standalone and Steam installs) and
`Documents/My Games/Path of Exile 2`. After connecting it prints what it found. Use these commands in the client's
text box if something is missing:

- `/poe2` – status and help
- `/poe2_log <path>` – path to `Path of Exile 2/logs/Client.txt`
- `/poe2_filter_dir <folder>` – your PoE2 filter folder
- `/poe2_base_filter <name>` – your normal filter to keep underneath (e.g. a NeverSink filter downloaded to that folder; subscribed online filters can't be read)
- `/poe2_character <name>` – which character's levels/deaths count (default: the first one that levels up)
- `/poe2_auto on|off`, `/poe2_clipboard on|off`, `/poe2_filter_sound on|off`, `/poe2_filter` (rewrite now)
- `/poe2_filter_reload on|off`, `/poe2_whispers [on|off]`, `/poe2_hide <category>`, `/poe2_show <category>`,
  `/poe2_chat_timing instant|zone`, `/poe2_chat_test`, `/poe2_chat_debug`

### Character API (not available yet)

The PoE 1 randomizer reads your character through GGG's official API. For PoE2 that needs an official OAuth
application, and GGG currently isn't accepting new registrations. The client already contains the gear and gem
checking for it, so it can be switched on once an app is approved. Until then, pickups use Ctrl+C.

Do not paste your POESESSID or any other login cookie into this client or anywhere else. Older test versions
had a session-cookie option; it has been removed and any saved cookie is deleted from disk automatically.

Settings are remembered between sessions. Old log lines are ignored: only things that happen while the client is
running count, so keep it open while you play (or click missed checks by hand).

## The rules (honor system)

| You received… | …which lets you |
|---|---|
| `Class - X` | Play class X (you start with it). |
| A skill gem (e.g. `Ice Nova`) | Engrave that skill from an Uncut Skill Gem. You may not engrave skills you haven't received. Spirit, utility and meta gems work the same. |
| `<Name> Support` | Socket that support. With `progressive_support_gems` off, one item unlocks the whole lineage (Barbs I, II and III). With it on, each copy unlocks the next level. |
| `Progressive Support Socket` | Each skill may hold **2 + (number received)** support gems (max 5). |
| `Progressive <slot or weapon type>` | 1 copy: Normal items in that slot/weapon type. 2: up to Magic. 3: up to Rare. 4: Uniques too. Rings left and right are separate. Off-hands (Shield, Buckler, Focus, Quiver) are separate too. |
| `Life Flask Slot` / `Mana Flask Slot` | Use that flask. |
| `Progressive Charm Slot` | Use one more charm (up to 3). |
| `Passive Skill Point` | Allocate one regular passive point. `Weapon Set Passive Points` = 2 weapon-set points. If `passive_points_in_pool` is 0, allocate passives normally. |
| `Ascendancy - X` | Ascend into X (only your class's ascendancies are in the pool). |
| `Progressive Ascendancy Trial` | Allocate 2 ascendancy points per item received. You still have to complete the trials in game. |

Everything else is allowed: currency, crafting, unequipped items, the weapon your character starts with if
`usable_starting_gear` is on (it is precollected as one `Progressive <weapon>`).

If you equip or use something you haven't received you're out of logic — just take it off.

## Checks

- **Pick up `<base>`** – the first time you pick up any item of that base type (any rarity). Ctrl+C it, or click the check.
- **Enter `<zone>`** – the first time you enter that campaign zone.
- **Defeat the boss of `<zone>`** – the zone's boss; plus **Complete the Trial of the Sekhemas / Trial of Chaos**.
- **Reach Level N** – up to `max_level_location`.
- **Defeat the pinnacle boss of `<area>`** – only with the pinnacle goal; each awards a `Pinnacle Boss Trophy`.
- **Victory – …** – click this when you reach your goal (e.g. you have entered The Ziggurat Refuge).

Anything not detected automatically can be clicked in the client at any time; nothing is lost by clicking late.

## DeathLink

With `death_link: true`, your deaths are sent automatically: when Client.txt says
`<YourCharacter> has been slain.`, the client sends a DeathLink, no button needed (the **Death Link** button still
works manually). A death within 15 seconds of receiving someone else's DeathLink isn't sent back.

The client only counts deaths of the character it tracks, which it learns from your first level-up after the client
starts (or set it with `/poe2_character <name>`). If another character dies, or you die before the client knows your
name, it says so in the client and tells you the command to fix it. `/poe2` shows the last death it saw and whether a
DeathLink was sent.

When someone else dies the button changes to show who — the PoE1 convention is to log out to character select (no XP
loss) rather than die.

## Options summary

`goal` (campaign, Act 1–4, pinnacle bosses), `starting_character`, `usable_starting_gear`, `starting_skill_gem`,
`include_ascendancy`, `progressive_support_gems`, `passive_points_in_pool`, `add_base_item_locations`,
`add_zone_locations`, `add_boss_locations`, `add_level_locations`, `max_level_location`, `pinnacle_bosses_required`.
If you turn most location types off, generation can fail with "Not enough locations" — turn some back on.
Short goals automatically drop content past the goal, and the item pool shrinks to fit.

## Logic in brief

To enter each act the generator expects a number of usable skill gems (right tier, plus a weapon type that can use them;
spells and minions need no weapon), gear unlocks, armour slots, supports, support sockets, passive points,
flask/charm slots and — from Act 4 — an ascendancy and trials. Skill tiers available per act are roughly:
Act 1 ≤3, Act 2 ≤7, Act 3 ≤11, Act 4 ≤13, Interludes and endgame ≤14.

Game data comes from the repoe-fork/poe2 export (patch 0.5.x). Weapon types not yet in the game (swords, axes, daggers,
claws, flails) and the Duelist are not included yet; they can be added when 1.0 releases.
