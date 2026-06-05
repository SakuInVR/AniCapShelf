from pathlib import Path

from anicapshelf.config import load_config


def test_load_config(tmp_path: Path):
    config_path = tmp_path / "anicapshelf.toml"
    config_path.write_text(
        """
[roots]
records = "Z:\\\\TV-Record"
captures = "Z:\\\\TV-Capture"

[sharex]
history_db = "Z:\\\\TV-Capture\\\\ShareX\\\\History.db"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.records_root == "Z:\\TV-Record"
    assert config.captures_root == "Z:\\TV-Capture"
    assert config.sharex_history_db == "Z:\\TV-Capture\\ShareX\\History.db"

