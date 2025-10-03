from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List, Dict, Any

class Lead(BaseModel):
    email: EmailStr
    phone: str
    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        return v.strip()

class ValuationInput(BaseModel):
    ebitda: float = Field(..., gt=0)
    net_debt: float = 0.0
    industry: Optional[str] = None
    # keep any other optional knobs you already had (user_tev, debt_pct, etc.)
    debt_pct: Optional[float] = None
    market_total_debt_to_ebitda: Optional[float] = None
    user_tev: Optional[float] = None
    extras: Optional[Dict[str, Any]] = None

class ChartBar(BaseModel):
    name: str
    value: float

class ValuationOutput(BaseModel):
    enterprise_value: float
    expected_valuation: float
    expected_low: Optional[float] = None
    expected_high: Optional[float] = None
    tev_low: Optional[float] = None  # ADD
    tev_high: Optional[float] = None  # ADD
    unlocked: bool = False
    bars: List[ChartBar] = []
    notes: Optional[str] = None
    notes: Optional[str] = None
