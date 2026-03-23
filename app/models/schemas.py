from __future__ import annotations

from pydantic import BaseModel, Field


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    seed_url: str = Field(min_length=1, max_length=1000)


class WatchlistCreate(BaseModel):
    type: str = Field(min_length=1, max_length=50)
    value: str = Field(min_length=1, max_length=500)
    label: str | None = Field(default=None, max_length=200)


class ReloadResponse(BaseModel):
    status: str
    loaded_targets: int
    loaded_watchlist: int
