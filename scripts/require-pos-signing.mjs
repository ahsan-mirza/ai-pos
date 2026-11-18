// Stops a production POS build before packaging when no signing certificate is configured.
const thumbprint = (process.env.AXIZPOS_SIGN_THUMBPRINT || "").replace(/\s+/g, "");
if (!/^[0-9a-fA-F]{40}$/.test(thumbprint)) {
  console.error(
    "Production signing stopped. Set AXIZPOS_SIGN_THUMBPRINT to the Windows certificate thumbprint. The private key stays in the certificate store and is not written to the repository.",
  );
  process.exit(1);
}
console.log("Production signing certificate is configured.");
