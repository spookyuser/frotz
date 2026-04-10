"""Z-Machine opcode implementations.

Each opcode handler takes a ZMachine instance.
Operands are in vm.operands, count in vm.operand_count.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
import sys
import os

if TYPE_CHECKING:
    from .zmachine import ZMachine


def to_signed(v: int) -> int:
    return v - 0x10000 if v >= 0x8000 else v


def to_unsigned(v: int) -> int:
    return v & 0xFFFF


# ============================================================
# 0OP opcodes
# ============================================================

def z_rtrue(vm: ZMachine):
    vm.do_return(1)


def z_rfalse(vm: ZMachine):
    vm.do_return(0)


def z_print(vm: ZMachine):
    """Print embedded string at PC."""
    text, new_pc = vm.text.decode_at_pc(vm.pc)
    vm.pc = new_pc
    vm.screen.print_str(text)


def z_print_ret(vm: ZMachine):
    """Print embedded string, newline, return true."""
    text, new_pc = vm.text.decode_at_pc(vm.pc)
    vm.pc = new_pc
    vm.screen.print_str(text)
    vm.screen.new_line()
    vm.do_return(1)


def z_nop(vm: ZMachine):
    pass


def z_save_v3(vm: ZMachine):
    """Save (V3: branch; V4+: handled by EXT)."""
    if vm.header.version <= 3:
        # Prompt for filename and save
        vm.screen.flush()
        vm.screen.print_str("[Save not supported in V3 mode]\n")
        vm.do_branch(False)
    else:
        # V4: store result
        vm.store_result(0)


def z_restore_v3(vm: ZMachine):
    """Restore (V3: branch; V4+: handled by EXT)."""
    if vm.header.version <= 3:
        vm.screen.flush()
        vm.screen.print_str("[Restore not supported in V3 mode]\n")
        vm.do_branch(False)
    else:
        vm.store_result(0)


def z_restart(vm: ZMachine):
    """Restart the game."""
    vm.memory.restart()
    vm.header = type(vm.header).from_memory(vm.memory)
    vm.header.setup_interpreter_fields(vm.memory)
    vm.stack = type(vm.stack)()
    vm.pc = vm.header.start_pc
    vm.screen.flush()


def z_ret_popped(vm: ZMachine):
    """Return value popped from stack."""
    value = vm.stack.pop()
    vm.do_return(value)


def z_pop_or_catch(vm: ZMachine):
    """V3: pop (discard top of stack). V5+: catch (store frame count)."""
    if vm.header.version >= 5:
        vm.store_result(vm.stack.frame_count)
    else:
        vm.stack.pop()


def z_quit(vm: ZMachine):
    vm.screen.flush()
    vm.finished = True


def z_new_line(vm: ZMachine):
    vm.screen.new_line()


def z_show_status(vm: ZMachine):
    """Display V3 status line."""
    if vm.header.version > 3:
        return

    # Global 0 = object number of current location
    loc_obj = vm.memory.read_word(vm.header.globals)
    location = vm.objects.get_name(loc_obj) if loc_obj else ""

    # Check if time game or score game
    if vm.header.config & 0x02:  # Time game
        hours = to_signed(vm.memory.read_word(vm.header.globals + 2))
        mins = to_signed(vm.memory.read_word(vm.header.globals + 4))
        right = f"Time: {hours:02d}:{mins:02d}"
    else:
        score = to_signed(vm.memory.read_word(vm.header.globals + 2))
        moves = to_signed(vm.memory.read_word(vm.header.globals + 4))
        right = f"Score: {score}  Moves: {moves}"

    vm.screen.show_status(location, right)


def z_verify(vm: ZMachine):
    """Verify game checksum."""
    # Calculate checksum of file from byte 0x40 onwards
    checksum = 0
    for i in range(0x40, vm.memory.size):
        checksum = (checksum + vm.memory.read_byte(i)) & 0xFFFF
    vm.do_branch(checksum == vm.header.checksum)


def z_piracy(vm: ZMachine):
    """Branch always (piracy check - always passes)."""
    vm.do_branch(True)


# ============================================================
# 1OP opcodes
# ============================================================

def z_jz(vm: ZMachine):
    """Branch if value is zero."""
    vm.do_branch(vm.operands[0] == 0)


def z_get_sibling(vm: ZMachine):
    """Get sibling of object, store and branch if non-zero."""
    sibling = vm.objects.get_sibling(vm.operands[0])
    vm.store_result(sibling)
    vm.do_branch(sibling != 0)


def z_get_child(vm: ZMachine):
    """Get first child of object, store and branch if non-zero."""
    child = vm.objects.get_child(vm.operands[0])
    vm.store_result(child)
    vm.do_branch(child != 0)


def z_get_parent(vm: ZMachine):
    """Get parent of object."""
    vm.store_result(vm.objects.get_parent(vm.operands[0]))


def z_get_prop_len(vm: ZMachine):
    """Get length of property data at given address."""
    vm.store_result(vm.objects.get_prop_len(vm.operands[0]))


def z_inc(vm: ZMachine):
    """Increment variable (indirect reference)."""
    var = vm.operands[0]
    value = to_unsigned(to_signed(vm.read_variable_indirect(var)) + 1)
    vm.write_variable_indirect(var, value)


def z_dec(vm: ZMachine):
    """Decrement variable (indirect reference)."""
    var = vm.operands[0]
    value = to_unsigned(to_signed(vm.read_variable_indirect(var)) - 1)
    vm.write_variable_indirect(var, value)


def z_print_addr(vm: ZMachine):
    """Print string at byte address."""
    text, _ = vm.text.decode_zstring(vm.operands[0])
    vm.screen.print_str(text)


def z_call_s(vm: ZMachine):
    """Call routine and store result. Works for 1OP, 2OP, and VAR forms."""
    store_var = vm.fetch_byte()
    routine = vm.operands[0]
    args = vm.operands[1:]
    vm.call_routine(routine, args, store_var)


def z_remove_obj(vm: ZMachine):
    """Remove object from its parent."""
    vm.objects.remove_obj(vm.operands[0])


def z_print_obj(vm: ZMachine):
    """Print short name of object."""
    name = vm.objects.get_name(vm.operands[0])
    vm.screen.print_str(name)


def z_ret(vm: ZMachine):
    """Return given value from current routine."""
    vm.do_return(vm.operands[0])


def z_jump(vm: ZMachine):
    """Unconditional jump (signed offset from current PC)."""
    offset = to_signed(vm.operands[0])
    vm.pc += offset - 2


def z_print_paddr(vm: ZMachine):
    """Print string at packed address."""
    byte_addr = vm.unpack_string_addr(vm.operands[0])
    text, _ = vm.text.decode_zstring(byte_addr)
    vm.screen.print_str(text)


def z_load(vm: ZMachine):
    """Load value of a variable (indirect)."""
    var = vm.operands[0]
    if var == 0:
        value = vm.stack.peek()
    elif var < 16:
        value = vm.stack.read_local(var)
    else:
        addr = vm.header.globals + 2 * (var - 16)
        value = vm.memory.read_word(addr)
    vm.store_result(value)


def z_not_or_call_n(vm: ZMachine):
    """V1-V4: bitwise NOT. V5+: call_n (1OP form)."""
    if vm.header.version <= 4:
        vm.store_result(~vm.operands[0] & 0xFFFF)
    else:
        # call_n: call and discard result
        routine = vm.operands[0]
        args = vm.operands[1:]
        vm.call_routine(routine, args, store_var=None, discard=True)


# ============================================================
# 2OP opcodes
# ============================================================

def z_je(vm: ZMachine):
    """Branch if first operand equals any subsequent operand."""
    a = vm.operands[0]
    result = any(a == vm.operands[i] for i in range(1, vm.operand_count))
    vm.do_branch(result)


def z_jl(vm: ZMachine):
    """Branch if signed a < signed b."""
    vm.do_branch(to_signed(vm.operands[0]) < to_signed(vm.operands[1]))


def z_jg(vm: ZMachine):
    """Branch if signed a > signed b."""
    vm.do_branch(to_signed(vm.operands[0]) > to_signed(vm.operands[1]))


def z_dec_chk(vm: ZMachine):
    """Decrement variable and branch if now less than value."""
    var = vm.operands[0]
    value = to_unsigned(to_signed(vm.read_variable_indirect(var)) - 1)
    vm.write_variable_indirect(var, value)
    vm.do_branch(to_signed(value) < to_signed(vm.operands[1]))


def z_inc_chk(vm: ZMachine):
    """Increment variable and branch if now greater than value."""
    var = vm.operands[0]
    value = to_unsigned(to_signed(vm.read_variable_indirect(var)) + 1)
    vm.write_variable_indirect(var, value)
    vm.do_branch(to_signed(value) > to_signed(vm.operands[1]))


def z_jin(vm: ZMachine):
    """Branch if object A is inside object B."""
    parent = vm.objects.get_parent(vm.operands[0]) if vm.operands[0] != 0 else 0
    vm.do_branch(parent == vm.operands[1])


def z_test(vm: ZMachine):
    """Branch if all flags in bitmap are set."""
    vm.do_branch((vm.operands[0] & vm.operands[1]) == vm.operands[1])


def z_or(vm: ZMachine):
    vm.store_result(vm.operands[0] | vm.operands[1])


def z_and(vm: ZMachine):
    vm.store_result(vm.operands[0] & vm.operands[1])


def z_test_attr(vm: ZMachine):
    """Branch if object has attribute."""
    result = vm.objects.get_attr(vm.operands[0], vm.operands[1]) if vm.operands[0] != 0 else False
    vm.do_branch(result)


def z_set_attr(vm: ZMachine):
    if vm.operands[0] != 0:
        vm.objects.set_attr(vm.operands[0], vm.operands[1])


def z_clear_attr(vm: ZMachine):
    if vm.operands[0] != 0:
        vm.objects.clear_attr(vm.operands[0], vm.operands[1])


def z_store(vm: ZMachine):
    """Store value in variable (indirect)."""
    var = vm.operands[0]
    value = vm.operands[1]
    # Note: z_store uses indirect write (replace top of stack, not push)
    vm.write_variable_indirect(var, value)


def z_insert_obj(vm: ZMachine):
    vm.objects.insert_obj(vm.operands[0], vm.operands[1])


def z_loadw(vm: ZMachine):
    """Load word from array."""
    addr = (vm.operands[0] + 2 * vm.operands[1]) & 0xFFFF
    vm.store_result(vm.memory.read_word(addr))


def z_loadb(vm: ZMachine):
    """Load byte from array."""
    addr = (vm.operands[0] + vm.operands[1]) & 0xFFFF
    vm.store_result(vm.memory.read_byte(addr))


def z_get_prop(vm: ZMachine):
    vm.store_result(vm.objects.get_prop(vm.operands[0], vm.operands[1]))


def z_get_prop_addr(vm: ZMachine):
    vm.store_result(vm.objects.get_prop_addr(vm.operands[0], vm.operands[1]))


def z_get_next_prop(vm: ZMachine):
    vm.store_result(vm.objects.get_next_prop(vm.operands[0], vm.operands[1]))


def z_add(vm: ZMachine):
    vm.store_result(to_unsigned(to_signed(vm.operands[0]) + to_signed(vm.operands[1])))


def z_sub(vm: ZMachine):
    vm.store_result(to_unsigned(to_signed(vm.operands[0]) - to_signed(vm.operands[1])))


def z_mul(vm: ZMachine):
    vm.store_result(to_unsigned(to_signed(vm.operands[0]) * to_signed(vm.operands[1])))


def z_div(vm: ZMachine):
    a = to_signed(vm.operands[0])
    b = to_signed(vm.operands[1])
    if b == 0:
        raise RuntimeError("Division by zero")
    # Z-machine division truncates towards zero
    result = int(a / b)  # Python 3 true division then truncate
    vm.store_result(to_unsigned(result))


def z_mod(vm: ZMachine):
    a = to_signed(vm.operands[0])
    b = to_signed(vm.operands[1])
    if b == 0:
        raise RuntimeError("Division by zero (mod)")
    # Z-machine mod: result has same sign as dividend
    result = a - int(a / b) * b
    vm.store_result(to_unsigned(result))


def z_call_n(vm: ZMachine):
    """Call routine and discard result."""
    routine = vm.operands[0]
    args = vm.operands[1:]
    vm.call_routine(routine, args, store_var=None, discard=True)


def z_set_colour(vm: ZMachine):
    """Set text colour (no-op in dumb mode)."""
    pass


def z_throw(vm: ZMachine):
    """Throw: unwind stack to given frame and return value."""
    value = vm.operands[0]
    frame_count = vm.operands[1]
    while vm.stack.frame_count > frame_count:
        vm.stack.pop_frame()
    vm.do_return(value)


# ============================================================
# VAR opcodes
# ============================================================

def z_storew(vm: ZMachine):
    """Store word in array."""
    addr = (vm.operands[0] + 2 * vm.operands[1]) & 0xFFFF
    vm.memory.write_word(addr, vm.operands[2])


def z_storeb(vm: ZMachine):
    """Store byte in array."""
    addr = (vm.operands[0] + vm.operands[1]) & 0xFFFF
    vm.memory.write_byte(addr, vm.operands[2])


def z_put_prop(vm: ZMachine):
    vm.objects.put_prop(vm.operands[0], vm.operands[1], vm.operands[2])


def z_read(vm: ZMachine):
    """Read a line of input and tokenize."""
    text_addr = vm.operands[0]
    parse_addr = vm.operands[1] if vm.operand_count > 1 else 0

    # Show status line for V1-V3
    if vm.header.version <= 3:
        z_show_status(vm)

    # Flush output
    vm.screen.flush()

    # Read input
    line = vm.io.read_line()

    # Convert to lowercase
    line = line.lower()

    # Store in text buffer
    if vm.header.version <= 4:
        # V1-V4: byte 0 = max length, text starts at byte 1, null-terminated
        max_len = vm.memory.read_byte(text_addr)
        line = line[:max_len]
        for i, c in enumerate(line):
            zscii = vm.text.char_to_zscii(c)
            vm.memory.write_byte(text_addr + 1 + i, zscii)
        vm.memory.write_byte(text_addr + 1 + len(line), 0)
    else:
        # V5+: byte 0 = max length, byte 1 = actual length, text starts at byte 2
        max_len = vm.memory.read_byte(text_addr)
        line = line[:max_len]
        vm.memory.write_byte(text_addr + 1, len(line))
        for i, c in enumerate(line):
            zscii = vm.text.char_to_zscii(c)
            vm.memory.write_byte(text_addr + 2 + i, zscii)

    # Tokenize if parse buffer provided
    if parse_addr != 0:
        vm.dictionary.tokenize(text_addr, parse_addr)

    # V5+ stores the terminating key
    if vm.header.version >= 5:
        vm.store_result(13)  # Return key


def z_print_char(vm: ZMachine):
    c = vm.text.zscii_to_char(vm.operands[0])
    if c:
        vm.screen.print_str(c)


def z_print_num(vm: ZMachine):
    vm.screen.print_str(str(to_signed(vm.operands[0])))


def z_random(vm: ZMachine):
    """Generate random number or seed."""
    r = to_signed(vm.operands[0])
    if r <= 0:
        # Seed the RNG
        if r == 0:
            vm._rng = __import__("random").Random()
            vm._rng_sequential = False
        else:
            vm._rng = __import__("random").Random(-r)
            vm._rng_sequential = (-r <= 1000)
            if vm._rng_sequential:
                vm._rng_counter = 0
                vm._rng_range = -r
        vm.store_result(0)
    else:
        if vm._rng_sequential:
            vm._rng_counter = (vm._rng_counter % vm._rng_range) + 1
            vm.store_result(vm._rng_counter)
        else:
            vm.store_result(vm._rng.randint(1, r))


def z_push(vm: ZMachine):
    vm.stack.push(vm.operands[0])


def z_pull(vm: ZMachine):
    """Pull value from stack into variable."""
    value = vm.stack.pop()
    var = vm.operands[0]
    vm.write_variable_indirect(var, value)


def z_split_window(vm: ZMachine):
    vm.screen.split_window(vm.operands[0])


def z_set_window(vm: ZMachine):
    vm.screen.set_window(vm.operands[0])


def z_erase_window(vm: ZMachine):
    vm.screen.erase_window(to_signed(vm.operands[0]))


def z_erase_line(vm: ZMachine):
    pass  # No-op in dumb mode


def z_set_cursor(vm: ZMachine):
    if vm.operand_count >= 2:
        vm.screen.set_cursor(vm.operands[0], vm.operands[1])


def z_get_cursor(vm: ZMachine):
    """Store cursor position in table. Stub: writes 1,1."""
    addr = vm.operands[0]
    vm.memory.write_word(addr, 1)
    vm.memory.write_word(addr + 2, 1)


def z_set_text_style(vm: ZMachine):
    vm.screen.set_text_style(vm.operands[0])


def z_buffer_mode(vm: ZMachine):
    vm.screen.buffer_mode(vm.operands[0])


def z_output_stream(vm: ZMachine):
    stream = to_signed(vm.operands[0])
    table_addr = vm.operands[1] if vm.operand_count > 1 else 0
    vm.screen.output_stream(stream, table_addr, vm.memory)


def z_input_stream(vm: ZMachine):
    vm.screen.input_stream(vm.operands[0])


def z_sound_effect(vm: ZMachine):
    pass  # No sound support


def z_read_char(vm: ZMachine):
    """Read a single character."""
    vm.screen.flush()
    key = vm.io.read_char()
    vm.store_result(key)


def z_scan_table(vm: ZMachine):
    """Scan a table for a value."""
    x = vm.operands[0]
    table = vm.operands[1]
    length = vm.operands[2]
    form = vm.operands[3] if vm.operand_count > 3 else 0x82

    field_size = form & 0x7F
    is_word = bool(form & 0x80)

    addr = table
    for _ in range(length):
        if is_word:
            val = vm.memory.read_word(addr)
        else:
            val = vm.memory.read_byte(addr)

        if val == x:
            vm.store_result(addr)
            vm.do_branch(True)
            return

        addr += field_size

    vm.store_result(0)
    vm.do_branch(False)


def z_not(vm: ZMachine):
    """Bitwise NOT."""
    vm.store_result(~vm.operands[0] & 0xFFFF)


def z_tokenise(vm: ZMachine):
    """Tokenize a text buffer."""
    text_addr = vm.operands[0]
    parse_addr = vm.operands[1]
    dict_addr = vm.operands[2] if vm.operand_count > 2 else 0
    flag = bool(vm.operands[3]) if vm.operand_count > 3 else False
    vm.dictionary.tokenize(text_addr, parse_addr, dict_addr, flag)


def z_encode_text(vm: ZMachine):
    """Encode text for dictionary lookup."""
    text_addr = vm.operands[0]
    length = vm.operands[1]
    offset = vm.operands[2]
    dest_addr = vm.operands[3]

    # Read the text
    text = ""
    for i in range(length):
        c = vm.memory.read_byte(text_addr + offset + i)
        text += vm.text.zscii_to_char(c)

    # Encode
    encoded = vm.text.encode_text(text)

    # Write to destination
    for i, word in enumerate(encoded):
        vm.memory.write_word(dest_addr + 2 * i, word)


def z_copy_table(vm: ZMachine):
    """Copy or zero a table."""
    first = vm.operands[0]
    second = vm.operands[1]
    size = to_signed(vm.operands[2])

    if second == 0:
        # Zero the table
        for i in range(abs(size)):
            vm.memory.write_byte(first + i, 0)
    elif size > 0:
        # Copy forward (may need to handle overlap)
        if first > second:
            for i in range(size):
                vm.memory.write_byte(second + i, vm.memory.read_byte(first + i))
        else:
            for i in range(size - 1, -1, -1):
                vm.memory.write_byte(second + i, vm.memory.read_byte(first + i))
    else:
        # Negative size: copy forward always (no overlap protection)
        for i in range(-size):
            vm.memory.write_byte(second + i, vm.memory.read_byte(first + i))


def z_print_table(vm: ZMachine):
    """Print a rectangular table."""
    addr = vm.operands[0]
    width = vm.operands[1]
    height = vm.operands[2] if vm.operand_count > 2 else 1
    skip = vm.operands[3] if vm.operand_count > 3 else 0

    for row in range(height):
        for col in range(width):
            c = vm.memory.read_byte(addr)
            ch = vm.text.zscii_to_char(c)
            if ch:
                vm.screen.print_str(ch)
            addr += 1
        if row < height - 1:
            vm.screen.new_line()
            addr += skip


def z_check_arg_count(vm: ZMachine):
    """Branch if argument number was provided."""
    arg_num = vm.operands[0]
    vm.do_branch(arg_num <= vm.stack.current_frame.arg_count)


# ============================================================
# EXT opcodes (V5+)
# ============================================================

def z_save(vm: ZMachine):
    """Save game state (EXT form, V5+)."""
    vm.screen.flush()
    try:
        vm.screen.print_str("Save filename: ")
        vm.screen.flush()
        filename = vm.io.read_line()
        if not filename:
            filename = "save.pyfz"
        from .quetzal import save_game
        success = save_game(vm, filename)
        vm.store_result(1 if success else 0)
    except Exception:
        vm.store_result(0)


def z_restore(vm: ZMachine):
    """Restore game state (EXT form, V5+)."""
    vm.screen.flush()
    try:
        vm.screen.print_str("Restore filename: ")
        vm.screen.flush()
        filename = vm.io.read_line()
        if not filename:
            filename = "save.pyfz"
        from .quetzal import restore_game
        success = restore_game(vm, filename)
        if success:
            # After restore, the store_result is for the *restored* instruction
            vm.store_result(2)  # 2 = restored successfully
        else:
            vm.store_result(0)
    except Exception:
        vm.store_result(0)


def z_log_shift(vm: ZMachine):
    """Logical shift."""
    value = vm.operands[0]
    places = to_signed(vm.operands[1])
    if places > 0:
        result = (value << places) & 0xFFFF
    elif places < 0:
        result = value >> (-places)
    else:
        result = value
    vm.store_result(result)


def z_art_shift(vm: ZMachine):
    """Arithmetic shift (preserves sign)."""
    value = to_signed(vm.operands[0])
    places = to_signed(vm.operands[1])
    if places > 0:
        result = (value << places) & 0xFFFF
    elif places < 0:
        result = to_unsigned(value >> (-places))
    else:
        result = to_unsigned(value)
    vm.store_result(result)


def z_set_font(vm: ZMachine):
    """Set font and return previous font."""
    result = vm.screen.set_font(vm.operands[0])
    vm.store_result(result)


def z_save_undo(vm: ZMachine):
    """Save undo state."""
    import copy
    vm._undo_state = (
        vm.memory.get_dynamic_state(),
        copy.deepcopy(vm.stack.frames),
        vm.pc,
    )
    vm.store_result(1)  # Success


def z_restore_undo(vm: ZMachine):
    """Restore undo state."""
    if vm._undo_state is None:
        vm.store_result(0)
        return

    dynamic_mem, frames, pc = vm._undo_state
    vm.memory.set_dynamic_state(dynamic_mem)
    vm.header.setup_interpreter_fields(vm.memory)
    import copy
    vm.stack.frames = copy.deepcopy(frames)
    vm.pc = pc
    vm.store_result(2)  # Restored


def z_print_unicode(vm: ZMachine):
    """Print a Unicode character."""
    code = vm.operands[0]
    try:
        vm.screen.print_str(chr(code))
    except (ValueError, OverflowError):
        vm.screen.print_str("?")


def z_check_unicode(vm: ZMachine):
    """Check if a Unicode character can be printed/read."""
    c = vm.operands[0]
    if 0x20 <= c <= 0x7E:
        vm.store_result(3)  # Can print and read
    elif c == 0xA0:
        vm.store_result(1)  # Can print
    elif 0xA1 <= c <= 0xFF:
        vm.store_result(3)
    else:
        vm.store_result(0)
