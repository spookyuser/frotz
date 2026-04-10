"""Z-Machine terminal I/O handling."""

from __future__ import annotations
import sys


class IO:
    """Handles terminal input/output for the Z-machine."""

    def __init__(self):
        self.input_stream = 0  # 0=keyboard, 1=file
        self.command_file = None

    def read_line(self, max_len: int = 200) -> str:
        """Read a line of input from the terminal."""
        line = input()
        # Truncate to max length
        if len(line) > max_len:
            line = line[:max_len]
        return line

    def read_char(self) -> int:
        """Read a single character, returning its ZSCII code."""
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
