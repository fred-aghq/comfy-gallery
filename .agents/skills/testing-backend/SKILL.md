---
name: testing-comfy-gallery-backend
description: Test the comfy-gallery backend end-to-end. Use when verifying backend bug fixes, scanner changes, metadata extraction, or API route changes.
---

# Testing comfy-gallery Backend

## Prerequisites

- Docker and Docker Compose installed
- The repo cloned at `~/repos/comfy-gallery`

## Devin Secrets Needed

None — the Docker stack uses local PostgreSQL with hardcoded dev credentials (`gallery:gallery`).

## Setup

### 1. Start the Docker Stack

```bash
cd ~/repos/comfy-gallery
docker compose up -d --build
```

This starts 3 services:
- **backend**: FastAPI on port 8000 (volume-mounts `./backend:/app` for live code)
- **frontend**: Vite dev server on port 5173
- **db**: PostgreSQL 17 on port 5432 (user: `gallery`, pass: `gallery`, db: `comfy_gallery`)

Wait for all services to be healthy: `docker compose ps`

### 2. Run Alembic Migrations (if schema changes)

```bash
docker compose exec backend alembic upgrade head
```

Verify column types with:
```bash
docker compose exec db psql -U gallery -d comfy_gallery -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='media_files';"
```

### 3. Prepare Test Media

The media volume maps `${MEDIA_ROOT:-./sample-media}` to `/media` inside the container (read-only).

To test scanning, copy ComfyUI-generated images into `./sample-media/`:
```bash
mkdir -p sample-media
cp /path/to/ComfyUI_image.png sample-media/
```

The backend volume-mounts `./backend:/app`, so code changes are live without rebuilding. If you change model definitions, restart the backend: `docker compose restart backend`.

## Running Unit Tests

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v
```

Tests use in-memory SQLite (not PostgreSQL), so they run without Docker. The test infrastructure swaps JSONB → JSON for SQLite compatibility.

Key test files:
- `tests/test_metadata.py` — metadata extraction (PNG, JPEG, video)
- `tests/test_scanner.py` — file discovery and scan_and_ingest
- `tests/test_thumbnails.py` — thumbnail generation
- `tests/test_api.py` — all API routes
- `tests/conftest.py` — shared fixtures and test DB setup

## E2E Testing Flows

### Scan & Ingest
1. Open `http://localhost:5173` in browser
2. Click **Rescan** button
3. Verify images appear in gallery grid with thumbnails
4. Check API: `curl http://localhost:8000/api/media?page=1` for correct metadata

### Verify Specific API Fixes
- **404 for missing media**: `curl -s -w '\n%{http_code}' http://localhost:8000/api/media/999999` — expect 404
- **Path traversal**: `curl -s -w '\n%{http_code}' --path-as-is 'http://localhost:8000/api/media/file/../../etc/passwd'` — expect 403
- **Health check**: `curl http://localhost:8000/api/health` — expect `{"status":"ok"}`

### Rescan Update Logic
1. Scan an image (Rescan button or `POST /api/scan`)
2. `touch sample-media/image.png` to update mtime
3. Rescan again — response should show `"updated": 1`
4. Rescan again (no changes) — should show `"updated": 0` (idempotent)

## Important Notes

- ComfyUI seeds can exceed int32 range (e.g., `721897303308196`). The `seed` column uses `BigInteger`. If you see `OverflowError: value out of int32 range`, check if the alembic migration has been run.
- The backend code is volume-mounted, so changes to Python files are picked up by uvicorn hot-reload. But schema changes may require `docker compose restart backend` or running migrations.
- The `sample-media` directory might not exist in a fresh clone — create it before testing scan functionality.
- The frontend proxies API requests to the backend, so testing via `http://localhost:5173` exercises the full stack.
