"""Z-Machine object table operations."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import Memory
    from .text import TextEngine

# V1-V3 object entry layout
O1_PARENT = 4
O1_SIBLING = 5
O1_CHILD = 6
O1_PROPERTY_OFFSET = 7
O1_SIZE = 9

# V4+ object entry layout
O4_PARENT = 6
O4_SIBLING = 8
O4_CHILD = 10
O4_PROPERTY_OFFSET = 12
O4_SIZE = 14


class ObjectTable:
    """Manages the Z-machine object table."""

    def __init__(self, memory: Memory, version: int, objects_addr: int,
                 text_engine: TextEngine):
        self.memory = memory
        self.version = version
        self.objects_addr = objects_addr
        self.text = text_engine

    def _object_address(self, obj: int) -> int:
        """Calculate the byte address of an object entry."""
        if obj == 0:
            raise RuntimeError("Attempt to address object 0")
        if self.version <= 3:
            # 31 default properties (62 bytes) before first object
            return self.objects_addr + (obj - 1) * O1_SIZE + 62
        else:
            # 63 default properties (126 bytes) before first object
            return self.objects_addr + (obj - 1) * O4_SIZE + 126

    # --- Attributes ---

    def get_attr(self, obj: int, attr: int) -> bool:
        addr = self._object_address(obj) + attr // 8
        byte_val = self.memory.read_byte(addr)
        return bool(byte_val & (0x80 >> (attr & 7)))

    def set_attr(self, obj: int, attr: int):
        addr = self._object_address(obj) + attr // 8
        byte_val = self.memory.read_byte(addr)
        byte_val |= 0x80 >> (attr & 7)
        self.memory.write_byte(addr, byte_val)

    def clear_attr(self, obj: int, attr: int):
        addr = self._object_address(obj) + attr // 8
        byte_val = self.memory.read_byte(addr)
        byte_val &= ~(0x80 >> (attr & 7))
        self.memory.write_byte(addr, byte_val)

    # --- Tree relations ---

    def get_parent(self, obj: int) -> int:
        if obj == 0:
            return 0
        addr = self._object_address(obj)
        if self.version <= 3:
            return self.memory.read_byte(addr + O1_PARENT)
        else:
            return self.memory.read_word(addr + O4_PARENT)

    def get_sibling(self, obj: int) -> int:
        if obj == 0:
            return 0
        addr = self._object_address(obj)
        if self.version <= 3:
            return self.memory.read_byte(addr + O1_SIBLING)
        else:
            return self.memory.read_word(addr + O4_SIBLING)

    def get_child(self, obj: int) -> int:
        if obj == 0:
            return 0
        addr = self._object_address(obj)
        if self.version <= 3:
            return self.memory.read_byte(addr + O1_CHILD)
        else:
            return self.memory.read_word(addr + O4_CHILD)

    def _set_parent(self, obj: int, val: int):
        addr = self._object_address(obj)
        if self.version <= 3:
            self.memory.write_byte(addr + O1_PARENT, val)
        else:
            self.memory.write_word(addr + O4_PARENT, val)

    def _set_sibling(self, obj: int, val: int):
        addr = self._object_address(obj)
        if self.version <= 3:
            self.memory.write_byte(addr + O1_SIBLING, val)
        else:
            self.memory.write_word(addr + O4_SIBLING, val)

    def _set_child(self, obj: int, val: int):
        addr = self._object_address(obj)
        if self.version <= 3:
            self.memory.write_byte(addr + O1_CHILD, val)
        else:
            self.memory.write_word(addr + O4_CHILD, val)

    # --- Object tree manipulation ---

    def remove_obj(self, obj: int):
        """Unlink an object from its parent and siblings."""
        if obj == 0:
            return

        parent = self.get_parent(obj)
        if parent == 0:
            return

        older_sibling = self.get_sibling(obj)

        # Clear parent and sibling of the object being removed
        self._set_parent(obj, 0)
        self._set_sibling(obj, 0)

        # Get first child of parent (youngest sibling)
        younger_sibling = self.get_child(parent)

        if younger_sibling == obj:
            # Object is the first child - replace with its sibling
            self._set_child(parent, older_sibling)
        else:
            # Walk sibling chain to find this object
            current = younger_sibling
            while current != 0:
                next_sib = self.get_sibling(current)
                if next_sib == obj:
                    self._set_sibling(current, older_sibling)
                    break
                current = next_sib

    def insert_obj(self, obj: int, dest: int):
        """Insert object as first child of destination."""
        if obj == 0:
            return

        # First remove from current location
        self.remove_obj(obj)

        # Get current first child of dest
        first_child = self.get_child(dest)

        # Make obj the new first child
        self._set_parent(obj, dest)
        self._set_sibling(obj, first_child)
        self._set_child(dest, obj)

    # --- Properties ---

    def _property_table_addr(self, obj: int) -> int:
        """Get address of property table for an object."""
        addr = self._object_address(obj)
        if self.version <= 3:
            addr += O1_PROPERTY_OFFSET
        else:
            addr += O4_PROPERTY_OFFSET
        return self.memory.read_word(addr)

    def get_name(self, obj: int) -> str:
        """Get the short name of an object."""
        if obj == 0:
            return ""
        prop_addr = self._property_table_addr(obj)
        # First byte is length of name in words
        name_len = self.memory.read_byte(prop_addr)
        if name_len == 0:
            return ""
        name, _ = self.text.decode_zstring(prop_addr + 1)
        return name

    def _first_property_addr(self, obj: int) -> int:
        """Get address of first property in the property list."""
        prop_addr = self._property_table_addr(obj)
        name_len = self.memory.read_byte(prop_addr)
        return prop_addr + 1 + 2 * name_len

    def _prop_size_and_data(self, prop_addr: int) -> tuple[int, int, int]:
        """Read property at prop_addr. Returns (prop_number, data_addr, data_size)."""
        size_byte = self.memory.read_byte(prop_addr)

        if size_byte == 0:
            return 0, 0, 0  # End of property list

        if self.version <= 3:
            prop_num = size_byte & 0x1F
            data_size = (size_byte >> 5) + 1
            data_addr = prop_addr + 1
        else:
            prop_num = size_byte & 0x3F
            if size_byte & 0x80:
                # Two-byte size
                next_byte = self.memory.read_byte(prop_addr + 1)
                data_size = next_byte & 0x3F
                if data_size == 0:
                    data_size = 64  # Spec 1.0
                data_addr = prop_addr + 2
            else:
                data_size = 1 if not (size_byte & 0x40) else 2
                data_addr = prop_addr + 1

        return prop_num, data_addr, data_size

    def _next_property_addr(self, prop_addr: int) -> int:
        """Get address of next property after the one at prop_addr."""
        size_byte = self.memory.read_byte(prop_addr)

        if self.version <= 3:
            data_size = (size_byte >> 5) + 1
            return prop_addr + 1 + data_size
        else:
            if size_byte & 0x80:
                next_byte = self.memory.read_byte(prop_addr + 1)
                data_size = next_byte & 0x3F
                if data_size == 0:
                    data_size = 64
                return prop_addr + 2 + data_size
            else:
                data_size = 1 if not (size_byte & 0x40) else 2
                return prop_addr + 1 + data_size

    def get_prop(self, obj: int, prop: int) -> int:
        """Get the value of a property. Returns default value if not present."""
        if obj == 0:
            return 0

        addr = self._first_property_addr(obj)

        while True:
            prop_num, data_addr, data_size = self._prop_size_and_data(addr)
            if prop_num == 0:
                break
            if prop_num == prop:
                if data_size == 1:
                    return self.memory.read_byte(data_addr)
                else:
                    return self.memory.read_word(data_addr)
            if prop_num < prop:
                break  # Properties are in descending order
            addr = self._next_property_addr(addr)

        # Return default value
        default_addr = self.objects_addr + 2 * (prop - 1)
        return self.memory.read_word(default_addr)

    def get_prop_addr(self, obj: int, prop: int) -> int:
        """Get the byte address of a property's data. Returns 0 if not found."""
        if obj == 0:
            return 0

        addr = self._first_property_addr(obj)

        while True:
            prop_num, data_addr, data_size = self._prop_size_and_data(addr)
            if prop_num == 0:
                return 0
            if prop_num == prop:
                return data_addr
            if prop_num < prop:
                return 0
            addr = self._next_property_addr(addr)

    def get_prop_len(self, data_addr: int) -> int:
        """Get the length of a property given the address of its data."""
        if data_addr == 0:
            return 0

        # The size byte is just before the data
        if self.version <= 3:
            size_byte = self.memory.read_byte(data_addr - 1)
            return (size_byte >> 5) + 1
        else:
            size_byte = self.memory.read_byte(data_addr - 1)
            if size_byte & 0x80:
                length = size_byte & 0x3F
                return 64 if length == 0 else length
            else:
                return 2 if size_byte & 0x40 else 1

    def get_next_prop(self, obj: int, prop: int) -> int:
        """Get the number of the next property after prop. If prop=0, get first."""
        if obj == 0:
            return 0

        addr = self._first_property_addr(obj)

        if prop == 0:
            # Return first property number
            prop_num, _, _ = self._prop_size_and_data(addr)
            return prop_num

        # Find the given property, then return the next
        while True:
            prop_num, data_addr, data_size = self._prop_size_and_data(addr)
            if prop_num == 0:
                return 0
            if prop_num == prop:
                next_addr = self._next_property_addr(addr)
                next_num, _, _ = self._prop_size_and_data(next_addr)
                return next_num
            addr = self._next_property_addr(addr)

    def put_prop(self, obj: int, prop: int, val: int):
        """Set the value of a property."""
        if obj == 0:
            return

        addr = self._first_property_addr(obj)

        while True:
            prop_num, data_addr, data_size = self._prop_size_and_data(addr)
            if prop_num == 0:
                raise RuntimeError(f"Property {prop} not found on object {obj}")
            if prop_num == prop:
                if data_size == 1:
                    self.memory.write_byte(data_addr, val & 0xFF)
                else:
                    self.memory.write_word(data_addr, val)
                return
            addr = self._next_property_addr(addr)
