# AxizPOS e-Invoicing

Optional UAE add-on. Separate package, same PostgreSQL database as the API.

```
uvicorn einvoicing.main:app --port 8090
python -m einvoicing.worker
```

Set `PYTHONPATH` to this directory. Copy `.env.example`. The only provider adapter is `mock`. Read `docs/PRODUCTION_READINESS.md` before treating any result as an FTA submission.

Tests, from this directory, with the API virtualenv:

```
python -m pytest tests/test_plugin.py
```

The migration in `migrations/` uses version table `alembic_version_einvoicing`. Do not run it against the live database without approval.
