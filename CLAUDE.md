# Claude Code Instructions

## Code Style

- Line length: 88 characters max

## Subprocess

Always pass `stdin=subprocess.DEVNULL` when calling `subprocess.run()` (or `Popen`)
for non-interactive commands (ffmpeg, deep-filter, shell scripts, etc.). Without it,
the child process inherits the parent's stdin and ffmpeg in particular will block
waiting for terminal input.

## Git Commits

Do not include Claude/Anthropic attribution in commit messages (no "Generated with
Claude Code" or "Co-Authored-By: Claude" lines).
