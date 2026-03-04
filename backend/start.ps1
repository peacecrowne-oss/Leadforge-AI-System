# Development startup script for LeadForge backend.
# Reads backend/.env and sets each KEY=VALUE as an environment variable,
# then launches uvicorn with --reload.
#
# Usage (from repo root or backend/):
#   .\backend\start.ps1
#   # or, from inside backend/:
#   .\start.ps1

$envFile = Join-Path $PSScriptRoot ".env"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Length -eq 2) {
                [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
                Write-Host "  env: $($parts[0].Trim()) set"
            }
        }
    }
} else {
    Write-Warning ".env not found at $envFile - JWT_SECRET may be unset"
}

Set-Location $PSScriptRoot
uvicorn main:app --reload
