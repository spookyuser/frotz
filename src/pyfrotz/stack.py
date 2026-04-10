"""Z-Machine call stack and routine frames."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RoutineFrame:
    """A single call stack frame."""
    return_pc: int
    local_vars: list[int] = field(default_factory=list)
    eval_stack: list[int] = field(default_factory=list)
    arg_count: int = 0
    store_var: int | None = None  # Variable to store return value (None = discard)
    discard_result: bool = False


class CallStack:
    """Manages the Z-machine call stack."""

    def __init__(self):
        self.frames: list[RoutineFrame] = []
        # Create initial dummy frame
        self.frames.append(RoutineFrame(return_pc=0))

    @property
    def current_frame(self) -> RoutineFrame:
        return self.frames[-1]

    def push_frame(self, return_pc: int, local_vars: list[int],
                   arg_count: int, store_var: int | None,
                   discard_result: bool = False):
        frame = RoutineFrame(
            return_pc=return_pc,
            local_vars=local_vars,
            arg_count=arg_count,
            store_var=store_var,
            discard_result=discard_result,
        )
        self.frames.append(frame)

    def pop_frame(self) -> RoutineFrame:
        if len(self.frames) <= 1:
            raise RuntimeError("Stack underflow: cannot pop initial frame")
        return self.frames.pop()

    def push(self, value: int):
        """Push a value onto the current frame's evaluation stack."""
        self.current_frame.eval_stack.append(value & 0xFFFF)

    def pop(self) -> int:
        """Pop a value from the current frame's evaluation stack."""
        stack = self.current_frame.eval_stack
        if not stack:
            raise RuntimeError("Stack underflow: evaluation stack is empty")
        return stack.pop()

    def peek(self) -> int:
        """Peek at the top of the current frame's evaluation stack."""
        stack = self.current_frame.eval_stack
        if not stack:
            raise RuntimeError("Stack underflow: evaluation stack is empty")
        return stack[-1]

    def read_local(self, idx: int) -> int:
        """Read local variable (1-indexed)."""
        return self.current_frame.local_vars[idx - 1]

    def write_local(self, idx: int, val: int):
        """Write local variable (1-indexed)."""
        self.current_frame.local_vars[idx - 1] = val & 0xFFFF

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def get_state(self) -> list[RoutineFrame]:
        """Return copy of frames for save/undo."""
        import copy
        return copy.deepcopy(self.frames)

    def set_state(self, frames: list[RoutineFrame]):
        """Restore frames from save/undo."""
        import copy
        self.frames = copy.deepcopy(frames)
