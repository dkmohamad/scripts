# Recorder TODO

## ~~Audio pre-processing~~ (done)

Implemented in `recorder/preprocess.py` using DeepFilterNet (vendor
binary) for neural denoising, plus librosa/scipy for analysis,
resampling, high-pass filtering, and peak normalization. Available as
the `preprocess` CLI (`preprocess analyze` / `preprocess clean`).

## ~~MP3 export~~ (done)

WAV recordings are converted to MP3 before archiving/uploading via
ffmpeg in the capture pipeline.

## Speaker diarization for single-track recordings

`capture process` currently produces plain text with no speaker
labels. Add diarization (e.g. pyannote-audio or whisper-diarize) to
detect speaker turns from a single audio stream, so phone recordings
of calls get `[Speaker 1]` / `[Speaker 2]` labels like dual-track
recordings do.

## ~~Notion integration~~ (done)

Completed recordings are pushed to Notion with metadata (date,
duration, solo vs call), MP3 audio attachment, transcript as page
content, and summary at the top. Configured via `NOTION_DATABASE_ID`
in `.env`.
