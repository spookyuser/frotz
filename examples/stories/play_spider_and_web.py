from __future__ import annotations

import io
from pathlib import Path

from pyfrotz import ZMachine

ROOT = Path(__file__).resolve().parents[2]
SPIDER_AND_WEB_Z5 = ROOT / "stories" / "spider-and-web.z5"


def load_story() -> bytes:
    return SPIDER_AND_WEB_Z5.read_bytes()


def run_with_scripted_input(story_data: bytes) -> str:
    """Run the game non-interactively with a fixed list of commands."""
    output = io.StringIO()
    vm = ZMachine(
        story_data,
        input_lines=["look", "examine door", "south", "north"],
        output=output,
    )

    try:
        vm.run()
    except EOFError:
        # Expected once the scripted commands are exhausted.
        vm.screen.flush()

    return output.getvalue()


def run_turn_by_turn(story_data: bytes) -> None:
    """Drive the VM one command at a time with step()."""
    vm = ZMachine(story_data)

    startup = vm.step()
    print("=== startup ===")
    print(startup["output"])

    for command in ["look", "examine door", "south"]:
        result = vm.step(command)
        print(f"=== command: {command!r} ===")
        print(result["output"])


def main() -> None:
    story_data = load_story()

    print(f"Loaded: {SPIDER_AND_WEB_Z5}")
    print()

    print("=== scripted input example ===")
    transcript = run_with_scripted_input(story_data)
    print(transcript)

    print("=== step() example ===")
    run_turn_by_turn(story_data)


if __name__ == "__main__":
    main()
