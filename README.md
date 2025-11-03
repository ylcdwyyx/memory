## 项目简介

memory-sync-manager 通过 `src/memory_sync/sync.py` 内置的 `MEMORY_SOURCE` 常量，将统一维护的用户记忆同步到多款 AI 编程工具的专属记忆文件，避免重复维护；若需要，也可以改为读取外部源文件。

## 文件结构

- `.gitignore`：忽略本地虚拟环境与临时缓存。
- `pyproject.toml`：uv 项目信息与可执行脚本定义。
- `uv.lock`：由 uv 生成的精确依赖锁文件。
- `memory_source.md`：可选的外部记忆正文示例，如需使用请修改配置指向该文件。
- `memory_targets_windows.toml`：Windows/WSL 环境默认目标配置。
- `memory_targets_macos.toml`：macOS 环境默认目标配置。
- `src/memory_sync/sync.py`：核心同步脚本与命令行入口，内联 `MEMORY_SOURCE` 供快速编辑。
- `tests/test_sync.py`：针对同步流程的 pytest 覆盖。
- `examples/`：示例输出目录，实际运行时会在此生成示例工具的记忆文件。

## 快速开始

1. 根据自身需求编辑 `src/memory_sync/sync.py` 顶部的 `MEMORY_SOURCE` 常量；若更偏好维护独立文件，可在对应的 `memory_targets_*.toml` 中把 `source` 改成外部路径。
2. 修改当前系统会使用的配置文件（Windows/WSL 对应 `memory_targets_windows.toml`，macOS 对应 `memory_targets_macos.toml`），将 `path` 指向各个工具的用户记忆文件；可选字段 `header`、`footer` 用于附加前后缀。
   - 在 WSL 中可以直接填写 Windows 风格路径（如 `C:/Users/...`），脚本会自动转换为 `/mnt/c/...`。
3. 执行同步：

```bash
uv run python -m memory_sync.sync
```

常用参数：

- `--config <path>`：指定其他配置文件。
- `--source <path>`：临时指定不同的源文件。
- `--dry-run`：预览需要更新的文件，不真实写入。
- `--quiet`：只在有变更时打印结果。

## 开发与测试

运行单元测试：

```bash
uv run pytest
```

修改脚本后请立即执行测试，确保同步逻辑可靠。
