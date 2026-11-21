"""Multi-agent framework that builds a playable pet-raising game."""

from .graph import run_pipeline
from .config import Settings

__all__ = ["run_pipeline", "Settings"]
__version__ = "0.1.0"
