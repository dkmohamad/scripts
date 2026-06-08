#!/usr/bin/env bash
# audio.sh - Shared audio conversion utilities
#
# Source this file to get audio helper functions.
# Requires: ffmpeg
#
# Usage:
#   source "$SHARED_DIR/audio.sh"

# Convert any audio file to 16kHz mono WAV via ffmpeg.
# If the file is already a .wav, copies it to dest as-is.
# Returns 1 if conversion fails (not an audio file).
#
# Usage: to_wav <src> <dest>
to_wav() {
    local src="$1" dest="$2"
    if [[ "${src,,}" == *.wav ]]; then
        cp "$src" "$dest"
        return 0
    fi
    if ffmpeg -y -i "$src" -ar 16000 -ac 1 "$dest" 2>/dev/null; then
        return 0
    else
        rm -f "$dest"
        return 1
    fi
}
