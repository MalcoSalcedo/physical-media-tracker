import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path

import acoustid
import numpy as np
import sounddevice as sd

FPCALC_ENVVAR = "FPCALC"
FPCALC_COMMAND = "fpcalc"


def record_clip(duration_seconds: float, sample_rate: int = 44100, device: int | None = None) -> np.ndarray:
    """Record a mono clip from the given input device (or the system default)."""
    audio = sd.rec(
        int(duration_seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=device,
    )
    sd.wait()
    return audio[:, 0]


def _write_wav(samples: np.ndarray, sample_rate: int, path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())


def identify_clip(samples: np.ndarray, sample_rate: int, api_key: str) -> list[tuple]:
    """Fingerprint a recorded clip and look it up via AcoustID.

    Returns (score, recording_id, title, artist) tuples, same shape as
    `acoustid.match()`. Writes the clip to a temporary WAV file since
    fpcalc operates on files, not in-memory PCM.

    Requires `fpcalc` on PATH (on the Pi: `apt install chromaprint`). On
    Windows, if it's not resolving, set FPCALC=<path to fpcalc.exe> in
    .env - pyacoustid respects that env var directly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = Path(tmpdir) / "clip.wav"
        _write_wav(samples, sample_rate, wav_path)
        return list(acoustid.match(api_key, str(wav_path), force_fpcalc=True))


def raw_fingerprint(samples: np.ndarray, sample_rate: int) -> list[int]:
    """Fingerprint a clip as a raw (uncompressed) list of integers.

    Used for local fingerprint comparison (app.local_match), which doesn't
    need the AcoustID service at all - just fpcalc's own `-raw` output,
    which sidesteps needing the separate libchromaprint shared library
    that decoding a *compressed* fingerprint would require.
    """
    fpcalc = os.environ.get(FPCALC_ENVVAR, FPCALC_COMMAND)
    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = Path(tmpdir) / "clip.wav"
        _write_wav(samples, sample_rate, wav_path)
        output = subprocess.run(
            [fpcalc, "-raw", "-json", str(wav_path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    return json.loads(output)["fingerprint"]
