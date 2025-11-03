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
DEFAULT_CONFIG = _MODULE_DIR.parents[1] / "memory_targets.toml"

RUNNING_ON_WINDOWS = sys.platform.startswith("win")
RUNNING_ON_WSL = (not RUNNING_ON_WINDOWS) and "microsoft" in platform.release().lower()

# 默认内联记忆内容，用户可直接编辑此常量
MEMORY_SOURCE = """始终保持回答中文,代码注释也中文
如果生成了文件作为工作的结果,请使用默认应用打开以方便检查(每次只打开一个最重要的文件)
如果任务比较复杂或任务重,先列出步骤让我确认而不是直接开干
展开工作前先检查当前目录如果不是 Git 仓库,如非,git init并马上保存一次,代码修改之后存档git
删除文件一定要告知
使用Chrome DevTools MCP或者写playwright脚本时,接管9336端口的chrome实例,复用现有标签页而不是新开标签页
最常用的mcp服务是Chrome DevTools MCP, 他是一个Model Context Protocol服务器，主要功能是让MCP客户端能够检查和调试浏览器实例
每个项目要有readme,里面要包含项目文件的描述
保持项目结构清晰简洁, 删除调试文件
遇到的调试错误在总结时指出来
脚本默认以无参数运行
Chrome DevTools MCP是你查你看浏览器的眼睛,在写playwright时要多用它
python:
    - 用uv管理 Python, uv pip安装依赖
    - 生成或修改的 Python 脚本马上运行并检查是否达到预期!!!!
    - 所有参数都有非空默认值
    - 若需要定位默认配置或资源文件，统一通过 Path(__file__).resolve() 向上定位到项目根目录，再拼接目标文件，避免依赖执行时的当前工作目录
如果遇到失败(没有达到预期),列出整个链路并分析有可能的问题点
"""

_INLINE_SOURCE_SENTINELS = {":inline", "inline", ":embedded", "embedded"}


@dataclasses.dataclass(slots=True)
class TargetConfig:
    path: Path
    header: Optional[str] = None
    footer: Optional[str] = None
    encoding: str = "utf-8"


@dataclasses.dataclass(slots=True)
class SyncResult:
    path: Path
    changed: bool
    dry_run: bool
    created: bool

    def render_message(self) -> str:
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
    elif isinstance(raw_source, str) and raw_source.strip().lower() in _INLINE_SOURCE_SENTINELS:
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

        targets.append(
            TargetConfig(
                path=_resolve_path(path.parent, Path(raw_path)),
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
    new_content = _compose_content(payload, target.header, target.footer)
    existing: Optional[str] = None
    if target.path.is_file():
        existing = target.path.read_text(encoding=target.encoding)

    changed = existing != new_content
    created = existing is None

    if not dry_run and changed:
        target.path.parent.mkdir(parents=True, exist_ok=True)
        target.path.write_text(new_content, encoding=target.encoding)

    return SyncResult(path=target.path, changed=changed, dry_run=dry_run, created=created)


def sync_memories(
    config: Path = DEFAULT_CONFIG,
    *,
    override_source: Optional[Path] = None,
    dry_run: bool = False,
) -> list[SyncResult]:
    config_path = config if config.is_absolute() else config.resolve()
    source_path, use_inline_source, targets = _load_config(config_path)

    if override_source is not None:
        source_path = override_source if override_source.is_absolute() else override_source.resolve()
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
