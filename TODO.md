# Recorder TODO

## Audio pre-processing

Add a pre-processing step between recording and transcription that:

- Checks audio levels and rejects recordings that are too quiet or
  clipped (exit with a clear error rather than producing garbage
  transcripts)
- Normalises volume (loudnorm or similar ffmpeg filter)
- Applies noise reduction / high-pass filter for cleaner whisper input

This should be a standalone script (`recorder/preprocess.sh`) that
capture.py and transcribe.sh can call, so it's also usable manually.

## MP3 export

Convert WAV recordings to MP3 before archiving or uploading. WAV files
are ~1.9 MB/min at 16kHz mono; MP3 reduces this ~10x. Needed before
pushing to Notion (file size limits) and for general storage.

## Notion integration

Push completed recordings to Notion:

- Create a database entry per recording with metadata (date, duration,
  participants if known, solo vs call)
- Attach the MP3 audio file
- Paste the transcript as page content
- Paste the summary (if available) at the top of the page
- Support both call transcripts and solo journal entries

Requires the Notion API token in `.env` and a target database ID.
