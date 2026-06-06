#!/usr/bin/env bash
# transcribe-meeting.sh - Transcribe paired meeting recordings
#
# Finds *-mic.wav / *-system.wav pairs in a directory, transcribes each
# track with transcribe.sh --csv, and merges them into a single
# speaker-labelled transcript sorted by timestamp.
#
# Usage:
#   transcribe-meeting.sh <directory>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_TAG="recorder"
source "$SCRIPT_DIR/env.sh"

TRANSCRIBE="$SCRIPT_DIR/transcribe.sh"

# ------------------------------------------------------------------
# Args
# ------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
    echo "Usage: transcribe-meeting.sh <directory>" >&2
    exit 1
fi

INPUT_DIR="$1"

if [[ ! -d "$INPUT_DIR" ]]; then
    echo "Error: '$INPUT_DIR' is not a directory." >&2
    exit 1
fi

# ------------------------------------------------------------------
# Find paired files
# ------------------------------------------------------------------

shopt -s nullglob
mic_files=("$INPUT_DIR"/meeting-*-mic.wav)
shopt -u nullglob

if [[ ${#mic_files[@]} -eq 0 ]]; then
    echo "No meeting-*-mic.wav files found in $INPUT_DIR" >&2
    exit 1
fi

for mic_file in "${mic_files[@]}"; do
    sys_file="${mic_file/-mic.wav/-system.wav}"
    base="${mic_file/-mic.wav/}"
    transcript="${base}-transcript.txt"

    if [[ ! -f "$sys_file" ]]; then
        echo "Warning: no matching system file for" \
            "$(basename "$mic_file"), skipping." >&2
        continue
    fi

    if [[ -f "$transcript" ]]; then
        echo "Skipping $(basename "$base") (transcript exists)"
        continue
    fi

    echo "Transcribing $(basename "$base")..."
    log_info "Transcribing $base"

    mic_csv="${base}-mic.csv"
    sys_csv="${base}-system.csv"

    # Transcribe each track to CSV
    "$TRANSCRIBE" --csv "$mic_file"
    "$TRANSCRIBE" --csv "$sys_file"

    # Merge CSVs: label, sort by start time, format as text
    awk -F',' '
        # Skip CSV headers
        NR == 1 && FNR == 1 { next }
        FNR == 1 && NR > 1  { next }
        {
            # Remove surrounding quotes from text field
            text = $3
            for (i = 4; i <= NF; i++) text = text "," $i
            gsub(/^ *"?|"? *$/, "", text)
            if (text == "") next
            start = $1 + 0
            label = (FILENAME ~ /-mic\.csv$/) \
                ? "[You]" : "[Them]"
            printf "%012.0f\t%s %s\n", start, label, text
        }
    ' "$mic_csv" "$sys_csv" \
        | sort -t$'\t' -k1,1n \
        | cut -f2- \
        > "$transcript"

    # Clean up intermediate CSVs
    rm -f "$mic_csv" "$sys_csv"

    line_count=$(wc -l < "$transcript")
    echo "Wrote $transcript ($line_count lines)"
    log_info "Transcript written: $transcript ($line_count lines)"
done
