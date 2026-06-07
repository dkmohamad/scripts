#!/usr/bin/env bash
# _compress.sh — Convert WAV files to MP3 after transcription.
#
# Usage: _compress.sh <session_dir> [--keep-wav]
#
# Converts all .wav files in session_dir to MP3 using libmp3lame VBR,
# then deletes originals unless --keep-wav is passed.

set -euo pipefail

SHARED_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../shared" && pwd)"
source "$SHARED_DIR/env.sh"

require_command ffmpeg "sudo apt install ffmpeg"

SESSION_DIR="$1"
KEEP_WAV=false

if [[ "${2:-}" == "--keep-wav" ]]; then
    KEEP_WAV=true
fi

if [[ ! -d "$SESSION_DIR" ]]; then
    echo "Error: session directory does not exist: $SESSION_DIR" >&2
    exit 1
fi

shopt -s nullglob
wav_files=("$SESSION_DIR"/*.wav)
shopt -u nullglob

if [[ ${#wav_files[@]} -eq 0 ]]; then
    echo "No .wav files found in $SESSION_DIR"
    exit 0
fi

for wav in "${wav_files[@]}"; do
    mp3="${wav%.wav}.mp3"
    basename_wav="$(basename "$wav")"
    basename_mp3="$(basename "$mp3")"

    wav_size=$(stat --printf="%s" "$wav")
    wav_human=$(numfmt --to=iec-i --suffix=B "$wav_size")

    ffmpeg -y -i "$wav" -codec:a libmp3lame -qscale:a 5 "$mp3" \
        -loglevel warning

    mp3_size=$(stat --printf="%s" "$mp3")
    mp3_human=$(numfmt --to=iec-i --suffix=B "$mp3_size")

    ratio=$(awk "BEGIN {printf \"%.1fx\", $wav_size / $mp3_size}")
    echo "  $basename_wav ($wav_human) -> $basename_mp3 ($mp3_human) [${ratio} reduction]"

    if [[ "$KEEP_WAV" == false ]]; then
        rm "$wav"
    fi
done

if [[ "$KEEP_WAV" == true ]]; then
    echo "  (kept original .wav files)"
fi
