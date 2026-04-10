"""Entry point for: python -m pyfrotz <storyfile>"""

from __future__ import annotations
import argparse
import sys

from .zmachine import ZMachine


def main():
    parser = argparse.ArgumentParser(
        prog="pyfrotz",
        description="pyfrotz - A Python Z-Machine interpreter",
    )
    parser.add_argument("story_file", help="Path to Z-code story file (.z3, .z5, etc.)")
    parser.add_argument("-s", "--seed", type=int, default=None,
                        help="Random number seed")
    args = parser.parse_args()

    try:
        with open(args.story_file, "rb") as f:
            story_data = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {args.story_file}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    if len(story_data) < 64:
        print("Error: File too small to be a Z-code story", file=sys.stderr)
        sys.exit(1)

    version = story_data[0]
    if version == 0 or version > 8:
        print(f"Error: Invalid Z-machine version: {version}", file=sys.stderr)
        sys.exit(1)

    vm = ZMachine(story_data)

    if args.seed is not None:
        import random
        vm._rng = random.Random(args.seed)

    try:
        vm.run()
    except KeyboardInterrupt:
        vm.screen.flush()
        print("\n[Interrupted]")
    except EOFError:
        vm.screen.flush()
        print("\n[End of input]")
    except Exception as e:
        vm.screen.flush()
        print(f"\n[Fatal error: {e}]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
