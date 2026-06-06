from __future__ import annotations

from pathlib import Path


def test_konomitv_integration_client_documents_required_metadata():
    root = Path(__file__).resolve().parents[1]
    client = (root / "integrations" / "konomitv" / "anicapshelf-capture-client.ts").read_text(
        encoding="utf-8"
    )
    readme = (root / "integrations" / "konomitv" / "README.md").read_text(encoding="utf-8")

    assert "uploadAnnotatedCapture" in client
    assert "ANICAPSHELF_QUICK_TAGS" in client
    assert "quickTags" in client
    assert "mergeTags" in client
    assert "playback_position_seconds" in client
    assert "recorded_program_id" in client
    assert "recording_file_path" in client
    assert "--allow-origin" in readme
    assert "player.video.currentTime" in readme
