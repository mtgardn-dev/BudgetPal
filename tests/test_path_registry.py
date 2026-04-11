from __future__ import annotations

import sys

from core.path_registry import BudgetPalPathRegistry


def test_runtime_root_uses_meipass_when_frozen(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert BudgetPalPathRegistry.runtime_root() == tmp_path.resolve()


def test_writable_root_uses_project_root_when_not_frozen(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert BudgetPalPathRegistry.writable_root() == BudgetPalPathRegistry.project_root()
    assert BudgetPalPathRegistry.project_root().name == "BudgetPal"


def test_config_file_is_under_project_config_when_not_frozen(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    config_path = BudgetPalPathRegistry.config_file()
    assert config_path.parent == BudgetPalPathRegistry.project_root() / "config"
    assert config_path.name == "budgetpal_config.json"


def test_writable_root_uses_windows_appdata_when_frozen(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    root = BudgetPalPathRegistry.writable_root()
    assert root == (tmp_path / "LocalAppData" / "BudgetPal")
    assert root.exists()


def test_bundled_config_template_prefers_runtime_when_frozen(tmp_path, monkeypatch) -> None:
    runtime = tmp_path / "meipass"
    config_dir = runtime / "config"
    config_dir.mkdir(parents=True)
    template = config_dir / "budgetpal_config.example.json"
    template.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(runtime), raising=False)

    resolved = BudgetPalPathRegistry.bundled_config_template_file()
    assert resolved == template.resolve()


def test_build_metadata_file_returns_runtime_version_json(tmp_path, monkeypatch) -> None:
    runtime = tmp_path / "meipass"
    metadata = runtime / "bootstrap_data" / "version.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(runtime), raising=False)

    resolved = BudgetPalPathRegistry.build_metadata_file()
    assert resolved == metadata.resolve()


def test_logo_image_file_prefers_runtime_image_when_frozen(tmp_path, monkeypatch) -> None:
    runtime = tmp_path / "meipass"
    images_dir = runtime / "images"
    images_dir.mkdir(parents=True)
    logo = images_dir / "BudgetPal_Logo_Lg.png"
    logo.write_bytes(b"png")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(runtime), raising=False)

    resolved = BudgetPalPathRegistry.logo_image_file()
    assert resolved == logo.resolve()


def test_help_root_prefers_runtime_help_when_frozen(tmp_path, monkeypatch) -> None:
    runtime = tmp_path / "meipass"
    help_dir = runtime / "help"
    help_dir.mkdir(parents=True)
    (help_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(runtime), raising=False)

    resolved = BudgetPalPathRegistry.help_root()
    assert resolved == help_dir.resolve()
