"""Z-Machine memory model."""

from __future__ import annotations


class Memory:
    """Manages the Z-machine memory map: dynamic, static, and high memory."""

    def __init__(self, data: bytes):
        self._data = bytearray(data)
        self._original_dynamic: bytes | None = None
        self._static_base = 0

    def setup(self, static_base: int):
        """Store the static memory boundary and save original dynamic memory."""
        self._static_base = static_base
        self._original_dynamic = bytes(self._data[:static_base])

    @property
    def size(self) -> int:
        return len(self._data)

    def read_byte(self, addr: int) -> int:
        return self._data[addr]

    def read_word(self, addr: int) -> int:
        return (self._data[addr] << 8) | self._data[addr + 1]

    def write_byte(self, addr: int, val: int):
        self._data[addr] = val & 0xFF

    def write_word(self, addr: int, val: int):
        val &= 0xFFFF
        self._data[addr] = (val >> 8) & 0xFF
        self._data[addr + 1] = val & 0xFF

    def slice(self, addr: int, length: int) -> bytes:
        return bytes(self._data[addr : addr + length])

    def restart(self):
        """Restore dynamic memory to its original state."""
        if self._original_dynamic is not None:
            self._data[: self._static_base] = self._original_dynamic

    def get_dynamic_state(self) -> bytes:
        """Return current dynamic memory for save/undo."""
        return bytes(self._data[: self._static_base])

    def set_dynamic_state(self, data: bytes):
        """Restore dynamic memory from save/undo."""
        self._data[: len(data)] = data

    @classmethod
    def from_file(cls, path: str) -> Memory:
        with open(path, "rb") as f:
            return cls(f.read())
