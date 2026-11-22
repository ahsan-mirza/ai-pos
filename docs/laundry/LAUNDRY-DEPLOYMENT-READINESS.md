# Laundry deployment readiness

Not ready for production deployment.

The catalog migration is `apps/api/alembic/versions/20261121_0121_laundry_catalog.py`. It revises `20261119_0120` and only adds tables. Do not apply it to production as part of this work. Do not apply it to the inventory acceptance database.

A tenant gets laundry by selecting the laundry profile or enabling `laundry_operations`. Existing plans are unchanged. The capability is not added to grocery, pharmacy, or food profiles.

Operational screens for orders, production, and delivery do not exist yet, so a laundry tenant cannot run a counter or a plant on this build.
