"""Z-Machine terminal I/O handling."""

from __future__ import annotations
import sys
from collections.abc import Iterator


class _NeedInput(Exception):
    """Raised when the VM needs input but none is available in step mode."""


class IO:
    """Handles terminal input/output for the Z-machine.

    For library use, pass *input_lines* to supply input programmatically
    instead of reading from stdin::

        io = IO(input_lines=["look", "south", "quit"])
    """

    def __init__(self, input_lines: list[str] | None = None):
        self.input_stream = 0  # 0=keyboard, 1=file
        self.command_file = None
        self._input_iter: Iterator[str] | None = None
        if input_lines is not None:
            self._input_iter = iter(input_lines)
        self._step_mode = False
        self._pending_command: str | None = None

    def set_command(self, command: str):
        """Buffer a single command for step mode."""
        self._pending_command = command

    def read_line(self, max_len: int = 200) -> str:
        """Read a line of input."""
        if self._step_mode:
            if self._pending_command is None:
                raise _NeedInput()
            line = self._pending_command
            self._pending_command = None
        elif self._input_iter is not None:
            try:
                line = next(self._input_iter)
            except StopIteration:
                raise EOFError("End of input")
        else:
            line = input()
        if len(line) > max_len:
            line = line[:max_len]
        return line

    def read_char(self) -> int:
        """Read a single character, returning its ZSCII code."""
        if self._step_mode:
            if self._pending_command is None:
                raise _NeedInput()
            line = self._pending_command
            self._pending_command = None
            if not line:
                return 13  # Return key
            return ord(line[0])

        if self._input_iter is not None:
            try:
                line = next(self._input_iter)
            except StopIteration:
                raise EOFError("End of input")
            if not line:
                return 13  # Return key
            return ord(line[0])

        if sys.stdin.isatty():
            ch = sys.stdin.read(1)
            if not ch:
                raise EOFError("End of input")
            if ch == "\n":
                return 13
            return ord(ch)
        else:
            # When piped, skip whitespace to find the next real character
            while True:
                ch = sys.stdin.read(1)
                if not ch:
                    raise EOFError("End of input")
                if ch == "\n" or ch == "\r":
                    continue
                return ord(ch)

    def print_str(self, text: str):
        """Print text to stdout."""
        sys.stdout.write(text)
        sys.stdout.flush()
