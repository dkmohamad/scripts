#!/usr/bin/env python3
"""Denoise and normalize audio for cleaner whisper transcription.

Uses DeepFilterNet (vendor binary) for neural speech enhancement and
librosa/scipy for analysis and post-processing.

Usage:
    preprocess analyze <file>
    preprocess clean <file> [-o output]
"""

import argparse
import functools
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

from recorder.lib import SCRIPTS_ROOT, log, run

DEEP_FILTER_BIN = (
    SCRIPTS_ROOT / "vendor" / "deep-filter" / "deep-filter"
)
_TO_WAV_SH = SCRIPTS_ROOT / "shared" / "audio.sh"


@dataclass
class AudioReport:
    """Diagnostics for an audio file."""

    path: str
    duration_s: float
    sample_rate: int
    rms_mean_db: float
    rms_max_db: float
    noise_floor_db: float
    snr_db: float
    clipping_ratio: float

    def __str__(self) -> str:
        """Format report as human-readable text."""
        return (
            f"  File:         {self.path}\n"
            f"  Duration:     {self.duration_s:.1f}s\n"
            f"  Sample rate:  {self.sample_rate} Hz\n"
            f"  RMS mean:     {self.rms_mean_db:.1f} dB\n"
            f"  RMS max:      {self.rms_max_db:.1f} dB\n"
            f"  Noise floor:  {self.noise_floor_db:.1f} dB\n"
            f"  SNR:          {self.snr_db:.1f} dB\n"
            f"  Clipping:     {self.clipping_ratio:.4%}"
        )


def analyze(audio_path: Path) -> AudioReport:
    """Compute audio diagnostics using librosa."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = _to_wav(audio_path, Path(tmp))
        y, sr = sf.read(str(wav), dtype="float32", always_2d=False)

    # Ensure mono
    if y.ndim > 1:
        y = np.mean(y, axis=1)

    rms = librosa.feature.rms(y=y)[0]
    rms_db = librosa.amplitude_to_db(rms, ref=1.0)

    rms_mean_db = float(np.mean(rms_db))
    rms_max_db = float(np.max(rms_db))
    noise_floor_db = float(np.percentile(rms_db, 10))
    snr_db = rms_mean_db - noise_floor_db
    clipping_ratio = float(np.mean(np.abs(y) > 0.99))

    return AudioReport(
        path=str(audio_path),
        duration_s=float(len(y) / sr),
        sample_rate=int(sr),
        rms_mean_db=rms_mean_db,
        rms_max_db=rms_max_db,
        noise_floor_db=noise_floor_db,
        snr_db=snr_db,
        clipping_ratio=clipping_ratio,
    )


def _with_analysis(
    fn: Callable[..., Path],
) -> Callable[..., Path]:
    """Log audio analysis before and after processing."""

    @functools.wraps(fn)
    def wrapper(audio_path: Path, *a: object, **kw: object) -> Path:
        log.info("=== Before ===")
        log.info(f"\n{analyze(audio_path)}")
        result = fn(audio_path, *a, **kw)
        log.info("=== After ===")
        log.info(f"\n{analyze(result)}")
        return result

    return wrapper


@_with_analysis
def preprocess(
    audio_path: Path, output_path: Path | None = None
) -> Path:
    """Denoise, resample, filter, and normalize audio for whisper."""
    if output_path is None:
        stem = _bare_stem(audio_path)
        output_path = audio_path.parent / f"{stem}_clean.wav"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # 0. Convert to WAV if needed (deep-filter requires WAV)
        wav_input = _to_wav(audio_path, tmp_dir)

        # 1. Denoise with DeepFilterNet
        log.info("Denoising with DeepFilterNet...")
        df_out = tmp_dir / "df_out"
        df_out.mkdir()
        denoised = _run_deep_filter(wav_input, df_out)

        # 2. Load denoised audio at 16kHz mono (whisper target)
        y, sr = librosa.load(str(denoised), sr=16000, mono=True)

    # 3. High-pass filter at 80 Hz
    y = _highpass(y, sr)

    # 4. Peak-normalize to -1 dB
    y = _peak_normalize(y, target_db=-1.0)

    # 5. Write output
    sf.write(str(output_path), y, sr, subtype="PCM_16")
    log.info(f"Wrote: {output_path}")

    return output_path


def main() -> None:
    """CLI entry point for audio preprocessing."""
    parser = argparse.ArgumentParser(
        prog="preprocess",
        description="Audio preprocessing for whisper transcription",
    )
    sub = parser.add_subparsers(dest="command")

    p_analyze = sub.add_parser(
        "analyze", help="Print audio diagnostics"
    )
    p_analyze.add_argument("file", type=Path)

    p_clean = sub.add_parser(
        "clean", help="Denoise and normalize audio"
    )
    p_clean.add_argument("file", type=Path)
    p_clean.add_argument("-o", "--output", type=Path, default=None)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if not args.file.is_file():
        log.error(f"File not found: {args.file}")
        sys.exit(1)

    if args.command == "analyze":
        report = analyze(args.file)
        log.info(f"\n{report}")

    elif args.command == "clean":
        preprocess(args.file, args.output)


# -- Private helpers ---------------------------------------------------------


def _bare_stem(path: Path) -> str:
    """Strip all extensions from a filename (e.g. 'foo.m4a.mp3' -> 'foo')."""
    stem = path.stem
    while Path(stem).suffix:
        stem = Path(stem).stem
    return stem


def _to_wav(path: Path, out_dir: Path) -> Path:
    """Convert any audio file to 16kHz mono WAV via shared/audio.sh."""
    if path.suffix.lower() == ".wav":
        return path
    dest = out_dir / f"{_bare_stem(path)}.wav"
    run(
        [
            "bash", "-c",
            f'source "{_TO_WAV_SH}" && to_wav "$1" "$2"',
            "_", str(path), str(dest),
        ],
        check=True,
    )
    return dest


def _run_deep_filter(input_path: Path, output_dir: Path) -> Path:
    """Run the deep-filter binary and return the output file path."""
    if not DEEP_FILTER_BIN.exists():
        raise FileNotFoundError(
            f"deep-filter binary not found: {DEEP_FILTER_BIN}"
        )

    cmd = [
        str(DEEP_FILTER_BIN),
        str(input_path),
        "--output-dir",
        str(output_dir),
    ]
    log.info(f"Running: {' '.join(cmd)}")
    run(cmd, check=True)

    # deep-filter writes <stem>.wav in the output dir
    stem = _bare_stem(input_path)
    output = output_dir / f"{stem}.wav"
    if not output.exists():
        # Fallback: find any wav in the output dir
        wavs = list(output_dir.glob("*.wav"))
        if not wavs:
            raise RuntimeError(
                "deep-filter produced no output in"
                f" {output_dir}"
            )
        output = wavs[0]
    return output


def _highpass(
    y: np.ndarray, sr: int, cutoff: int = 80
) -> np.ndarray:
    """Apply a 4th-order Butterworth high-pass filter."""
    sos = butter(4, cutoff, btype="high", fs=sr, output="sos")
    return sosfilt(sos, y)


def _peak_normalize(
    y: np.ndarray, target_db: float = -1.0
) -> np.ndarray:
    """Peak-normalize audio to target dB."""
    peak = np.max(np.abs(y))
    if peak == 0:
        return y
    target_amp = 10 ** (target_db / 20)
    return y * (target_amp / peak)


if __name__ == "__main__":
    main()
