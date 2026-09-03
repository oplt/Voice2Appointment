# Runbook: Migration failure

**Impact:** Deploy fails or app cannot start against schema.

## Detect

- Alembic upgrade non-zero in CI/CD or container entrypoint
- Startup logs referencing migration revision mismatch

## Diagnose

1. Note current DB revision vs code head (`alembic heads` / `current`).

From the repo root:

```bash
alembic current
alembic heads
alembic upgrade head
```

Or from `backend/` (same files):

```bash
cd backend && PYTHONPATH=. alembic current
```

Do **not** autogenerate a second “initial” / “create users” revision. Head is `c9d0e1f2a3b4`. New revisions must `Revises:` that head.
2. Inspect failing revision SQL; check locks/timeouts on PostgreSQL.
3. Do not run destructive downgrades without explicit approval.

### DuplicateTable / missing `alembic_version`

`alembic upgrade head` starting at `-> c9a6910c93ea` while `res_user` already exists means the schema was created outside Alembic (often `Base.metadata.create_all` in tests) and **`alembic_version` is missing**.

`make migrate` (`backend/scripts/alembic_upgrade.py`) adds any missing model columns/indexes, stamps head, then upgrades. It does not drop tables or user rows.

If repair cannot add a NOT NULL column on a populated table, stop and inspect with `alembic current` / `\d tablename` rather than stamping blindly.

## Mitigate

- Fix forward migration; prefer additive changes.
- If mid-deploy: keep old app revision serving until DB is consistent.
- Restore from backup only with documented data-loss approval.

## Verify

- `alembic upgrade head` idempotent twice.
- App `/health/ready` succeeds against migrated DB.
