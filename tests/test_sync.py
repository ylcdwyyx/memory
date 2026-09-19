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
    # 工具目录先存在，才允许部署（新语义：不存在则跳过，见后面的 test_skips_*）
    (tmp_path / "out").mkdir()
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
    assert not any(result.skipped for result in results)


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


def test_skips_target_when_tool_dir_missing(tmp_path: Path) -> None:
    source = write(tmp_path / "source.md", "内容")
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "absent_tool/AGENTS.md"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config)

    assert results[0].skipped is True
    assert results[0].changed is False
    assert results[0].created is False
    # 关键：不能替没装工具把目录建出来
    assert not (tmp_path / "absent_tool").exists()
    assert "[未部署]" in results[0].render_message()
    assert source.exists()


def test_tool_dir_allows_creating_nested_subdirs(tmp_path: Path) -> None:
    write(tmp_path / "source.md", "内容")
    (tmp_path / "tool").mkdir()
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "tool/deep/nested/AGENTS.md"
tool_dir = "tool"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config)

    assert results[0].skipped is False
    assert results[0].created is True
    assert (tmp_path / "tool/deep/nested/AGENTS.md").read_text(encoding="utf-8") == "内容\n"


def test_explicit_tool_dir_missing_skips_nested_target(tmp_path: Path) -> None:
    write(tmp_path / "source.md", "内容")
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "absent/deep/AGENTS.md"
tool_dir = "absent"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config)

    assert results[0].skipped is True
    assert not (tmp_path / "absent").exists()


def test_dry_run_reports_skip_without_creating_tool_dir(tmp_path: Path) -> None:
    write(tmp_path / "source.md", "内容")
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "absent/AGENTS.md"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config, dry_run=True)

    assert results[0].skipped is True
    assert results[0].dry_run is True
    assert not (tmp_path / "absent").exists()


def test_tool_dir_resolved_relative_to_config(tmp_path: Path) -> None:
    write(tmp_path / "source.md", "内容")
    config_dir = tmp_path / "cfg"
    (config_dir / "tool").mkdir(parents=True)
    config = config_dir / "config.toml"
    config.write_text(
        """
source = "../source.md"

[[targets]]
path = "tool/AGENTS.md"
tool_dir = "tool"
""".strip(),
        encoding="utf-8",
    )

    results = sync_memories(config)

    assert results[0].skipped is False
    assert (config_dir / "tool/AGENTS.md").exists()


def test_tool_dir_must_be_string(tmp_path: Path) -> None:
    write(tmp_path / "source.md", "内容")
    config = tmp_path / "config.toml"
    config.write_text(
        """
source = "source.md"

[[targets]]
path = "out/AGENTS.md"
tool_dir = 123
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        sync_memories(config)


def test_shipped_windows_config_tool_dir_is_ancestor_of_path() -> None:
    """真实配置里每个目标的 tool_dir 都必须是 path 的祖先（或等于其父目录）。"""
    config = Path(sync_module.__file__).resolve().parents[2] / "memory_targets_windows.toml"
    _, _, targets = sync_module._load_config(config)

    assert targets
    for target in targets:
        assert target.tool_dir.is_absolute(), target.path
        assert target.tool_dir in target.path.parents, target.path
