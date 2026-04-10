"""Z-Machine text encoding and decoding (ZSCII / Z-characters)."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import Memory

# Default alphabet tables
ALPHABET_A0 = "abcdefghijklmnopqrstuvwxyz"
ALPHABET_A1 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALPHABET_A2_V1 = " 0123456789.,!?_#'\"/\\<-:()"
ALPHABET_A2 = " ^0123456789.,!?_#'\"/\\-:()"

# ZSCII to Latin-1 extra characters (codes 155-223)
ZSCII_TO_UNICODE = [
    0xe4, 0xf6, 0xfc, 0xc4, 0xd6, 0xdc, 0xdf, 0xbb,
    0xab, 0xeb, 0xef, 0xff, 0xcb, 0xcf, 0xe1, 0xe9,
    0xed, 0xf3, 0xfa, 0xfd, 0xc1, 0xc9, 0xcd, 0xd3,
    0xda, 0xdd, 0xe0, 0xe8, 0xec, 0xf2, 0xf9, 0xc0,
    0xc8, 0xcc, 0xd2, 0xd9, 0xe2, 0xea, 0xee, 0xf4,
    0xfb, 0xc2, 0xca, 0xce, 0xd4, 0xdb, 0xe5, 0xc5,
    0xf8, 0xd8, 0xe3, 0xf1, 0xf5, 0xc3, 0xd1, 0xd5,
    0xe6, 0xc6, 0xe7, 0xc7, 0xfe, 0xf0, 0xde, 0xd0,
    0xa3, 0x00, 0x00, 0xa1, 0xbf,
]


class TextEngine:
    """Handles Z-character / ZSCII encoding and decoding."""

    def __init__(self, memory: Memory, version: int, abbreviations_addr: int,
                 alphabet_addr: int = 0):
        self.memory = memory
        self.version = version
        self.abbreviations_addr = abbreviations_addr
        self.alphabet_addr = alphabet_addr

    def _alphabet(self, table: int, index: int) -> str:
        """Return character from alphabet table."""
        if self.alphabet_addr != 0:
            addr = self.alphabet_addr + 26 * table + index
            c = self.memory.read_byte(addr)
            return self.zscii_to_char(c)

        if table == 0:
            return ALPHABET_A0[index]
        elif table == 1:
            return ALPHABET_A1[index]
        else:
            alpha = ALPHABET_A2_V1 if self.version == 1 else ALPHABET_A2
            return alpha[index]

    def zscii_to_char(self, code: int) -> str:
        """Convert a ZSCII code to a Python character."""
        if code == 0:
            return ""
        if code == 13:
            return "\n"
        if 32 <= code <= 126:
            return chr(code)
        if 155 <= code <= 223:
            idx = code - 155
            if idx < len(ZSCII_TO_UNICODE):
                u = ZSCII_TO_UNICODE[idx]
                if u != 0:
                    return chr(u)
            return "?"
        return ""

    def char_to_zscii(self, c: str) -> int:
        """Convert a Python character to ZSCII code."""
        if not c:
            return 0
        code = ord(c)
        if code == 10 or code == 13:
            return 13
        if 32 <= code <= 126:
            return code
        # Search extra characters
        for i, u in enumerate(ZSCII_TO_UNICODE):
            if u == code:
                return 155 + i
        return ord("?")

    def decode_zstring(self, addr: int) -> tuple[str, int]:
        """Decode a Z-string starting at addr.

        Returns (decoded_string, address_after_string).
        """
        result: list[str] = []
        self._decode(addr, result, is_word_addr=False)
        # Calculate end address
        end = addr
        while True:
            word = self.memory.read_word(end)
            end += 2
            if word & 0x8000:
                break
        return "".join(result), end

    def decode_packed_addr(self, packed: int) -> str:
        """Decode a string at a packed address."""
        result: list[str] = []
        if self.version <= 3:
            byte_addr = packed * 2
        elif self.version <= 5:
            byte_addr = packed * 4
        elif self.version <= 7:
            byte_addr = packed * 4 + self.memory.read_word(0x2a) * 8  # strings offset
        else:
            byte_addr = packed * 8
        self._decode(byte_addr, result, is_word_addr=False)
        return "".join(result)

    def decode_at_pc(self, pc: int) -> tuple[str, int]:
        """Decode an embedded string at the current PC. Returns (string, new_pc)."""
        result: list[str] = []
        new_pc = self._decode(pc, result, is_word_addr=False)
        return "".join(result), new_pc

    def _decode(self, addr: int, output: list[str], is_word_addr: bool = False) -> int:
        """Core Z-character decoder. Returns address after last word read."""
        shift_state = 0
        shift_lock = 0
        status = 0  # 0=normal, 1=abbreviation, 2=zscii_high, 3=zscii_low
        prev_c = 0

        while True:
            word = self.memory.read_word(addr)
            addr += 2

            for i in (10, 5, 0):
                c = (word >> i) & 0x1F

                if status == 0:  # Normal
                    if shift_state == 2 and c == 6:
                        # Next two Z-chars form a 10-bit ZSCII code
                        status = 2
                    elif self.version == 1 and c == 1:
                        output.append("\n")
                    elif self.version >= 2 and shift_state == 2 and c == 7:
                        output.append("\n")
                    elif c >= 6:
                        output.append(self._alphabet(shift_state, c - 6))
                    elif c == 0:
                        output.append(" ")
                    elif self.version >= 3 and c <= 3:
                        # Abbreviation: c is 1, 2, or 3
                        status = 1
                    elif self.version >= 2 and c == 1:
                        status = 1
                    else:
                        # Shift characters (2-5)
                        shift_state = (shift_lock + (c & 1) + 1) % 3
                        if self.version <= 2 and c >= 4:
                            shift_lock = shift_state
                        continue  # Don't reset shift_state

                    shift_state = shift_lock

                elif status == 1:  # Abbreviation
                    ptr_addr = self.abbreviations_addr + 64 * (prev_c - 1) + 2 * c
                    abbr_addr = self.memory.read_word(ptr_addr)
                    # Abbreviations use word addresses (multiply by 2)
                    self._decode(abbr_addr * 2, output)
                    status = 0

                elif status == 2:  # ZSCII high bits
                    status = 3

                elif status == 3:  # ZSCII low bits
                    zscii_code = (prev_c << 5) | c
                    output.append(self.zscii_to_char(zscii_code))
                    status = 0

                prev_c = c

            if word & 0x8000:
                break

        return addr

    def encode_text(self, text: str, version: int | None = None) -> list[int]:
        """Encode text to Z-character words for dictionary lookup.

        Returns list of 2 or 3 words (V3: 2 words = 6 Z-chars, V5: 3 words = 9 Z-chars).
        """
        v = version or self.version
        resolution = 2 if v <= 3 else 3
        max_zchars = 3 * resolution
        zchars: list[int] = []

        for ch in text:
            if len(zchars) >= max_zchars:
                break
            # Search in alphabet tables
            found = False
            for table in range(3):
                for index in range(26):
                    if ch == self._alphabet(table, index):
                        if table != 0:
                            zchars.append(3 + table if v >= 3 else 1 + table)
                        zchars.append(index + 6)
                        found = True
                        break
                if found:
                    break

            if not found:
                # Encode as ZSCII literal
                zscii = self.char_to_zscii(ch)
                zchars.append(5)
                zchars.append(6)
                zchars.append(zscii >> 5)
                zchars.append(zscii & 0x1F)

        # Pad with 5s
        while len(zchars) < max_zchars:
            zchars.append(5)

        # Truncate
        zchars = zchars[:max_zchars]

        # Pack into words
        words = []
        for i in range(resolution):
            w = (zchars[3 * i] << 10) | (zchars[3 * i + 1] << 5) | zchars[3 * i + 2]
            words.append(w)

        # Set high bit on last word
        words[-1] |= 0x8000

        return words
