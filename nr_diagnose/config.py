"""Configuration loader - reads from .env and environment variables only."""

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    base_url: str
    api_key: str
    model: str
    agents_dir: str
    local_data: str
    verbose: bool = False


def load() -> Config:
    """Load configuration from .env file and environment variables."""
    # Load .env file from current directory or project root
    load_dotenv()

    home_dir = Path.home()

    return Config(
        base_url=os.getenv("ANTHROPIC_BASE_URL", "https://nerd-completion.staging-service.nr-ops.net"),
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        model=os.getenv("LLM_MODEL_NAME", "claude-sonnet-4-5-20250514"),
        agents_dir=os.getenv("NR_DIAGNOSE_AGENTS_DIR", ""),
        local_data=str(home_dir / ".nr-diagnose"),
    )
