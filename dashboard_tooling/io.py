from __future__ import annotations

import csv
import json
from pathlib import Path


class IoError(RuntimeError):
    pass


def load_json(path: Path) -> object:
    if not path.exists():
        raise IoError(f"file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise IoError(f"invalid JSON in {path}: {exc}") from exc
    except OSError as exc:
        raise IoError(f"could not read {path}: {exc}") from exc


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: object) -> None:
    try:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except OSError as exc:
        raise IoError(f"could not write {path}: {exc}") from exc


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    try:
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
    except OSError as exc:
        raise IoError(f"could not write {path}: {exc}") from exc


def write_text(path: Path, content: str) -> None:
    try:
        with path.open("w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as exc:
        raise IoError(f"could not write {path}: {exc}") from exc

