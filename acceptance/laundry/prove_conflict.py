"""Two signed-in sessions edit one laundry order. Prints no secrets."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
vals: dict[str, str] = {}
for line in (ROOT / ".env.laundry-acceptance").read_text(encoding="utf-8").splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    vals[key.strip()] = value.strip()

BASE = "http://127.0.0.1:18082"


def call(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    request = Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Tenant-Domain": "laundry-a",
        },
    )
    with urlopen(request) as response:
        return response.status, json.loads(response.read().decode())


def login() -> str:
    status, body = call(
        "POST",
        "/api/v1/auth/login-password",
        "",
        {"username": vals["ADMIN_USERNAME"], "password": vals["ADMIN_PASSWORD"]},
    )
    if status != 200:
        raise SystemExit("login failed")
    return str(body["access_token"])


def main() -> None:
    first = login()
    second = login()
    _, services = call("GET", "/api/v1/laundry/services?active=true", first)
    _, customers = call("GET", "/api/v1/customers?limit=20", first)
    _, stores = call("GET", "/api/v1/stores", first)
    shirt = next(row["id"] for row in services if row["name"] == "Dry clean shirt")
    status, order = call(
        "POST",
        "/api/v1/laundry/orders",
        first,
        {
            "idempotency_key": uuid.uuid4().hex,
            "intake_store_id": stores[0]["id"],
            "customer_id": customers[0]["id"],
            "order_type": "WALK_IN",
            "garments": [
                {"service_id": shirt, "quantity": 1, "description": "Session shirt", "condition": "tear"},
            ],
        },
    )
    if status != 201:
        raise SystemExit("create failed")
    version = order["version"]
    garment_id = order["garments"][0]["id"]

    def edit(token: str, field: str, value: str) -> int:
        try:
            code, _body = call(
                "POST",
                f"/api/v1/laundry/orders/{order['id']}/garments",
                token,
                {"garment_id": garment_id, "version": version, field: value},
            )
            return code
        except Exception as exc:
            return getattr(exc, "code", 0)

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda item: edit(*item), [(first, "description", "Pressed"), (second, "condition", "fading")]))
    _, kept = call("GET", f"/api/v1/laundry/orders/{order['id']}", first)
    garment = kept["garments"][0]
    print(json.dumps({
        "codes": sorted(codes),
        "description": garment["description"],
        "condition": garment["condition"],
        "version": kept["version"],
    }))
    if sorted(codes) != [200, 409]:
        raise SystemExit(1)
    if garment["description"] == "Pressed" and garment["condition"] == "fading":
        raise SystemExit("both edits were stored")


if __name__ == "__main__":
    main()
