from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "profile-art.json"


def load_config(
    path: Path = DEFAULT_CONFIG, required: set[str] | None = None
) -> dict[str, Any]:
    values = json.loads(path.read_text(encoding="utf-8"))
    missing = (required or set()).difference(values)
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"Missing profile art settings: {names}")
    return values


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path
