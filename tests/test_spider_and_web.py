"""Tests for pyfrotz using Spider and Web.

These tests exercise pyfrotz as a library: programmatic input, captured
output, no stdin/stdout interaction.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pyfrotz import ZMachine

ROOT = Path(__file__).resolve().parents[1]
SPIDER_AND_WEB_Z5 = ROOT / "stories" / "spider-and-web.z5"


def _load(path: Path) -> bytes:
    return path.read_bytes()


def _run(story_data: bytes, commands: list[str]) -> str:
    """Run a Z-machine game with the given commands and return all output."""
    buf = io.StringIO()
    vm = ZMachine(story_data, input_lines=commands, output=buf)
    try:
        vm.run()
    except EOFError:
        vm.screen.flush()
    return buf.getvalue()


def _step_output(result: dict[str, object]) -> str:
    """Return typed step output for assertions."""
    output = result["output"]
    assert isinstance(output, str)
    return output


# ---- fixtures -------------------------------------------------------


@pytest.fixture(scope="module")
def z5_data() -> bytes:
    return _load(SPIDER_AND_WEB_Z5)


# ---- Spider and Web tests ------------------------------------------


class TestSpiderAndWeb:
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


# ---- Step API tests ---------------------------------------------------


class TestStepAPIZ5:
    def test_startup(self, z5_data: bytes):
        """step() with no command returns the startup text."""
        vm = ZMachine(z5_data)
        result = vm.step()
        assert "Spider And Web" in _step_output(result)
        assert result["finished"] is False

    def test_look(self, z5_data: bytes):
        """step('look') returns the room description."""
        vm = ZMachine(z5_data)
        vm.step()  # startup
        result = vm.step("look")
        assert "End of Alley" in _step_output(result)
        assert result["finished"] is False

    def test_multiple_steps(self, z5_data: bytes):
        """Multiple step() calls each return their own turn's output."""
        vm = ZMachine(z5_data)
        startup = vm.step()
        look = vm.step("look")
        south = vm.step("south")
        # startup has the title
        assert "Spider And Web" in _step_output(startup)
        # look has the room description but not the title (that was in startup)
        assert "End of Alley" in _step_output(look)
        # south moves to a new room
        assert "Mouth of Alley" in _step_output(south)

    def test_output_isolation(self, z5_data: bytes):
        """Each step's output contains only that turn's text."""
        vm = ZMachine(z5_data)
        vm.step()
        look = vm.step("look")
        # The title should NOT appear in the look output
        assert "Spider And Web" not in _step_output(look)

    def test_examine(self, z5_data: bytes):
        """step('examine door') returns the door description."""
        vm = ZMachine(z5_data)
        vm.step()  # startup
        result = vm.step("examine door")
        assert "naked sheet of metal" in _step_output(result)

    def test_movement_roundtrip(self, z5_data: bytes):
        """step() tracks state across moves."""
        vm = ZMachine(z5_data)
        vm.step()  # startup
        south = vm.step("south")
        assert "Mouth of Alley" in _step_output(south)
        north = vm.step("north")
        assert "End of Alley" in _step_output(north)
