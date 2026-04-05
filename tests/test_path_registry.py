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
