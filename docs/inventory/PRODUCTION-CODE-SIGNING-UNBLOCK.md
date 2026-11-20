# Production code-signing unblock

Date: 20 November 2026. Status: **OPTIONAL — NOT CONFIGURED**.

A missing certificate no longer stops the build. The unsigned procedure is `UNSIGNED-WINDOWS-RELEASE-POLICY.md`. This note is how to turn signing back on. No thumbprint was invented.

## What was checked

- `AXIZPOS_SIGN_THUMBPRINT` is unset in the build environment.
- `Cert:\CurrentUser\My` and `Cert:\LocalMachine\My` contain no certificate with the code-signing extended key usage `1.3.6.1.5.5.7.3.3`.
- The repository has no Azure Trusted Signing profile, HSM, or other managed signing provider. The release workflow signs with the Windows certificate selected by `AXIZPOS_SIGN_THUMBPRINT`.
- The publisher recorded for the installer is `AxizPOS`. The timestamp server is `http://timestamp.digicert.com`.

The certificates present are device, client-authentication, or content certificates. None is an authorized AxizPOS code-signing certificate, and none was used.

## Who can clear it

The repository does not name a person. The owner is whoever administers the GitHub Actions secret `AXIZPOS_SIGN_THUMBPRINT` for `.github/workflows/release-pos.yml` and the Windows certificate store that `signtool` will use. `TAURI_WINDOWS_SIGNTOOL_PATH` is the optional second secret when `signtool.exe` is not on the default Windows SDK path. The publish job uses the GitHub environment named `production`.

## What to provide

| Requirement | Value |
|---|---|
| Certificate type | Authenticode code-signing certificate |
| Publisher | AxizPOS, matching the organization allowed to publish the product |
| Extended key usage | Code signing, `1.3.6.1.5.5.7.3.3` |
| Validity | Current at the time of the build, with a chain that Windows trusts |
| Private key | Available to `signtool` in the certificate store or the managed signing service. Do not export it into the repository, a log, or a chat. |
| Thumbprint format | 40 hexadecimal characters, spaces optional |
| Build variable | `AXIZPOS_SIGN_THUMBPRINT` |

A self-signed development certificate, a personal certificate, or a certificate whose subject is not the AxizPOS publisher is not acceptable.

## After the certificate is installed

Confirm the thumbprint and the code-signing usage without printing the private key:

```powershell
Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My |
  Where-Object { $_.EnhancedKeyUsageList.ObjectId -contains "1.3.6.1.5.5.7.3.3" } |
  Select-Object Subject, Issuer, Thumbprint, NotAfter, HasPrivateKey
```

Build with the same command. A valid thumbprint signs. An empty thumbprint stays unsigned.

```powershell
$env:AXIZPOS_SIGN_THUMBPRINT = "<40-hex-thumbprint>"
pnpm --filter @ai-pos/desktop build:win
```

Verify the installer. This command fails unless the file has a trusted SHA-256 Authenticode signature and an RFC 3161 timestamp:

```powershell
powershell -NoProfile -File scripts/verify-pos-signature.ps1 -Target dist\POS-Setup-*.exe
```

`scripts/require-pos-signing.mjs` warns and continues when the thumbprint is missing. It still exits 1 when a thumbprint is set but is not 40 hexadecimal characters. On 20 November 2026 the missing-thumbprint path exited 0 and the installer was marked `UNSIGNED`.
