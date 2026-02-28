"""
Epicollect5 Bot using Playwright for async browser automation.
Supports parallel chunk uploads using multiple browser contexts.
"""

import asyncio
from pathlib import Path
from typing import Optional, Callable, Awaitable

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from src.logger import logger


# Constants
EPICOLLECT5_URL = "https://five.epicollect.net"
WAIT_TIMEOUT = 30000  # 30 seconds in milliseconds
UPLOAD_TIMEOUT = 600000  # 10 minutes for large file uploads


class Epicollect5Bot:
    """
    Async Playwright-based bot for automating Epicollect5 uploads.

    Supports:
    - Async operations for better performance
    - Multiple browser contexts for parallel uploads
    - Persistent browser state for session management
    """

    def __init__(
        self,
        project_name: str,
        project_email: str,
        headless: bool = True,
        user_data_dir: Optional[Path] = None,
    ):
        self.project_name = project_name
        self.project_email = project_email
        self.headless = headless
        self.user_data_dir = user_data_dir or self._get_default_user_data_dir()

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    @staticmethod
    def _get_default_user_data_dir() -> Path:
        """Get the default user data directory for browser persistence."""
        return Path(__file__).parent.parent / "browser_data"

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def start(self) -> None:
        """Start the browser and create a new context."""
        self._playwright = await async_playwright().start()

        # Ensure user data directory exists
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        # Launch browser with persistent context for session management
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        # Create context with persistent storage
        self._context = await self._browser.new_context(
            storage_state=(
                self._get_storage_state_path() if self._storage_state_exists() else None
            ),
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        self._page = await self._context.new_page()
        logger.info("Browser started successfully")

    async def close(self) -> None:
        """Close browser and save state."""
        if self._context:
            try:
                # Save storage state for session persistence
                await self._context.storage_state(
                    path=str(self._get_storage_state_path())
                )
                logger.info("Browser state saved")
            except Exception as e:
                logger.warning(f"Could not save browser state: {e}")

            await self._context.close()

        if self._browser:
            await self._browser.close()

        if self._playwright:
            await self._playwright.stop()

        logger.info("Browser closed")

    def _get_storage_state_path(self) -> Path:
        """Get path to storage state file."""
        return self.user_data_dir / "storage_state.json"

    def _storage_state_exists(self) -> bool:
        """Check if storage state file exists."""
        return self._get_storage_state_path().exists()

    async def login(self) -> bool:
        """
        Check if logged in to Epicollect5.
        Relies on session persistence from storage state.

        Returns:
            True if logged in, False otherwise.
        """
        logger.info(f"Checking Epicollect5 login status...")

        # Go to the login page
        await self._page.goto(f"{EPICOLLECT5_URL}/login", wait_until="networkidle")

        # Check if already logged in by looking for user menu or similar
        if await self._is_logged_in():
            logger.info("Already logged in from previous session")
            return True

        logger.error(
            "Not logged in. Please ensure a valid session exists in browser_data/"
        )
        return False

    async def _is_logged_in(self) -> bool:
        """Check if user is already logged in."""
        try:
            # Look for common logged-in indicators
            user_menu = self._page.locator(
                '[class*="user"], [class*="profile"], [class*="account"], [aria-label*="account" i]'
            )
            if await user_menu.count() > 0:
                return True

            # Check for logout link
            logout_link = self._page.locator(
                'a:has-text("Logout"), button:has-text("Logout")'
            )
            if await logout_link.count() > 0:
                return True

            # Check URL for dashboard or project pages
            current_url = self._page.url
            if "/myprojects" in current_url or "/project/" in current_url:
                return True

        except Exception:
            # Best-effort check: on any error, log and treat as "not logged in".
            logger.debug("Error while checking Epicollect5 login status", exc_info=True)

        return False

    async def navigate_to_project_data(self) -> None:
        """Navigate to the project's data page."""
        logger.info(f"Navigating to project: {self.project_name}")

        # Navigate to project data page
        project_url = f"{EPICOLLECT5_URL}/project/{self.project_name}/data"
        await self._page.goto(project_url, wait_until="networkidle")

        # Wait for the page to load
        await self._page.wait_for_load_state("domcontentloaded")
        logger.info("Project data page loaded")

    async def click_upload_beta_button(self) -> None:
        """Click the Upload BETA button."""
        logger.info("Looking for Upload BETA button...")

        # Try different selectors for the upload button
        upload_btn_selectors = [
            'button:has-text("Upload BETA")',
            'button:has-text("Upload")',
            'a:has-text("Upload BETA")',
            'a:has-text("Upload")',
            '[class*="upload"]',
            'button[class*="btn"]:has-text("Upload")',
        ]

        for selector in upload_btn_selectors:
            try:
                btn = self._page.locator(selector).first
                if await btn.count() > 0:
                    await btn.click()
                    await self._page.wait_for_load_state("networkidle")
                    logger.info("Upload button clicked")
                    return
            except Exception:
                continue

        raise Exception("Upload button not found")

    async def upload_csv_file(self, file_path: Path) -> None:
        """Upload a CSV file to Epicollect5."""
        logger.info(f"Uploading file: {file_path}")

        # Wait for file input to be available
        file_input = self._page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=WAIT_TIMEOUT)

        # Upload the file
        await file_input.set_input_files(str(file_path))
        logger.info("File selected for upload")

        # Click upload/confirm button if present
        try:
            confirm_btn = self._page.locator(
                'button:has-text("Upload"), button:has-text("Confirm"), button:has-text("Import")'
            ).first
            if await confirm_btn.count() > 0:
                await confirm_btn.click()
        except Exception as e:
            logger.debug(f"No confirm button needed: {e}")

    async def wait_for_upload_completion(self) -> None:
        """Wait for the upload to complete by detecting the 'Download failed rows' button."""
        logger.info("Waiting for upload to complete...")

        try:
            # Wait for the "Download failed rows" button which indicates upload completion
            download_failed_btn = self._page.locator(
                'span.hidden-xs:has-text("Download failed rows")'
            )
            await download_failed_btn.wait_for(state="visible", timeout=UPLOAD_TIMEOUT)
            logger.info("Upload completed - 'Download failed rows' button detected")
            return

        except Exception as e:
            logger.warning(f"Upload completion check failed: {e}")

    async def close_modal(self) -> None:
        """Close any open modal dialogs."""
        try:
            close_selectors = [
                'button:has-text("Close")',
                'button:has-text("Done")',
                'button:has-text("OK")',
                '[aria-label="Close"]',
                '[class*="close"]',
                ".modal-close",
            ]

            for selector in close_selectors:
                try:
                    btn = self._page.locator(selector).first
                    if await btn.count() > 0 and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.5)
                        return
                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"Modal close attempt: {e}")


class ParallelUploader:
    """
    Manages parallel uploads using multiple browser contexts.

    This allows processing multiple chunks simultaneously for faster uploads.
    """

    def __init__(
        self,
        project_name: str,
        project_email: str,
        max_workers: int = 2,
        headless: bool = True,
    ):
        self.project_name = project_name
        self.project_email = project_email
        self.max_workers = max_workers
        self.headless = headless

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._storage_state_path: Optional[Path] = None

        # Context pool for reusing browser contexts
        self._context_pool: list[BrowserContext] = []
        self._available_contexts: Optional[asyncio.Queue] = None

    @staticmethod
    def _get_user_data_dir() -> Path:
        """Get the user data directory for browser persistence."""
        return Path(__file__).parent.parent / "browser_data"

    def _get_storage_state_path(self) -> Path:
        """Get path to storage state file."""
        return self._get_user_data_dir() / "storage_state.json"

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def start(self) -> None:
        """Start the browser for parallel operations."""
        self._playwright = await async_playwright().start()

        # Ensure user data directory exists
        self._get_user_data_dir().mkdir(parents=True, exist_ok=True)
        self._storage_state_path = self._get_storage_state_path()

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        # Create context pool for reusing browser contexts
        await self._create_context_pool()
        logger.info(
            f"Parallel uploader started with {self.max_workers} reusable contexts"
        )

    async def _create_context_pool(self) -> None:
        """Create a pool of reusable browser contexts."""
        self._available_contexts = asyncio.Queue()
        self._context_pool = []

        storage_state = None
        if self._storage_state_path and self._storage_state_path.exists():
            storage_state = str(self._storage_state_path)

        for i in range(self.max_workers):
            context = await self._browser.new_context(
                storage_state=storage_state,
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            self._context_pool.append(context)
            await self._available_contexts.put(context)

        logger.info(f"Created pool of {self.max_workers} reusable browser contexts")

    async def close(self) -> None:
        """Close all contexts and the browser."""
        # Close all pooled contexts
        for context in self._context_pool:
            try:
                await context.close()
            except Exception as e:
                logger.warning(f"Error closing context: {e}")
        self._context_pool.clear()

        if self._browser:
            await self._browser.close()

        if self._playwright:
            await self._playwright.stop()

        logger.info("Parallel uploader closed")

    async def login_and_save_state(self) -> bool:
        """
        Login and save browser state for use by workers.
        Uses existing session if available from previous login.
        The session is persisted and shared across all workers.

        Returns:
            True if already logged in, False if login was attempted.
        """
        # Create a context for login with existing storage state if available
        storage_state = None
        if self._storage_state_path and self._storage_state_path.exists():
            try:
                storage_state = str(self._storage_state_path)
                logger.info("Loading existing session from storage state")
            except Exception as e:
                logger.warning(f"Could not load storage state: {e}")

        context = await self._browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()

        try:
            # Navigate to login
            await page.goto(f"{EPICOLLECT5_URL}/login", wait_until="networkidle")

            # Check if already logged in
            if await self._check_logged_in(page):
                logger.info("Already logged in from previous session")
                # Save current state to ensure it's up to date
                await context.storage_state(path=str(self._storage_state_path))
                return True

            # If not logged in, log error - user needs to login manually first
            logger.error(
                "User is not logged in. Please ensure a valid session exists in browser_data/"
            )
            return False

        finally:
            await context.close()

    async def verify_login(self) -> bool:
        """
        Verify that the user is logged in before processing chunks.
        This ensures no chunk processing starts until login is confirmed.

        Returns:
            True if user is logged in, False otherwise.
        """
        logger.info("Verifying login session...")

        # Load storage state
        storage_state = None
        if self._storage_state_path and self._storage_state_path.exists():
            storage_state = str(self._storage_state_path)
        else:
            logger.error("No storage state found - user not logged in")
            return False

        # Create a context to verify login
        context = await self._browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()

        try:
            # Navigate to login page to check if session is valid
            await page.goto(f"{EPICOLLECT5_URL}/myprojects", wait_until="networkidle")

            # Check if we're logged in (not redirected to login)
            is_logged_in = await self._check_logged_in(page)

            if is_logged_in:
                logger.info("Login session verified successfully")
            else:
                logger.error("Login session verification failed - user not logged in")

            return is_logged_in

        except Exception as e:
            logger.error(f"Login verification error: {e}")
            return False

        finally:
            await context.close()

    async def _check_logged_in(self, page: Page) -> bool:
        """Check if user is logged in on the given page."""
        try:
            # Check URL for logged-in pages
            current_url = page.url
            if "/myprojects" in current_url or "/project/" in current_url:
                return True

            # Look for logout link/button
            logout_link = page.locator(
                'a:has-text("Logout"), button:has-text("Logout"), a:has-text("Sign out")'
            )
            if await logout_link.count() > 0:
                return True

            # Look for user avatar or profile indicator
            user_indicators = page.locator(
                '[class*="avatar"], [class*="user-menu"], [class*="profile"]'
            )
            if await user_indicators.count() > 0:
                return True

        except Exception as e:
            logger.debug(f"Login check error: {e}")

        return False

    async def upload_chunk(
        self,
        file_path: Path,
        chunk_number: int,
        total_chunks: int,
        progress_callback: Optional[Callable[[int, int, str], Awaitable[None]]] = None,
    ) -> bool:
        """
        Upload a single chunk using a worker context.
        All workers share the same session cookies from the login.

        Args:
            file_path: Path to the chunk CSV file.
            chunk_number: Current chunk number.
            total_chunks: Total number of chunks.
            progress_callback: Async callback to report progress.

        Returns:
            True if upload succeeded, False otherwise.
        """
        # Get a context from the pool (blocks if none available)
        context = await self._available_contexts.get()
        logger.info(f"Worker acquired context for chunk {chunk_number}/{total_chunks}")

        page = None
        try:
            page = await context.new_page()

            try:
                # Navigate directly to project data (login was already verified before starting chunks)
                logger.info(f"Chunk {chunk_number}: Navigating to project...")
                project_url = f"{EPICOLLECT5_URL}/project/{self.project_name}/data"
                await page.goto(project_url, wait_until="networkidle")

                # Click upload button
                upload_btn_selectors = [
                    'button:has-text("Upload BETA")',
                    'button:has-text("Upload")',
                    'a:has-text("Upload BETA")',
                ]

                for selector in upload_btn_selectors:
                    try:
                        btn = page.locator(selector).first
                        if await btn.count() > 0:
                            await btn.click()
                            await page.wait_for_load_state("networkidle")
                            break
                    except Exception:
                        continue

                # Upload file
                file_input = page.locator('input[type="file"]').first
                await file_input.wait_for(state="attached", timeout=WAIT_TIMEOUT)
                await file_input.set_input_files(str(file_path))

                # Click confirm if present
                try:
                    confirm_btn = page.locator(
                        'button:has-text("Upload"), button:has-text("Confirm"), button:has-text("Import")'
                    ).first
                    if await confirm_btn.count() > 0:
                        await confirm_btn.click()
                except Exception as exc:
                    logger.warning(
                        "Chunk %s: Failed to click confirm/import button: %s",
                        chunk_number,
                        exc,
                    )

                # Wait for completion by detecting the "Download failed rows" button
                logger.info(f"Chunk {chunk_number}: Waiting for upload completion...")
                download_failed_btn = page.locator(
                    'span.hidden-xs:has-text("Download failed rows")'
                )
                await download_failed_btn.wait_for(
                    state="visible", timeout=UPLOAD_TIMEOUT
                )
                logger.info(
                    f"Chunk {chunk_number}: 'Download failed rows' button detected"
                )

                await page.wait_for_load_state("networkidle")

                # Close modal
                try:
                    close_btn = page.locator(
                        'button:has-text("Close"), button:has-text("Done")'
                    ).first
                    if await close_btn.count() > 0 and await close_btn.is_visible():
                        await close_btn.click()
                except Exception:
                    pass

                if progress_callback:
                    await progress_callback(
                        chunk_number,
                        total_chunks,
                        f"Chunk {chunk_number}/{total_chunks} completed!",
                    )

                logger.info(
                    f"Chunk {chunk_number}/{total_chunks} uploaded successfully"
                )
                return True

            except Exception as e:
                logger.error(f"Chunk {chunk_number} failed: {e}")
                if progress_callback:
                    await progress_callback(
                        chunk_number,
                        total_chunks,
                        f"Chunk {chunk_number} failed: {e}",
                    )
                return False

        finally:
            # Close page but keep context for reuse
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")
            # Return context to pool for reuse
            await self._available_contexts.put(context)
            logger.debug(f"Context returned to pool for chunk {chunk_number}")

    async def upload_chunks_parallel(
        self,
        chunk_files: list[Path],
        progress_callback: Optional[Callable[[int, int, str], Awaitable[None]]] = None,
    ) -> dict:
        """
        Upload multiple chunks in parallel.

        Args:
            chunk_files: List of paths to chunk CSV files.
            progress_callback: Async callback to report progress.

        Returns:
            Dictionary with success/failure counts.
        """
        total_chunks = len(chunk_files)

        # Create tasks for all chunks
        tasks = [
            self.upload_chunk(
                file_path=chunk_file,
                chunk_number=i + 1,
                total_chunks=total_chunks,
                progress_callback=progress_callback,
            )
            for i, chunk_file in enumerate(chunk_files)
        ]

        # Run all tasks (Queue-based context pool controls concurrency)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes and failures, and log any exceptions explicitly
        successes = sum(1 for r in results if r is True)
        exceptions = [r for r in results if isinstance(r, Exception)]
        failures = total_chunks - successes
        if exceptions:
            for exc in exceptions:
                logger.error("Chunk upload exception: %s", exc)

        return {
            "total": total_chunks,
            "successes": successes,
            "failures": failures,
        }
