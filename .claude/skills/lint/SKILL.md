---
name: lint
description: Run linters on Python and Bash files
user-invocable: true
disable-model-invocation: true
---

## Instructions

Run all linters and report results. **All checks must pass** before
code can be committed.

### 1. Ruff (Python)

```bash
ruff check .
```

If there are auto-fixable issues, run:

```bash
ruff check --fix .
```

Then re-run `ruff check .` to confirm everything passes.

### 2. Pyright (Python type checking)

```bash
pyright
```

Warnings are acceptable (e.g. from untyped third-party libraries).
Only **errors** count as failures.

### 3. ShellCheck (Bash)

```bash
git ls-files '*.sh' | xargs shellcheck
```

### 4. Report

Configuration for each tool lives at the project root
(`pyproject.toml`, `pyrightconfig.json`, `.shellcheckrc`). All
tools can be run independently outside of this skill.

Print a summary. If any linter reported errors that could not be
auto-fixed, list them clearly and do **not** say "lint passed".

Only say "All checks passed" when ruff, pyright, and shellcheck
all exit 0.
