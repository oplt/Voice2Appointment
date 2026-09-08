# Phase 3 connection budget

`DB_POOL_SIZE` is the maximum persistent connections per process and
`DB_MAX_OVERFLOW` is additional burst capacity. The defaults are deliberately
small: 5 and 0.

For the production Procfile shown in this repository:

| Process group | Processes | Max connections/process | Budget |
| --- | ---: | ---: | ---: |
| Web | 2 | 5 | 10 |
| Voice | 1 | 5 | 5 |
| Critical, notifications, provider sync, media, maintenance workers | 5 | 5 | 25 |
| Headroom for migrations, psql, monitoring | — | — | 10 |
| Total required PostgreSQL `max_connections` | — | — | 50 |

Before changing worker counts, `DB_POOL_SIZE`, or `DB_MAX_OVERFLOW`, recalculate:

`(web processes × web pool maximum) + (voice processes × voice pool maximum) + (worker processes × worker pool maximum) + headroom`

Keep that number below PostgreSQL `max_connections`. Observe
`db_pool_checked_out`, `db_pool_capacity`, and `db_pool_wait_ms` before making
any pool increase.
