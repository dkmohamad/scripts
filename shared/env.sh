#!/usr/bin/env bash
# env.sh - Global shared environment for all scripts
#
# Source this file to get common utilities and project-wide settings.
# Individual tools should source this first, then define their own env.sh.
#
# Usage:
#   SHARED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../shared" && pwd)"
#   source "$SHARED_DIR/env.sh"

# ------------------------------------------------------------------------------
# Project paths
# ------------------------------------------------------------------------------

# Root of the scripts project (parent of shared/)
SCRIPTS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Shared directory
SHARED_DIR="$SCRIPTS_ROOT/shared"

# Vendor directory (third-party dependencies)
VENDOR_DIR="$SCRIPTS_ROOT/vendor"

# ------------------------------------------------------------------------------
# Common utilities
# ------------------------------------------------------------------------------

# Check if a command exists
command_exists() {
    command -v "$1" &>/dev/null
}

# Require a command, exit with error if missing
require_command() {
    local cmd="$1"
    local install_hint="${2:-}"
    if ! command_exists "$cmd"; then
        echo "Error: '$cmd' is required but not installed." >&2
        [[ -n "$install_hint" ]] && echo "Install with: $install_hint" >&2
        exit 1
    fi
}

# Get available system memory as human-readable string
get_mem_avail() {
    awk '/MemAvailable/ {printf "%.1fGB", $2/1024/1024}' /proc/meminfo
}

# Datestamp for output filenames (YYYYMMDD-HHMMSS)
datestamp() {
    date +%Y%m%d-%H%M%S
}

# Get GPU memory usage (returns "N/A" if nvidia-smi unavailable)
get_gpu_mem() {
    nvidia-smi --query-gpu=memory.used,memory.total \
        --format=csv,noheader,nounits 2>/dev/null \
        | awk -F', ' '{printf "%dMB/%dMB", $1, $2}' \
        || echo "N/A"
}

# ------------------------------------------------------------------------------
# Source logging utilities
# ------------------------------------------------------------------------------

source "$SHARED_DIR/logging.sh"
