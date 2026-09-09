# Phase 3 / Phase 12 connection budget

`DB_POOL_SIZE` is the maximum persistent connections **per OS process** and
`DB_MAX_OVERFLOW` is additional burst capacity.

Celery prefork workers matter: `--concurrency N` means **N child processes**,
and each child imports its own SQLAlchemy engine/pool. Counting only the parent
worker process undercounts the budget.

## Production Procfile.production (default pools)

| Process group | Processes (children) | Pool / process | Budget |
| --- | ---: | ---: | ---: |
| Web (Gunicorn `--workers 2`) | 2 | 5 | 10 |
| Voice (1 Uvicorn) | 1 | 5 | 5 |
| Celery `critical` (`--concurrency 2`) | 2 | **2** | 4 |
| Celery `notifications` (`--concurrency 2`) | 2 | **2** | 4 |
| Celery `provider_sync` (`--concurrency 2`) | 2 | **2** | 4 |
| Celery `media` (`--concurrency 1`) | 1 | **2** | 2 |
| Celery `maintenance` (`--concurrency 1`) | 1 | **2** | 2 |
| Headroom (migrate, psql, monitoring) | — | — | 10 |
| **Total required PostgreSQL `max_connections`** | — | — | **≈43** |

Worker processes should set a **smaller** pool than HTTP/voice:

```text
DB_POOL_SIZE=2
DB_MAX_OVERFLOW=0
```

HTTP and voice keep `DB_POOL_SIZE=5` unless metrics show wait pressure.

## Anti-pattern (do not use)

If every Celery child kept pool size **5**:

```text
HTTP 10 + Voice 5 + Celery children 8×5=40 + headroom 10 ≈ 65+
```

That exceeds the old documented total of 50.

## Formula

```text
(web_workers × web_pool)
+ (voice_processes × voice_pool)
+ (Σ celery_queue_concurrency × celery_pool)
+ headroom
< Postgres max_connections
```

Observe `db_pool_checked_out`, `db_pool_capacity`, and `db_pool_wait_ms` before
raising any pool size.
