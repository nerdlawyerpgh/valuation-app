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
# Fallback tables (used if CSVs are missing or malformed)
# =============================================================================
_TEV_FALLBACK = pd.DataFrame([
    {"TEV": "10–25",   "Multiple": 6.7, "Average": 6.2},
    {"TEV": "25–50",   "Multiple": 7.2, "Average": 7.0},
    {"TEV": "50–100",  "Multiple": 8.3, "Average": 8.0},
    {"TEV": "100–250", "Multiple":10.3, "Average": 8.8},
    {"TEV": "250–500", "Multiple": 8.1, "Average":10.0},
])
_INDUSTRY_FALLBACK = pd.DataFrame([
    {"Industry":"All-Industry","Multiple":7.1,"Average":6.6}
])
PE_STACK_MULTIPLE = 5.92   # simple fallback track


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

def _first_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
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
    # columns: TEV, Multiple, Average, (optional dispersion columns; see _band_dispersion)
    return _load_csv_or_fallback("multiples_tev.csv", ["TEV","Multiple","Average"], _TEV_FALLBACK)

def _load_industry_table() -> pd.DataFrame:
    # columns: Industry, Multiple, Average, (optional dispersion)
    return _load_csv_or_fallback("multiples_industry.csv", ["Industry","Multiple","Average"], _INDUSTRY_FALLBACK)

def _load_leverage_table() -> Optional[pd.DataFrame]:
    """
    Expect columns:
      - TEV
      - Debt_EBITDA (or 'Leverage')
    Optional dispersion/sample-size columns will be mapped to _L_sd / _L_n.
    """
    for p in (_here() / "multiples_leverage.csv", Path.cwd() / "multiples_leverage.csv"):
        if p.exists():
            try:
                df = pd.read_csv(p)
                df.columns = [c.strip() for c in df.columns]
                lev_col = _first_col(df, ["Debt_EBITDA","Debt/EBITDA","Leverage"])
                if not lev_col:
                    LOG.warning(f"Leverage CSV {p} missing Debt_EBITDA/Leverage; ignoring.")
                    return None
                df["_norm"] = df["TEV"].map(_norm_band_label)
                df["_L"] = pd.to_numeric(df[lev_col], errors="coerce")

                # Optional dispersion
                sd_col = _first_col(df, ["Debt_EBITDA_SD","Debt/EBITDA_SD","Leverage_SD","StdDev_Leverage","Stdev_Leverage","Sigma_L"])
                n_col  = _first_col(df, ["N_Leverage","N","n","Samples","Count","Num","Observations"])
                if sd_col: df["_L_sd"] = pd.to_numeric(df[sd_col], errors="coerce")
                if n_col:  df["_L_n"]  = pd.to_numeric(df[n_col],  errors="coerce")

                LOG.info(f"Using leverage CSV at {p} rows={len(df)}")
                return df
            except Exception as e:
                LOG.warning(f"Failed to read leverage CSV {p}: {e}")
    LOG.info("No leverage CSV found; Mode B will use overall_L if provided.")
    return None


# =============================================================================
# Normalization and dispersion helpers
# =============================================================================
def _norm_band_label(s: str) -> str:
    """Normalize a TEV label to 'lo-hi' (handles hyphen/en dash, ignores $ and M)."""
    s = str(s)
    m = re.search(r"(\d+)\s*[–-]\s*(\d+)", s)
    return f"{m.group(1)}-{m.group(2)}" if m else s.strip()

def _band_dispersion(row: pd.Series) -> Tuple[Optional[float], Optional[float]]:
    """
    Try to read stdev & n for a multiples row (TEV or Industry).
    Flexible header support.
    Returns (stdev, n) or (None, None) if not found.
    """
    stdev = None; n = None
    for k in ["StdDev","Stdev","SD","Sigma","Stdev_Multiple","Multiple_SD"]:
        if k in row.index:
            try: stdev = float(row[k])
            except Exception: pass
            break
    for k in ["N","n","Samples","Count","Num","Observations"]:
        if k in row.index:
            try: n = float(row[k])
            except Exception: pass
            break
    if n is not None and n <= 0: n = None
    if stdev is not None and stdev < 0: stdev = None
    return stdev, n

def _leverage_stats_for_band(leverage_df: Optional[pd.DataFrame], band_label: str) -> Tuple[Optional[float], Optional[float]]:
    """Return (L_sd, L_n) for the normalized band label."""
    if leverage_df is None:
        return (None, None)
    norm = _norm_band_label(band_label)
    hit = leverage_df.loc[leverage_df["_norm"] == norm]
    if hit.empty:
        return (None, None)
    L_sd = float(hit.iloc[0]["_L_sd"]) if "_L_sd" in hit.columns and pd.notna(hit.iloc[0]["_L_sd"]) else None
    L_n  = float(hit.iloc[0]["_L_n"])  if "_L_n"  in hit.columns and pd.notna(hit.iloc[0]["_L_n"])  else None
    return (L_sd, L_n)


# =============================================================================
# Band selection from debt% (Mode B)
# =============================================================================
def _select_band_by_debt_pct(
    d: float,                      # user debt% of TEV (decimal 0..1)
    tev_df: pd.DataFrame,          # TEV multiples; cols: TEV, Multiple
    leverage_df: Optional[pd.DataFrame],  # leverage table with _norm, _L (Debt/EBITDA)
    overall_L: Optional[float] = None,    # fallback L if no leverage_df
) -> Tuple[str, float, float, float]:
    """
    Choose the band whose implied debt% (L / m) is closest to d.

    Returns:
        (band_label, multiple_current, L_used, implied_debt_pct_for_band)

    Example:
      d = 0.60 ; for band '25–50': m=6.5, L=3.9
      implied = L/m = 3.9/6.5 ≈ 0.60 -> likely match
    """
    if leverage_df is None and overall_L is None:
        raise ValueError("Need leverage_df or overall_L to infer band from debt%")

    rows = []
    for _, row in tev_df.iterrows():
        band_label = str(row["TEV"])
        m = float(row["Multiple"])
        if leverage_df is not None:
            norm = _norm_band_label(band_label)
            hit = leverage_df.loc[leverage_df["_norm"] == norm]
            L = float(hit.iloc[0]["_L"]) if not hit.empty else float(overall_L or 4.0)
        else:
            L = float(overall_L or 4.0)
        implied = L / m
        rows.append((band_label, m, L, implied, abs(implied - d)))

    rows.sort(key=lambda t: t[4])          # sort by |implied - d|
    band_label, m_curr, L_used, implied, _diff = rows[0]
    LOG.info(
        f"Mode B: d={d:.2%} -> band={band_label}, L={L_used:.2f}, "
        f"m={m_curr:.2f}, implied={implied:.2%}, Δ={_diff:.2%}"
    )
    return band_label, m_curr, L_used, implied

# =============================================================================
# CI helpers
# =============================================================================
def _ci_from_se(mean: float, se: float, z: float = 1.96) -> Tuple[float, float]:
    lo = max(0.0, mean - z * se)
    hi = max(0.0, mean + z * se)
    return lo, hi


# =============================================================================
# Main entry point
# =============================================================================
def compute_valuation(payload: ValuationInput) -> ValuationOutput:
    """
    Core calculator used by the API.

    Inputs (key ones):
      - payload.ebitda: float USD
      - payload.debt_pct: Optional[float] (0..1). If provided, we use Mode B to pick a band.
      - payload.industry: Optional[str]. If matches a row, we compute industry EV tracks.

    Outputs:
      - enterprise_value: headline EV (uses TEV current multiple)
      - expected_valuation: headline expected (prefers industry current -> industry avg -> TEV current)
      - expected_low / expected_high: min/max or 95% CI when dispersion available
      - bars: data series for charting (labels + values)
      - notes: debug breadcrumb (mode, band, multiples)
    """
    e = float(payload.ebitda)
    d = float(payload.debt_pct) if payload.debt_pct is not None else None
    LOG.info(f"Inputs: EBITDA={e:,.0f}, debt%={'NA' if d is None else f'{d:.0%}'}, industry={payload.industry!r}")

    # 1) Load tables
    tev_df = _load_tev_table()
    ind_df = _load_industry_table()
    lev_df = _load_leverage_table()

    # 2) Select band & multiples
    if d is not None:
        band_label, m_curr, L_used, implied = _select_band_by_debt_pct(
            d=d,
            tev_df=tev_df,
            leverage_df=lev_df,
            overall_L=payload.market_total_debt_to_ebitda or 4.0,
        )
        #row = tev_df.loc[_norm_band_label(tev_df["TEV"]) == _norm_band_label(band_label)]
        mask = tev_df["TEV"].astype(str).map(_norm_band_label) == _norm_band_label(band_label)
        row = tev_df.loc[mask]
        if row.empty:
            # fallback to first row to avoid crashes; also log it
            LOG.warning(f"No TEV row matched band={band_label!r}; falling back to first row")
            row = tev_df.iloc[[0]]
        m_avg = float(row.iloc[0]["Average"]) if not row.empty else m_curr
        tev_estimated = (L_used * e) / max(d, 1e-6)   # TEV = e * L / d
        debt_over_ebitda = d * m_curr                 # realism check
        LOG.debug(f"Mode B: TEV_est={tev_estimated:,.0f}, D/EBITDA_implied={debt_over_ebitda:.2f}")
    else:
        r = tev_df.iloc[0]   # default band if no debt%
        band_label, m_curr, m_avg = str(r["TEV"]), float(r["Multiple"]), float(r["Average"])
        tev_estimated = None
        debt_over_ebitda = None
        L_used = payload.market_total_debt_to_ebitda or 4.0

    # 3) EV tracks
    EV_TEV_current = e * m_curr
    EV_TEV_avg     = e * m_avg

    ind_curr = ind_avg = None
    EV_IND_current = EV_IND_avg = None
    if payload.industry and isinstance(ind_df, pd.DataFrame) and len(ind_df):
        sel = ind_df.loc[ind_df["Industry"].astype(str).str.strip().str.lower()
                         == payload.industry.strip().lower()]
        if not sel.empty:
            ind_curr = float(sel.iloc[0]["Multiple"])
            ind_avg  = float(sel.iloc[0]["Average"])
            EV_IND_current = e * ind_curr
            EV_IND_avg     = e * ind_avg
            LOG.debug(f"Industry: {payload.industry!r} -> mult={ind_curr:.2f}, avg={ind_avg:.2f}")
        else:
            LOG.info(f"Industry {payload.industry!r} not found; skipping industry tracks.")

    EV_PE_stack = e * PE_STACK_MULTIPLE

    LOG.debug(
        "EV tracks: "
        f"TEV curr={EV_TEV_current:,.0f}, TEV avg={EV_TEV_avg:,.0f}, "
        f"IND curr={'NA' if EV_IND_current is None else f'{EV_IND_current:,.0f}'}, "
        f"IND avg={'NA' if EV_IND_avg is None else f'{EV_IND_avg:,.0f}'}, "
        f"PE stack={EV_PE_stack:,.0f}"
    )

    # 4) Headline values
    enterprise_value = EV_TEV_current
    expected_candidates = [x for x in (EV_IND_current, EV_IND_avg, EV_TEV_current) if x is not None]
    expected = expected_candidates[0] if expected_candidates else EV_TEV_current

    # 5) Statistical CI (if possible), else envelope
    # User debt% input noise (stdev) for CI on Mode B (can override via VAL_D_SD)
    D_SD = float(os.getenv("VAL_D_SD", "0.03"))  # 3 percentage points

    ci_low = ci_high = None
    ci_method = None

    # CASE A: Mode B CI around TEV = e * L_bar / d if leverage dispersion present
    if d is not None and lev_df is not None:
        L_sd, L_n = _leverage_stats_for_band(lev_df, band_label)
        if L_sd and L_n and L_sd > 0 and L_n > 0 and d > 0:
            se_Lbar = L_sd / math.sqrt(L_n)
            var_Lterm = (se_Lbar ** 2) / (d ** 2)
            var_dterm = 0.0
            if D_SD > 0:
                var_dterm = ((L_used ** 2) * (D_SD ** 2)) / (d ** 4)
            se_modeB = e * math.sqrt(var_Lterm + var_dterm)
            mean_modeB = (L_used * e) / d
            ci_low, ci_high = _ci_from_se(mean_modeB, se_modeB, z=1.96)
            ci_method = "modeB_CI(Lbar,d)"
            LOG.info(f"CI: {ci_method} -> [{ci_low:,.0f}, {ci_high:,.0f}] (SE={se_modeB:,.0f})")

    # CASE B: CI from multiples for whichever track produced 'expected'
    if ci_low is None or ci_high is None:
        # Which source produced expected? Pref order: IND current -> IND avg -> TEV current
        if EV_IND_current is not None and abs(expected - EV_IND_current) < 1e-6:
            src = "IND_current"
            sel = ind_df.loc[ind_df["Industry"].astype(str).str.strip().str.lower()
                             == (payload.industry or "").strip().lower()]
            if not sel.empty:
                s, n = _band_dispersion(sel.iloc[0])
                if s and n:
                    se = e * (s / math.sqrt(n))
                    ci_low, ci_high = _ci_from_se(expected, se, 1.96)
                    ci_method = "EV_CI(industry_multiple)"
        elif EV_IND_avg is not None and abs(expected - EV_IND_avg) < 1e-6:
            src = "IND_avg"
            sel = ind_df.loc[ind_df["Industry"].astype(str).str.strip().str.lower()
                             == (payload.industry or "").strip().lower()]
            if not sel.empty:
                s, n = _band_dispersion(sel.iloc[0])
                if s and n:
                    se = e * (s / math.sqrt(n))
                    ci_low, ci_high = _ci_from_se(expected, se, 1.96)
                    ci_method = "EV_CI(industry_avg~dispersion_of_current)"
        else:
            src = "TEV_current"
            #tev_row = tev_df.loc[_norm_band_label(tev_df["TEV"]) == _norm_band_label(band_label)]
            mask_ci = tev_df["TEV"].astype(str).map(_norm_band_label) == _norm_band_label(band_label)
            tev_row = tev_df.loc[mask_ci]
            if not tev_row.empty:
                s, n = _band_dispersion(tev_row.iloc[0])
                if s and n:
                    se = e * (s / math.sqrt(n))
                    ci_low, ci_high = _ci_from_se(expected, se, 1.96)
                    ci_method = "EV_CI(tev_multiple)"
        if ci_method:
            LOG.info(f"CI: {ci_method} -> [{ci_low:,.0f}, {ci_high:,.0f}]")

    # CASE C: Envelope fallback
    vals = [v for v in (EV_IND_current, EV_IND_avg, EV_TEV_current, EV_TEV_avg, EV_PE_stack) if v is not None]
    envelope_low  = float(min(vals)) if vals else float(expected)
    envelope_high = float(max(vals)) if vals else float(expected)
    final_low  = ci_low  if (ci_low  is not None) else envelope_low
    final_high = ci_high if (ci_high is not None) else envelope_high
    LOG.info(f"Range returned: [{final_low:,.0f}, {final_high:,.0f}] ({'CI' if ci_low is not None else 'envelope'})")

    # 6) Chart bars for the frontend
    bars: List[ChartBar] = []
    def add(label: str, v: Optional[float]):
        if v is not None:
            bars.append(ChartBar(name=label, value=float(v)))
    add(f"TEV Current ({band_label}M)", EV_TEV_current)
    add(f"TEV 5-yr Avg ({band_label}M)", EV_TEV_avg)
    add("Industry Current", EV_IND_current)
    add("Industry 5-yr Avg", EV_IND_avg)
    add("PE Stack", EV_PE_stack)

    return ValuationOutput(
        enterprise_value=float(EV_TEV_current),
        expected_valuation=float(expected),
        expected_low=final_low,
        expected_high=final_high,
        unlocked=False,  # your gating logic can flip this
        bars=bars,
            notes=(
                f"mode={'B' if d is not None else 'default'}; "
                f"band={band_label}; m_curr={m_curr:.2f}; m_avg={m_avg:.2f}"
                + (f"; L={L_used:.2f}" if L_used is not None else "")
            ),
    )
