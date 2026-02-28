"""
FastAPI web application for Epicollect5 Bulk Uploader.
Provides a web interface to upload CSV files and process them in the background.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.routes import router

app = FastAPI(
    title="Epicollect5 Bulk Uploader", description="Upload CSV files to Epicollect5"
)

# Mount static files for favicon
STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include routes
app.include_router(router)
