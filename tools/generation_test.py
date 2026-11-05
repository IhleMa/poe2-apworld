#!/usr/bin/env python3
"""Generate many random multiworlds with this world to catch generation failures.

Each run creates 6 PoE2 players with random options and runs Archipelago's Generate.py.
"Not enough locations" errors for option sets that turn almost every location type off
are expected and counted separately.

Usage:  python tools/generation_test.py <path to Archipelago source checkout> [runs]
The .apworld must be installed in that checkout (custom_worlds/ or worlds/).
"""
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GAME = "PathOfExile2"
GOALS = ["victory - complete the campaign", "victory - complete act 1", "victory - complete act 2",
         "victory - complete act 3", "victory - complete act 4", "victory - defeat pinnacle bosses"]
CLASSES = ["random_class", "warrior", "mercenary", "ranger", "huntress", "monk", "sorceress", "witch", "druid"]


def random_options(rng: random.Random) -> dict:
    return {
        "goal": rng.choice(GOALS),
        "starting_character": rng.choice(CLASSES),
        "usable_starting_gear": rng.choice(["true", "false"]),
        "starting_skill_gem": rng.choice(["true", "false"]),
        "include_ascendancy": rng.choice(["true", "false"]),
        "progressive_support_gems": rng.choice(["true", "false"]),
        "passive_points_in_pool": rng.choice([0, 30, 123]),
        "add_base_item_locations": rng.choice(["true", "true", "false"]),
        "add_zone_locations": rng.choice(["true", "false"]),
        "add_boss_locations": rng.choice(["true", "false"]),
        "add_level_locations": rng.choice(["true", "false"]),
        "max_level_location": rng.choice([10, 40, 90]),
        "pinnacle_bosses_required": rng.randint(1, 10),
        "progression_balancing": rng.choice([0, 50, 99]),
    }


def main() -> int:
    ap_dir = Path(sys.argv[1]).resolve()
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    ok = expected = failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for run in range(runs):
            rng = random.Random(run)
            players, out = Path(tmp, f"r{run}", "players"), Path(tmp, f"r{run}", "out")
            players.mkdir(parents=True)
            out.mkdir()
            for p in range(6):
                opts = "".join(f"  {k}: {v}\n" for k, v in random_options(rng).items())
                (players / f"p{p}.yaml").write_text(f"name: P{p}\ngame: {GAME}\n{GAME}:\n{opts}", encoding="utf-8")
            result = subprocess.run([sys.executable, "Generate.py", "--player_files_path", str(players),
                                     "--outputpath", str(out), "--seed", str(run)],
                                    cwd=ap_dir, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900)
            log = result.stdout + result.stderr
            if "Done. Enjoy" in log:
                ok += 1
                status = "ok"
            elif "Not enough locations" in log:
                expected += 1
                status = "too few locations (expected for extreme options)"
            else:
                failed += 1
                errors = [l for l in log.splitlines() if "Error" in l or "Exception" in l][-3:]
                status = "FAILED: " + " | ".join(errors)
            print(f"run {run}: {status}", flush=True)
            shutil.rmtree(players.parent, ignore_errors=True)
    print(f"\n{ok} ok, {expected} expected 'not enough locations', {failed} failed out of {runs}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
