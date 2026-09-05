"""Enforce backend source-size limits while containing legacy exceptions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = Path(__file__).with_name("file_size_baseline.json")


def effective_lines(path: Path) -> int:
    return sum(
        bool(line.strip()) and not line.lstrip().startswith("#")
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def limit_for(path: Path) -> int:
    relative = path.relative_to(ROOT)
    if path.name in {"router.py", "routes.py"}:
        return 200
    if path.name == "service.py" or "providers" in relative.parts:
        return 300
    return 400


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prune-baseline", action="store_true")
    args = parser.parse_args()
    baseline: dict[str, int] = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    stale: list[str] = []

    for path in sorted((ROOT / "app").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        count = effective_lines(path)
        limit = limit_for(path)
        allowance = baseline.get(relative)
        if allowance is not None and count <= limit:
            stale.append(relative)
        elif count > (allowance if allowance is not None else limit):
            failures.append(
                f"{relative}: {count} effective lines exceeds "
                f"{allowance if allowance is not None else limit}"
            )

    missing = sorted(set(baseline) - {p.relative_to(ROOT).as_posix() for p in (ROOT / "app").rglob("*.py")})
    stale.extend(missing)
    if args.prune_baseline and stale:
        for relative in stale:
            baseline.pop(relative, None)
        BASELINE_PATH.write_text(
            json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        stale = []
    elif stale:
        failures.extend(
            f"{relative}: stale baseline; run check_file_sizes.py --prune-baseline"
            for relative in stale
        )

    if failures:
        print("\n".join(failures))
        return 1
    print("Backend file-size architecture check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
