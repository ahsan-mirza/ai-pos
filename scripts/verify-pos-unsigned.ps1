# Fails unless the file has no Authenticode signature.
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Target
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Target)) {
    Write-Error "Unsigned verification stopped. The file was not found."
    exit 1
}

$signature = Get-AuthenticodeSignature -LiteralPath $Target
if ($signature.Status -ne "NotSigned") {
    Write-Error "Unsigned verification failed. $($signature.Status) is not an unsigned file."
    exit 1
}
Write-Output "UNSIGNED NotSigned"
