# Data fabric — real database stack

Spins up the three databases the Forge data fabric queries: **PostgreSQL**
(hosts the `finance` and `banking` DBs), **MySQL** (`retail`), and **MongoDB**
(`healthcare`).

The fabric ([platform/backend/forge/fabric/](../../platform/backend/forge/fabric/))
auto-detects these servers: if they're reachable it seeds and queries them
(`mode: docker`); otherwise it silently falls back to embedded SQLite / an
in-process document store (`mode: embedded`). Either way the `/fabric` page and
`/api/fabric/*` endpoints work.

## Start / stop

```bash
docker compose -f docker/fabric/compose.yml up -d      # start
docker compose -f docker/fabric/compose.yml ps         # status / health
docker compose -f docker/fabric/compose.yml down        # stop  (keep data)
docker compose -f docker/fabric/compose.yml down -v     # stop + wipe volumes
```

On first request the fabric creates the `banking` database and seeds all four
domains with deterministic demo data (same rows as the embedded engines).

## Ports & credentials

| Service    | Port  | Database(s)        |
|------------|-------|--------------------|
| PostgreSQL | 5432  | `finance`, `banking` |
| MySQL      | 3306  | `retail`           |
| MongoDB    | 27017 | `healthcare`       |

User `forge`, password from `FABRIC_DB_PASSWORD` (default `forge_fabric_pwd` —
a local demo credential, not a real secret). Override the host/password for the
backend with `FABRIC_DB_HOST` / `FABRIC_DB_PASSWORD`.

## Note for restricted networks

If `docker pull` fails with `EOF` from `production.cloudfront.docker.com`, add a
registry mirror to `~/.docker/daemon.json` and restart Docker:

```json
{ "registry-mirrors": ["https://mirror.gcr.io"] }
```
