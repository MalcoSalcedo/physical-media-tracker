import numpy as np


def rms(samples: np.ndarray) -> float:
    """Root-mean-square energy of an audio chunk."""
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


class GapDetector:
    """Detects the brief silence between tracks from a stream of audio chunks.

    Feed consecutive chunks via `process_chunk`. It fires a gap event
    (returns True) once a continuous span of silence at least
    `min_gap_seconds` long has been observed, and won't fire again until
    real audio resumes and then goes silent again - so one gap produces
    exactly one event, not one per chunk.

    Silence is measured in `sub_window_seconds`-sized pieces *within* each
    submitted chunk, not as a single average over the whole chunk. A real
    CD player's skip-mute is often shorter than or comparable to a single
    recorded chunk (2s in production); if the true silence doesn't align
    with chunk boundaries, averaging RMS over the *entire* chunk lets
    surrounding loud audio dilute it enough to never read as silent at all
    - RMS averages in power (squared amplitude), so even a small loud
    portion dominates. Confirmed on a real recorded skip (see DEVLOG,
    2026-08-18): the two chunks straddling a genuine ~1.55s silent gap had
    whole-chunk RMS of 1592 and 322 - both comfortably above a 200
    threshold - despite each containing a large fraction of true silence.
    Sub-window measurement fixes this without changing how audio is
    recorded.
    """

    def __init__(
        self,
        sample_rate: int,
        silence_threshold: float = 200.0,
        min_gap_seconds: float = 1.2,
        sub_window_seconds: float = 0.1,
    ):
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.min_gap_samples = int(min_gap_seconds * sample_rate)
        self.sub_window_samples = max(1, int(sub_window_seconds * sample_rate))
        self._silent_samples = 0
        self._gap_fired = False

    def process_chunk(self, samples: np.ndarray) -> bool:
        """Feed in the next chunk of audio. Returns True on a new gap event."""
        fired = False
        for start in range(0, len(samples), self.sub_window_samples):
            sub = samples[start : start + self.sub_window_samples]
            if rms(sub) < self.silence_threshold:
                self._silent_samples += len(sub)
                if self._silent_samples >= self.min_gap_samples and not self._gap_fired:
                    self._gap_fired = True
                    fired = True
            else:
                self._silent_samples = 0
                self._gap_fired = False
        return fired
