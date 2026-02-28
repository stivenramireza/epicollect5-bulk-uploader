# Epicollect5 Bulk Uploader

A vibe coded web application that automates bulk CSV data uploads to [Epicollect5](https://five.epicollect.net) with async parallel processing. It uses [Playwright](https://playwright.dev/python/) to drive a headless Chromium browser, splitting large CSV files into chunks and uploading them in parallel through multiple browser contexts.

## How It Works

1. You submit a CSV file through the web interface along with your Epicollect5 project name and email.
2. The server splits the CSV into chunks of 150 rows each.
3. A pool of up to 2 headless browser contexts uploads chunks in parallel, each automating the Epicollect5 "Upload BETA" workflow.
4. The frontend polls for progress every 5 seconds and displays real-time status updates.

Browser session cookies are persisted to `browser_data/storage_state.json` so that subsequent uploads reuse the existing login without re-authentication.

## Prerequisites

- Python 3.14+
- A valid Epicollect5 account with access to the target project
- A pre-existing browser session (see [Authentication](#authentication))

## Getting Started

### Local Setup

```bash
# Create and activate a virtual environment
python3.14 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Chromium for Playwright
playwright install chromium
```

For development (code formatting):

```bash
pip install -r requirements_local.txt
```

### Run the Application

```bash
# Development (auto-reload)
uvicorn src.main:app --reload --host 0.0.0.0 --port 5000

# Production
uvicorn src.main:app --host 0.0.0.0 --port 5000
```

Then open http://localhost:5000 in your browser.

### Docker

```bash
docker build -t epicollect5-bulk-uploader .
docker run -p 5000:5000 epicollect5-bulk-uploader
```

## Authentication

The bot runs in headless mode and cannot perform interactive logins. You must provide a valid session before your first upload:

1. Run the app in **non-headless mode** (modify `headless=True` to `headless=False` in `src/services.py` temporarily), or manually create the session file.
2. Log in to Epicollect5 through the browser window that opens.
3. The session is saved to `browser_data/storage_state.json` and reused for all future uploads.

If the session expires, delete `browser_data/` and repeat the login process.

## Usage

1. Open the web interface at http://localhost:5000.
2. Enter your **Project Name** (the slug from your Epicollect5 project URL, e.g., `my-project`).
3. Enter your **Project Email** (the email associated with the Epicollect5 project).
4. Select the number of **Parallel Workers** (1 or 2).
5. Upload a CSV file (drag-and-drop or click to browse).
6. Click **Upload and Process** and monitor progress in real time.

Only one upload job can run at a time. If a job is already in progress, new submissions are rejected until it finishes.

## API Endpoints

| Method | Path       | Description                                      |
|--------|------------|--------------------------------------------------|
| GET    | `/`        | Serves the web interface                         |
| POST   | `/upload`  | Accepts a CSV file and starts background processing |
| GET    | `/status`  | Returns the current job status as JSON           |

### POST /upload

Form fields:
- `file` — CSV file (required)
- `project_name` — Epicollect5 project slug (required)
- `project_email` — Account email (required)
- `max_workers` — Number of parallel browser contexts, 1-2 (default: 2)

### GET /status

Returns JSON with fields: `running`, `progress`, `percentage`, `total_records`, `processed_chunks`, `total_chunks`, `error`, `has_browser_profile`, `max_workers`, `start_time`, `end_time`.

## Project Structure

```
src/
  main.py             # FastAPI app initialization, static file mounting
  routes.py           # HTTP endpoints and request validation
  services.py         # Job lifecycle, CSV chunking, progress tracking
  epicollect5_bot.py  # Playwright browser automation (Epicollect5Bot + ParallelUploader)
  logger.py           # Logging configuration (uses uvicorn's logger)
templates/
  index.html          # Single-page web interface (Tailwind CSS)
static/
  favicon.ico         # Favicon
```

Runtime directories (created automatically, not checked into git):
- `files/` — Temporary storage for uploaded CSVs and chunk files (cleaned up after processing)
- `browser_data/` — Playwright session persistence (`storage_state.json`)

## Code Formatting

This project uses [Black](https://black.readthedocs.io/) for code formatting:

```bash
# Format all files
black .

# Check formatting without modifying files
black --check .
```

## License

This project is licensed under the [MIT License](LICENSE).
