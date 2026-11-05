from worlds.AutoWorld import World
from BaseClasses import CollectionState

from . import poe2


def canReachRegion(world: World, state: CollectionState, player: int, region: str) -> bool:
    """Path of Exile 2: can the player enter campaign region number `region` (see poe2.REGIONS)?"""
    return poe2.meets(world, state, player, poe2.requirements_for(world, int(region)))


def canReachPinnacle(world: World, state: CollectionState, player: int) -> bool:
    """Path of Exile 2: is the character strong enough for endgame pinnacle bosses?"""
    return poe2.meets(world, state, player, poe2.pinnacle_requirements(world))
