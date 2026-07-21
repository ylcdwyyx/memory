[CmdletBinding()]
param(
    [ValidateSet("fast", "full", "e2e")]
    [string]$Scope = "full"
)

# 跨项目 Python 验收模板。当前调用方：wechat、wa、business、alibaba。
# 复制到项目 scripts\verify.ps1 后即可使用；项目级脚本可按需补充 E2E 命令。
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到项目虚拟环境：$python"
}

$env:UV_CACHE_DIR = Join-Path $projectRoot ".uv-cache"

function Invoke-ProjectPython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & uv run --python $python python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "命令失败（退出码 $LASTEXITCODE）：python $($Arguments -join ' ')"
    }
}

Push-Location $projectRoot
try {
    Write-Host "== 验收：Python 语法检查 ==" -ForegroundColor Cyan
    $pythonFiles = @(rg --files -g "*.py" -g "!.venv/**" -g "!archive/**" -g "!latest_images/**" -g "!downloads/**")
    if ($pythonFiles.Count -eq 0) {
        throw "未找到 Python 文件"
    }
    Invoke-ProjectPython -m py_compile @pythonFiles

    if ($Scope -eq "fast") {
        Write-Host "== 局部自动验收通过 ==" -ForegroundColor Green
        exit 0
    }

    Write-Host "== 验收：完整 pytest ==" -ForegroundColor Cyan
    $testTargets = @(rg --files -g "test_*.py" -g "*_test.py" -g "!.venv/**" -g "!archive/**" |
        Where-Object { $_ -match "^(tests|test)[\\/]" -or $_ -match "[\\/]tests[\\/]" })
    if ($testTargets.Count -eq 0) {
        throw "未找到受管理的测试文件（tests/ 或 test/）；请先补充测试目录或项目级验证脚本。"
    }
    Invoke-ProjectPython -m pytest -q @testTargets

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
