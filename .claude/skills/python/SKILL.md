---
name: python
description: Python coding conventions for this project
---

## Conventions

Apply these rules when writing or modifying Python code in this project.

### Logging

- Use the shared logger from `recorder.lib`:
  ```python
  from recorder.lib import log
  ```
- **Never** use `print()` for pipeline output. Use `log.info()`, `log.warning()`,
  or `log.error()` instead.
- **Never** create wrapper functions around the logger (no `log_info`, `log_warn`,
  etc.) — call `log.info()` / `log.warning()` / `log.error()` directly.
- The logger has a `StreamHandler` on stdout (plain `%(message)s` format) configured
  in `lib.py`. Pipeline entry points (`capture.py`) attach a `FileHandler` to write
  timestamped logs to `session_dir / "capture.log"`.

### Style

- Line length: 88 characters max.
- Imports: group stdlib, then third-party, then local (`recorder.*`), separated by
  blank lines. Sort alphabetically within each group.
