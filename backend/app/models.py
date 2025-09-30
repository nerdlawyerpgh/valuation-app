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
    # NEW: show a range (min..max) based on the set of multiples we compute
    expected_low: Optional[float] = None
    expected_high: Optional[float] = None

    unlocked: bool = False
    # NEW: a simple dataset the frontend can chart
    bars: List[ChartBar] = []
    notes: Optional[str] = None
