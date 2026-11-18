# Fails unless the file has a trusted SHA-256 Authenticode signature and an RFC 3161 timestamp.
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Target
)

$ErrorActionPreference = "Stop"

function Find-SignTool {
    if ($env:TAURI_WINDOWS_SIGNTOOL_PATH -and (Test-Path -LiteralPath $env:TAURI_WINDOWS_SIGNTOOL_PATH)) {
        return $env:TAURI_WINDOWS_SIGNTOOL_PATH
    }
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $roots = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots" -Name KitsRoot10 -ErrorAction SilentlyContinue
    if (-not $roots) {
        return $null
    }
    $bin = Join-Path $roots.KitsRoot10 "bin"
    $arch = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
    $kits = Get-ChildItem -Path $bin -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
    foreach ($kit in $kits) {
        $candidate = Join-Path $kit.FullName "$arch\signtool.exe"
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

if (-not (Test-Path -LiteralPath $Target)) {
    Write-Error "Signature verification stopped. The installer was not found."
    exit 1
}
$signtool = Find-SignTool
if (-not $signtool) {
    Write-Error "Signature verification stopped. signtool.exe was not found."
    exit 1
}

$output = & $signtool verify /pa /v $Target 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Error "Signature verification failed."
    exit 1
}
if ($output -notmatch "sha256") {
    Write-Error "Signature verification failed. The file is not SHA-256 signed."
    exit 1
}
if ($output -notmatch "timestamp") {
    Write-Error "Signature verification failed. The signature has no timestamp."
    exit 1
}
foreach ($line in $output -split "`r?`n") {
    if ($line -match "Issued to:") {
        Write-Output $line.Trim()
    }
}
Write-Output "Signature and timestamp verified."
