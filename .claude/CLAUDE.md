# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Epicollect5 Bulk Uploader is a FastAPI web application that automates bulk CSV data uploads to the [Epicollect5](https://five.epicollect.net) data collection platform. It uses Playwright to automate browser interactions, splitting large CSV files into chunks and uploading them in parallel using multiple browser contexts.

## Commands

### Development Setup

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements_local.txt
playwright install chromium
```

### Run the Application

```bash
# Development (auto-reload)
uvicorn src.main:app --reload --host 0.0.0.0 --port 5000

# Production
uvicorn src.main:app --host 0.0.0.0 --port 5000
```

### Linting / Formatting

```bash
black .
```

### Docker

```bash
docker build -t epicollect5-bulk-uploader .
docker run -p 5000:5000 epicollect5-bulk-uploader
```

## Architecture

The application has four layers:

1. **Frontend** (`templates/index.html`): A single-page interface built with Tailwind CSS. Submits uploads via `fetch()` and polls `/status` every 5 seconds for progress.

2. **Routes** (`src/routes.py`): Thin FastAPI layer — `POST /upload` saves the CSV and spawns a background thread; `GET /status` returns the in-memory job state as JSON.

3. **Services** (`src/services.py`): Orchestrates job lifecycle. Maintains a global `job_status` dict (not persisted). Splits the CSV into chunks (150 rows each by default), invokes the bot async via a new event loop in a background thread, and fires progress callbacks.

4. **Bot** (`src/epicollect5_bot.py`): `ParallelUploader` creates a pool of Playwright browser contexts (up to 2). Contexts are managed via an `asyncio.Queue`. Workers acquire a context, upload one chunk to Epicollect5 via browser automation, then return the context to the pool. Login session is persisted to `browser_data/storage_state.json` and shared across workers.

### Threading and Async Model

`POST /upload` runs on FastAPI's main event loop. It spawns a **daemon thread** (`threading.Thread`) that creates its own `asyncio` event loop via `asyncio.new_event_loop()`. Inside that loop, `run_bot_async()` splits the CSV and launches all chunk upload tasks with `asyncio.gather()`. Concurrency is bounded by the `asyncio.Queue`-based context pool (max 2 contexts), not by a semaphore or thread pool. The global `job_status` dict is mutated from both the background thread (sync `update_progress`) and async tasks (`update_progress_async`), which is safe here because only one job runs at a time.

### Two Bot Classes

`epicollect5_bot.py` contains two classes:
- **`Epicollect5Bot`** — single-context bot used for login and basic operations. Not used during parallel uploads.
- **`ParallelUploader`** — creates a browser context pool. This is what `services.py` actually uses for uploads. Each `upload_chunk` call acquires a context from the queue, opens a new page, performs the upload, closes the page, and returns the context.

### Key Constraints

- Only one upload job runs at a time (enforced in `services.py` via `is_job_running()`).
- Max 2 parallel workers (capped in `routes.py` validation via `max(1, min(2, max_workers))`).
- Job state is in-memory — lost on server restart.
- Chunk files are written to `files/` and cleaned up in the `finally` block after processing.
- The Epicollect5 URL (`https://five.epicollect.net`) is hardcoded as `EPICOLLECT5_URL` in `epicollect5_bot.py`.
- Upload completion is detected by waiting for the `span.hidden-xs:has-text("Download failed rows")` element to become visible (up to 10-minute timeout via `UPLOAD_TIMEOUT`).
- Browser session requires a pre-existing login saved in `browser_data/storage_state.json`. Login cannot be performed interactively in headless mode.

### Runtime Directories

- `files/` — created automatically by `routes.py`. Holds the uploaded `sample.csv` and temporary `temp_chunk_*.csv` files (cleaned up after processing).
- `browser_data/` — holds `storage_state.json` for Playwright session persistence. Created automatically by the bot. Can be cleared via `clear_browser_profile()` in `services.py`.
