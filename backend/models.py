"""Pydantic models for MySetup v15 signal tracker."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Literal

from pydantic import BaseModel, Field, ConfigDict


# =========================================================
# HELPERS
# =========================================================

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =========================================================
# SIGNAL CREATE MODEL
# =========================================================

class SignalCreate(BaseModel):
    """
    Payload posted by scanner engine to /api/signals
    """

    model_config = ConfigDict(extra="allow")

    # ─────────────────────────────
    # CORE
    # ─────────────────────────────

    symbol: str
    side: Literal["LONG", "SHORT"]

    entry: float
    sl: float

    tp1: float
    tp2: float
    tp3: float

    rr1: float = 0.0
    rr2: float = 0.0
    rr3: float = 0.0

    risk_pct: float = 0.0

    # ─────────────────────────────
    # SCORING / QUALITY
    # ─────────────────────────────

    tier: Optional[str] = "A"
    grade: Optional[str] = None

    strength: Optional[float] = None
    strength_label: Optional[str] = None

    score: Optional[int] = None
    max_score: Optional[int] = None
    pct: Optional[float] = None

    # ─────────────────────────────
    # CLASSIFICATION
    # ─────────────────────────────

    entry_path: Optional[str] = None
    regime: Optional[str] = None

    session: Optional[str] = None
    timeframe: Optional[str] = "15m"

    setup_type: Optional[str] = None
    entry_model: Optional[str] = None
    liquidity_event: Optional[str] = None
    htf_bias: Optional[str] = None

    # ─────────────────────────────
    # EXTRA CONTEXT
    # ─────────────────────────────

    confluence: Optional[Dict[str, Any]] = None

    reasons: list[str] = []

    timestamp: Optional[str] = None

    # optional chart/debug info
    notes: Optional[str] = None

    # scanner version tracking
    strategy_version: Optional[str] = "v15"

    # scanner-generated fingerprint
    fingerprint: Optional[str] = None


# =========================================================
# SIGNAL STORAGE MODEL
# =========================================================

class Signal(BaseModel):

    model_config = ConfigDict(extra="ignore")

    # ─────────────────────────────
    # IDs / META
    # ─────────────────────────────

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    strategy_version: str = "v15"

    fingerprint: Optional[str] = None

    # ─────────────────────────────
    # TRADE CORE
    # ─────────────────────────────

    symbol: str
    side: str

    entry: float

    sl: float
    sl_initial: float

    tp1: float
    tp2: float
    tp3: float

    rr1: float = 0.0
    rr2: float = 0.0
    rr3: float = 0.0

    risk_pct: float = 0.0

    # ─────────────────────────────
    # QUALITY / SCORE
    # ─────────────────────────────

    tier: str = "A"
    grade: Optional[str] = None

    strength: Optional[float] = None
    strength_label: Optional[str] = None

    score: Optional[int] = None
    max_score: Optional[int] = None
    pct: Optional[float] = None

    # ─────────────────────────────
    # CLASSIFICATION
    # ─────────────────────────────

    entry_path: Optional[str] = None
    regime: Optional[str] = None

    session: Optional[str] = None
    timeframe: str = "15m"

    setup_type: Optional[str] = None
    entry_model: Optional[str] = None
    liquidity_event: Optional[str] = None
    htf_bias: Optional[str] = None

    # ─────────────────────────────
    # EXTRA CONTEXT
    # ─────────────────────────────

    confluence: Optional[Dict[str, Any]] = None

    reasons: list[str] = []

    notes: Optional[str] = None

    # ─────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────

    status: str = "OPEN"

    # TP tracking
    hit_tp1: bool = False
    hit_tp2: bool = False
    hit_tp3: bool = False

    bars_to_tp1: Optional[int] = None
    bars_to_tp2: Optional[int] = None
    bars_to_tp3: Optional[int] = None

    bars_elapsed: int = 0

    # performance
    max_favorable_r: float = 0.0
    max_adverse_r: float = 0.0

    result_r: Optional[float] = None

    # ─────────────────────────────
    # TIMESTAMPS
    # ─────────────────────────────

    created_at: str = Field(default_factory=_utc_now_iso)

    updated_at: str = Field(default_factory=_utc_now_iso)

    resolved_at: Optional[str] = None

    last_resolved_open_time: Optional[int] = None

    # ─────────────────────────────
    # OPTIONAL FUTURE ANALYTICS
    # ─────────────────────────────

    entry_price_live: Optional[float] = None

    highest_price_seen: Optional[float] = None
    lowest_price_seen: Optional[float] = None

    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None

    btc_regime: Optional[str] = None