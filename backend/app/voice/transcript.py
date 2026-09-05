"""Per-call bounded transcript capture."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence


def _truncate_utf8(value: str, maximum: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum:
        return value, False
    if maximum <= 0:
        return "", True
    clipped = encoded[:maximum]
    while clipped:
        try:
            return clipped.decode("utf-8"), True
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return "", True


class BoundedTranscript(Sequence[str]):
    """List-like transcript with per-message and total UTF-8 byte limits."""

    def __init__(self, *, max_bytes: int, max_message_bytes: int) -> None:
        self.max_bytes = max(1, int(max_bytes))
        self.max_message_bytes = max(1, min(int(max_message_bytes), self.max_bytes))
        self._lines: list[str] = []
        self._bytes = 0
        self.truncated = False
        self.dropped_messages = 0

    def __len__(self) -> int:
        return len(self._lines)

    def __getitem__(self, index):  # noqa: ANN001, ANN204
        return self._lines[index]

    def __iter__(self) -> Iterator[str]:
        return iter(self._lines)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, BoundedTranscript):
            return self._lines == other._lines
        if isinstance(other, Sequence) and not isinstance(other, (str, bytes)):
            return self._lines == list(other)
        return False

    @property
    def byte_count(self) -> int:
        return self._bytes

    def append_message(self, role: str, content: str) -> bool:
        prefix = f"{role.strip()}: " if role.strip() else ""
        message, message_truncated = _truncate_utf8(
            prefix + content.strip(), self.max_message_bytes
        )
        separator_bytes = 1 if self._lines else 0
        line, total_truncated = _truncate_utf8(
            message,
            self.max_bytes - self._bytes - separator_bytes,
        )
        if not line:
            self.truncated = True
            self.dropped_messages += 1
            return False
        self._lines.append(line)
        self._bytes += separator_bytes + len(line.encode("utf-8"))
        if message_truncated or total_truncated:
            self.truncated = True
        return True

    def append(self, line: str) -> None:
        self.append_message("", str(line))

    def extend(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.append(str(line))

    def clear(self) -> None:
        self._lines.clear()
        self._bytes = 0
        self.truncated = False
        self.dropped_messages = 0

    def text(self) -> str:
        return "\n".join(self._lines)

    def metadata(self) -> dict[str, int | bool]:
        return {
            "bytes": self._bytes,
            "max_bytes": self.max_bytes,
            "truncated": self.truncated,
            "dropped_messages": self.dropped_messages,
        }
