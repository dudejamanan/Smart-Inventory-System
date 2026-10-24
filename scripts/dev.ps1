param([switch]$Hardware)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3.11 -m venv .venv }
$env:PYTHONPATH = Join-Path $projectRoot 'backend'
if ($Hardware) { & '.\.venv\Scripts\python.exe' -m app } else { & '.\.venv\Scripts\python.exe' -m app --simulate }
