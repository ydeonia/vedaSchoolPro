"""
Centralized logging configuration for VedaFlow.
Call setup_logging() once at app startup.
"""
import logging
import sys


def setup_logging(debug: bool = False):
    """Configure structured logging for the application."""
    level = logging.DEBUG if debug else logging.INFO

    # Format: timestamp — logger — level — message
    formatter = logging.Formatter(
        fmt="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(level)

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console)

    # Silence noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING if not debug else logging.INFO)

    logging.getLogger("vedaflow").info(f"Logging initialized (level={logging.getLevelName(level)})")
