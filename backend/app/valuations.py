# backend/app/valuations.py
from __future__ import annotations
import os, re, math, logging
from pathlib import Path
from typing import Optional, List, Tuple
import pandas as pd

from .models import ValuationInput, ValuationOutput, ChartBar

# =============================================================================
# Logging
# =============================================================================
LOG = logging.getLogger("valuation")
if not LOG.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[valuation] %(levelname)s: %(message)s"))
    LOG.addHandler(h)
DEBUG = str(os.getenv("VAL_DEBUG", "")).lower() in ("1", "true", "yes", "on")
LOG.setLevel(logging.DEBUG if DEBUG else logging.INFO)

def _here() -> Path:
    return Path(__file__).resolve().parent


# =============================================================================
# Fallback tables (updated with Q2 2025 GF Data)
# =============================================================================
_TEV_FALLBACK = pd.DataFrame([
    {"TEV": "10-25",   "Multiple": 6.1, "Average": 5.9},
    {"TEV": "25-50",   "Multiple": 6.8, "Average": 6.7},
    {"TEV": "50-100",  "Multiple": 7.7, "Average": 7.7},
    {"TEV": "100-250", "Multiple": 9.0, "Average": 8.6},
    {"TEV": "250-500", "Multiple": 8.0, "Average": 9.7},
])

_INDUSTRY_FALLBACK = pd.DataFrame([
    {"Industry": "Manufacturing", "Multiple": 6.5, "Average": 6.4},
    {"Industry": "Business Services", "Multiple": 7.5, "Average": 7.0},
    {"Industry": "Healthcare Services", "Multiple": 8.3, "Average": 7.7},
    {"Industry": "Distribution", "Multiple": 7.0, "Average": 6.8},
    {"Industry": "All-Industry", "Multiple": 6.9, "Average": 6.9},
])

PE_STACK_MULTIPLE = 5.92

# Expected Debt/EBITDA by TEV band (from GF Data Chart 22)
_DEBT_EBITDA_BENCHMARKS = {
    "10-25": 3.9,
    "25-50": 4.3,
    "50-100": 3.4,
    "100-250": 4.2,
    "250-500": 4.6,
}


# =============================================================================
# CSV loading helpers
# =============================================================================
def _read_csv(path: Path) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path)
        LOG.debug(f"Loaded CSV {path} shape={df.shape} cols={list(df.columns)}")
        return df
    except Exception as e:
        LOG.warning(f"Failed to read CSV {path}: {e}")
        return None

def _load_csv_or_fallback(filename: str, needed: List[str], fallback: pd.DataFrame) -> pd.DataFrame:
    for p in (_here() / filename, Path.cwd() / filename):
        if p.exists():
            df = _read_csv(p)
            if df is None:
                continue
            df.columns = [c.strip() for c in df.columns]
            if set(needed).issubset(df.columns):
                LOG.info(f"Using CSV '{filename}' at {p}")
                return df
            LOG.warning(f"{filename} at {p} missing {set(needed)-set(df.columns)}; using fallback")
            break
    LOG.warning(f"No usable {filename}; using fallback shape={fallback.shape}")
    return fallback.copy()

def _load_tev_table() -> pd.DataFrame:
    return _load_csv_or_fallback("multiples_tev.csv", ["TEV","Multiple","Average"], _TEV_FALLBACK)

def _load_industry_table() -> pd.DataFrame:
    return _load_csv_or_fallback("multiples_industry.csv", ["Industry","Multiple","Average"], _INDUSTRY_FALLBACK)


# =============================================================================
# Helper functions
# =============================================================================
def _norm_band_label(s: str) -> str:
    """Normalize a TEV label to 'lo-hi' format"""
    s = str(s)
    m = re.search(r"(\d+)\s*[-–—]\s*(\d+)", s)
    return f"{m.group(1)}-{m.group(2)}" if m else s.strip()

def _find_tev_band(tev: float) -> str:
    """Determine which TEV band a value falls into (in millions)"""
    tev_m = tev / 1_000_000
    if tev_m < 25:
        return "10-25"
    elif tev_m < 50:
        return "25-50"
    elif tev_m < 100:
        return "50-100"
    elif tev_m < 250:
        return "100-250"
    else:
        return "250-500"


# =============================================================================
# Main entry point
# =============================================================================
def compute_valuation(payload: ValuationInput) -> ValuationOutput:
    """
    Core calculator using industry multiples as primary method.
    
    Methodology:
    1. Apply industry-specific multiple to EBITDA → get baseline TEV
    2. Add error margin (±15% default) to create TEV range
    3. Validate debt sustainability using implied Debt/EBITDA
    4. Calculate expected sale price from TEV range
    """
    e = float(payload.ebitda)
    d = float(payload.debt_pct) if payload.debt_pct is not None else None
    industry = payload.industry
    
    debt_str = f"{d:.0%}" if d is not None else "N/A"
    LOG.info(f"Inputs: EBITDA={e:,.0f}, debt%={debt_str}, industry={industry!r}")

    # 1) Load data
    tev_df = _load_tev_table()
    ind_df = _load_industry_table()

    # 2) Get industry multiple (primary method)
    ind_mult_current = ind_mult_avg = None
    
    if industry and isinstance(ind_df, pd.DataFrame) and len(ind_df):
        sel = ind_df.loc[ind_df["Industry"].astype(str).str.strip().str.lower()
                         == industry.strip().lower()]
        if not sel.empty:
            ind_mult_current = float(sel.iloc[0]["Multiple"])
            ind_mult_avg = float(sel.iloc[0]["Average"])
            LOG.info(f"Industry '{industry}': current={ind_mult_current:.2f}x, avg={ind_mult_avg:.2f}x")
        else:
            LOG.warning(f"Industry '{industry}' not found; using All-Industry")
    
    # Fallback to All-Industry if no specific industry match
    if ind_mult_current is None:
        all_ind = ind_df.loc[ind_df["Industry"].astype(str).str.lower() == "all-industry"]
        if not all_ind.empty:
            ind_mult_current = float(all_ind.iloc[0]["Multiple"])
            ind_mult_avg = float(all_ind.iloc[0]["Average"])
        else:
            # Ultimate fallback from TEV table
            ind_mult_current = float(tev_df.iloc[0]["Multiple"])
            ind_mult_avg = float(tev_df.iloc[0]["Average"])
    
    # 3) Calculate baseline TEV from industry multiple
    tev_current = e * ind_mult_current
    tev_avg = e * ind_mult_avg
    tev_baseline = tev_current  # Use current as baseline
    
    LOG.info(f"Baseline TEV: current={tev_current:,.0f}, avg={tev_avg:,.0f}")
    
    # 4) Add error margin to TEV (±15% default, configurable)
    # This accounts for deal-specific factors, negotiation, market timing
    error_margin = float(os.getenv("TEV_ERROR_MARGIN", "0.15"))  # 15%
    tev_low = tev_baseline * (1 - error_margin)
    tev_high = tev_baseline * (1 + error_margin)
    
    LOG.info(f"TEV range with ±{error_margin:.0%} margin: [{tev_low:,.0f}, {tev_high:,.0f}]")
    
    # 5) Determine TEV band and validate debt sustainability
    band_label = _find_tev_band(tev_baseline)
    expected_debt_ebitda = _DEBT_EBITDA_BENCHMARKS.get(band_label, 4.0)
    
    debt_warning = None
    if d is not None:
        # Calculate implied debt from TEV
        implied_debt = tev_baseline * d
        implied_debt_ebitda = implied_debt / e
        
        LOG.info(f"Debt validation: band={band_label}, "
                f"implied D/EBITDA={implied_debt_ebitda:.2f}x, "
                f"benchmark={expected_debt_ebitda:.2f}x")
        
        # Flag if over-leveraged (>20% above benchmark)
        if implied_debt_ebitda > expected_debt_ebitda * 1.2:
            debt_warning = (f"Debt/EBITDA of {implied_debt_ebitda:.1f}x exceeds "
                          f"typical range for {band_label}M TEV tier "
                          f"(benchmark: {expected_debt_ebitda:.1f}x)")
            LOG.warning(debt_warning)
    
    # 6) Calculate additional valuation tracks for context
    # Get TEV band multiples for comparison
    tev_band_row = tev_df.loc[tev_df["TEV"].astype(str).map(_norm_band_label) == band_label]
    if not tev_band_row.empty:
        tev_mult_current = float(tev_band_row.iloc[0]["Multiple"])
        tev_mult_avg = float(tev_band_row.iloc[0]["Average"])
        EV_TEV_current = e * tev_mult_current
        EV_TEV_avg = e * tev_mult_avg
    else:
        EV_TEV_current = tev_current
        EV_TEV_avg = tev_avg
    
    EV_PE_stack = e * PE_STACK_MULTIPLE
    
    # 7) Report TEV only - equity value calculation requires net debt review
    # Sale Price (Equity Value) = TEV - Net Debt (requires financial statements)
    expected_valuation = tev_baseline  # Keep for backward compatibility
    expected_low = tev_low
    expected_high = tev_high
    
    # 8) Chart bars for visualization
    bars: List[ChartBar] = []
    bars.append(ChartBar(name=f"TEV Range Low", value=float(tev_low)))
    bars.append(ChartBar(name=f"TEV Range High", value=float(tev_high)))
    bars.append(ChartBar(name=f"Industry Current ({industry or 'All'})", value=float(tev_current)))
    bars.append(ChartBar(name=f"Industry 5-yr Avg", value=float(tev_avg)))
    bars.append(ChartBar(name=f"TEV Band Current ({band_label}M)", value=float(EV_TEV_current)))
    bars.append(ChartBar(name=f"TEV Band 5-yr Avg", value=float(EV_TEV_avg)))
    bars.append(ChartBar(name="PE Stack", value=float(EV_PE_stack)))
    
    # 9) Notes for transparency
    notes = (f"Method: Industry multiple; "
        f"Industry={industry or 'All-Industry'}; "
        f"Multiple={ind_mult_current:.2f}x; "
        f"Band={band_label}M; "
        f"TEV range=±{error_margin:.0%}; "
        f"Note: Sale price (equity value) = TEV - Net Debt (requires financial review)")
    if debt_warning:
        notes += f"; WARNING: {debt_warning}"
    
    return ValuationOutput(
        enterprise_value=float(tev_baseline),
        expected_valuation=float(expected_valuation),
        expected_low=float(expected_low),
        expected_high=float(expected_high),
        tev_low=float(tev_low),  # Make sure your ValuationOutput model has these fields
        tev_high=float(tev_high),
        unlocked=False,
        bars=bars,
        notes=notes,
    )