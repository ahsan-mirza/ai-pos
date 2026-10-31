"""Independent FastAPI process. Run: uvicorn einvoicing.main:app --port 8090"""

from __future__ import annotations

import os
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from einvoicing.db import SessionLocal, get_engine
from einvoicing.service import accept_webhook, connect_provider, dashboard, list_invoices, update_settings

app = FastAPI(title="AxizPOS e-Invoicing", version="0.1.0")


def _tenant(authorization: str | None) -> uuid.UUID:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="authentication_required")
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="jwt_secret_missing")
    import jwt

    try:
        claims = jwt.decode(authorization.split(" ", 1)[1], secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid_token") from exc
    tid = claims.get("tid")
    if not tid:
        raise HTTPException(status_code=401, detail="invalid_token")
    return uuid.UUID(str(tid))


def _session() -> Session:
    return SessionLocal()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "einvoicing"}


@app.get("/ready")
def ready() -> dict:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database_unavailable") from exc
    return {"status": "ready"}


@app.get("/api/v1/einvoicing/dashboard")
def dash(authorization: str | None = Header(default=None)) -> dict:
    tenant_id = _tenant(authorization)
    db = _session()
    try:
        return dashboard(db, tenant_id)
    finally:
        db.close()


@app.get("/api/v1/einvoicing/invoices")
def invoices(authorization: str | None = Header(default=None), status: str | None = None) -> list[dict]:
    tenant_id = _tenant(authorization)
    db = _session()
    try:
        return list_invoices(db, tenant_id, status=status)
    finally:
        db.close()


@app.put("/api/v1/einvoicing/configuration")
async def configuration(request: Request, authorization: str | None = Header(default=None)) -> dict:
    tenant_id = _tenant(authorization)
    payload = await request.json()
    payload.pop("tenant_id", None)
    db = _session()
    try:
        result = update_settings(db, tenant_id, payload)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        db.close()


@app.post("/api/v1/einvoicing/providers/test")
async def providers(request: Request, authorization: str | None = Header(default=None)) -> dict:
    tenant_id = _tenant(authorization)
    payload = await request.json()
    db = _session()
    try:
        result = connect_provider(db, tenant_id, str(payload.get("provider_code") or ""))
        db.commit()
        return result
    finally:
        db.close()


@app.post("/api/v1/einvoicing/webhooks/{provider_code}")
async def webhook(provider_code: str, request: Request) -> dict:
    """Tenant comes from the stored participant mapping. A body tenant id is only a claim to reject."""
    body = await request.body()
    claimed = None
    if body.startswith(b"{"):
        import json

        try:
            claimed = json.loads(body).get("tenant_id")
        except json.JSONDecodeError:
            claimed = None
    db = _session()
    try:
        result = accept_webhook(
            db,
            provider_code=provider_code,
            body=body,
            signature=request.headers.get("x-einvoicing-signature", ""),
            timestamp=request.headers.get("x-einvoicing-timestamp", ""),
            event_id=request.headers.get("x-einvoicing-event-id", ""),
            participant_id=request.headers.get("x-einvoicing-participant", ""),
            claimed_tenant=str(claimed) if claimed else None,
        )
        db.commit()
    finally:
        db.close()
    if result.get("accepted"):
        return result
    reason = result.get("reason")
    status = 401 if reason in {"bad_signature", "unknown_account", "tenant_mismatch"} else 400
    raise HTTPException(status_code=status, detail=reason or "rejected")
