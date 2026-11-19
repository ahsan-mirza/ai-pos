import os
import re
from pathlib import Path

path = Path(os.environ["LOCALAPPDATA"]) / "com.axizpos.pharmacy.acceptance" / "EBWebView" / "Default" / "Local Storage" / "leveldb"
files = sorted(path.glob("*.log")) + sorted(path.glob("*.ldb"))
print("files", [item.name for item in files])
blob = b"".join(item.read_bytes() for item in files)
text = blob.decode("utf-8", "ignore")
flat = re.sub(r"[\x00-\x1f]", "", text)
keys = sorted(set(re.findall(r"ai-pos\.[A-Za-z0-9._:-]+", flat)))
print("keys")
for key in keys:
    if "register-capabilities" in key or key.startswith("ai-pos.promotions") or key == "ai-pos.register-capabilities":
        print(key)
seen = set()
for match in re.finditer(r"register-capabilities\.v1:[^{]{0,160}", flat):
    window = flat[match.start():match.start() + 5000]
    tenant = re.search(r'"tenant_id":"([^"]+)"', window)
    profile = re.search(r'"business_profile":"([^"]+)"', window)
    revision = re.search(r'"entitlement_revision":(\d+)', window)
    fetched = re.search(r'"fetched_at":"([^"]+)"', window)
    caps = re.search(r'"capabilities":\[(.*?)\]', window)
    identity = (
        match.group(0)[:120],
        tenant.group(1) if tenant else "missing",
        profile.group(1) if profile else "missing",
        revision.group(1) if revision else "missing",
    )
    if identity in seen:
        continue
    seen.add(identity)
    names = caps.group(1) if caps else ""
    print("snapshot", identity[0])
    print(" tenant", identity[1], "profile", identity[2], "revision", identity[3])
    print(" fetched", fetched.group(1) if fetched else "missing")
    print(" capabilities", names)
print("legacy_present", "ai-pos.register-capabilities\"" in flat or flat.count("ai-pos.register-capabilities{") > 0)
