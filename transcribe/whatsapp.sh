#!/usr/bin/env bash
# whatsapp.sh - Batch transcribe WhatsApp voice notes
#
# Converts .ogg files to 16kHz mono WAV, transcribes with whisper.cpp,
# and writes output to a timestamped file in the current directory.
#
# Usage: ./transcribe/whatsapp.sh <directory>

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <directory-with-ogg-files>" >&2
    exit 1
fi

INPUT_DIR="$1"

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: '$INPUT_DIR' is not a directory" >&2
    exit 1
fi

shopt -s nullglob
OGG_FILES=("$INPUT_DIR"/*.ogg)
shopt -u nullglob

if [ ${#OGG_FILES[@]} -eq 0 ]; then
    echo "Error: no .ogg files found in '$INPUT_DIR'" >&2
    exit 1
fi

OUTPUT="transcriptions-$(datestamp).txt"
TMPWAV=$(mktemp /tmp/whatsapp_XXXXXX.wav)
trap 'rm -f "$TMPWAV"' EXIT

echo "Transcribing ${#OGG_FILES[@]} files..." >&2

for f in "${OGG_FILES[@]}"; do
    base=$(basename "$f")
    ffmpeg -y -i "$f" -ar 16000 -ac 1 "$TMPWAV" 2>/dev/null

    text=$("$WHISPER_BIN" \
        -m "$WHISPER_MODEL" -f "$TMPWAV" -np -nt -sns \
        --vad -vm "$VAD_MODEL" 2>/dev/null \
        | tr '\n' ' ' | tr -s ' ' | sed 's/^ *//; s/ *$//')

    echo "$base"
    echo "$text"
    echo

    echo "  $base" >&2
done > "$OUTPUT"

echo "Wrote $OUTPUT" >&2
