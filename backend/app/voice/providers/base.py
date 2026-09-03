"""Minimal streaming speech-to-text provider contract."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    is_final: bool


class SpeechToTextProvider(Protocol):
    name: str

    async def available(self) -> bool: ...

    def transcribe_stream(
        self, audio: AsyncIterator[bytes]
    ) -> AsyncIterator[TranscriptEvent]: ...
