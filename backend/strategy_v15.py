from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from indicators import (
    bullish_sweep,
    bearish_sweep,
    bullish_displacement,
    bearish_displacement,
)

from strategy.mtf_bias  import get_mtf_bias
from strategy.structure import detect_structure
from strategy.fvg       import bullish_fvg_reclaim, bearish_fvg_reclaim
from strategy.btc_filter import get_btc_bias
from strategy.execution  import bullish_execution, bearish_execution
from strategy.scoring    import calculate_score
from strategy.risk       import build_risk_model


log = logging.getLogger(__name__)


# ============================================================
# GRADE / TIER
# ============================================================

# Grade thresholds — tunable without touching logic
GRADE_THRESHOLDS: list[tuple[int, str, str]] = [
    # (min_score, grade, tier)
    (90, "A+", "S"),   # fix #6/#15 — A+ maps to tier S
    (80, "A",  "A"),
    (70, "B",  "B"),   # fix #15 — B grade added so mid-quality setups are tracked
    # C tier deliberately omitted: too noisy, track but don't trade
]


def grade_setup(score: int) -> tuple[str, str] | tuple[None, None]:
    """Return (grade, tier) or (None, None) if score below minimum threshold."""
    for min_score, grade, tier in GRADE_THRESHOLDS:
        if score >= min_score:
            return grade, tier
    return None, None


# ============================================================
# SESSION DETECTION  (fix #9)
# ============================================================

def get_session() -> str:
    """
    Return the dominant trading session at current UTC time.
    Priority: overlap > london > ny > asia > off_hours
    """
    hour = datetime.now(timezone.utc).hour
    if 13 <= hour < 16:   # London + NY both open — highest confluence
        return "overlap"
    if 7 <= hour < 13:
        return "london"
    if 16 <= hour < 22:
        return "ny"
    if 0 <= hour < 7:
        return "asia"
    return "off_hours"    # 22:00-00:00 UTC — avoid


# ============================================================
# DYNAMIC SETUP TYPE  (fix #7)
# ============================================================

def build_setup_type(
    side:        str,
    has_sweep:   bool,
    has_fvg:     bool,
    has_disp:    bool,
    structure:   dict,
) -> str:
    """
    Derive setup_type from what actually fired rather than hardcoding one string.
    This is what populates the 'By Setup Type' breakdown table in the dashboard.
    """
    if side == "LONG":
        bos   = structure.get("bullish_bos",   False)
        choch = structure.get("bullish_choch", False)
    else:
        bos   = structure.get("bearish_bos",   False)
        choch = structure.get("bearish_choch", False)

    if has_sweep and has_fvg:
        return "sweep_reclaim"
    if has_fvg and has_disp and not has_sweep:
        return "fvg_continuation"
    if (bos or choch) and has_disp and not has_fvg:
        return "ob_reversal"
    if has_disp and has_sweep:
        return "deviation_breakout"
    return "mixed"          # fallback — should rarely hit


# ============================================================
# DYNAMIC ENTRY MODEL  (fix #8)
# ============================================================

def build_entry_model(
    has_fvg:  bool,
    has_exec: bool,
) -> str:
    """
    Derive entry_model from confluence rather than hardcoding 'smc_reclaim'.
    This is what populates the 'By Entry Model' breakdown table.
    """
    if has_fvg and has_exec:
        return "confirmation"   # waited for both FVG + execution trigger
    if has_fvg:
        return "reclaim"        # FVG reclaim only — standard
    return "aggressive"         # no FVG, took the displacement directly


# ============================================================
# HTF BIAS STRING  (fix #5)
# ============================================================

def build_htf_bias(bias: dict) -> str:
    """
    Dashboard filters/analytics expect 'bull' | 'bear' | 'neutral'.
    Original code set htf_bias = side.lower() → 'long'/'short' which is wrong.
    """
    if bias.get("bullish") and not bias.get("bearish"):
        return "bull"
    if bias.get("bearish") and not bias.get("bullish"):
        return "bear"
    return "neutral"


# ============================================================
# LIQUIDITY EVENT  (fix #10)
# ============================================================

def build_liquidity_event(
    side:      str,
    has_sweep: bool,
    has_disp:  bool,
) -> str:
    """
    Populate the 'By Liquidity Event' dashboard table.
    Without this field all rows show '—'.
    """
    if side == "LONG":
        if has_sweep and has_disp:
            return "bsl_sweep_displacement"
        if has_sweep:
            return "bsl_sweep"
        if has_disp:
            return "bullish_displacement"
    else:
        if has_sweep and has_disp:
            return "ssl_sweep_displacement"
        if has_sweep:
            return "ssl_sweep"
        if has_disp:
            return "bearish_displacement"
    return "none"


# ============================================================
# RISK PCT BY GRADE  (fix #12)
# ============================================================

RISK_BY_TIER: dict[str, float] = {
    "S": 1.0,    # A+ — full size
    "A": 0.75,   # A  — three-quarter size
    "B": 0.50,   # B  — half size
}


# ============================================================
# CONFLICT RESOLUTION  (fix #1)
# ============================================================

def resolve_conflict(
    bias:      dict,
    btc:       dict,
    structure: dict,
) -> str:
    """
    Called when both LONG and SHORT conditions fire simultaneously.
    Priority: BTC bias → MTF bias → structure strength (BOS > CHOCH).
    """
    # 1. BTC bias as tiebreaker
    btc_bull = btc.get("bullish", False)
    btc_bear = btc.get("bearish", False)
    if btc_bull and not btc_bear:
        return "LONG"
    if btc_bear and not btc_bull:
        return "SHORT"

    # 2. MTF bias as tiebreaker
    if bias.get("bullish") and not bias.get("bearish"):
        return "LONG"
    if bias.get("bearish") and not bias.get("bullish"):
        return "SHORT"

    # 3. Structure strength — BOS is a stronger confirmation than CHOCH
    long_strength  = 2 if structure.get("bullish_bos")  else 1
    short_strength = 2 if structure.get("bearish_bos")  else 1
    return "LONG" if long_strength >= short_strength else "SHORT"


# ============================================================
# BUILD SIGNAL
# ============================================================

def build_signal(
    symbol:  str,
    df_15m:  pd.DataFrame,
    df_1h:   pd.DataFrame,
    df_4h:   pd.DataFrame,
    btc_15m: pd.DataFrame,
) -> dict | None:

    if len(df_15m) < 100 or len(df_1h) < 100 or len(df_4h) < 100:
        return None

    # ── MTF BIAS ─────────────────────────────────────────────
    bias = get_mtf_bias(df_4h=df_4h, df_1h=df_1h, df_15m=df_15m)

    # ── STRUCTURE ─────────────────────────────────────────────
    structure = detect_structure(df_15m)

    # ── SWEEPS & DISPLACEMENT ─────────────────────────────────
    long_sweep  = bullish_sweep(df_15m)
    short_sweep = bearish_sweep(df_15m)
    long_disp   = bullish_displacement(df_15m)
    short_disp  = bearish_displacement(df_15m)

    # ── FVG ───────────────────────────────────────────────────
    bullish_fvg = bullish_fvg_reclaim(df_15m)
    bearish_fvg = bearish_fvg_reclaim(df_15m)

    # ── BTC FILTER ────────────────────────────────────────────
    btc = get_btc_bias(btc_15m)

    # ── EXECUTION ─────────────────────────────────────────────
    execution_long  = bullish_execution(df_15m)
    execution_short = bearish_execution(df_15m)

    # ── SETUP CONDITIONS ─────────────────────────────────────
    #
    # fix #2: BTC filter now used as a hard gate — no LONG signal
    #         when BTC is bearish, no SHORT when BTC is bullish.
    #
    # fix #3: FVG now optional but execution is also checked.
    #         The set is: sweep + displacement + structure + (fvg OR execution).
    #         This gives the strategy flexibility while maintaining quality.
    #
    btc_not_bear = not btc.get("bearish", False)
    btc_not_bull = not btc.get("bullish", False)

    long_structure  = structure.get("bullish_bos") or structure.get("bullish_choch")
    short_structure = structure.get("bearish_bos") or structure.get("bearish_choch")

    long_confluence  = bullish_fvg or execution_long   # fix #3/#4
    short_confluence = bearish_fvg or execution_short

    long_valid = (
        long_sweep
        and long_disp
        and bias.get("bullish")
        and long_structure
        and long_confluence      # fix #3/#4
        and btc_not_bear         # fix #2
    )

    short_valid = (
        short_sweep
        and short_disp
        and bias.get("bearish")
        and short_structure
        and short_confluence     # fix #3/#4
        and btc_not_bull         # fix #2
    )

    # ── CONFLICT RESOLUTION  (fix #1) ────────────────────────
    if long_valid and short_valid:
        side = resolve_conflict(bias, btc, structure)
        log.warning(
            "[CONFLICT] %s both sides valid — resolved to %s via tiebreaker",
            symbol, side,
        )
    elif long_valid:
        side = "LONG"
    elif short_valid:
        side = "SHORT"
    else:
        return None

    # ── SCORE ────────────────────────────────────────────────
    score, reasons = calculate_score(
        side            = side,
        bias            = bias,
        structure       = structure,
        bullish_fvg     = bullish_fvg,
        bearish_fvg     = bearish_fvg,
        btc             = btc,
        execution_long  = execution_long,
        execution_short = execution_short,
    )

    # fix #13 — validate reasons; a high score with no reasons means a scoring bug
    if score >= 70 and not reasons:
        log.warning(
            "[SCORING BUG] %s %s score=%d but reasons list is empty — check calculate_score",
            symbol, side, score,
        )

    # ── GRADE / TIER  (fix #6/#15) ───────────────────────────
    grade, tier = grade_setup(score)

    if grade is None:
        return None

    # ── RISK MODEL ───────────────────────────────────────────
    risk = build_risk_model(side=side, df_15m=df_15m)

    if not risk:
        return None

    # ── DERIVED FIELDS ───────────────────────────────────────
    has_sweep = long_sweep  if side == "LONG" else short_sweep
    has_fvg   = bullish_fvg if side == "LONG" else bearish_fvg
    has_disp  = long_disp   if side == "LONG" else short_disp
    has_exec  = execution_long if side == "LONG" else execution_short

    setup_type      = build_setup_type(side, has_sweep, has_fvg, has_disp, structure)  # fix #7
    entry_model     = build_entry_model(has_fvg, has_exec)                              # fix #8
    htf_bias        = build_htf_bias(bias)                                              # fix #5
    liquidity_event = build_liquidity_event(side, has_sweep, has_disp)                 # fix #10
    session         = get_session()                                                      # fix #9
    risk_pct        = RISK_BY_TIER.get(tier, 0.5)                                      # fix #12

    # Entry path: describes the confluence path taken — useful for the dashboard
    # entry_path column (fix #14)
    entry_path = f"{setup_type}/{entry_model}"

    # ── FINAL SIGNAL ─────────────────────────────────────────
    return {
        # Identity
        "symbol":    symbol,
        "side":      side,

        # fix #6: tier (S/A/B/C) and grade (A+/A/B) are now separate fields
        "tier":  tier,
        "grade": grade,

        # Prices
        "entry": risk["entry"],
        "sl":    risk["sl"],
        "tp1":   risk["tp1"],
        "tp2":   risk["tp2"],
        "tp3":   risk["tp3"],

        # Risk/reward
        "rr1": risk["rr1"],
        "rr2": risk["rr2"],
        "rr3": risk["rr3"],

        # Scoring — fix #11: removed redundant max_score/pct
        "score": score,

        # Classification — fix #5/#7/#8/#9/#10/#14
        "timeframe":       "15m",
        "setup_type":      setup_type,
        "entry_model":     entry_model,
        "entry_path":      entry_path,
        "htf_bias":        htf_bias,
        "session":         session,
        "liquidity_event": liquidity_event,

        # Position sizing — fix #12
        "risk_pct": risk_pct,

        # Confluence reasons list
        "reasons": reasons,
    }