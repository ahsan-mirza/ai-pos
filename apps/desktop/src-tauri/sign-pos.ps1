# Signs one AxizPOS binary with the certificate already in the Windows certificate store.
# The thumbprint comes from AXIZPOS_SIGN_THUMBPRINT. The private key is never read from the repo.
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

$thumbprint = ($env:AXIZPOS_SIGN_THUMBPRINT -replace "\s", "")
if ($thumbprint -notmatch "^[0-9A-Fa-f]{40}$") {
    Write-Error "Production signing stopped. AXIZPOS_SIGN_THUMBPRINT must be the certificate thumbprint from the Windows certificate store."
    exit 1
}
if (-not (Test-Path -LiteralPath $Target)) {
    Write-Error "Production signing stopped. The file to sign was not found."
    exit 1
}
$signtool = Find-SignTool
if (-not $signtool) {
    Write-Error "Production signing stopped. signtool.exe was not found. Install the Windows SDK or set TAURI_WINDOWS_SIGNTOOL_PATH."
    exit 1
}

& $signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /sha1 $thumbprint /d "AxizPOS" $Target
if ($LASTEXITCODE -ne 0) {
    Write-Error "Production signing stopped. signtool rejected the file."
    exit $LASTEXITCODE
}
