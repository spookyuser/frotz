"""Z-Machine screen model (dumb terminal mode)."""

from __future__ import annotations
import sys


class Screen:
    """Manages the Z-machine screen output in dumb terminal mode."""

    def __init__(self, version: int, width: int = 80):
        self.version = version
        self.width = width
        self.current_window = 0  # 0=lower, 1=upper
        self.upper_height = 0
        self.buffered = True
        self._buffer = ""
        self._column = 0
        self.transcript_file = None
        self.command_file = None
        self._output_streams: set[int] = {1}  # Stream 1 (screen) on by default
        self._memory_streams: list[tuple[int, int]] = []  # (addr, original_addr) stack
        self._memory_stream_data: list[list[int]] = []
        self._memory = None

    def print_char(self, c: str):
        """Print a single character to active output streams."""
        if 3 in self._output_streams and self._memory_stream_data:
            # Stream 3 (memory) takes priority and suppresses screen output
            self._memory_stream_data[-1].append(ord(c[0]) if c else 0)
            return

        if 1 in self._output_streams:
            self._screen_print(c)

        if 2 in self._output_streams and self.transcript_file:
            self.transcript_file.write(c)
            self.transcript_file.flush()

    def print_str(self, text: str):
        """Print a string to active output streams."""
        for c in text:
            self.print_char(c)

    def _screen_print(self, c: str):
        """Output a character to the screen."""
        # In dumb terminal mode, suppress upper window output since we
        # cannot position the cursor. The status line info is already
        # part of the game's normal lower window output.
        if self.current_window == 1:
            return
        if c == "\n":
            sys.stdout.write(self._buffer + "\n")
            sys.stdout.flush()
            self._buffer = ""
            self._column = 0
        elif self.buffered:
            self._buffer += c
            self._column += 1
            # Word wrap
            if self._column >= self.width:
                # Find last space for word wrap
                last_space = self._buffer.rfind(" ")
                if last_space > 0:
                    sys.stdout.write(self._buffer[:last_space] + "\n")
                    self._buffer = self._buffer[last_space + 1:]
                else:
                    sys.stdout.write(self._buffer + "\n")
                    self._buffer = ""
                self._column = len(self._buffer)
                sys.stdout.flush()
        else:
            sys.stdout.write(c)
            self._column += 1
            sys.stdout.flush()

    def flush(self):
        """Flush any buffered output."""
        if self._buffer:
            sys.stdout.write(self._buffer)
            sys.stdout.flush()
            self._buffer = ""

    def new_line(self):
        self.print_char("\n")

    def split_window(self, lines: int):
        """Split the screen, creating an upper window of the given height."""
        self.upper_height = lines

    def set_window(self, window: int):
        """Set the active window."""
        if self.current_window == 0 and window == 1:
            self.flush()
        self.current_window = window

    def erase_window(self, window: int):
        """Erase a window. -1 = unsplit and clear, -2 = clear without unsplit."""
        if window == 0xFFFF or window == -1:  # -1 as unsigned
            self.upper_height = 0
            self.current_window = 0
        self.flush()

    def set_cursor(self, row: int, col: int):
        """Set cursor position in upper window (mostly a no-op in dumb mode)."""
        pass

    def set_text_style(self, style: int):
        """Set text style (no-op in dumb mode)."""
        pass

    def buffer_mode(self, mode: int):
        """Enable/disable output buffering."""
        if mode == 0:
            self.flush()
        self.buffered = bool(mode)

    def set_colour(self, fg: int, bg: int):
        """Set text colour (no-op in dumb mode)."""
        pass

    def set_font(self, font: int) -> int:
        """Set font. Returns previous font or 0 if unavailable."""
        if font == 1 or font == 4:  # Normal or fixed-width
            return 1
        return 0

    # --- Output streams ---

    def output_stream(self, stream: int, addr: int = 0, memory=None):
        """Enable or disable an output stream."""
        if stream > 0:
            self._output_streams.add(stream)
            if stream == 3 and memory is not None:
                self._memory = memory
                self._memory_streams.append((addr + 2, addr))
                self._memory_stream_data.append([])
        elif stream < 0:
            s = -stream
            if s != 3:
                self._output_streams.discard(s)
            if s == 3 and self._memory_stream_data:
                data = self._memory_stream_data.pop()
                table_addr, orig_addr = self._memory_streams.pop()
                if self._memory is not None:
                    self._memory.write_word(orig_addr, len(data))
                    for i, ch in enumerate(data):
                        self._memory.write_byte(table_addr + i, ch)
                if not self._memory_stream_data:
                    self._output_streams.discard(3)

    def input_stream(self, stream: int):
        """Select input stream (0=keyboard, 1=file). Mostly no-op."""
        pass

    def show_status(self, location: str, score_or_time: str):
        """Display V3 status line."""
        self.flush()
        # Format: location left-justified, score/time right-justified
        status = location[:self.width - len(score_or_time) - 1]
        padding = self.width - len(status) - len(score_or_time)
        if padding < 1:
            padding = 1
        line = status + " " * padding + score_or_time
        sys.stdout.write("\n[" + line[:self.width - 2] + "]\n")
        sys.stdout.flush()
