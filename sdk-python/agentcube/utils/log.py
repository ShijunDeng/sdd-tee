"""Logging utilities for AgentCube SDK."""

import logging
from typing import Union


def get_logger(name: str, level: Union[int, str] = logging.INFO) -> logging.Logger:
    """Create and configure a logger with the given name and level."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
