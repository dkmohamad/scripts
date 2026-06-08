#!/usr/bin/env bash
# transcribe.sh - Batch transcribe audio files with whisper.cpp
#
# Accepts a directory or individual files. Non-wav files are converted
# to 16kHz mono WAV first, then transcribed.
#
# Usage:
#   transcribe.sh [options] <directory>
#   transcribe.sh [options] <file> [file...]
#
# Options:
#   --babel  Use the multilingual model (auto-detects language)
#   --csv    Output per-file CSV with timestamps (start,end,text)
#            instead of a single merged plain-text file
#
# Examples:
#   transcribe.sh ~/audio              # all files in dir -> .txt
#   transcribe.sh --babel ~/audio      # multilingual
#   transcribe.sh --csv file1.wav      # single file -> file1.csv
#   transcribe.sh --csv a.wav b.wav    # two files -> a.csv, b.csv

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

BABEL=false
CSV=false
while [[ "${1:-}" == --* ]]; do
    case "$1" in
        --babel) BABEL=true ;;
        --csv)   CSV=true ;;
        *) echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
    shift
done

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
    if $BABEL; then
        whisper_transcribe_multi "$1"
    else
        whisper_transcribe "$1"
    fi | tr '\n' ' ' | tr -s ' ' | sed 's/^ *//; s/ *$//'
}

# Transcribe a wav file to CSV with timestamps.
# Writes <output_base>.csv via whisper-cli -ocsv.
transcribe_csv() {
    local input="$1" output_base="$2"
    local model="$WHISPER_MODEL"
    local extra_args=()
    if $BABEL; then
        model="$WHISPER_MODEL_MULTI"
        extra_args=(--language auto -mc 0)
    fi
    "$WHISPER_BIN" \
        -m "$model" -f "$input" -np -sns \
        --vad -vm "$VAD_MODEL" \
        "${extra_args[@]}" \
        -ocsv -of "$output_base" \
        2> >(tee >(logger -t "$LOG_TAG" -p user.err) >&2)
}

if [ $# -lt 1 ]; then
    echo "Usage: $0 <dir|file...>" >&2
    exit 1
fi

if [ -d "$1" ]; then
    collect_files "$1" "${AUDIO_EXTS[@]}"
else
    FILES=("$@")
    for f in "${FILES[@]}"; do
        if [ ! -f "$f" ]; then
            echo "Error: '$f' not found" >&2
            exit 1
        fi
    done
fi

TMPWAV=$(mktemp /tmp/transcribe_XXXXXX.wav)
trap 'rm -f "$TMPWAV"' EXIT

echo "Transcribing ${#FILES[@]} files..." >&2

if $CSV; then
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

        output_base="${f%.*}"
        transcribe_csv "$wav" "$output_base"
        echo "  $name -> $(basename "$output_base").csv" >&2
    done
else
    OUTPUT="transcriptions-$(datestamp).txt"

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
    done > "$OUTPUT"

    echo "Wrote $OUTPUT" >&2
fi
