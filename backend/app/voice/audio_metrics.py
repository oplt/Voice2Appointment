"""Audio latency calculation helpers."""


def estimate_legacy_buffer_latency_ms(
    frames: int = 20, frame_bytes: int = 160, sample_rate: int = 8000
) -> float:
    """Document the old 20x160 mu-law coalesce cost (~400 ms at 8 kHz)."""
    return frames * frame_bytes / sample_rate * 1000
