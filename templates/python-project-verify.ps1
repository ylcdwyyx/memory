[CmdletBinding()]
param(
    [ValidateSet("fast", "full", "e2e")]
    [string]$Scope = "full",

    # 共享调用方（如 wa）以 & 调用本模板时，$PSScriptRoot 指向模板自身目录，
    # 推不出调用方项目根，需显式传入；省略时仍按「模板被复制到 <项目>\scripts\」推导。
    [string]$ProjectRoot = "",

    # 枚举时要跳过的目录前缀（/ 结尾）。项目可在 wrapper 里追加自己的杂物目录
    # （如 wa 的 runtime/、data/），默认值与历史行为一致。
    [string[]]$SkipPrefix = @(".venv/", "archive/", "latest_images/", "downloads/", "node_modules/")
)

# 跨项目 Python 验收模板。当前调用方：wechat、wa、business、alibaba。
# 复制到项目 scripts\verify.ps1 后即可使用；项目级脚本可按需补充 E2E 命令。
$ErrorActionPreference = "Stop"
$projectRoot = if ($ProjectRoot) { $ProjectRoot } else { Split-Path -Parent $PSScriptRoot }
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到项目虚拟环境：$python"
}

$env:UV_CACHE_DIR = Join-Path $projectRoot ".uv-cache"

# 枚举项目文件：优先 ripgrep；未安装 rg 时退回 git 索引，保证验收脚本可移植。
function Get-RepoFiles {
    param(
        [Parameter(Mandatory)][string[]]$Include,
        [string[]]$SkipPrefix = @(".venv/", "archive/", "latest_images/", "downloads/", "node_modules/")
    )
    if (Get-Command rg -ErrorAction SilentlyContinue) {
        $rgArgs = @("--files")
        foreach ($pat in $Include) { $rgArgs += @("-g", $pat) }
        foreach ($pre in $SkipPrefix) { $rgArgs += @("-g", "!$pre**") }
        $out = @(& rg @rgArgs 2>$null)
        if ($LASTEXITCODE -eq 0) { return $out }
    }
    $tracked = @(& git ls-files 2>$null)
    if ($LASTEXITCODE -ne 0 -or $tracked.Count -eq 0) {
        $tracked = @(Get-ChildItem -LiteralPath $projectRoot -Recurse -File -ErrorAction SilentlyContinue |
            ForEach-Object { $_.FullName.Substring($projectRoot.Length).TrimStart([char]92, [char]47) })
    }
    $normalized = @($tracked | ForEach-Object { ($_ -replace '\\', "/") })
    $matched = foreach ($pat in $Include) {
        foreach ($p in $normalized) {
            $name = $p.Substring($p.LastIndexOf("/") + 1)
            if ($name -notlike $pat) { continue }
            $skip = $false
            foreach ($pre in $SkipPrefix) { if ($p.StartsWith($pre)) { $skip = $true; break } }
            if (-not $skip) { $p }
        }
    }
    return @($matched | Sort-Object -Unique)
}

function Invoke-ProjectPython {
    # 注意：这里不能用高级函数 param([string[]]$Arguments + ValueFromRemainingArguments)。
    # PowerShell 会把调用方传入的数组实参折叠成「单个空格连接串」再绑定（2026-11-01
    # 实测，两种调用写法都复现），py_compile 会收到一个整串文件名报 No such file
    # or directory。简单函数用 $args 原样收集、@args 逐元素 splat，实测展开正常。
    & uv run --python $python python @args
    if ($LASTEXITCODE -ne 0) {
        throw "命令失败（退出码 $LASTEXITCODE）：python $($args -join ' ')"
    }
}

Push-Location $projectRoot
try {
    Write-Host "== 验收：Python 语法检查 ==" -ForegroundColor Cyan
    $pythonFiles = @(Get-RepoFiles -Include @("*.py") -SkipPrefix $SkipPrefix)
    if ($pythonFiles.Count -eq 0) {
        throw "未找到 Python 文件"
    }
    # Windows 单条命令行上限 32K：wa 全仓 *.py 数千个，一把传给 uv run 会报
    # 「文件名或扩展名太长」导致 hook 永远失败。按 200 个/批切分逐批编译。
    $batchSize = 200
    for ($i = 0; $i -lt $pythonFiles.Count; $i += $batchSize) {
        $end = [Math]::Min($i + $batchSize - 1, $pythonFiles.Count - 1)
        Invoke-ProjectPython -m py_compile @($pythonFiles[$i..$end])
    }

    if ($Scope -eq "fast") {
        Write-Host "== 局部自动验收通过 ==" -ForegroundColor Green
        exit 0
    }

    Write-Host "== 验收：完整 pytest ==" -ForegroundColor Cyan
    $testTargets = @(Get-RepoFiles -Include @("test_*.py", "*_test.py") -SkipPrefix $SkipPrefix |
        Where-Object { $_ -match "^(tests|test)[\\/]" -or $_ -match "[\\/]tests[\\/]" })
    if ($testTargets.Count -eq 0) {
        throw "未找到受管理的测试文件（tests/ 或 test/）；请先补充测试目录或项目级验证脚本。"
    }
    # 测试文件过千时同样会撞 32K 命令行上限，逐批传给 pytest；
    # 任一批非 0 都会在 Invoke-ProjectPython 里 throw，失败不会被吞。
    for ($i = 0; $i -lt $testTargets.Count; $i += $batchSize) {
        $end = [Math]::Min($i + $batchSize - 1, $testTargets.Count - 1)
        Invoke-ProjectPython -m pytest -q @($testTargets[$i..$end])
    }

    if ($Scope -eq "full") {
        Write-Host "== 自动验收通过 ==" -ForegroundColor Green
        Write-Host "未覆盖：真实 GUI、WPS、外部 API 与消息发送。需要时运行 .\scripts\verify.ps1 -Scope e2e。" -ForegroundColor Yellow
        exit 0
    }

    throw "尚未完成验收：E2E 涉及 GUI/WPS/外部发送，必须执行项目约定的人工真实链路并记录结果；不能用自动化测试替代。"
}
finally {
    Pop-Location
}
