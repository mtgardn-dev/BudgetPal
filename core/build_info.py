from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from core.path_registry import BudgetPalPathRegistry


@dataclass(frozen=True)
class BuildInfo:
    version: str
    commit: str
    built_at_utc: str


def _package_version() -> str:
    try:
        return package_version("budgetpal")
    except PackageNotFoundError:
        return "0.1.0"


def load_build_info() -> BuildInfo:
    info = BuildInfo(version=_package_version(), commit="unknown", built_at_utc="unknown")
    metadata_path = BudgetPalPathRegistry.build_metadata_file()
    if not metadata_path:
        return info

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return info

    return BuildInfo(
        version=str(payload.get("build_tag") or info.version),
        commit=str(payload.get("commit") or info.commit),
        built_at_utc=str(payload.get("built_at_utc") or info.built_at_utc),
    )
