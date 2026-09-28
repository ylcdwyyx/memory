from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅供类型检查器与 IDE 解析，运行时不触发导入
    from .sync import DEFAULT_CONFIG, SyncResult, TargetConfig, main, sync_memories

__all__ = [
    "DEFAULT_CONFIG",
    "SyncResult",
    "TargetConfig",
    "main",
    "sync_memories",
]


def __getattr__(name: str):
    # 惰性转发：避免 import memory_sync 时就把 .sync 放进 sys.modules，
    # 否则 `python -m memory_sync.sync` 会触发 runpy 的 RuntimeWarning。
    if name in __all__:
        from . import sync

        return getattr(sync, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
