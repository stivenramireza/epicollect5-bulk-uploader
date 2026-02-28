import logging

# Use uvicorn's logger for consistent FastAPI logging
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)
