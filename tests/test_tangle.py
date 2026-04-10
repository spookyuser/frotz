"""Tests for pyfrotz using the Tangle (Spider And Web) game files.

These tests exercise pyfrotz as a library: programmatic input, captured
output, no stdin/stdout interaction.
"""

from __future__ import annotations

import io
import os

import pytest

from pyfrotz import ZMachine

TESTS_ROOT = os.path.dirname(os.path.abspath(__file__))
Z5_PATH = os.path.join(TESTS_ROOT, "Tangle.z5")
Z8_PATH = os.path.join(TESTS_ROOT, "Tangle.z8")


def _load(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _run(story_data: bytes, commands: list[str]) -> str:
    """Run a Z-machine game with the given commands and return all output."""
    buf = io.StringIO()
    vm = ZMachine(story_data, input_lines=commands, output=buf)
    try:
        vm.run()
    except EOFError:
        vm.screen.flush()
    return buf.getvalue()


# ---- fixtures -------------------------------------------------------


@pytest.fixture(scope="module")
def z5_data() -> bytes:
    return _load(Z5_PATH)


@pytest.fixture(scope="module")
def z8_data() -> bytes:
    return _load(Z8_PATH)


# ---- Tangle.z5 tests -----------------------------------------------


class TestTangleZ5:
    def test_startup_banner(self, z5_data: bytes):
        """Game prints the intro text and title on startup."""
        output = _run(z5_data, [])
        assert "Spider And Web" in output
        assert "Andrew Plotkin" in output
        assert "Release 4" in output

    def test_look(self, z5_data: bytes):
        """'look' prints the room description."""
        output = _run(z5_data, ["look"])
        # The initial room description appears in the intro, and again
        # after the explicit 'look' command.
        assert output.count("End of Alley") >= 2
        assert "narrow dead end" in output

    def test_examine_door(self, z5_data: bytes):
        """'examine door' describes the metal door."""
        output = _run(z5_data, ["examine door"])
        assert "naked sheet of metal" in output

    def test_movement(self, z5_data: bytes):
        """Moving south then north works correctly."""
        output = _run(z5_data, ["south", "north"])
        assert "Mouth of Alley" in output
        assert "broad street" in output

    def test_multiple_commands(self, z5_data: bytes):
        """A sequence of commands all produce expected output."""
        output = _run(z5_data, ["look", "south", "look", "north"])
        assert "End of Alley" in output
        assert "Mouth of Alley" in output

    def test_about(self, z5_data: bytes):
        """The 'about' meta-command prints game information."""
        output = _run(z5_data, ["about"])
        assert "copyright" in output.lower()

    def test_unrecognized_verb(self, z5_data: bytes):
        """An unrecognized verb is reported gracefully."""
        output = _run(z5_data, ["xyzzy"])
        assert (
            "not a verb i recogni" in output.lower()
            or "didn't understand" in output.lower()
        )

    def test_inventory(self, z5_data: bytes):
        """'inventory' works at game start."""
        output = _run(z5_data, ["inventory"])
        # At the start you carry a guidebook
        assert "carrying" in output.lower() or "nothing" in output.lower()


# ---- Tangle.z8 tests -----------------------------------------------


class TestTangleZ8:
    def test_startup_banner(self, z8_data: bytes):
        """Game prints the intro text and title on startup."""
        output = _run(z8_data, [])
        assert "Spider And Web" in output
        assert "Andrew Plotkin" in output

    def test_look(self, z8_data: bytes):
        """'look' prints the room description."""
        output = _run(z8_data, ["look"])
        assert output.count("End of Alley") >= 2
        assert "narrow dead end" in output

    def test_examine_door(self, z8_data: bytes):
        """'examine door' describes the metal door."""
        output = _run(z8_data, ["examine door"])
        assert "naked sheet of metal" in output

    def test_movement(self, z8_data: bytes):
        """Moving south then north works correctly."""
        output = _run(z8_data, ["south", "north"])
        assert "Mouth of Alley" in output
        assert "broad street" in output

    def test_multiple_commands(self, z8_data: bytes):
        """A sequence of commands all produce expected output."""
        output = _run(z8_data, ["look", "south", "look", "north"])
        assert "End of Alley" in output
        assert "Mouth of Alley" in output

    def test_about(self, z8_data: bytes):
        """The 'about' meta-command prints game information."""
        output = _run(z8_data, ["about"])
        assert "copyright" in output.lower()


# ---- Cross-version tests -------------------------------------------


class TestCrossVersion:
    def test_same_intro(self, z5_data: bytes, z8_data: bytes):
        """Both versions produce the same intro text (ignoring errors)."""
        out5 = _run(z5_data, [])
        out8 = _run(z8_data, [])
        # Both should contain the game title and opening paragraph
        for phrase in ["Spider And Web", "On the whole", "End of Alley"]:
            assert phrase in out5, f"z5 missing: {phrase}"
            assert phrase in out8, f"z8 missing: {phrase}"

    def test_same_look_output(self, z5_data: bytes, z8_data: bytes):
        """Both versions produce matching room descriptions for 'look'."""
        out5 = _run(z5_data, ["look"])
        out8 = _run(z8_data, ["look"])
        # Both should describe the alley (word-wrap may split phrases
        # across lines, so collapse whitespace before checking)
        out5_flat = " ".join(out5.split())
        out8_flat = " ".join(out8.split())
        for phrase in ["narrow dead end", "plain metal door", "firmly shut"]:
            assert phrase in out5_flat, f"z5 missing: {phrase}"
            assert phrase in out8_flat, f"z8 missing: {phrase}"


# ---- Step API tests ---------------------------------------------------


class TestStepAPIZ5:
    def test_startup(self, z5_data: bytes):
        """step() with no command returns the startup text."""
        vm = ZMachine(z5_data)
        result = vm.step()
        assert "Spider And Web" in result["output"]
        assert result["finished"] is False

    def test_look(self, z5_data: bytes):
        """step('look') returns the room description."""
        vm = ZMachine(z5_data)
        vm.step()  # startup
        result = vm.step("look")
        assert "End of Alley" in result["output"]
        assert result["finished"] is False

    def test_multiple_steps(self, z5_data: bytes):
        """Multiple step() calls each return their own turn's output."""
        vm = ZMachine(z5_data)
        startup = vm.step()
        look = vm.step("look")
        south = vm.step("south")
        # startup has the title
        assert "Spider And Web" in startup["output"]
        # look has the room description but not the title (that was in startup)
        assert "End of Alley" in look["output"]
        # south moves to a new room
        assert "Mouth of Alley" in south["output"]

    def test_output_isolation(self, z5_data: bytes):
        """Each step's output contains only that turn's text."""
        vm = ZMachine(z5_data)
        startup = vm.step()
        look = vm.step("look")
        # The title should NOT appear in the look output
        assert "Spider And Web" not in look["output"]

    def test_examine(self, z5_data: bytes):
        """step('examine door') returns the door description."""
        vm = ZMachine(z5_data)
        vm.step()  # startup
        result = vm.step("examine door")
        assert "naked sheet of metal" in result["output"]

    def test_movement_roundtrip(self, z5_data: bytes):
        """step() tracks state across moves."""
        vm = ZMachine(z5_data)
        vm.step()  # startup
        south = vm.step("south")
        assert "Mouth of Alley" in south["output"]
        north = vm.step("north")
        assert "End of Alley" in north["output"]


class TestStepAPIZ8:
    def test_startup(self, z8_data: bytes):
        """step() with no command returns the startup text."""
        vm = ZMachine(z8_data)
        result = vm.step()
        assert "Spider And Web" in result["output"]
        assert result["finished"] is False

    def test_look(self, z8_data: bytes):
        """step('look') returns the room description."""
        vm = ZMachine(z8_data)
        vm.step()  # startup
        result = vm.step("look")
        assert "End of Alley" in result["output"]

    def test_multiple_steps(self, z8_data: bytes):
        """Multiple step() calls each return their own turn's output."""
        vm = ZMachine(z8_data)
        startup = vm.step()
        look = vm.step("look")
        south = vm.step("south")
        assert "Spider And Web" in startup["output"]
        assert "End of Alley" in look["output"]
        assert "Mouth of Alley" in south["output"]

    def test_output_isolation(self, z8_data: bytes):
        """Each step's output contains only that turn's text."""
        vm = ZMachine(z8_data)
        startup = vm.step()
        look = vm.step("look")
        assert "Spider And Web" not in look["output"]
