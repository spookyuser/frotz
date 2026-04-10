"""Z-Machine story file header parsing."""

from __future__ import annotations
from dataclasses import dataclass
from .memory import Memory

# Header byte offsets (from frotz.h)
H_VERSION = 0
H_CONFIG = 1
H_RELEASE = 2
H_RESIDENT_SIZE = 4
H_START_PC = 6
H_DICTIONARY = 8
H_OBJECTS = 10
H_GLOBALS = 12
H_DYNAMIC_SIZE = 14
H_FLAGS = 16
H_SERIAL = 18
H_ABBREVIATIONS = 24
H_FILE_SIZE = 26
H_CHECKSUM = 28
H_INTERPRETER_NUMBER = 30
H_INTERPRETER_VERSION = 31
H_SCREEN_ROWS = 32
H_SCREEN_COLS = 33
H_SCREEN_WIDTH = 34
H_SCREEN_HEIGHT = 36
H_FONT_HEIGHT = 38
H_FONT_WIDTH = 39
H_FUNCTIONS_OFFSET = 40
H_STRINGS_OFFSET = 42
H_DEFAULT_BACKGROUND = 44
H_DEFAULT_FOREGROUND = 45
H_TERMINATING_KEYS = 46
H_ALPHABET = 52
H_EXTENSION_TABLE = 54


@dataclass
class Header:
    version: int
    config: int
    release: int
    resident_size: int
    start_pc: int
    dictionary: int
    objects: int
    globals: int
    dynamic_size: int
    flags: int
    serial: bytes
    abbreviations: int
    file_size: int
    checksum: int
    functions_offset: int
    strings_offset: int
    terminating_keys: int
    alphabet: int
    extension_table: int

    @classmethod
    def from_memory(cls, mem: Memory) -> Header:
        version = mem.read_byte(H_VERSION)

        # File size calculation depends on version
        raw_file_size = mem.read_word(H_FILE_SIZE)
        if version <= 3:
            file_size = raw_file_size * 2
        elif version <= 5:
            file_size = raw_file_size * 4
        else:
            file_size = raw_file_size * 8

        return cls(
            version=version,
            config=mem.read_byte(H_CONFIG),
            release=mem.read_word(H_RELEASE),
            resident_size=mem.read_word(H_RESIDENT_SIZE),
            start_pc=mem.read_word(H_START_PC),
            dictionary=mem.read_word(H_DICTIONARY),
            objects=mem.read_word(H_OBJECTS),
            globals=mem.read_word(H_GLOBALS),
            dynamic_size=mem.read_word(H_DYNAMIC_SIZE),
            flags=mem.read_word(H_FLAGS),
            serial=mem.slice(H_SERIAL, 6),
            abbreviations=mem.read_word(H_ABBREVIATIONS),
            file_size=file_size,
            checksum=mem.read_word(H_CHECKSUM),
            functions_offset=mem.read_word(H_FUNCTIONS_OFFSET),
            strings_offset=mem.read_word(H_STRINGS_OFFSET),
            terminating_keys=mem.read_word(H_TERMINATING_KEYS),
            alphabet=mem.read_word(H_ALPHABET),
            extension_table=mem.read_word(H_EXTENSION_TABLE),
        )

    def setup_interpreter_fields(self, mem: Memory):
        """Write interpreter capabilities into the header."""
        if self.version >= 4:
            mem.write_byte(H_INTERPRETER_NUMBER, 6)  # MS-DOS
            mem.write_byte(H_INTERPRETER_VERSION, ord('F'))  # 'F' for pyfrotz
            mem.write_byte(H_SCREEN_ROWS, 255)
            mem.write_byte(H_SCREEN_COLS, 80)

        if self.version >= 5:
            mem.write_word(H_SCREEN_WIDTH, 80)
            mem.write_word(H_SCREEN_HEIGHT, 255)
            mem.write_byte(H_FONT_HEIGHT, 1)
            mem.write_byte(H_FONT_WIDTH, 1)
            mem.write_byte(H_DEFAULT_BACKGROUND, 2)  # Black
            mem.write_byte(H_DEFAULT_FOREGROUND, 9)  # White

        # Set flags: we support fixed-width font
        if self.version <= 3:
            config = 0x20  # Split screen support
            mem.write_byte(H_CONFIG, config)
        else:
            config = 0x04 | 0x08 | 0x10  # Bold, italic, fixed
            mem.write_byte(H_CONFIG, config)

        # Clear flags we don't support
        flags = mem.read_word(H_FLAGS)
        if self.version >= 5:
            flags &= ~0x0008  # No graphics
            flags &= ~0x0020  # No mouse
            flags &= ~0x0080  # No sound
            flags &= ~0x0100  # No menus
        mem.write_word(H_FLAGS, flags)
