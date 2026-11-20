# Unsigned Windows release policy

Date: 20 November 2026.

Authenticode signing is optional. A missing certificate does not stop the production build. A present but malformed thumbprint still stops it. No dummy certificate, self-signed production identity, or false signature is created.

## What the build does

`pnpm --filter @ai-pos/desktop build:win` reads `AXIZPOS_SIGN_THUMBPRINT`.

| Thumbprint | Result |
|---|---|
| Unset, or `AXIZPOS_SIGN_MODE=unsigned` | The build passes `--no-sign`. The executable and installer are checked with `Get-AuthenticodeSignature` and must be `NotSigned`. Metadata says `UNSIGNED`. |
| 40 hexadecimal characters | `scripts/sign-pos.ps1` signs with that certificate. `scripts/verify-pos-signature.ps1` must show a SHA-256 signature and a timestamp. A failed verification fails the build. |
| Any other value | The build stops before packaging. |

The private key stays in the Windows certificate store. The build does not print it and does not write it into the installer.

`dist/POS-Setup-<version>.signing.json` records `signing` as `SIGNED` or `UNSIGNED`. An unsigned file also says that Authenticode does not identify the publisher. SHA-256 files are written beside the installer and the executable.

## What an unsigned installer means

An unsigned installer does not establish a verified publisher through Authenticode. Windows SmartScreen or the installer dialog may say the publisher is unknown. It is not a signed, trusted, publisher-verified, or enterprise-approved release. The SHA-256 hash shows the file was not changed after the build. It does not identify who published it.

Do not install an unsigned candidate over a register that is already in use by a store. The production identifier is `com.aipos.desktop`.

## Signing a later release

Install an AxizPOS code-signing certificate in the Windows certificate store, or provide it to the GitHub Actions runner. Set `AXIZPOS_SIGN_THUMBPRINT` to its 40-character thumbprint. Leave `scripts/sign-pos.ps1` and `scripts/verify-pos-signature.ps1` in place. Run `build:win` again. The same pipeline signs and then verifies. No second build system is required.

The GitHub workflow `.github/workflows/release-pos.yml` passes the secret through when it exists. An empty secret produces the unsigned artifact and still uploads the checksum and the signing metadata. Publishing that artifact is a separate manual choice and is not a production deployment by itself.
