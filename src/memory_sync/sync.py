from __future__ import annotations

import argparse
import dataclasses
import platform
import sys
from pathlib import Path
from typing import Iterable, List, Optional

WINDOWS_DRIVE_PREFIX = "/mnt"
WSL_UNC_PREFIX = "//wsl.localhost/"

try:  # Python 3.11 compatibility
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


_MODULE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _MODULE_DIR.parents[1]

RUNNING_ON_WINDOWS = sys.platform.startswith("win")
RUNNING_ON_WSL = (not RUNNING_ON_WINDOWS) and "microsoft" in platform.release().lower()


def _detect_default_config() -> Path:
    """根据当前运行环境选择默认配置文件，优先使用存在的候选项。"""
    candidates = []
    if RUNNING_ON_WINDOWS or RUNNING_ON_WSL:
        candidates.append(_PROJECT_ROOT / "memory_targets_windows.toml")

    system_name = platform.system().lower()
    if system_name == "darwin":
        candidates.append(_PROJECT_ROOT / "memory_targets_macos.toml")

    candidates.append(_PROJECT_ROOT / "memory_targets.toml")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # 如果都不存在，仍返回第一个候选项，交由后续逻辑抛出更明确的错误
    return candidates[0]


DEFAULT_CONFIG = _detect_default_config()

# 默认内联记忆内容，用户可直接编辑此常量
MEMORY_SOURCE = """提出你认为更好的建议
"""

_INLINE_SOURCE_SENTINELS = {":inline", "inline", ":embedded", "embedded"}


@dataclasses.dataclass(slots=True)
class TargetConfig:
    path: Path
    # 判断「该工具是否装在这台机器上」的锚点目录：不存在就整个目标跳过，不建任何目录。
    # 默认取 path 的父目录；当目标文件位于工具内部的深层子目录时（如
    # ~/.trae-cn/user_rules/xxx.md、~/.accio/accounts/<id>/agents/<did>/agent-core/MEMORY.md），
    # 应在配置里显式把 tool_dir 指到工具根目录，这样工具在、子目录缺失时才允许按需创建。
    tool_dir: Path
    header: Optional[str] = None
    footer: Optional[str] = None
    encoding: str = "utf-8"


@dataclasses.dataclass(slots=True)
class SyncResult:
    path: Path
    changed: bool
    dry_run: bool
    created: bool
    skip_reason: Optional[str] = None

    @property
    def skipped(self) -> bool:
        return self.skip_reason is not None

    def render_message(self) -> str:
        if self.skipped:
            return f"[未部署] {self.path} — {self.skip_reason}"
        if self.dry_run and self.changed:
            return f"[dry-run] {self.path} 将被更新"
        if self.dry_run:
            return f"[dry-run] {self.path} 无需更新"
        if self.created:
            return f"[写入] {self.path} 已创建"
        if self.changed:
            return f"[写入] {self.path} 已更新"
        return f"[跳过] {self.path} 已是最新"


def _ensure_trailing_newline(block: str) -> str:
    return block if block.endswith("\n") else block + "\n"


def _compose_content(body: str, header: Optional[str], footer: Optional[str]) -> str:
    parts: List[str] = []
    if header:
        parts.append(_ensure_trailing_newline(header))
    parts.append(_ensure_trailing_newline(body))
    if footer:
        parts.append(_ensure_trailing_newline(footer))
    return "".join(parts)


def _load_config(path: Path) -> tuple[Optional[Path], bool, list[TargetConfig]]:
    if not path.is_file():
        raise FileNotFoundError(f"配置文件 {path} 不存在")

    data = tomllib.loads(path.read_text(encoding="utf-8"))

    raw_source = data.get("source")
    use_inline_source = False
    source_path: Optional[Path] = None

    if raw_source is None:
        use_inline_source = True
    elif (
        isinstance(raw_source, str)
        and raw_source.strip().lower() in _INLINE_SOURCE_SENTINELS
    ):
        use_inline_source = True
    elif isinstance(raw_source, str):
        source_path = _resolve_path(path.parent, Path(raw_source))
    else:
        raise ValueError("配置文件中的 source 字段必须是字符串或省略")

    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("配置文件中的 targets 至少需要包含一个条目")

    targets: list[TargetConfig] = []
    for idx, entry in enumerate(raw_targets, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"targets 第 {idx} 条不是合法的对象")
        raw_path = entry.get("path")
        if not raw_path:
            raise ValueError(f"targets 第 {idx} 条缺少 path 字段")

        header = entry.get("header")
        footer = entry.get("footer")
        encoding = entry.get("encoding", "utf-8")
        raw_tool_dir = entry.get("tool_dir")
        if raw_tool_dir is not None and not isinstance(raw_tool_dir, str):
            raise ValueError(f"targets 第 {idx} 条的 tool_dir 必须是字符串")

        target_path = _resolve_path(path.parent, Path(raw_path))
        tool_dir = (
            _resolve_path(path.parent, Path(raw_tool_dir))
            if raw_tool_dir
            else target_path.parent
        )

        targets.append(
            TargetConfig(
                path=target_path,
                tool_dir=tool_dir,
                header=header,
                footer=footer,
                encoding=encoding,
            )
        )

    return source_path, use_inline_source, targets


def _resolve_path(base: Path, candidate: Path) -> Path:
    text = str(candidate)
    if _looks_like_windows_path(text):
        if RUNNING_ON_WINDOWS:
            return Path(text)
        if RUNNING_ON_WSL:
            return _to_wsl_path(text)
        return Path(text)
    if _looks_like_wsl_unc_path(text):
        if RUNNING_ON_WINDOWS:
            return Path(text)
        if RUNNING_ON_WSL:
            return _from_wsl_unc_path(text)
        return Path(text)
    if candidate.is_absolute():
        return candidate
    return (base / candidate).resolve()


def _looks_like_windows_path(text: str) -> bool:
    return len(text) >= 3 and text[1] == ":" and text[2] in ("/", "\\")


def _to_wsl_path(text: str) -> Path:
    drive = text[0].lower()
    rest = text[3:].lstrip("\\/")
    unixified = rest.replace("\\", "/")
    return Path(WINDOWS_DRIVE_PREFIX) / drive / unixified


def _looks_like_wsl_unc_path(text: str) -> bool:
    normalized = text.replace("\\", "/")
    return normalized.lower().startswith(WSL_UNC_PREFIX)


def _from_wsl_unc_path(text: str) -> Path:
    normalized = text.replace("\\", "/")
    suffix = normalized[len(WSL_UNC_PREFIX) :].lstrip("/")
    if not suffix:
        raise ValueError(f"WSL UNC 路径 {text} 缺少发行版与实际路径")

    parts = suffix.split("/", 1)
    if len(parts) == 1:
        raise ValueError(f"WSL UNC 路径 {text} 缺少实际路径部分")

    _, inner_path = parts
    if not inner_path:
        raise ValueError(f"WSL UNC 路径 {text} 缺少实际路径部分")

    return Path("/") / inner_path


def _sync_single(target: TargetConfig, payload: str, dry_run: bool) -> SyncResult:
    # 工具没装就整个跳过：既不写文件，也不替它把目录建出来（否则会在机器上留下空壳配置目录）
    if not target.tool_dir.is_dir():
        return SyncResult(
            path=target.path,
            changed=False,
            dry_run=dry_run,
            created=False,
            skip_reason=f"工具不存在（{target.tool_dir} 缺失）",
        )

    new_content = _compose_content(payload, target.header, target.footer)
    existing: Optional[str] = None
    if target.path.is_file():
        existing = target.path.read_text(encoding=target.encoding)

    changed = existing != new_content
    created = existing is None

    if not dry_run and changed:
        target.path.parent.mkdir(parents=True, exist_ok=True)
        target.path.write_text(new_content, encoding=target.encoding)

    return SyncResult(
        path=target.path, changed=changed, dry_run=dry_run, created=created
    )


def sync_memories(
    config: Path = DEFAULT_CONFIG,
    *,
    override_source: Optional[Path] = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    config_path = config if config.is_absolute() else config.resolve()
    source_path, use_inline_source, targets = _load_config(config_path)

    if override_source is not None:
        source_path = (
            override_source
            if override_source.is_absolute()
            else override_source.resolve()
        )
        use_inline_source = False

    if use_inline_source and override_source is None:
        body = MEMORY_SOURCE
    else:
        if source_path is None:
            raise ValueError("配置文件缺少 source 字段，且未启用内联内容")
        if not source_path.is_file():
            raise FileNotFoundError(f"源文件 {source_path} 不存在")
        body = source_path.read_text(encoding="utf-8")

    results = [_sync_single(target, body, dry_run) for target in targets]
    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步多款 AI 工具的用户记忆文件")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="配置文件路径（默认：memory_targets.toml）",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="覆盖配置中的源记忆文件路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅显示将要同步的文件，而不实际写入",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="安静模式，仅在发生变更时输出",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        results = sync_memories(
            args.config,
            override_source=args.source,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # pylint: disable=broad-except
        parser.error(str(exc))
        return 2

    for result in results:
        message = result.render_message()
        if args.quiet and not result.changed:
            continue
        print(message)

    if any(result.changed for result in results):
        return 1 if args.dry_run else 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
