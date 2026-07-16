import json

MAX_ALIGN_OFFSET = 120
MAX_BIT_ERROR = 2


def _popcount(x: int) -> int:
    return bin(x).count("1")


def similarity(a: list[int], b: list[int]) -> float:
    """Similarity (0-1) between two raw (uncompressed) Chromaprint fingerprints.

    Same alignment-search approach Chromaprint itself uses: slide the two
    fingerprints against each other within a bounded offset range and count
    how many aligned sub-fingerprint pairs differ by only a couple of bits.
    Works on the raw integer fingerprint `fpcalc -raw` gives us directly, so
    it doesn't need the separate libchromaprint shared library the ctypes
    bindings require.
    """
    if not a or not b:
        return 0.0

    counts = [0] * (len(a) + len(b) + 1)
    for i in range(len(a)):
        jbegin = max(0, i - MAX_ALIGN_OFFSET)
        jend = min(len(b), i + MAX_ALIGN_OFFSET)
        for j in range(jbegin, jend):
            bit_error = _popcount(a[i] ^ b[j])
            if bit_error <= MAX_BIT_ERROR:
                offset = i - j + len(b)
                counts[offset] += 1
    return max(counts) / min(len(a), len(b))


def encode_fingerprint(raw_fingerprint: list[int]) -> str:
    return json.dumps(raw_fingerprint)


def decode_fingerprint(data: str) -> list[int]:
    return json.loads(data)
