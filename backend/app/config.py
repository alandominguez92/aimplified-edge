"""Runtime configuration, read once from the environment / .env file."""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    sgo_api_key: str = os.getenv("SPORTSGAMEODDS_API_KEY", "").strip()
    mlb_season: int = int(os.getenv("MLB_SEASON", "2026"))
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5174")

    @property
    def odds_enabled(self) -> bool:
        return bool(self.sgo_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
