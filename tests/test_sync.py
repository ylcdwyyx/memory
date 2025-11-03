from __future__ import annotations

from pathlib import Path

import pytest

from memory_sync.sync import sync_memories
import memory_sync.sync as sync_module


def write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_default_config_points_to_project_root() -> None:
    module_root = Path(sync_module.__file__).resolve().parents[2]
    assert sync_module.DEFAULT_CONFIG.parent == module_root
    assert sync_module.DEFAULT_CONFIG.name in {
        "memory_targets_windows.toml",
        "memory_targets_macos.toml",
        "memory_targets.toml",
    }
    assert sync_module.DEFAULT_CONFIG.is_absolute()
    assert sync_module.DEFAULT_CONFIG.exists()


def test_sync_creates_and_updates_targets(tmp_path: Path) -> None:
    source = write(tmp_path / "source.md", "核心内容")
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "out/a.md"
header = "# Header"

[[targets]]
path = "out/b.txt"
footer = "Footer"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config)

    a_text = (tmp_path / "out/a.md").read_text(encoding="utf-8")
    b_text = (tmp_path / "out/b.txt").read_text(encoding="utf-8")

    assert "# Header\n" in a_text
    assert "核心内容\n" in a_text
    assert "Footer\n" in b_text

    assert all(result.changed for result in results)
    assert all(not result.dry_run for result in results)


def test_dry_run_keeps_original_content(tmp_path: Path) -> None:
    source = write(tmp_path / "source.md", "新的内容")
    target_path = write(tmp_path / "target.txt", "旧内容\n")
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
source = "source.md"

[[targets]]
path = "{target_path.name}"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config, dry_run=True)

    preserved = target_path.read_text(encoding="utf-8")
    assert preserved == "旧内容\n"
    assert results[0].dry_run is True
    assert results[0].changed is True


def test_windows_style_path_translates_to_wsl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sync_module, "RUNNING_ON_WINDOWS", False)
    monkeypatch.setattr(sync_module, "RUNNING_ON_WSL", True)

    source = write(tmp_path / "source.md", "内容")
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "C:/Temp/wsl-test.txt"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config, dry_run=True)

    expected_path = Path("/mnt/c/Temp/wsl-test.txt")
    assert results[0].path == expected_path
    assert results[0].dry_run is True


def test_windows_style_path_keeps_native_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sync_module, "RUNNING_ON_WINDOWS", True)
    monkeypatch.setattr(sync_module, "RUNNING_ON_WSL", False)

    source = write(tmp_path / "source.md", "内容")
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "C:/Temp/wsl-test.txt"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config, dry_run=True)

    expected_path = Path("C:/Temp/wsl-test.txt")
    assert results[0].path == expected_path
    assert results[0].dry_run is True


def test_wsl_unc_path_translates_to_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sync_module, "RUNNING_ON_WINDOWS", False)
    monkeypatch.setattr(sync_module, "RUNNING_ON_WSL", True)

    source = write(tmp_path / "source.md", "WSL")
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "//wsl.localhost/Ubuntu/home/lenovo/claude.md"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config, dry_run=True)

    expected_path = Path("/home/lenovo/claude.md")
    assert results[0].path == expected_path
    assert results[0].dry_run is True


def test_wsl_unc_path_keeps_unc_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sync_module, "RUNNING_ON_WINDOWS", True)
    monkeypatch.setattr(sync_module, "RUNNING_ON_WSL", False)

    source = write(tmp_path / "source.md", "WSL")
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "//wsl.localhost/Ubuntu/home/lenovo/claude.md"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config, dry_run=True)

    expected_path = Path("//wsl.localhost/Ubuntu/home/lenovo/claude.md")
    assert results[0].path == expected_path
    assert results[0].dry_run is True


def test_missing_source_raises(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "missing.md"

[[targets]]
path = "out.txt"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError):
        sync_memories(config)
