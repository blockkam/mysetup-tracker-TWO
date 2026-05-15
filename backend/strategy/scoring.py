from __future__ import annotations

import logging

log = logging.getLogger(__name__)


# ============================================================
# SCORING WEIGHTS
# Designed so the theoretical maximum sums to exactly 100.
#
# Weight breakdown:
#   bias component      :  0 – 15   (bias["score"] in [0, 1] * 15)
#   base sweep+disp     : 40        (always present — gates already enforced)
#   structure (BOS|CHOCH): 10 or 15 (CHOCH > BOS, mutually exclusive)
#   FVG reclaim         : 10
#   BTC direction       : 10
#   BTC strong trend    :  5        (only if direction already aligned)
#   execution trigger   : 10
#   ─────────────────────────────────
#   Theoretical max     : 15 + 40 + 15 + 10 + 10 + 5 + 10 = 105
#
# We cap at 100 via MIN(raw, MAX_RAW) / MAX_RAW * 100 normalization.
# This means every published score is a true 0-100 percentage.
# ============================================================

W_BIAS_MULTIPLIER = 15
W_BASE            = 40   # sweep + displacement (always present)
W_BOS             = 10
W_CHOCH           = 15   # CHOCH is a stronger structural signal than BOS
W_FVG             = 10
W_BTC_DIRECTION   = 10
W_BTC_STRONG      =  5   # bonus — only when direction is already aligned
W_EXECUTION       = 10

MAX_RAW = (
    W_BIAS_MULTIPLIER   # max bias when bias["score"] == 1.0
    + W_BASE
    + W_CHOCH           # CHOCH > BOS so this is the max structure contribution
    + W_FVG
    + W_BTC_DIRECTION
    + W_BTC_STRONG
    + W_EXECUTION
)  # = 105


def _normalize(raw: float) -> int:
    """Clamp raw score to MAX_RAW then scale to 0-100 integer."""
    return round(min(raw, MAX_RAW) / MAX_RAW * 100)


# ============================================================
# CALCULATE SCORE
# ============================================================

def calculate_score(
    side:           str,
    bias:           dict,
    structure:      dict,
    bullish_fvg:    bool,
    bearish_fvg:    bool,
    btc:            dict,
    execution_long: bool,
    execution_short: bool,
) -> tuple[int, list[str]]:

    raw     = 0.0
    reasons: list[str] = []

    # ── fix #8: copy list so we don't mutate the bias dict's own list ──────
    bias_reasons = list(bias.get("reasons", []))

    # ── HTF BIAS COMPONENT ─────────────────────────────────────────────────
    bias_raw_score = bias.get("score", 0)

    # fix #3: validate bias["score"] is in expected range
    if not (0 <= bias_raw_score <= 1):
        log.warning(
            "[SCORING] bias['score']=%s is outside [0, 1] — check get_mtf_bias(); "
            "clamping to [0, 1] for safety",
            bias_raw_score,
        )
        bias_raw_score = max(0.0, min(1.0, float(bias_raw_score)))

    bias_points = bias_raw_score * W_BIAS_MULTIPLIER
    raw += bias_points
    reasons.extend(bias_reasons)

    # ── fix #4: use elif so LONG and SHORT blocks are mutually exclusive ───
    if side == "LONG":
        raw += W_BASE
        reasons.append("bullish sweep + displacement")

        # fix #1: BOS and CHOCH are mutually exclusive — CHOCH scores higher
        # (CHOCH is a change of character; BOS is a continuation break)
        if structure.get("bullish_choch"):
            raw += W_CHOCH
            reasons.append("bullish CHOCH")
        elif structure.get("bullish_bos"):
            raw += W_BOS
            reasons.append("bullish BOS")

        if bullish_fvg:
            raw += W_FVG
            reasons.append("bullish FVG reclaim")

        # fix #5: BTC direction check
        if btc.get("bullish"):
            raw += W_BTC_DIRECTION
            reasons.append("BTC bullish")
            # fix #6: strong_trend bonus ONLY when direction is already aligned
            if btc.get("strong_trend"):
                raw += W_BTC_STRONG
                reasons.append("BTC strong bullish trend")

        # fix #7: label matches actual timeframe (execution is from df_15m, not 5m)
        if execution_long:
            raw += W_EXECUTION
            reasons.append("15m bullish execution trigger")

    elif side == "SHORT":
        raw += W_BASE
        reasons.append("bearish sweep + displacement")

        # fix #1: BOS and CHOCH mutually exclusive
        if structure.get("bearish_choch"):
            raw += W_CHOCH
            reasons.append("bearish CHOCH")
        elif structure.get("bearish_bos"):
            raw += W_BOS
            reasons.append("bearish BOS")

        if bearish_fvg:
            raw += W_FVG
            reasons.append("bearish FVG reclaim")

        # fix #5 + fix #6: BTC direction + aligned trend bonus
        if btc.get("bearish"):
            raw += W_BTC_DIRECTION
            reasons.append("BTC bearish")
            if btc.get("strong_trend"):
                raw += W_BTC_STRONG
                reasons.append("BTC strong bearish trend")

        if execution_short:
            raw += W_EXECUTION
            reasons.append("15m bearish execution trigger")

    else:
        log.error("[SCORING] Unknown side=%r — returning score=0", side)
        return 0, []

    # fix #2: normalize to strict 0-100 integer
    score = _normalize(raw)

    log.debug(
        "[SCORING] %s raw=%.1f max_raw=%d normalized=%d reasons=%s",
        side, raw, MAX_RAW, score, reasons,
    )

    return score, reasons