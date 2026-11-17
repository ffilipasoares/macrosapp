"""The "eat well" standards: numbers and food lists the week balance check uses.

They live in a data file so a nutritionist's criteria can replace them without
code changes. Every plan reports which version it was checked against.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

_DIR = Path(__file__).parent


class CheckStandard(BaseModel):
    label: str
    min_share_of_days: float | None = Field(default=None, ge=0, le=1)
    min_meals: int | None = Field(default=None, ge=0)
    max_meals: int | None = Field(default=None, ge=0)
    min_kinds: int | None = Field(default=None, ge=0)


class Standards(BaseModel):
    version: str
    reviewed_by: str | None = None
    note: str = ""
    checks: dict[str, CheckStandard]
    proteins: dict[str, list[str]]
    foods: dict[str, list[str]]


@lru_cache
def load(name: str = "default") -> Standards:
    return Standards.model_validate(json.loads((_DIR / f"{name}.json").read_text()))
