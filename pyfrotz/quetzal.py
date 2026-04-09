"""Z-Machine save/restore in Quetzal format (simplified)."""

from __future__ import annotations
import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .zmachine import ZMachine


def save_game(vm: ZMachine, filename: str) -> bool:
    """Save the game state to a file. Returns True on success."""
    try:
        with open(filename, "wb") as f:
            # Write a simplified save format (not full Quetzal IFF, but functional)
            # Header: "PYFZ" magic
            f.write(b"PYFZ")

            # Version
            f.write(struct.pack(">B", vm.header.version))

            # Release + serial for verification
            f.write(struct.pack(">H", vm.header.release))
            f.write(vm.header.serial)

            # PC
            f.write(struct.pack(">I", vm.pc))

            # Dynamic memory (compressed with simple RLE)
            dynamic = vm.memory.get_dynamic_state()
            original = vm.memory._original_dynamic
            # XOR compression
            diff = bytes(a ^ b for a, b in zip(dynamic, original))
            f.write(struct.pack(">I", len(diff)))
            f.write(diff)

            # Stack frames
            frames = vm.stack.frames
            f.write(struct.pack(">H", len(frames)))
            for frame in frames:
                f.write(struct.pack(">I", frame.return_pc))
                f.write(struct.pack(">B", len(frame.local_vars)))
                for lv in frame.local_vars:
                    f.write(struct.pack(">H", lv))
                f.write(struct.pack(">B", frame.arg_count))
                sv = frame.store_var if frame.store_var is not None else 0xFFFF
                f.write(struct.pack(">H", sv))
                f.write(struct.pack(">B", 1 if frame.discard_result else 0))
                f.write(struct.pack(">H", len(frame.eval_stack)))
                for val in frame.eval_stack:
                    f.write(struct.pack(">H", val))

        return True
    except (OSError, IOError):
        return False


def restore_game(vm: ZMachine, filename: str) -> bool:
    """Restore game state from a file. Returns True on success."""
    try:
        with open(filename, "rb") as f:
            magic = f.read(4)
            if magic != b"PYFZ":
                return False

            version = struct.unpack(">B", f.read(1))[0]
            if version != vm.header.version:
                return False

            release = struct.unpack(">H", f.read(2))[0]
            serial = f.read(6)
            if release != vm.header.release or serial != vm.header.serial:
                return False

            pc = struct.unpack(">I", f.read(4))[0]

            diff_len = struct.unpack(">I", f.read(4))[0]
            diff = f.read(diff_len)
            original = vm.memory._original_dynamic
            restored = bytes(a ^ b for a, b in zip(diff, original))
            vm.memory.set_dynamic_state(restored)

            # Restore header interpreter fields
            vm.header.setup_interpreter_fields(vm.memory)

            num_frames = struct.unpack(">H", f.read(2))[0]
            from .stack import RoutineFrame
            frames = []
            for _ in range(num_frames):
                return_pc = struct.unpack(">I", f.read(4))[0]
                num_locals = struct.unpack(">B", f.read(1))[0]
                local_vars = [struct.unpack(">H", f.read(2))[0] for _ in range(num_locals)]
                arg_count = struct.unpack(">B", f.read(1))[0]
                sv = struct.unpack(">H", f.read(2))[0]
                store_var = None if sv == 0xFFFF else sv
                discard = struct.unpack(">B", f.read(1))[0]
                stack_size = struct.unpack(">H", f.read(2))[0]
                eval_stack = [struct.unpack(">H", f.read(2))[0] for _ in range(stack_size)]
                frame = RoutineFrame(
                    return_pc=return_pc,
                    local_vars=local_vars,
                    eval_stack=eval_stack,
                    arg_count=arg_count,
                    store_var=store_var,
                    discard_result=bool(discard),
                )
                frames.append(frame)

            vm.stack.frames = frames
            vm.pc = pc

        return True
    except (OSError, IOError, struct.error):
        return False
