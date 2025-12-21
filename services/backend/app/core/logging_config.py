"""Logging configuration for Noesis backend."""
import logging
import sys
import os

def setup_logging():
    """Configure application logging based on environment."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    environment = os.getenv("ENVIRONMENT", "development")
    
    # Configure logging format
    if environment == "production":
        # Structured logging for production
        log_format = '{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "function": "%(funcName)s", "line": %(lineno)d, "message": "%(message)s"}'
    else:
        # Human-readable for development
        log_format = '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s'
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the specified module."""
    return logging.getLogger(name)
