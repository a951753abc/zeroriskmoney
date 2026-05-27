from decimal import Decimal
from pathlib import Path
import tomllib
from pydantic import BaseModel, field_validator

class Settings(BaseModel):
    funding_rate: Decimal
    min_net_threshold: Decimal
    entry_execution_buffer: Decimal
    exit_basis_buffer: Decimal
    max_cross_leg_ms: int
    stale_quote_ms: int
    refresh_seconds: int = 2

    @field_validator("funding_rate", "min_net_threshold",
                     "entry_execution_buffer", "exit_basis_buffer")
    @classmethod
    def non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

def load_settings(path: Path) -> Settings:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Settings(**data)
