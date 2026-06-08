---
name: commit
description: Stage and commit changes
disable-model-invocation: true
allowed-tools: Bash(git *)
---

## Current state
!`git status`
!`git diff`
!`git diff --cached`

## Pre-flight

Run `/lint` first. **Do not commit if any lint check fails.**

## Instructions

Stage and commit the current changes. Follow these rules strictly:

1. Stage relevant files (prefer naming files explicitly over `git add -A`)
2. Never include `.env` or files containing secrets
3. Write a commit message with:
   - **Title**: max 50 characters, imperative mood (e.g. "Add feature" not "Added feature")
   - **Body** (if needed): wrap at 72 characters, explain *why* not *what*
4. **No AI attribution** — no "Co-Authored-By", "Generated with Claude", or similar lines
5. Use a HEREDOC to pass the message:

```bash
git commit -m "$(cat <<'EOF'
Title here (max 50 chars)

Optional body wrapped at 72 characters. Explain
the motivation for the change if not obvious from
the title alone.
EOF
)"
```

If there are no changes to commit, say so and stop.
