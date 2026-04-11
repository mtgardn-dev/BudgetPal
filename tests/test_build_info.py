from __future__ import annotations

import json

from core import build_info


def test_load_build_info_reads_metadata(monkeypatch, tmp_path) -> None:
    payload = {
        "build_tag": "v1.2.3",
        "commit": "abc1234",
        "built_at_utc": "2026-04-10T12:00:00Z",
    }
    metadata = tmp_path / "version.json"
    metadata.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(build_info.BudgetPalPathRegistry, "build_metadata_file", lambda: metadata)
    monkeypatch.setattr(build_info, "_package_version", lambda: "0.0.0")

    info = build_info.load_build_info()

    assert info.version == "v1.2.3"
    assert info.commit == "abc1234"
    assert info.built_at_utc == "2026-04-10T12:00:00Z"


def test_load_build_info_falls_back_to_package_version(monkeypatch) -> None:
    monkeypatch.setattr(build_info.BudgetPalPathRegistry, "build_metadata_file", lambda: None)
    monkeypatch.setattr(build_info, "_package_version", lambda: "9.9.9")

    info = build_info.load_build_info()

    assert info.version == "9.9.9"
    assert info.commit == "unknown"
    assert info.built_at_utc == "unknown"
