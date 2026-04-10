from __future__ import annotations

import io
from pathlib import Path

import pytest

from pyfrotz import ZMachine

ROOT = Path(__file__).resolve().parents[1]
THE_Z_FILES_Z8 = ROOT / "stories" / "the-z-files.z8"
THE_FIRST_MILE_TEST_DRIVE_Z8 = ROOT / "stories" / "the-first-mile-test-drive.z8"


def _load(path: Path) -> bytes:
    return path.read_bytes()


def _run(story_data: bytes, commands: list[str]) -> str:
    buf = io.StringIO()
    vm = ZMachine(story_data, input_lines=commands, output=buf)
    try:
        vm.run()
    except EOFError:
        vm.screen.flush()
    return buf.getvalue()


@pytest.fixture(scope="module")
def the_z_files_data() -> bytes:
    return _load(THE_Z_FILES_Z8)


@pytest.fixture(scope="module")
def the_first_mile_test_drive_data() -> bytes:
    return _load(THE_FIRST_MILE_TEST_DRIVE_Z8)


class TestZ8Games:
    def test_the_z_files_startup_banner(self, the_z_files_data: bytes):
        output = _run(the_z_files_data, [])
        assert "THE Z-FILES" in output
        assert "Release 3 / Serial number 980519" in output
        assert "[Press any key to start.]" in output

    def test_the_z_files_accepts_input_after_prompt(self, the_z_files_data: bytes):
        output = _run(the_z_files_data, [""])
        assert "THE Z-FILES" in output
        assert "legally available" in output

    def test_the_first_mile_test_drive_startup_text(
        self, the_first_mile_test_drive_data: bytes
    ):
        output = _run(the_first_mile_test_drive_data, [])
        assert "Las Vegas" in output
        assert "Dead Rock, Arkansas" in output

    def test_the_first_mile_test_drive_step_api_startup(
        self, the_first_mile_test_drive_data: bytes
    ):
        vm = ZMachine(the_first_mile_test_drive_data)
        result = vm.step()
        output = result["output"]
        assert isinstance(output, str)
        assert "Las Vegas" in output
        assert result["finished"] is False
