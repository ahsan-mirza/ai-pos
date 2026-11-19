import os
from pathlib import Path

roots = [
    Path(os.environ["APPDATA"]) / "com.axizpos.pharmacy.acceptance",
    Path(os.environ["LOCALAPPDATA"]) / "com.axizpos.pharmacy.acceptance",
]
needles = [b"register-capabilities", b"ai-pos.promotions", b"pharmacy_catalog", b"entitlement_revision"]
for root in roots:
    if not root.exists():
        print("missing", root)
        continue
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if any(needle in data for needle in needles):
            print(path.relative_to(root), path.stat().st_size)
