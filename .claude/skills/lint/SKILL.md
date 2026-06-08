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

### 2. ShellCheck (Bash)

```bash
git ls-files '*.sh' | xargs shellcheck
```

Configuration lives in `.shellcheckrc` at the project root. Both
tools can be run independently outside of this skill.

### 3. Report

Print a summary. If any linter reported errors that could not be
auto-fixed, list them clearly and do **not** say "lint passed".

Only say "All checks passed" when both ruff and shellcheck exit 0.
