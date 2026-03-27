# Scripts

A collection of utility scripts for Linux.

## Tools

| Tool | Description |
|------|-------------|
| [transcribe](transcribe/) | Push-to-talk voice dictation using whisper.cpp |
| [gdrive-mount](gdrive-mount/) | Mount Google Drive as FUSE filesystem via rclone |

## Structure

```
scripts/
├── shared/         # Common utilities (logging, helpers)
├── transcribe/     # Voice-to-text tools
├── gdrive-mount/   # Google Drive mounting
└── vendor/         # Third-party dependencies (submodules)
```

## Shared Utilities

All tools source `shared/env.sh` which provides:

- **Logging** - `log_info`, `log_warn`, `log_error` write to systemd journal
- **Helpers** - `require_command`, `get_mem_avail`, `get_gpu_mem`
- **Paths** - `SCRIPTS_ROOT`, `SHARED_DIR`, `VENDOR_DIR`

Each tool has its own `env.sh` for tool-specific configuration.

## Setup

Clone with submodules:

```bash
git clone --recurse-submodules git@github.com:dkmohamad/scripts.git
```

See individual tool READMEs for setup instructions.
