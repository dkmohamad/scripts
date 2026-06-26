# Recorder TODO

Design decisions and their rationale now live in the code docs — see
`recorder/README.md` ("Design notes") and the module docstrings
(`recorder/stt.py`, `recorder/audio-setup.sh`, `recorder/transcribe.py`).

## Open

- Evaluate Speechmatics' built-in **summary** and **sentiment** on real
  recordings (`Transcript.summary` / `Transcript.sentiment_analysis`, available
  from the batch SDK in the same job), with a view to dropping the Claude
  `summarise.py` step. Caveats to check first: sentiment is English-only, and
  Arabic summarization support is unconfirmed — so this needs a real check on
  actual lesson audio before relying on it.

- **Use channel diarization for multi-channel sources instead of mono mixdown.**
  *Deferred: first see how the current echo-cancelled mono + speaker diarization
  performs on a real lesson before changing anything.*

  Background: a phone-call recording
  (`~/Recordings/capture-20260626-091711`) came back with all speech under a
  single `SPEAKER S1`, despite `diarization=speaker`. Investigation found two
  independent causes:

  1. **Mono mixdown destroys free speaker separation.** The raw `.m4a` was
     2-channel with the two call parties on separate channels (measured L/R
     correlation ≈ -0.0001, i.e. independent content — not dual-mono). The
     pipeline folds everything to mono before Speechmatics sees it
     (`shared/audio.sh:21` ffmpeg `-ac 1`, and `preprocess.py:130`
     `librosa.load(mono=True)`), so two cleanly-separated voices get blended
     and acoustic diarization then collapses them to one.
  2. **The source was band-limited/muffled at capture.** 16 kbps AAC; 95% of
     energy below ~960 Hz, 99% below ~1.7 kHz (consonant/fricative cues at
     2-8 kHz essentially absent). DeepFilterNet `--cleanup` can't restore
     bandwidth that was never captured, so it can't fix intelligibility here.
     Note the log's `SNR 28→40 dB` overstates the gain: it's
     `mean_RMS - 10th-pct_RMS`, and denoising just pushes silent gaps toward
     -92 dB while mean RMS actually dropped 13 dB. Unfixable in post — needs a
     higher-bitrate capture upstream.

  Recommendation — prefer channel diarization whenever the source has ≥2
  decorrelated channels; fall back to acoustic speaker diarization only for
  true single-channel audio. Reserve mono mixdown for *dual-mono* stereo
  (redundant copies), detectable by the same L/R correlation check (≈0 = keep
  channels, ≈1 = safe to fold). By source type:

  - **Phone call recording** — source is already 2-channel and decorrelated.
    Just skip the downmix and use channel diarization. Easiest win, process-path
    only, no capture change. (`stt.py` already exposes the SDK's
    `channel_diarization_labels` field.)
  - **Meeting (mic + system, AEC on)** — `_record_meeting.sh` already has two
    clean streams in hand (`echo-cancel-source` = you, `...sink.monitor` =
    far-end) but `record_mixed` folds them to mono. Echo cancellation is what
    makes channel separation safe again (pre-AEC the far-end bled into the mic,
    which is why mono was correct then). Change capture to record 2-channel
    (mic=L, system=R) and use channel diarization. Caveat: channel diar
    separates *sides*, not individual people — multiple far-end speakers share
    one channel, so a group meeting wants `channel_and_speaker` (verify the
    installed SDK exposes it) to also split the remote side acoustically.
  - **Phone mic, in-person (rare)** — one physical mic, all voices acoustically
    summed; only acoustic speaker diarization is possible. Accept lower
    accuracy; no fix without multi-mic hardware.

  Bonus: for the clean digital sources (call / meeting) DeepFilterNet cleanup is
  unnecessary and can muffle the audio further — the same source-type branch
  could default `--cleanup` off for digital sources and on only for the
  phone-mic-in-room case.
