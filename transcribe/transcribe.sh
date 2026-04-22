#!/usr/bin/env bash
# transcribe.sh - Batch transcribe audio files with whisper.cpp
#
# Accepts a directory of audio files. Non-wav files are converted
# to 16kHz mono WAV first, then all wav files are transcribed.
# Output is written to a timestamped file in the current directory.
#
# Usage: ./transcribe/transcribe.sh <directory>

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

AUDIO_EXTS=(wav ogg m4a mp3 opus flac mp4)

# Collect files matching extensions from a directory.
# Sets FILES array in caller's scope. Exits with error if dir
# is invalid or no files match.
# Usage: collect_files <dir> <ext> [<ext>...]
collect_files() {
    local dir="$1"; shift
    local -a exts=("$@")

    if [ ! -d "$dir" ]; then
        echo "Error: '$dir' is not a directory" >&2
        exit 1
    fi

    FILES=()
    shopt -s nullglob
    for ext in "${exts[@]}"; do
        FILES+=("$dir"/*."$ext")
    done
    shopt -u nullglob

    if [ ${#FILES[@]} -eq 0 ]; then
        local joined
        joined=$(printf ", .%s" "${exts[@]}")
        echo "Error: no ${joined:2} files in '$dir'" >&2
        exit 1
    fi
}

# Convert a non-wav audio file to 16kHz mono WAV via ffmpeg.
# Returns 1 if conversion fails (not an audio file).
preprocess() {
    local src="$1" dest="$2"
    if ffmpeg -y -i "$src" -ar 16000 -ac 1 "$dest" 2>/dev/null; then
        return 0
    else
        rm -f "$dest"
        return 1
    fi
}

# Transcribe a wav file, returning cleaned text on stdout.
transcribe() {
    whisper_transcribe "$1" \
        | tr '\n' ' ' | tr -s ' ' | sed 's/^ *//; s/ *$//'
}

if [ $# -lt 1 ]; then
    echo "Usage: $0 <directory>" >&2
    exit 1
fi

collect_files "$1" "${AUDIO_EXTS[@]}"

TMPWAV=$(mktemp /tmp/transcribe_XXXXXX.wav)
trap 'rm -f "$TMPWAV"' EXIT

OUTPUT="transcriptions-$(datestamp).txt"

echo "Transcribing ${#FILES[@]} files..." >&2

for f in "${FILES[@]}"; do
    name=$(basename "$f")

    if [[ "$f" == *.wav ]]; then
        wav="$f"
    else
        if ! preprocess "$f" "$TMPWAV"; then
            echo "  $name (skipped, not audio)" >&2
            continue
        fi
        wav="$TMPWAV"
    fi

    text=$(transcribe "$wav")

    echo "$name"
    echo "$text"
    echo

    echo "  $name" >&2
# stdout from the loop body is redirected to the output file;
# stderr (progress lines) still prints to the terminal.
done > "$OUTPUT"

echo "Wrote $OUTPUT" >&2
