// Reports whether this Windows build will be Authenticode-signed.
// A missing thumbprint is an unsigned build, not a failed build.
// A thumbprint that is present but not 40 hexadecimal characters still stops the build.
const thumbprint = (process.env.AXIZPOS_SIGN_THUMBPRINT || "").replace(/\s+/g, "");
if (process.env.AXIZPOS_SIGN_MODE === "unsigned") {
  console.warn(
    "WARNING: AXIZPOS_SIGN_MODE=unsigned. This Windows build is UNSIGNED. Authenticode will not identify the publisher.",
  );
  process.exit(0);
}
if (thumbprint === "") {
  console.warn(
    "WARNING: AXIZPOS_SIGN_THUMBPRINT is not set. This Windows build is UNSIGNED. Authenticode will not identify the publisher. Windows SmartScreen may show an unknown-publisher warning.",
  );
  process.exit(0);
}
if (!/^[0-9a-fA-F]{40}$/.test(thumbprint)) {
  console.error(
    "Production signing stopped. AXIZPOS_SIGN_THUMBPRINT is set but is not 40 hexadecimal characters. The private key is not read from the repository.",
  );
  process.exit(1);
}
console.log("Authenticode signing is configured. The private key stays in the certificate store.");
