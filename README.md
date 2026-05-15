# Crypto Dashboard + Binance Perp Scanner

## Overview

This project is a crypto trading dashboard and Binance perpetual futures scanner using:

* TradingView Pine Script
* Python backend scanner
* Telegram alerts
* Multi-timeframe analysis

Goal:
Generate high-quality intraday/swing long-short setups with strong RR while reducing fakeouts and late entries.

---

# Current Core Logic

The system currently uses combinations of:

* Market structure
* Liquidity sweeps
* Fair Value Gaps (FVG)
* Order Blocks (OB)
* Trend alignment
* Volume/volatility
* Multi-timeframe confluence

---

# Current Workflow

1. Scanner checks Binance perp pairs
2. Conditions are evaluated
3. Pine dashboard visualizes setups
4. Telegram alerts are sent for valid setups
5. Manual execution/trade management

---

# Current Focus Areas

Need optimization for:

* Earlier entries without excessive noise
* Reducing fakeouts
* Better SL placement
* Better TP logic
* Higher RR opportunities
* Better confluence scoring
* Avoiding chop/range conditions
* Alert quality over quantity

---

# Important Questions

Please review:

* Core trading logic
* Entry/exit conditions
* Filters and confirmations
* Market structure handling
* Multi-timeframe logic
* Dashboard usefulness
* Alert quality
* Potential repaint/lag issues
* Weak/noisy conditions
* Missing confirmations
* Statistical tracking improvements

---

# Requested Output

Please suggest:

* High-impact improvements only
* Modular upgrades instead of complete rewrite
* Better long/short criteria
* Confluence scoring system
* Setup ranking system (A/B/C quality)
* Better SL/TP framework
* Tracking metrics for long-term evaluation

---

# Tech Stack

Frontend:

* React/Tailwind dashboard

Backend:

* Python scanner

Alerts:

* Telegram

Charting:

* TradingView Pine Script
