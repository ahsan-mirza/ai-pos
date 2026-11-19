import json
import os
import re
from pathlib import Path

path = Path(os.environ["LOCALAPPDATA"]) / "com.axizpos.pharmacy.acceptance" / "EBWebView" / "Default" / "Local Storage" / "leveldb" / "000003.log"
data = path.read_bytes()
text = data.decode("utf-8", "ignore")
keys = sorted(set(re.findall(r"ai-pos\.[a-z0-9._:-]+", text)))
print("keys")
for key in keys:
    print(key)
flat = re.sub(r"[\x00-\x1f]", "", text)
for match in re.finditer(r"register-capabilities\.v1:[^{]{0,120}", flat):
    start = match.start()
    window = flat[start:start + 2500]
    tenant = re.search(r'"tenant_id":"([^"]+)"', window)
    profile = re.search(r'"business_profile":"([^"]+)"', window)
    revision = re.search(r'"entitlement_revision":(\d+)', window)
    pharmacy = "pharmacy_catalog" in window[:900]
    print(
        match.group(0)[:110],
        "tenant", tenant.group(1) if tenant else "missing",
        "profile", profile.group(1) if profile else "missing",
        "revision", revision.group(1) if revision else "missing",
        "pharmacy_catalog", pharmacy,
    )
