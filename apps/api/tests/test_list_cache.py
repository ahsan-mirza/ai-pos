"""Tenant-scoped list cache: a second read is a hit, a bump or another tenant is a miss."""

from app.core.cache import reset
from app.services import list_cache
from app.tenancy.context import TenantRef, use_tenant


def _tenant(tenant_id: str) -> TenantRef:
    return TenantRef(id=tenant_id, slug=tenant_id, name=tenant_id, database_url="postgresql://unused")


def test_remember_hits_until_the_resource_version_changes() -> None:
    reset()
    calls = {"n": 0}

    def load() -> list[dict[str, int]]:
        calls["n"] += 1
        return [{"n": calls["n"]}]

    with use_tenant(_tenant("tenant-a")):
        assert list_cache.remember("models", "all", 30, load) == [{"n": 1}]
        assert list_cache.remember("models", "all", 30, load) == [{"n": 1}]
        list_cache.bump("models")
        assert list_cache.remember("models", "all", 30, load) == [{"n": 2}]
        assert list_cache.remember("models", "brand-1|", 30, load) == [{"n": 3}]


def test_remember_does_not_share_entries_between_tenants() -> None:
    reset()

    def load_for(name: str):
        def load() -> list[dict[str, str]]:
            return [{"tenant": name}]

        return load

    with use_tenant(_tenant("tenant-a")):
        assert list_cache.remember("models", "all", 30, load_for("a")) == [{"tenant": "a"}]
    with use_tenant(_tenant("tenant-b")):
        assert list_cache.remember("models", "all", 30, load_for("b")) == [{"tenant": "b"}]
    with use_tenant(_tenant("tenant-a")):
        assert list_cache.remember("models", "all", 30, load_for("a-again")) == [{"tenant": "a"}]
