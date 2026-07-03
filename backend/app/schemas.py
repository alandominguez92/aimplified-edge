"""Pydantic models mirroring the frontend's `types.ts`.

Field names are snake_case but serialize to camelCase via `to_camel`, so the
JSON the API emits is 1:1 with what the React app expects — no mapping layer.
FastAPI dumps responses by alias by default.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

Side = Literal["over", "under"]
Condition = Literal["clear", "cloudy", "rain", "dome"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ParlayLeg(CamelModel):
    prob: float       # model true probability for the leg
    odds: int         # American odds
    game_key: str     # legs sharing a game_key are correlated


class BookSide(CamelModel):
    line: float
    odds: int


class BookOdds(CamelModel):
    book: str
    over: Optional[BookSide] = None
    under: Optional[BookSide] = None


class Weather(CamelModel):
    temp_f: int
    condition: Condition


class Projection(CamelModel):
    projected_k: float
    low: float
    high: float
    confidence: float
    edge: float
    recommended_side: Optional[Side] = None
    last5_k: list[int] = []
    park_factor: float
    weather: Weather


class SharpSignal(CamelModel):
    side: Optional[Side] = None
    strength: float
    ticket_pct: int
    open_line: float
    current_line: float


class PitcherProp(CamelModel):
    # Reused for both markets. `pitcher` holds the player name and `projection`
    # the projected stat value; `market` disambiguates (strikeouts vs hits).
    id: str
    market: str = "strikeouts"
    game_time: str
    pitcher: str
    team: str
    opponent: str
    is_home: bool
    market_line: float
    books: list[BookOdds]
    projection: Projection
    sharp: SharpSignal
    # Hits board only: trailing 10-day form driving the "hottest bats" ranking.
    l10_avg: Optional[float] = None
    l10_line: Optional[str] = None  # e.g. "16/34"
