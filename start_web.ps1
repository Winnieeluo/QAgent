$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "demo-repo\.git"))) {
  python (Join-Path $PSScriptRoot "create_demo_repo.py") --out (Join-Path $PSScriptRoot "demo-repo")
  if ($LASTEXITCODE -ne 0) { throw "Synthetic demo repository creation failed" }
}
Write-Host "QAAgent: http://127.0.0.1:8765/"
Write-Host "按 Ctrl+C 停止本地服务。"
python -m web.app
