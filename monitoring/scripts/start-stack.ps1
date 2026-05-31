<#
.SYNOPSIS
  Start Prometheus + Grafana for transcript agent monitoring.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
docker compose up -d
Write-Host ""
Write-Host "Grafana:    http://localhost:3001"
Write-Host "Prometheus: http://localhost:9090"
Write-Host ""
Write-Host "Run the agent with metrics enabled:"
Write-Host '  $env:AGENT_METRICS_ENABLED = "true"'
Write-Host "  adk run code_local"
Write-Host ""
Write-Host "Agent metrics: http://127.0.0.1:9464/metrics"
