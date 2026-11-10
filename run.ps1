# ============================================================
#  一键启动（Windows PowerShell）
#  作者：贾皓杰 (JHJ)
#
#  第一次运行会：建虚拟环境 -> 装依赖 -> 复制 .env -> 启动服务
#  之后直接再运行一次就启动
#
#  用法：
#    .\run.ps1
# ============================================================

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

# 1. 虚拟环境
$venv = Join-Path $Root ".venv"
if (-not (Test-Path -LiteralPath $venv)) {
    Write-Host "==> 创建虚拟环境（只需要一次）" -ForegroundColor Yellow
    python -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"

# 2. 依赖
$flag = Join-Path $venv ".deps-ok"
if (-not (Test-Path -LiteralPath $flag)) {
    Write-Host "==> 安装依赖（第一次比较慢）" -ForegroundColor Yellow
    & $py -m pip install --upgrade pip -q
    & $py -m pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "依赖安装失败，请检查网络或 Python 版本" }
    New-Item -ItemType File -Force -Path $flag | Out-Null
}

# 3. 配置文件
$envFile = Join-Path $Root ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $Root ".env.example") -Destination $envFile
    Write-Host "==> 已生成 .env（要接大模型请把 AI_API_KEY 填上）" -ForegroundColor Yellow
}

# 4. 启动
Write-Host ""
Write-Host "接口文档: http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "默认账号: admin / Jhj@123456" -ForegroundColor Green
Write-Host ""
& $py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
