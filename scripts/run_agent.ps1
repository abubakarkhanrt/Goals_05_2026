<#
.SYNOPSIS
  Run the transcript agent with local Ollama or cloud Gemini.

.DESCRIPTION
  ADK does not support `adk run code --local`. Use this wrapper instead:

    .\scripts\run_agent.ps1 -Mode local
    .\scripts\run_agent.ps1 -Mode cloud
    .\scripts\run_agent.ps1 -Mode local -Web

  Equivalent direct ADK commands:
    adk run code_local
    adk run code_cloud
#>
param(
    [ValidateSet("local", "cloud")]
    [string]$Mode = "local",
    [switch]$Web,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassThru
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$AgentFolder = if ($Mode -eq "cloud") { "code_cloud" } else { "code_local" }
$Adk = Join-Path $ProjectRoot "venv\Scripts\adk.exe"
if (-not (Test-Path $Adk)) {
    $Adk = "adk"
}

if ($Web) {
    & $Adk web @PassThru
    Write-Host ""
    Write-Host "In the ADK web UI, select agent: $AgentFolder"
} else {
    & $Adk run $AgentFolder @PassThru
}
