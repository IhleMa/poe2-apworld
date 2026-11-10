# Object classes from AP that represent different types of options that you can create
from Options import Option, FreeText, NumericOption, Toggle, DefaultOnToggle, Choice, TextChoice, Range, NamedRange, OptionGroup, PerGameCommonOptions, OptionSet
# These helper methods allow you to determine if an option has been set, or what its value is, for any player in the multiworld
from ..Helpers import is_option_enabled, get_option_value
from typing import Type, Any


####################################################################
# NOTE: At the time that options are created, Manual has no concept of the multiworld or its own world.
#       Options are defined before the world is even created.
#
# Example of creating your own option:
#
#   class MakeThePlayerOP(Toggle):
#       """Should the player be overpowered? Probably not, but you can choose for this to do... something!"""
#       display_name = "Make me OP"
#
#   options["make_op"] = MakeThePlayerOP
#
#
# Then, to see if the option is set, you can call is_option_enabled or get_option_value.
#####################################################################


# To add an option, use the before_options_defined hook below and something like this:
#   options["total_characters_to_win_with"] = TotalCharactersToWinWith
#
SKILL_CATEGORIES = ["Class", "All", "Mace", "Quarterstaff", "Spear", "Bow", "Crossbow", "Primal", "Elemental", "Occult"]


class SkillCategories(OptionSet):
    """Which skill gem categories are in the item pool. These are the game's own skill categories:

    Mace, Quarterstaff, Spear, Bow, Crossbow, Primal (talisman / shapeshifting skills), Elemental (sorcery: fire,
    cold, lightning spells) and Occult (chaos, curses, minions).

    "Class" means your class's own category (Warrior: Mace, Mercenary: Crossbow, Ranger: Bow, Huntress: Spear,
    Monk: Quarterstaff, Sorceress: Elemental, Witch: Occult, Druid: Primal). "All" puts every skill gem in the pool.
    Example for a spell-casting Warrior: ["Class", "Elemental"]. Applies to skill, spirit, utility and meta gems."""
    display_name = "Skill Categories"
    valid_keys = SKILL_CATEGORIES
    default = frozenset({"Class"})


class SupportGems(Choice):
    """Which support gems are in the item pool.

    Matching: supports from your skill categories, plus every support GGG recommends for the skill gems in your pool.
    All: every support gem."""
    display_name = "Support Gems"
    option_matching = 0
    option_all = 1
    default = 0


def before_options_defined(options: dict[str, Type[Option[Any]]]) -> dict[str, Type[Option[Any]]]:
    options["skill_categories"] = SkillCategories
    options["support_gems"] = SupportGems
    return options

# This is called after any manual options are defined, in case you want to see what options are defined or want to modify the defined options
def after_options_defined(options: Type[PerGameCommonOptions]):
    # To access a modifiable version of options check the dict in options.type_hints
    # For example if you want to change DLC_enabled's display name you would do:
    # options.type_hints["DLC_enabled"].display_name = "New Display Name"

    #  Here's an example on how to add your aliases to the generated goal
    # options.type_hints['goal'].aliases.update({"example": 0, "second_alias": 1})
    # options.type_hints['goal'].options.update({"example": 0, "second_alias": 1})  #for an alias to be valid it must also be in options

    pass

# Use this Hook if you want to add your Option to an Option group (existing or not)
def before_option_groups_created(groups: dict[str, list[Type[Option[Any]]]]) -> dict[str, list[Type[Option[Any]]]]:
    # Put the gem pool options at the top of the "Item Pool" group
    pool = groups.setdefault("Item Pool", [])
    for option in (SupportGems, SkillCategories):
        if option not in pool:
            pool.insert(0, option)
    return groups

def after_option_groups_created(groups: list[OptionGroup]) -> list[OptionGroup]:
    return groups
