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
