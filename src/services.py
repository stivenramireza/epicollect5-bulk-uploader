"""
Bot services for Epicollect5 application.
Handles background processing and job status management with async support.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from src.epicollect5_bot import ParallelUploader
from src.logger import logger

# Configuration
DEFAULT_CHUNK_SIZE = 150
DEFAULT_MAX_WORKERS = 2  # Number of parallel browser contexts

# Track job status (shared between coroutines)
job_status = {
    "running": False,
    "progress": "",
    "total_records": 0,
    "processed_chunks": 0,
    "total_chunks": 0,
    "percentage": 0,
    "start_time": None,
    "end_time": None,
    "error": None,
    "max_workers": DEFAULT_MAX_WORKERS,
}


def get_job_status() -> dict:
    """Get the current job status."""
    profile_path = _get_browser_profile_path()
    has_browser_profile = profile_path.exists()

    return {
        "running": job_status["running"],
        "progress": job_status["progress"],
        "total_records": job_status["total_records"],
        "processed_chunks": job_status["processed_chunks"],
        "total_chunks": job_status["total_chunks"],
        "percentage": job_status["percentage"],
        "error": job_status["error"],
        "has_browser_profile": has_browser_profile,
        "max_workers": job_status["max_workers"],
        "start_time": (
            job_status["start_time"].isoformat() if job_status["start_time"] else None
        ),
        "end_time": (
            job_status["end_time"].isoformat() if job_status["end_time"] else None
        ),
    }


def is_job_running() -> bool:
    """Check if a job is currently running."""
    return job_status["running"]


def _get_browser_profile_path() -> Path:
    """Return the path to the browser_data directory at project root."""
    return Path(__file__).parent.parent / "browser_data"


async def update_progress_async(
    chunk_number: int, total_chunks: int, message: str
) -> None:
    """Update job status with progress information (async version)."""
    global job_status
    job_status["processed_chunks"] = chunk_number
    job_status["total_chunks"] = total_chunks
    job_status["percentage"] = (
        int((chunk_number / total_chunks) * 100) if total_chunks > 0 else 0
    )
    job_status["progress"] = message

    # Log progress to console
    logger.info(
        f"Progress: {job_status['percentage']}% - Chunk {chunk_number}/{total_chunks} - {message}"
    )


def update_progress(chunk_number: int, total_chunks: int, message: str) -> None:
    """Update job status with progress information (sync version)."""
    global job_status
    job_status["processed_chunks"] = chunk_number
    job_status["total_chunks"] = total_chunks
    job_status["percentage"] = (
        int((chunk_number / total_chunks) * 100) if total_chunks > 0 else 0
    )
    job_status["progress"] = message

    logger.info(
        f"Progress: {job_status['percentage']}% - Chunk {chunk_number}/{total_chunks} - {message}"
    )


async def run_bot_async(
    file_path: Path,
    project_name: str,
    project_email: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> None:
    """
    Run the Epicollect5 bot asynchronously with parallel chunk processing.

    Args:
        file_path: Path to the CSV file to upload.
        project_name: Epicollect5 project name/slug.
        project_email: Email for Epicollect5 login.
        max_workers: Number of parallel browser contexts for uploads.
        chunk_size: Number of records per chunk.
    """
    global job_status

    job_status["running"] = True
    job_status["start_time"] = datetime.now()
    job_status["error"] = None
    job_status["percentage"] = 0
    job_status["processed_chunks"] = 0
    job_status["progress"] = "Starting bot..."
    job_status["max_workers"] = max_workers

    logger.info("=" * 60)
    logger.info("STARTING EPICOLLECT5 BOT (ASYNC PARALLEL MODE)")
    logger.info(f"Project: {project_name}")
    logger.info(f"Email: {project_email}")
    logger.info(f"Max Workers: {max_workers}")
    logger.info(f"Chunk Size: {chunk_size}")
    logger.info("=" * 60)

    chunk_files: list[Path] = []

    try:
        # Read and count records
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_records = len(lines) - 1  # Exclude header
        job_status["total_records"] = total_records

        total_chunks = (total_records + chunk_size - 1) // chunk_size
        job_status["total_chunks"] = total_chunks

        logger.info(
            f"Found {total_records} records to process in {total_chunks} chunks"
        )
        update_progress(0, total_chunks, f"Found {total_records} records to process")

        # Create chunk files
        header = lines[0]
        data_rows = lines[1:]

        update_progress(0, total_chunks, "Creating chunk files...")

        for i in range(0, total_records, chunk_size):
            chunk_rows = data_rows[i : i + chunk_size]
            chunk_number = (i // chunk_size) + 1

            temp_file = file_path.parent / f"temp_chunk_{chunk_number}.csv"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(header)
                f.writelines(chunk_rows)

            chunk_files.append(temp_file)

        logger.info(f"Created {len(chunk_files)} chunk files")

        # Create parallel uploader
        async with ParallelUploader(
            project_name=project_name,
            project_email=project_email,
            max_workers=max_workers,
            headless=True,
        ) as uploader:

            # Login and save state (uses existing session if available)
            update_progress(0, total_chunks, "Logging in...")

            await uploader.login_and_save_state()

            # Verify user is logged in before processing any chunks
            update_progress(0, total_chunks, "Verifying login session...")
            is_logged_in = await uploader.verify_login()

            if not is_logged_in:
                raise Exception(
                    "Login verification failed. Please try again and complete the login process."
                )

            logger.info("Login verified successfully - ready to process chunks")
            update_progress(0, total_chunks, "Login verified, starting uploads...")

            # Track how many chunks have completed
            completed_count = 0
            completed_lock = asyncio.Lock()

            async def progress_callback(_chunk_num: int, total: int, msg: str) -> None:
                """Track progress based on the number of completed chunks."""
                nonlocal completed_count
                async with completed_lock:
                    completed_count += 1
                    await update_progress_async(completed_count, total, msg)

            # Start parallel uploads
            update_progress(
                0,
                total_chunks,
                f"Starting parallel upload with {max_workers} workers...",
            )

            result = await uploader.upload_chunks_parallel(
                chunk_files=chunk_files,
                progress_callback=progress_callback,
            )

            # Log results
            logger.info("=" * 60)
            if result["failures"] == 0:
                job_status["percentage"] = 100
                job_status["progress"] = "Completed successfully!"
                logger.info("ALL RECORDS UPLOADED SUCCESSFULLY!")
            else:
                job_status["progress"] = (
                    f"Completed with {result['failures']} failed chunks"
                )
                logger.warning(
                    f"Upload completed with errors: {result['failures']} chunks failed"
                )

            job_status["end_time"] = datetime.now()
            duration = job_status["end_time"] - job_status["start_time"]

            logger.info(f"Records processed: {total_records}")
            logger.info(f"Chunks: {total_chunks}")
            logger.info(f"Successful: {result['successes']}")
            logger.info(f"Failed: {result['failures']}")
            logger.info(f"Duration: {duration}")
            logger.info("=" * 60)

    except Exception as e:
        job_status["error"] = str(e)
        job_status["progress"] = f"Error: {e}"
        job_status["end_time"] = datetime.now()

        logger.error("=" * 60)
        logger.error(f"BOT FAILED: {e}")
        logger.error("=" * 60)
        raise

    finally:
        # Clean up chunk files
        for temp_file in chunk_files:
            try:
                if temp_file.exists():
                    os.remove(temp_file)
            except Exception as e:
                logger.warning(f"Could not remove temp file {temp_file}: {e}")

        job_status["running"] = False


def run_bot_in_background(
    file_path: Path,
    project_name: str,
    project_email: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> None:
    """
    Run the bot in a background asyncio event loop.

    This is called from a background thread to run the async bot.
    """
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(
            run_bot_async(
                file_path=file_path,
                project_name=project_name,
                project_email=project_email,
                max_workers=max_workers,
            )
        )
    finally:
        loop.close()


async def clear_browser_profile() -> bool:
    """Clear the browser profile to logout."""
    import shutil

    profile_path = _get_browser_profile_path()

    if profile_path.exists():
        try:
            shutil.rmtree(profile_path)
            logger.info("Browser profile cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to clear browser profile: {e}")
            return False

    return True
