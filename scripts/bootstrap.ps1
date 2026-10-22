$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command '$Name' was not found on PATH."
  }
}

# Each app reads .env.development on this machine (.env.dev / .env.production elsewhere).
# Returns $true only when the file was created from the template, so its secrets still need generating.
function Ensure-DevelopmentEnv([string]$App) {
  $Example = "$App\.env.development.example"
  $Destination = "$App\.env.development"
  $Legacy = "$App\.env"
  if (-not (Test-Path $Example)) {
    throw "Missing env template: $Example"
  }
  if (Test-Path $Destination) {
    Write-Host "Kept existing $Destination"
    return $false
  }
  if (Test-Path $Legacy) {
    Move-Item $Legacy $Destination
    Write-Host "Moved $Legacy to $Destination (values kept)"
    return $false
  }
  Copy-Item $Example $Destination
  Write-Host "Created $Destination"
  return $true
}

Require-Command "node"
Require-Command "pnpm"
Require-Command "python"

Write-Host "Installing workspace packages..."
pnpm install

$ApiEnvCreated = Ensure-DevelopmentEnv "apps\api"
Ensure-DevelopmentEnv "apps\web" | Out-Null
Ensure-DevelopmentEnv "apps\desktop" | Out-Null
if ($ApiEnvCreated) {
  Write-Host "Generating secrets for the new apps\api\.env.development..."
  node ".\scripts\generate-secrets.mjs"
  Write-Host "Set DATABASE_URL in apps\api\.env.development before migrating."
}

$VenvPython = Join-Path $Root "apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Host "Creating API virtualenv..."
  python -m venv "apps\api\.venv"
}

Write-Host "Installing API dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r "apps\api\requirements.txt" -r "apps\api\requirements-dev.txt"

Write-Host "Generating desktop icons..."
node ".\scripts\generate-icon.mjs"

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Next:"
Write-Host "  docker compose up -d   (skip if PostgreSQL already runs on 5432)"
Write-Host "  pnpm --filter @ai-pos/api migrate"
Write-Host "  pnpm --filter @ai-pos/api seed"
Write-Host "  pnpm dev"
