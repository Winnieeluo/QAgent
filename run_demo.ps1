param(
  [string]$Base = "main",
  [switch]$WithPrAgent
)
$ErrorActionPreference = "Stop"
$demoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Join-Path $demoRoot "demo-repo"
$artifacts = Join-Path $demoRoot "artifacts"
if (-not (Test-Path -LiteralPath (Join-Path $repo ".git"))) {
  python (Join-Path $demoRoot "create_demo_repo.py") --out $repo
  if ($LASTEXITCODE -ne 0) { throw "Synthetic demo repository creation failed" }
}
New-Item -ItemType Directory -Path $artifacts -Force | Out-Null
python (Join-Path $demoRoot "qa_agent.py") --repo $repo --base $Base --out $artifacts
if ($LASTEXITCODE -ne 0) { throw "Deterministic QA failed" }
if ($WithPrAgent) {
  $env:CONFIG__GIT_PROVIDER = "local"
  Push-Location $repo
  try {
    python -m pr_agent.cli --pr_url $Base review
    if ($LASTEXITCODE -ne 0) { throw "PR-Agent failed" }
  } finally {
    Pop-Location
  }
}
Write-Host "Review evidence: $artifacts"
