# Remove stale ADK agent folders from the hyphenated rename (code-local → code_local).
# Stop `adk web` / `adk run` first so session.db is not locked.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "..")

foreach ($stale in @("code-local", "code-cloud", ".code-local-stale")) {
    $path = Join-Path (Get-Location) $stale
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path
        Write-Host "Removed $stale"
    }
}

Write-Host "Done. Start the agent with: adk web  (select code_local or code_cloud)"
