from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    records_root: str | None = None
    captures_root: str | None = None
    sharex_history_db: str | None = None


def load_config(path: str | Path | None) -> AppConfig:
    if path is None:
        return AppConfig()
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    roots = data.get("roots", {})
    sharex = data.get("sharex", {})
    return AppConfig(
        records_root=roots.get("records"),
        captures_root=roots.get("captures"),
        sharex_history_db=sharex.get("history_db"),
    )

