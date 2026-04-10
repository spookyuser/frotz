"""Z-Machine dictionary parsing and tokenization."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import Memory
    from .text import TextEngine


class Dictionary:
    """Handles Z-machine dictionary lookup and input tokenization."""

    def __init__(self, memory: Memory, version: int, dict_addr: int,
                 text_engine: TextEngine):
        self.memory = memory
        self.version = version
        self.dict_addr = dict_addr
        self.text = text_engine

        # Parse dictionary header
        addr = dict_addr
        num_separators = memory.read_byte(addr)
        addr += 1
        self.separators: list[int] = []
        for _ in range(num_separators):
            self.separators.append(memory.read_byte(addr))
            addr += 1
        self.entry_length = memory.read_byte(addr)
        addr += 1
        self.entry_count = self._read_signed_word(addr)
        addr += 2
        self.entries_start = addr

    def _read_signed_word(self, addr: int) -> int:
        """Read a potentially signed word (entry count can be negative)."""
        val = self.memory.read_word(addr)
        if val & 0x8000:
            return val - 0x10000
        return val

    def lookup(self, encoded: list[int]) -> int:
        """Look up encoded Z-text in the dictionary. Returns address or 0."""
        resolution = 2 if self.version <= 3 else 3
        count = abs(self.entry_count)

        if self.entry_count > 0:
            # Sorted dictionary - binary search
            low, high = 0, count - 1
            while low <= high:
                mid = (low + high) // 2
                entry_addr = self.entries_start + mid * self.entry_length
                match = self._compare_entry(entry_addr, encoded, resolution)
                if match == 0:
                    return entry_addr
                elif match < 0:
                    low = mid + 1
                else:
                    high = mid - 1
        else:
            # Unsorted - linear search
            for i in range(count):
                entry_addr = self.entries_start + i * self.entry_length
                if self._compare_entry(entry_addr, encoded, resolution) == 0:
                    return entry_addr

        return 0

    def _compare_entry(self, entry_addr: int, encoded: list[int],
                       resolution: int) -> int:
        """Compare encoded text with dictionary entry. Returns <0, 0, >0."""
        for i in range(resolution):
            entry_word = self.memory.read_word(entry_addr + 2 * i)
            if encoded[i] < entry_word:
                return -1
            if encoded[i] > entry_word:
                return 1
        return 0

    def tokenize(self, text_addr: int, parse_addr: int,
                 dict_addr: int = 0, flag: bool = False):
        """Tokenize input text and fill the parse buffer.

        text_addr: address of text buffer (byte 0=max, byte 1=actual length in V5+)
        parse_addr: address of parse buffer (byte 0=max tokens)
        dict_addr: alternate dictionary (0 = use default)
        flag: if True, only fill in dict addresses for recognized words
        """
        use_dict = dict_addr if dict_addr != 0 else self.dict_addr

        # Read the input text
        if self.version <= 4:
            # V1-V4: text starts at byte 1, null-terminated
            text_start = text_addr + 1
            chars = []
            addr = text_start
            while True:
                c = self.memory.read_byte(addr)
                if c == 0:
                    break
                chars.append(c)
                addr += 1
        else:
            # V5+: byte 1 = length, text starts at byte 2
            text_len = self.memory.read_byte(text_addr + 1)
            text_start = text_addr + 2
            chars = [self.memory.read_byte(text_start + i) for i in range(text_len)]

        # Split into tokens
        tokens = self._split_tokens(chars, text_start)

        # Get max number of tokens the parse buffer can hold
        max_tokens = self.memory.read_byte(parse_addr)

        # Write token count
        num_tokens = min(len(tokens), max_tokens)
        self.memory.write_byte(parse_addr + 1, num_tokens)

        # Process each token
        for i in range(num_tokens):
            word_text, word_start, word_len = tokens[i]

            # Encode for dictionary lookup
            encoded = self.text.encode_text(word_text)

            # Look up in dictionary
            if dict_addr != 0:
                entry = self._lookup_in_dict(encoded, use_dict)
            else:
                entry = self.lookup(encoded)

            # Write to parse buffer: 4 bytes per entry
            # word 0: dictionary address (0 if not found)
            # byte 2: length of word
            # byte 3: position in text buffer
            entry_addr = parse_addr + 2 + i * 4

            if flag and entry == 0:
                # Don't overwrite if flag is set and word not found
                pass
            else:
                self.memory.write_word(entry_addr, entry)

            self.memory.write_byte(entry_addr + 2, word_len)
            self.memory.write_byte(entry_addr + 3, word_start - text_addr +
                                   (1 if self.version <= 4 else 2))

    def _split_tokens(self, chars: list[int], text_start: int
                      ) -> list[tuple[str, int, int]]:
        """Split ZSCII chars into tokens. Returns list of (text, start_addr, length)."""
        tokens: list[tuple[str, int, int]] = []
        i = 0

        while i < len(chars):
            c = chars[i]

            if c == ord(" "):
                i += 1
                continue

            # Check if this is a separator
            if c in self.separators:
                tokens.append((chr(c), text_start + i, 1))
                i += 1
                continue

            # Collect a word
            start = i
            while i < len(chars) and chars[i] != ord(" ") and chars[i] not in self.separators:
                i += 1

            word = "".join(chr(chars[j]) for j in range(start, i))
            tokens.append((word, text_start + start, i - start))

        return tokens

    def _lookup_in_dict(self, encoded: list[int], dict_address: int) -> int:
        """Look up a word in an arbitrary dictionary."""
        addr = dict_address
        num_sep = self.memory.read_byte(addr)
        addr += 1 + num_sep
        entry_length = self.memory.read_byte(addr)
        addr += 1
        entry_count_raw = self.memory.read_word(addr)
        if entry_count_raw & 0x8000:
            entry_count = entry_count_raw - 0x10000
        else:
            entry_count = entry_count_raw
        addr += 2
        entries_start = addr

        resolution = 2 if self.version <= 3 else 3
        count = abs(entry_count)

        if entry_count > 0:
            low, high = 0, count - 1
            while low <= high:
                mid = (low + high) // 2
                ea = entries_start + mid * entry_length
                match = self._compare_entry(ea, encoded, resolution)
                if match == 0:
                    return ea
                elif match < 0:
                    low = mid + 1
                else:
                    high = mid - 1
        else:
            for i in range(count):
                ea = entries_start + i * entry_length
                if self._compare_entry(ea, encoded, resolution) == 0:
                    return ea

        return 0
