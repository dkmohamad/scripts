# Recorder TODO

## ~~Audio pre-processing~~ (done)

Implemented in `recorder/preprocess.py` using DeepFilterNet (vendor
binary) for neural denoising, plus librosa/scipy for analysis,
resampling, high-pass filtering, and peak normalization. Available as
the `preprocess` CLI (`preprocess analyze` / `preprocess clean`).

## ~~MP3 export~~ (done)

WAV recordings are converted to MP3 before archiving/uploading via
ffmpeg in the capture pipeline.

## Speaker bleed in dual-track call recordings (echo-cancel)

`capture stop` records mic + system as separate tracks and labels
them `[You]`/`[Them]` purely by which track they came from. When the
call is on open speakers (e.g. HDMI monitor + webcam mic), the far
speaker leaks acoustically into the mic, so BOTH tracks transcribe
BOTH voices and the labels become meaningless. Seen badly in the
Arabic lesson recordings, where `[You]` and `[Them]` are near
duplicates of the whole conversation.

Two fixes:

1. **Headphones (primary).** No acoustic loop → clean separation,
   no code change. Optionally have `capture start` read the active
   output port and skip/disable AEC when headphones are in use.

2. **Acoustic echo cancellation (fallback for speaker use).** This
   box runs PipeWire 1.0.5 with the webrtc AEC backend already
   installed (`libspa-aec-webrtc.so`,
   `libpipewire-module-echo-cancel.so`, `libwebrtc-audio-processing1`).
   - Phase 1: load `libpipewire-module-echo-cancel` via
     `~/.config/pipewire/pipewire.conf.d/99-echo-cancel.conf`
     (webrtc), capture = C615 mic, playback = HDMI. Creates
     `echo_cancel_source` (mic minus leaked far-end) and
     `echo_cancel_sink` (the reference). A/B the cancellation quality
     before any code change.
   - Phase 2: point `_record_meeting.sh` at `echo_cancel_source` for
     the mic track and `echo_cancel_sink.monitor` for the system
     track. Downstream consolidate/interleave/labelling is unchanged.
   - Fallback: offline AEC in `preprocess.py` using the two recorded
     tracks (mic = near-end, system = far-end reference) —
     deterministic and testable with a synthetic bleed fixture.

## Speaker diarization for single-track recordings

`capture process` produces plain text with no speaker labels. Whisper
does ASR only — it has no concept of *who* is speaking — so diarization
("who spoke when") is a separate step layered alongside it: VAD →
speaker embeddings (ECAPA-TDNN) → clustering → assign each transcribed
segment to the overlapping speaker turn. Result: phone recordings of
calls get `[Speaker 1]` / `[Speaker 2]` labels like dual-track ones.

Only this path needs diarization. Dual-track `capture stop` already
has ground-truth separation (track = speaker) once the bleed is fixed
(see echo-cancel above) — so this is an alternative to that work, for a
different recording type, not a replacement.

Two ways to add it:

1. **pyannote as a post-step (keeps whisper.cpp).** Run
   `pyannote/speaker-diarization-3.1` on the audio to get speaker turns
   (RTTM), keep the existing whisper.cpp CSV with timestamps, then
   overlay: label each segment with the speaker whose turn overlaps it
   most. Smallest change to the pipeline — it's an extra step in
   `transcribe_monologue`, not a rewrite — but adds a torch + pyannote
   dependency and a gated HuggingFace token.

2. **Switch this path to WhisperX.** All-in-one: faster-whisper +
   wav2vec2 forced alignment (word-level timestamps) + pyannote
   diarization + segment→speaker assignment, output already labelled.
   Cleaner result, but replaces whisper.cpp for the monologue path
   (two transcription engines to maintain) and pulls in the full torch
   stack.

Caveats either way:
- Labels are anonymous (`SPEAKER_00/01`), not "You"/"Them". Map them
  with a heuristic (who speaks first, or match each cluster against a
  short reference clip of David's voice).
- Diarization error rate rises with overlapping speech, short turns,
  and similar voices. The phone case is favourable: two distinct
  voices (David vs. a female teacher), so clustering separates easily.

## ~~Notion integration~~ (done)

Completed recordings are pushed to Notion with metadata (date,
duration, solo vs call), MP3 audio attachment, transcript as page
content, and summary at the top. Configured via `NOTION_DATABASE_ID`
in `.env`.
