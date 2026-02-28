"""
FastAPI routes for Epicollect5 Bot application.
"""

import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from src.services import (
    get_job_status,
    is_job_running,
    run_bot_in_background,
    DEFAULT_MAX_WORKERS,
)
from src.logger import logger

router = APIRouter()

PROJECT_ROOT = Path(__file__).parent.parent
UPLOAD_FOLDER = PROJECT_ROOT / "files"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve the favicon."""
    favicon_path = PROJECT_ROOT / "static" / "favicon.ico"
    return FileResponse(favicon_path)


@router.get("/", response_class=HTMLResponse)
async def index():
    """Render the main upload page."""
    html_path = PROJECT_ROOT / "templates" / "index.html"
    return HTMLResponse(content=html_path.read_text(), status_code=200)


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    project_name: str = Form(...),
    project_email: str = Form(...),
    max_workers: int = Form(DEFAULT_MAX_WORKERS),
):
    """Handle CSV file upload and start background processing with parallel workers."""
    if is_job_running():
        raise HTTPException(
            status_code=400, detail="A job is already running. Please wait."
        )

    if not project_name or not project_email:
        raise HTTPException(
            status_code=400, detail="Project name and email are required"
        )

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

    # Validate max_workers (between 1 and 2, consistent with UI)
    max_workers = max(1, min(2, max_workers))

    # Save the uploaded file
    file_path = UPLOAD_FOLDER / "sample.csv"
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Count records
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    record_count = len(lines) - 1

    logger.info(f"File uploaded: {file.filename} ({record_count} records)")
    logger.info(f"Max workers: {max_workers}")

    # Start background processing
    thread = threading.Thread(
        target=run_bot_in_background,
        args=(file_path, project_name, project_email, max_workers),
    )
    thread.daemon = True
    thread.start()

    return JSONResponse(
        content={
            "message": f"Upload started! Processing {record_count} records with {max_workers} parallel workers.",
            "records": record_count,
            "max_workers": max_workers,
        }
    )


@router.get("/status")
async def get_status():
    """Get the current job status."""
    return JSONResponse(content=get_job_status())
