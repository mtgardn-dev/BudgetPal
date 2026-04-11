from __future__ import annotations

from core.services.help_service import HelpService


def test_get_topic_path_uses_registry_help_root(monkeypatch, tmp_path) -> None:
    help_root = tmp_path / "help"
    help_root.mkdir(parents=True)
    index = help_root / "index.html"
    index.write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr("core.services.help_service.BudgetPalPathRegistry.help_root", lambda: help_root)
    service = HelpService()

    path = service.get_topic_path("index")
    assert path == index.resolve()


def test_open_topic_returns_browser_result(monkeypatch, tmp_path) -> None:
    help_root = tmp_path / "help"
    help_root.mkdir(parents=True)
    page = help_root / "settings_reference.html"
    page.write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr("core.services.help_service.BudgetPalPathRegistry.help_root", lambda: help_root)
    monkeypatch.setattr("core.services.help_service.webbrowser.open", lambda _uri: True)
    service = HelpService()

    assert service.open_topic("settings_reference")


def test_get_help_path_rejects_parent_traversal(monkeypatch, tmp_path) -> None:
    help_root = tmp_path / "help"
    help_root.mkdir(parents=True)

    monkeypatch.setattr("core.services.help_service.BudgetPalPathRegistry.help_root", lambda: help_root)
    service = HelpService()

    try:
        service.get_help_path("../secret.txt")
    except ValueError as exc:
        assert "relative path" in str(exc)
    else:
        raise AssertionError("Expected ValueError for traversal path")
