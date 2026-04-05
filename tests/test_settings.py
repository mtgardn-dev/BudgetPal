from __future__ import annotations

from core.settings import BudgetPalSettings


def test_load_returns_defaults_when_initial_save_fails(tmp_path, monkeypatch) -> None:
    mgr = BudgetPalSettings(path=tmp_path / "budgetpal_config.json")

    def raise_oserror(_settings):
        raise OSError("write blocked")

    monkeypatch.setattr(mgr, "save", raise_oserror)
    loaded = mgr.load()

    assert loaded["database"]["path"] == ""
    assert loaded["logging"]["level"] == "INFO"
    assert loaded["ui"]["last_import_dir"] == ""


def test_load_returns_merged_when_writeback_fails(tmp_path, monkeypatch) -> None:
    cfg_path = tmp_path / "budgetpal_config.json"
    cfg_path.write_text('{"logging": {"level": "DEBUG"}}', encoding="utf-8")

    mgr = BudgetPalSettings(path=cfg_path)

    def raise_oserror(_settings):
        raise OSError("write blocked")

    monkeypatch.setattr(mgr, "save", raise_oserror)
    loaded = mgr.load()

    assert loaded["logging"]["level"] == "DEBUG"
    assert "ui" in loaded
    assert "window" in loaded["ui"]
    assert "last_import_dir" in loaded["ui"]
