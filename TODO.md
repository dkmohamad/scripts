# Recorder TODO

## ~~Audio pre-processing~~ (done)

Implemented in `recorder/preprocess.py` using DeepFilterNet (vendor
binary) for neural denoising, plus librosa/scipy for analysis,
resampling, high-pass filtering, and peak normalization. Available as
the `preprocess` CLI (`preprocess analyze` / `preprocess clean`).

## ~~MP3 export~~ (done)

WAV recordings are converted to MP3 before archiving/uploading via
ffmpeg in the capture pipeline.

## ~~Notion integration~~ (done)

Completed recordings are pushed to Notion with metadata (date,
duration, solo vs call), MP3 audio attachment, transcript as page
content, and summary at the top. Configured via `NOTION_DATABASE_ID`
in `.env`.
