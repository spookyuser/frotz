"""Z-Machine instruction decoding.

Instruction forms (from the Z-Machine Standards Document):
- Long:     2OP, opcode in bottom 5 bits. Bits 6,5 select operand types.
- Short:    0OP or 1OP. Bits 5-4 select operand type. Bottom 4 bits = opcode.
- Variable: VAR, 0-4 operands. Bottom 5 bits = opcode.
- Extended: Prefixed by 0xBE. Next byte = opcode. Variable-style operand types.

Operand type bits: 00=large const (2 bytes), 01=small const (1 byte),
                   10=variable, 11=omitted.
"""

from __future__ import annotations

# Operand type constants
OP_LARGE = 0
OP_SMALL = 1
OP_VAR = 2
OP_OMITTED = 3

# Opcode form constants
FORM_LONG = 0
FORM_SHORT = 1
FORM_VARIABLE = 2
FORM_EXTENDED = 3

# Opcode count type
COUNT_0OP = 0
COUNT_1OP = 1
COUNT_2OP = 2
COUNT_VAR = 3
COUNT_EXT = 4

# Which 2OP opcodes store a result
STORE_2OP = {
    0x08, 0x09,             # or, and
    0x0F, 0x10,             # loadw, loadb
    0x11, 0x12, 0x13,       # get_prop, get_prop_addr, get_next_prop
    0x14, 0x15, 0x16, 0x17, 0x18,  # add, sub, mul, div, mod
}

# Which 1OP opcodes store a result
STORE_1OP = {
    0x01, 0x02, 0x03, 0x04,  # get_sibling, get_child, get_parent, get_prop_len
    0x08,                     # call_s (1OP)
    0x0E, 0x0F,              # load (and call_n has no store)
}

# Which 0OP opcodes store a result: none normally (save/restore in V4+ but handled separately)

# Which VAR opcodes store a result
STORE_VAR = {
    0x00,                    # call_s
    0x04,                    # read (V5+ only, but we'll check version)
    0x07,                    # random
    0x08,                    # push? no - push doesn't store. Actually:
    # Let me be more precise:
}

# We'll use a comprehensive lookup instead
# These are indexed by opcode number within their category

# 2OP opcodes that branch
BRANCH_2OP = {
    0x01, 0x02, 0x03,  # je, jl, jg
    0x04, 0x05,         # dec_chk, inc_chk
    0x06, 0x07,         # jin, test
    0x0A,               # test_attr
}

# 1OP opcodes that branch
BRANCH_1OP = {
    0x00,  # jz
    0x01,  # get_sibling
    0x02,  # get_child
}

# 0OP opcodes that branch
BRANCH_0OP = {
    0x05, 0x06,  # save, restore (V3 only - branch; V4+ store)
    0x0D,        # verify
    0x0F,        # piracy
}


def stores_result_2op(opcode: int, version: int) -> bool:
    """Does this 2OP opcode store a result?"""
    if opcode in (0x08, 0x09):  # or, and
        return True
    if opcode in (0x0F, 0x10):  # loadw, loadb
        return True
    if opcode in (0x11, 0x12, 0x13):  # get_prop, get_prop_addr, get_next_prop
        return True
    if opcode in (0x14, 0x15, 0x16, 0x17, 0x18):  # add, sub, mul, div, mod
        return True
    if opcode in (0x19,) and version >= 4:  # call_s (2OP)
        return True
    return False


def stores_result_1op(opcode: int, version: int) -> bool:
    """Does this 1OP opcode store a result?"""
    if opcode in (0x01, 0x02):  # get_sibling, get_child
        return True
    if opcode == 0x03:  # get_parent
        return True
    if opcode == 0x04:  # get_prop_len
        return True
    if opcode == 0x08:  # call_s (1OP version)
        return version >= 4
    if opcode == 0x0E:  # load
        return True
    return False


def stores_result_0op(opcode: int, version: int) -> bool:
    """Does this 0OP opcode store a result?"""
    if opcode in (0x05, 0x06) and version >= 4:  # save, restore in V4+
        return True
    if opcode == 0x09 and version >= 5:  # catch
        return True
    return False


def stores_result_var(opcode: int, version: int) -> bool:
    """Does this VAR opcode store a result?"""
    # call_s at VAR positions
    if opcode in (0x00, 0x19, 0x1A):  # call_s variants
        return True
    if opcode == 0x04 and version >= 5:  # read in V5+
        return True
    if opcode == 0x07:  # random
        return True
    if opcode == 0x0E:  # read_char
        return True
    if opcode == 0x17:  # scan_table
        return True
    if opcode == 0x18 and version >= 5:  # not (V5 it's in VAR)
        return True
    return False


def stores_result_ext(opcode: int, version: int) -> bool:
    """Does this EXT opcode store a result?"""
    if opcode in (0x00, 0x01):  # save, restore
        return True
    if opcode in (0x02, 0x03):  # log_shift, art_shift
        return True
    if opcode == 0x04:  # set_font
        return True
    if opcode in (0x09, 0x0A):  # save_undo, restore_undo
        return True
    if opcode == 0x0C:  # check_unicode
        return True
    return False


def branches_2op(opcode: int, version: int) -> bool:
    return opcode in BRANCH_2OP


def branches_1op(opcode: int, version: int) -> bool:
    return opcode in BRANCH_1OP


def branches_0op(opcode: int, version: int) -> bool:
    if opcode in (0x05, 0x06) and version <= 3:  # save, restore branch in V3
        return True
    if opcode == 0x0D:  # verify
        return True
    if opcode == 0x0F:  # piracy
        return True
    return False


def branches_var(opcode: int, version: int) -> bool:
    if opcode == 0x17:  # scan_table
        return True
    return False


def branches_ext(opcode: int, version: int) -> bool:
    return False
