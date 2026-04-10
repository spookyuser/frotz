pyfrotz

A Python Z-Machine interpreter.

Run the interpreter with:

```bash
uv run --project /private/tmp/frotz python -m pyfrotz /private/tmp/frotz/tests/Tangle.z5
```

Run tests with:

```bash
uv run --project /private/tmp/frotz --with pytest pytest
```

## Simple programmatic example

A minimal example lives at:

- `examples/simple/play_tangle_z8.py`

It loads `tests/Tangle.z8` and shows two ways to use `pyfrotz` as a library:

1. run the game with a list of scripted commands
2. drive the game one turn at a time with `step()`

Run it with:

```bash
uv run --project /private/tmp/frotz python /private/tmp/frotz/examples/simple/play_tangle_z8.py
```

What it demonstrates:

- reading `tests/Tangle.z8`
- creating a `ZMachine`
- capturing output in memory instead of using interactive stdin/stdout
- printing a tiny programmatic play demo
