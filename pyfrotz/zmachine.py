"""Z-Machine virtual machine - the main orchestrator."""

from __future__ import annotations
import io as IO_module
import random as pyrandom

from .memory import Memory
from .header import Header
from .stack import CallStack
from .text import TextEngine
from .objects import ObjectTable
from .dictionary import Dictionary
from .screen import Screen
from .io import IO
from . import instructions as instr


def to_signed(v: int) -> int:
    """Convert unsigned 16-bit to signed."""
    return v - 0x10000 if v >= 0x8000 else v


def to_unsigned(v: int) -> int:
    """Convert signed to unsigned 16-bit."""
    return v & 0xFFFF


class ZMachine:
    """The Z-Machine virtual machine.

    For library use, supply *input_lines* and *output* to run
    non-interactively::

        import io
        buf = io.StringIO()
        vm = ZMachine(story_data, input_lines=["look", "quit"], output=buf)
        vm.run()
        print(buf.getvalue())
    """

    def __init__(self, story_data: bytes, *,
                 input_lines: list[str] | None = None,
                 output: IO_module.TextIOBase | None = None):
        self.memory = Memory(story_data)
        self.header = Header.from_memory(self.memory)

        if self.header.version not in (1, 2, 3, 4, 5, 7, 8):
            raise RuntimeError(f"Unsupported Z-machine version: {self.header.version}")

        self.memory.setup(self.header.dynamic_size)
        self.header.setup_interpreter_fields(self.memory)

        self.stack = CallStack()
        self.screen = Screen(self.header.version, output=output)
        self.io = IO(input_lines=input_lines)

        self.text = TextEngine(
            self.memory, self.header.version,
            self.header.abbreviations, self.header.alphabet,
        )
        self.objects = ObjectTable(
            self.memory, self.header.version,
            self.header.objects, self.text,
        )
        self.dictionary = Dictionary(
            self.memory, self.header.version,
            self.header.dictionary, self.text,
        )

        self.pc = self.header.start_pc
        self.finished = False

        # Current instruction operands
        self.operands: list[int] = []
        self.operand_count = 0

        # Random number generator
        self._rng = pyrandom.Random()
        self._rng_sequential = False
        self._rng_counter = 0
        self._rng_range = 0

        # Undo state
        self._undo_state: tuple | None = None

    # --- Memory access helpers ---

    def read_variable(self, var_num: int) -> int:
        """Read a variable: 0=stack pop, 1-15=local, 16-255=global."""
        if var_num == 0:
            return self.stack.pop()
        elif var_num < 16:
            return self.stack.read_local(var_num)
        else:
            addr = self.header.globals + 2 * (var_num - 16)
            return self.memory.read_word(addr)

    def write_variable(self, var_num: int, value: int):
        """Write a variable: 0=stack push, 1-15=local, 16-255=global."""
        value &= 0xFFFF
        if var_num == 0:
            self.stack.push(value)
        elif var_num < 16:
            self.stack.write_local(var_num, value)
        else:
            addr = self.header.globals + 2 * (var_num - 16)
            self.memory.write_word(addr, value)

    def read_variable_indirect(self, var_num: int) -> int:
        """Read variable for inc/dec - peek stack instead of pop."""
        if var_num == 0:
            return self.stack.peek()
        elif var_num < 16:
            return self.stack.read_local(var_num)
        else:
            addr = self.header.globals + 2 * (var_num - 16)
            return self.memory.read_word(addr)

    def write_variable_indirect(self, var_num: int, value: int):
        """Write variable for inc/dec - replace stack top instead of push."""
        value &= 0xFFFF
        if var_num == 0:
            stack = self.stack.current_frame.eval_stack
            if stack:
                stack[-1] = value
            else:
                self.stack.push(value)
        elif var_num < 16:
            self.stack.write_local(var_num, value)
        else:
            addr = self.header.globals + 2 * (var_num - 16)
            self.memory.write_word(addr, value)

    # --- Instruction fetch ---

    def fetch_byte(self) -> int:
        val = self.memory.read_byte(self.pc)
        self.pc += 1
        return val

    def fetch_word(self) -> int:
        val = self.memory.read_word(self.pc)
        self.pc += 2
        return val

    # --- Operand loading ---

    def load_operand(self, op_type: int) -> int:
        """Load a single operand based on its type."""
        if op_type == instr.OP_LARGE:
            return self.fetch_word()
        elif op_type == instr.OP_SMALL:
            return self.fetch_byte()
        elif op_type == instr.OP_VAR:
            var_num = self.fetch_byte()
            return self.read_variable(var_num)
        else:
            raise RuntimeError(f"Invalid operand type: {op_type}")

    def load_all_operands(self, specifier: int) -> list[int]:
        """Load up to 4 operands from a specifier byte."""
        operands = []
        for i in (6, 4, 2, 0):
            op_type = (specifier >> i) & 0x03
            if op_type == instr.OP_OMITTED:
                break
            operands.append(self.load_operand(op_type))
        return operands

    # --- Store and branch ---

    def store_result(self, value: int):
        """Read store variable from instruction stream and write value."""
        var_num = self.fetch_byte()
        self.write_variable(var_num, value & 0xFFFF)

    def do_branch(self, condition: bool):
        """Read branch data from instruction stream and branch if condition matches."""
        first = self.fetch_byte()
        branch_on_true = bool(first & 0x80)
        short_branch = bool(first & 0x40)

        if short_branch:
            offset = first & 0x3F
        else:
            second = self.fetch_byte()
            offset = ((first & 0x3F) << 8) | second
            # Sign extend 14-bit value
            if offset & 0x2000:
                offset -= 0x4000

        if condition == branch_on_true:
            if offset == 0:
                self.do_return(0)
            elif offset == 1:
                self.do_return(1)
            else:
                self.pc += offset - 2

    # --- Routine call/return ---

    def unpack_routine_addr(self, packed: int) -> int:
        """Convert a packed routine address to a byte address."""
        if self.header.version <= 3:
            return packed * 2
        elif self.header.version <= 5:
            return packed * 4
        elif self.header.version <= 7:
            return packed * 4 + self.header.functions_offset * 8
        else:
            return packed * 8

    def unpack_string_addr(self, packed: int) -> int:
        """Convert a packed string address to a byte address."""
        if self.header.version <= 3:
            return packed * 2
        elif self.header.version <= 5:
            return packed * 4
        elif self.header.version <= 7:
            return packed * 4 + self.header.strings_offset * 8
        else:
            return packed * 8

    def call_routine(self, packed_addr: int, args: list[int],
                     store_var: int | None, discard: bool = False):
        """Call a routine at the given packed address."""
        if packed_addr == 0:
            # Calling address 0 returns false
            if store_var is not None and not discard:
                self.write_variable(store_var, 0)
            return

        byte_addr = self.unpack_routine_addr(packed_addr)

        # Read number of local variables
        old_pc = self.pc
        self.pc = byte_addr
        num_locals = self.fetch_byte()

        if num_locals > 15:
            raise RuntimeError(f"Routine at {byte_addr:#x} has {num_locals} locals (max 15)")

        # Initialize local variables
        local_vars = []
        for i in range(num_locals):
            if self.header.version <= 4:
                # V1-V4: defaults from story file
                default = self.fetch_word()
            else:
                # V5+: locals initialize to 0
                default = 0

            if i < len(args):
                local_vars.append(args[i] & 0xFFFF)
            else:
                local_vars.append(default)

        # Push frame
        self.stack.push_frame(
            return_pc=old_pc,
            local_vars=local_vars,
            arg_count=len(args),
            store_var=store_var,
            discard_result=discard,
        )

    def do_return(self, value: int):
        """Return from the current routine."""
        frame = self.stack.pop_frame()
        self.pc = frame.return_pc

        if not frame.discard_result and frame.store_var is not None:
            self.write_variable(frame.store_var, value & 0xFFFF)

    # --- Main execution loop ---

    def run(self):
        """Main fetch-decode-execute loop."""
        while not self.finished:
            self._execute_one()

    def _execute_one(self):
        """Execute a single instruction."""
        opcode = self.fetch_byte()

        if opcode < 0x80:
            # Long form: 2OP
            t1 = instr.OP_VAR if (opcode & 0x40) else instr.OP_SMALL
            t2 = instr.OP_VAR if (opcode & 0x20) else instr.OP_SMALL
            self.operands = [self.load_operand(t1), self.load_operand(t2)]
            self.operand_count = 2
            self._dispatch_2op(opcode & 0x1F)

        elif opcode < 0xB0:
            # Short form: 1OP or 0OP
            op_type = (opcode >> 4) & 0x03
            if op_type == 3:
                # Actually a 0OP
                self.operands = []
                self.operand_count = 0
                self._dispatch_0op(opcode & 0x0F)
            else:
                self.operands = [self.load_operand(op_type)]
                self.operand_count = 1
                self._dispatch_1op(opcode & 0x0F)

        elif opcode < 0xC0:
            if opcode == 0xBE and self.header.version >= 5:
                # Extended opcode (encoded as 0OP 0x0E)
                ext_opcode = self.fetch_byte()
                spec = self.fetch_byte()
                self.operands = self.load_all_operands(spec)
                self.operand_count = len(self.operands)
                self._dispatch_ext(ext_opcode)
            else:
                # Short form: 0OP
                self.operands = []
                self.operand_count = 0
                self._dispatch_0op(opcode - 0xB0)

        else:
            # Variable form
            if opcode == 0xBE and self.header.version >= 5:
                # Extended opcode
                ext_opcode = self.fetch_byte()
                spec = self.fetch_byte()
                self.operands = self.load_all_operands(spec)
                self.operand_count = len(self.operands)
                self._dispatch_ext(ext_opcode)
            elif opcode == 0xEC or opcode == 0xFA:
                # Double VAR: up to 8 operands
                spec1 = self.fetch_byte()
                spec2 = self.fetch_byte()
                self.operands = self.load_all_operands(spec1)
                self.operands.extend(self.load_all_operands(spec2))
                self.operand_count = len(self.operands)
                idx = opcode - 0xC0
                if idx < 0x20:
                    self._dispatch_2op(idx)
                else:
                    self._dispatch_var(idx - 0x20)
            else:
                spec = self.fetch_byte()
                self.operands = self.load_all_operands(spec)
                self.operand_count = len(self.operands)
                idx = opcode - 0xC0
                if idx < 0x20:
                    # Variable-form encoding of 2OP opcode
                    self._dispatch_2op(idx)
                else:
                    # True VAR opcode
                    self._dispatch_var(idx - 0x20)

    # --- Opcode dispatch ---

    def _dispatch_0op(self, opcode: int):
        from . import opcodes
        handler = _0OP_TABLE.get(opcode)
        if handler is None:
            raise RuntimeError(f"Unimplemented 0OP opcode: {opcode:#x} at PC {self.pc:#x}")
        handler(self)

    def _dispatch_1op(self, opcode: int):
        handler = _1OP_TABLE.get(opcode)
        if handler is None:
            raise RuntimeError(f"Unimplemented 1OP opcode: {opcode:#x} at PC {self.pc:#x}")
        handler(self)

    def _dispatch_2op(self, opcode: int):
        handler = _2OP_TABLE.get(opcode)
        if handler is None:
            raise RuntimeError(f"Unimplemented 2OP opcode: {opcode:#x} at PC {self.pc:#x}")
        handler(self)

    def _dispatch_var(self, opcode: int):
        handler = _VAR_TABLE.get(opcode)
        if handler is None:
            raise RuntimeError(f"Unimplemented VAR opcode: {opcode:#x} at PC {self.pc:#x}")
        handler(self)

    def _dispatch_ext(self, opcode: int):
        handler = _EXT_TABLE.get(opcode)
        if handler is None:
            raise RuntimeError(f"Unimplemented EXT opcode: {opcode:#x} at PC {self.pc:#x}")
        handler(self)


# Opcode dispatch tables - populated by opcodes module
_0OP_TABLE: dict[int, callable] = {}
_1OP_TABLE: dict[int, callable] = {}
_2OP_TABLE: dict[int, callable] = {}
_VAR_TABLE: dict[int, callable] = {}
_EXT_TABLE: dict[int, callable] = {}


def _register_opcodes():
    """Register all opcode handlers into dispatch tables."""
    from . import opcodes as op

    # 0OP opcodes (0xB0-0xBF)
    _0OP_TABLE.update({
        0x00: op.z_rtrue,
        0x01: op.z_rfalse,
        0x02: op.z_print,
        0x03: op.z_print_ret,
        0x04: op.z_nop,
        0x05: op.z_save_v3,
        0x06: op.z_restore_v3,
        0x07: op.z_restart,
        0x08: op.z_ret_popped,
        0x09: op.z_pop_or_catch,
        0x0A: op.z_quit,
        0x0B: op.z_new_line,
        0x0C: op.z_show_status,
        0x0D: op.z_verify,
        # 0x0E: extended (handled separately)
        0x0F: op.z_piracy,
    })

    # 1OP opcodes (0x80-0x8F)
    _1OP_TABLE.update({
        0x00: op.z_jz,
        0x01: op.z_get_sibling,
        0x02: op.z_get_child,
        0x03: op.z_get_parent,
        0x04: op.z_get_prop_len,
        0x05: op.z_inc,
        0x06: op.z_dec,
        0x07: op.z_print_addr,
        0x08: op.z_call_s,      # 1OP form
        0x09: op.z_remove_obj,
        0x0A: op.z_print_obj,
        0x0B: op.z_ret,
        0x0C: op.z_jump,
        0x0D: op.z_print_paddr,
        0x0E: op.z_load,
        0x0F: op.z_not_or_call_n,
    })

    # 2OP opcodes - these are in the first 0x20 entries of var_opcodes in C
    # In our design we dispatch them separately
    _2OP_TABLE.update({
        0x01: op.z_je,
        0x02: op.z_jl,
        0x03: op.z_jg,
        0x04: op.z_dec_chk,
        0x05: op.z_inc_chk,
        0x06: op.z_jin,
        0x07: op.z_test,
        0x08: op.z_or,
        0x09: op.z_and,
        0x0A: op.z_test_attr,
        0x0B: op.z_set_attr,
        0x0C: op.z_clear_attr,
        0x0D: op.z_store,
        0x0E: op.z_insert_obj,
        0x0F: op.z_loadw,
        0x10: op.z_loadb,
        0x11: op.z_get_prop,
        0x12: op.z_get_prop_addr,
        0x13: op.z_get_next_prop,
        0x14: op.z_add,
        0x15: op.z_sub,
        0x16: op.z_mul,
        0x17: op.z_div,
        0x18: op.z_mod,
        0x19: op.z_call_s,      # 2OP form (V4+)
        0x1A: op.z_call_n,      # 2OP form (V5+)
        0x1B: op.z_set_colour,
        0x1C: op.z_throw,
    })

    # VAR opcodes (0xE0-0xFF, indexed as 0x00-0x3F)
    _VAR_TABLE.update({
        0x00: op.z_call_s,       # VAR form
        0x01: op.z_storew,
        0x02: op.z_storeb,
        0x03: op.z_put_prop,
        0x04: op.z_read,
        0x05: op.z_print_char,
        0x06: op.z_print_num,
        0x07: op.z_random,
        0x08: op.z_push,
        0x09: op.z_pull,
        0x0A: op.z_split_window,
        0x0B: op.z_set_window,
        0x0C: op.z_call_s,      # call_vs2
        0x0D: op.z_erase_window,
        0x0E: op.z_erase_line,
        0x0F: op.z_set_cursor,
        0x10: op.z_get_cursor,
        0x11: op.z_set_text_style,
        0x12: op.z_buffer_mode,
        0x13: op.z_output_stream,
        0x14: op.z_input_stream,
        0x15: op.z_sound_effect,
        0x16: op.z_read_char,
        0x17: op.z_scan_table,
        0x18: op.z_not,
        0x19: op.z_call_n,      # call_vn
        0x1A: op.z_call_n,      # call_vn2
        0x1B: op.z_tokenise,
        0x1C: op.z_encode_text,
        0x1D: op.z_copy_table,
        0x1E: op.z_print_table,
        0x1F: op.z_check_arg_count,
    })

    # EXT opcodes (V5+)
    _EXT_TABLE.update({
        0x00: op.z_save,
        0x01: op.z_restore,
        0x02: op.z_log_shift,
        0x03: op.z_art_shift,
        0x04: op.z_set_font,
        0x09: op.z_save_undo,
        0x0A: op.z_restore_undo,
        0x0B: op.z_print_unicode,
        0x0C: op.z_check_unicode,
    })


_register_opcodes()
