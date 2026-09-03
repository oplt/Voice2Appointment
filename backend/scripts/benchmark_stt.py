"""Score captured STT benchmark results from a JSON Lines manifest.

Each row contains provider, language, audio_path, reference, transcript, entities,
date_times and optional latency/resource/cost measurements. Provider invocation is
kept separate so the same captured Twilio audio is submitted to every backend.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def word_error_rate(reference: str, transcript: str) -> float:
    expected, actual = _words(reference), _words(transcript)
    if not expected:
        return 0.0 if not actual else 1.0
    previous = list(range(len(actual) + 1))
    for row, expected_word in enumerate(expected, start=1):
        current = [row]
        for column, actual_word in enumerate(actual, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected_word != actual_word),
                )
            )
        previous = current
    return previous[-1] / len(expected)


def phrase_accuracy(phrases: list[str], transcript: str) -> float:
    if not phrases:
        return 1.0
    normalized = " ".join(_words(transcript))
    matches = sum(" ".join(_words(phrase)) in normalized for phrase in phrases)
    return matches / len(phrases)


def summarize(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[f"{record['provider']}:{record['language']}"].append(record)
    report: dict[str, dict[str, float]] = {}
    optional = (
        "first_partial_ms",
        "final_transcript_ms",
        "gpu_utilization_percent",
        "ram_mb",
        "cost_per_minute",
    )
    for key, rows in grouped.items():
        metrics = {
            "samples": float(len(rows)),
            "wer": mean(word_error_rate(row["reference"], row["transcript"]) for row in rows),
            "entity_accuracy": mean(
                phrase_accuracy(row.get("entities", []), row["transcript"]) for row in rows
            ),
            "date_time_accuracy": mean(
                phrase_accuracy(row.get("date_times", []), row["transcript"])
                for row in rows
            ),
        }
        for name in optional:
            values = [float(row[name]) for row in rows if row.get(name) is not None]
            if values:
                metrics[name] = mean(values)
        report[key] = metrics
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.manifest.read_text().splitlines() if line]
    result = json.dumps(summarize(records), indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)


if __name__ == "__main__":
    main()
