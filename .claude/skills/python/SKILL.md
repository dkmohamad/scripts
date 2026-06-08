---
name: python
description: Python coding conventions for this project
---

## Conventions

Apply these rules when writing or modifying Python code in this project.
Pylance (strict) and ruff enforce most of these automatically — these
guidelines fill in what the tools cannot catch.

### Type annotations

- Annotate **all** function signatures: parameters and return types.
- Use built-in generics (`list[str]`, `dict[str, int]`) — never
  `typing.List` / `typing.Dict`.
- Use `X | None` — never `Optional[X]`.
- Module-level constants do not need annotations when the type is
  obvious from the value.

### Imports

- One import per line (except multiple names from the same module).
- Group: stdlib → third-party → local (`recorder.*`), separated by
  blank lines. Sort alphabetically within each group (ruff `I` rule).
- Prefer `from x import y` over bare `import x` for specific names.
- Avoid wildcard imports (`from x import *`).
- Lazy imports inside functions are fine when the module is heavy or
  only needed conditionally (this is an established pattern in the
  codebase, e.g. `from recorder.transcribe import ...` inside
  `cmd_stop`).

### Naming

- Modules/packages: `lower_with_under`
- Classes: `CapWords`
- Functions, methods, variables: `lower_with_under`
- Constants: `CAPS_WITH_UNDER`
- Private/internal names: single leading underscore (`_helper`)
- Avoid single-character names except loop counters (`i`, `n`) and
  well-known conventions (`f` for file handles).

### Docstrings

- Every **module** gets a docstring (one-line or paragraph).
- Every **public function/class** gets a docstring.
- Private helpers (`_foo`) need a docstring only when the purpose is
  not obvious from the name and signature.
- Use triple double-quotes (`"""`). One-liners stay on a single line.
  Multi-line docstrings: summary line, blank line, then body.
- For functions with non-trivial args, document them:
  ```
  Args:
      name: Description.
  Returns:
      Description.
  Raises:
      ValueError: When ...
  ```
- Do **not** add docstrings to code you are not otherwise modifying.

### Logging

- Use the shared logger from `recorder.lib`:
  ```python
  from recorder.lib import log
  ```
- **Never** use `print()` for pipeline output. Use `log.info()`,
  `log.warning()`, or `log.error()`.
- **Never** create wrapper functions around the logger (no `log_info`,
  `log_warn`, etc.) — call `log.info()` / `log.warning()` /
  `log.error()` directly.
- The logger has a `StreamHandler` on stdout (plain `%(message)s`
  format) configured in `lib.py`. Pipeline entry points (`capture.py`)
  attach a `FileHandler` for timestamped file logging.

### Error handling

- Never use bare `except:`. Catch specific exceptions.
- Keep `try` blocks tight — only wrap the code that can raise.
- Never use `assert` for validation; use explicit conditionals.
- Use `sys.exit(1)` for fatal errors in CLI entry points; raise
  exceptions in library code.

### Functions

- Never use mutable default arguments. Use `None` as a sentinel:
  ```python
  def f(items: list[str] | None = None) -> None:
      items = items or []
  ```
- Keep functions short and focused. Extract helpers when a function
  grows beyond ~40 lines or handles multiple concerns.

### Style

PEP 8 compliance is enforced by ruff and Pylance — do not duplicate
those rules here. Just write PEP 8 code and the linters will catch
the rest. Line length is 88 characters (configured in `pyproject.toml`).
