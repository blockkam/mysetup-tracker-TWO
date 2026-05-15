import { useEffect, useMemo, useState, useCallback } from "react";
import axios from "axios";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  BarChart, Bar, CartesianGrid, ReferenceLine, AreaChart, Area,
} from "recharts";
import {
  RefreshCw, Send, Activity, TrendingUp, TrendingDown, Clock,
  Search, ChevronDown, ChevronRight, AlertTriangle, Info, X,
  PanelLeftClose, PanelLeftOpen,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// ─── Formatters ───────────────────────────────────────────────────────────────
const fmt    = (n, d = 2) => (n == null || isNaN(n) ? "—" : Number(n).toFixed(d));
const fmtPct = (n)        => (n == null || isNaN(n) ? "—" : (n * 100).toFixed(1) + "%");
const fmtR   = (n)        => (n == null || isNaN(n) ? "—" : (n >= 0 ? "+" : "") + Number(n).toFixed(2) + "R");
const fmtDur = (mins)     => {
  if (!mins) return "—";
  if (mins < 60) return `${Math.round(mins)}m`;
  const h = Math.floor(mins / 60), m = Math.round(mins % 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
};
const shortTime = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toISOString().slice(5, 16).replace("T", " ");
};

// ─── Pill ─────────────────────────────────────────────────────────────────────
const Pill     = ({ children, tone = "dim" }) => <span className={`pill pill-${tone}`}>{children}</span>;
const sideTone = (s) => (s === "LONG" ? "green" : "red");

// ─── Alert computation ────────────────────────────────────────────────────────
function buildAlerts(metrics, signals) {
  const out = [];
  if (!metrics) return out;

  const streak = metrics.current_streak ?? 0;
  if (streak <= -3)
    out.push({ type: "warn", msg: `${Math.abs(streak)}-trade losing streak · consider reducing position size` });

  if ((metrics.max_drawdown ?? 0) <= -5)
    out.push({ type: "warn", msg: `Drawdown at ${fmtR(metrics.max_drawdown)} · review rules before next trade` });

  (signals?.items || [])
    .filter(s => s.status === "OPEN" && s.rr1 > 0 && s.max_favorable_r != null && s.max_favorable_r / s.rr1 >= 0.8)
    .forEach(s => out.push({ type: "info", msg: `${s.symbol} OPEN · ${fmtR(s.max_favorable_r)} MFE · approaching TP1` }));

  return out;
}

// ─── Sidebar collapsible section ──────────────────────────────────────────────
function SidebarSection({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginBottom: 14 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          width: "100%", background: "none", border: "none", cursor: "pointer",
          padding: "0 0 5px", color: "inherit",
        }}
      >
        <span style={{ fontSize: 10, letterSpacing: ".12em", color: "var(--dim)", textTransform: "uppercase" }}>
          {title}
        </span>
        {open
          ? <ChevronDown  size={10} color="var(--dim)" />
          : <ChevronRight size={10} color="var(--dim)" />}
      </button>
      {open && <div>{children}</div>}
    </div>
  );
}

// ─── Sidebar filter pill ──────────────────────────────────────────────────────
function FPill({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "block", width: "100%", textAlign: "left",
        fontSize: 11, padding: "3px 8px", borderRadius: 5, marginBottom: 3,
        border: `0.5px solid ${active ? "var(--amber)" : "var(--border)"}`,
        background: active ? "rgba(245,184,0,.12)" : "transparent",
        color: active ? "var(--amber)" : "var(--dim)",
        cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap",
      }}
    >
      {label}
    </button>
  );
}

// ─── KPI card (large, row 1) ──────────────────────────────────────────────────
function KpiCard({ label, value, sub, color, spark }) {
  return (
    <div className="kpi" style={{ position: "relative", overflow: "hidden" }}>
      <div className="lbl">{label}</div>
      <div className="val num" style={{ color }}>{value}</div>
      {sub && <div className="sub mono">{sub}</div>}
      {spark && (
        <svg style={{ position: "absolute", bottom: 0, right: 0, opacity: 0.14 }}
             width={60} height={32} viewBox="0 0 60 32">
          <polyline fill="none" stroke={color || "var(--text)"} strokeWidth={1.5} points={spark} />
        </svg>
      )}
    </div>
  );
}

// ─── Mini KPI (small, row 2) ──────────────────────────────────────────────────
function MiniKpi({ label, value, color }) {
  return (
    <div style={{
      background: "var(--surface-2, #131920)", border: "0.5px solid var(--border)",
      borderRadius: 6, padding: "7px 10px",
    }}>
      <div style={{ fontSize: 9, letterSpacing: ".08em", color: "var(--dim)", textTransform: "uppercase", marginBottom: 2 }}>
        {label}
      </div>
      <div className="num" style={{ fontSize: 14, fontWeight: 500, color: color || "var(--text)" }}>
        {value}
      </div>
    </div>
  );
}

// ─── Group breakdown table ────────────────────────────────────────────────────
function GroupTable({ title, rows, keyLabel }) {
  return (
    <div className="panel">
      <div className="panel-hd">
        <div style={{ fontSize: 12, letterSpacing: ".1em", color: "var(--dim)", textTransform: "uppercase" }}>{title}</div>
        <Pill tone="dim">{rows?.length || 0}</Pill>
      </div>
      <div className="panel-bd" style={{ padding: 0 }}>
        <div className="scroll">
          <table className="t">
            <thead>
              <tr>
                <th>{keyLabel}</th>
                <th className="r">N</th>
                <th className="r">WR</th>
                <th className="r">Total</th>
                <th className="r">Avg</th>
                <th className="r">MFE</th>
                <th className="r">MAE</th>
              </tr>
            </thead>
            <tbody>
              {(rows || []).map((r) => (
                <tr key={r.key}>
                  <td className="mono">{r.key}</td>
                  <td className="r num">{r.n}</td>
                  <td className="r num" style={{ color: r.win_rate >= 0.5 ? "var(--green)" : "var(--red)" }}>
                    {fmtPct(r.win_rate)}
                  </td>
                  <td className="r num" style={{ color: r.total_r >= 0 ? "var(--green)" : "var(--red)" }}>
                    {fmtR(r.total_r)}
                  </td>
                  <td className="r num">{fmtR(r.avg_r)}</td>
                  <td className="r num">{fmt(r.avg_mfe)}</td>
                  <td className="r num">{fmt(r.avg_mae)}</td>
                </tr>
              ))}
              {(!rows || rows.length === 0) && (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", color: "var(--dim)", padding: 28 }}>
                    No data yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── Open positions panel ─────────────────────────────────────────────────────
function OpenPositions({ items }) {
  const open = useMemo(() => items.filter(s => s.status === "OPEN"), [items]);

  return (
    <div className="panel">
      <div className="panel-hd">
        <div style={{ fontSize: 12, letterSpacing: ".1em", color: "var(--dim)", textTransform: "uppercase" }}>
          Open positions
        </div>
        <Pill tone={open.length > 0 ? "amber" : "dim"}>{open.length} live</Pill>
      </div>
      <div className="panel-bd" style={{ padding: 0 }}>
        {open.length === 0 ? (
          <div style={{ textAlign: "center", color: "var(--dim)", padding: "28px 0", fontSize: 12 }}>
            No open trades
          </div>
        ) : (
          open.map(s => {
            const mfePct = s.rr1 > 0 && s.max_favorable_r != null
              ? Math.min(100, Math.max(0, (s.max_favorable_r / s.rr1) * 100))
              : 0;
            const positive = (s.max_favorable_r ?? 0) >= 0;
            return (
              <div key={s.id} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "8px 12px", borderBottom: "0.5px solid var(--border)",
              }}>
                <span className="mono" style={{ fontWeight: 700, minWidth: 80, fontSize: 12 }}>
                  {s.symbol}
                </span>
                <Pill tone={sideTone(s.side)}>
                  {s.side === "LONG"
                    ? <><TrendingUp size={9} style={{ verticalAlign: "middle" }} /> LONG</>
                    : <><TrendingDown size={9} style={{ verticalAlign: "middle" }} /> SHORT</>}
                </Pill>
                <Pill tone={s.tier === "S" ? "amber" : s.tier === "A" ? "aqua" : "dim"}>{s.tier}</Pill>

                {/* MFE progress bar toward TP1 */}
                <div style={{ flex: 1 }}>
                  <div style={{ height: 5, borderRadius: 3, background: "var(--surface-2, #131920)", overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 3, width: `${mfePct}%`,
                      background: positive ? "var(--green)" : "var(--red)",
                      transition: "width .3s",
                    }} />
                  </div>
                  <div style={{ fontSize: 9, color: "var(--dim)", marginTop: 2 }}>
                    MFE {fmt(s.max_favorable_r, 2)}R → TP1 {fmt(s.rr1, 2)}R ({Math.round(mfePct)}%)
                  </div>
                </div>

                <span className="num" style={{
                  fontSize: 12, minWidth: 48, textAlign: "right",
                  color: positive ? "var(--green)" : "var(--red)",
                }}>
                  {fmtR(s.max_favorable_r)}
                </span>
                <Clock size={10} color="var(--amber)" />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ─── Session × day heatmap ────────────────────────────────────────────────────
// Expects metrics.by_session_day: [{ session, day, win_rate, n }]
// Add GET /api/metrics?days=N returning by_session_day to your backend.
function SessionHeatmap({ data }) {
  const SESSIONS  = ["Asia", "London", "Overlap", "NY"];
  const WEEKDAYS  = ["Mon", "Tue", "Wed", "Thu", "Fri"];

  const lookup = useMemo(() => {
    const m = {};
    (data || []).forEach(d => { m[`${d.session}|${d.day}`] = d; });
    return m;
  }, [data]);

  const cellBg = (wr) => {
    if (wr == null) return "var(--surface-2, #131920)";
    if (wr >= 0.70) return "rgba(38,208,124,.75)";
    if (wr >= 0.55) return "rgba(38,208,124,.40)";
    if (wr >= 0.45) return "rgba(245,184,0,.35)";
    return "rgba(255,93,108,.40)";
  };

  return (
    <div className="panel">
      <div className="panel-hd">
        <div style={{ fontSize: 12, letterSpacing: ".1em", color: "var(--dim)", textTransform: "uppercase" }}>
          Win rate · session × day
        </div>
        {!data && (
          <span style={{ fontSize: 10, color: "var(--dim)" }}>needs by_session_day in /metrics</span>
        )}
      </div>
      <div className="panel-bd">
        <div style={{ display: "grid", gridTemplateColumns: "54px repeat(5, 1fr)", gap: 3 }}>
          {/* header row */}
          <div />
          {WEEKDAYS.map(d => (
            <div key={d} style={{ fontSize: 10, color: "var(--dim)", textAlign: "center", paddingBottom: 4 }}>{d}</div>
          ))}
          {/* data rows */}
          {SESSIONS.map(session => (
            <>
              <div key={`lbl-${session}`}
                   style={{ fontSize: 10, color: "var(--dim)", display: "flex", alignItems: "center" }}>
                {session}
              </div>
              {WEEKDAYS.map(day => {
                const cell = lookup[`${session}|${day}`];
                const wr   = cell?.win_rate ?? null;
                return (
                  <div
                    key={`${session}-${day}`}
                    title={cell ? `${session} ${day}: ${(wr * 100).toFixed(0)}% (n=${cell.n})` : "No data"}
                    style={{
                      height: 22, borderRadius: 3, background: cellBg(wr),
                      display: "flex", alignItems: "center", justifyContent: "center",
                    }}
                  >
                    {wr != null && (
                      <span style={{ fontSize: 9, color: "rgba(255,255,255,.75)" }}>
                        {(wr * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                );
              })}
            </>
          ))}
        </div>

        {/* Legend */}
        <div style={{ display: "flex", gap: 10, marginTop: 10, fontSize: 9, color: "var(--dim)", alignItems: "center", flexWrap: "wrap" }}>
          {[
            ["rgba(38,208,124,.75)", "≥70%"],
            ["rgba(38,208,124,.40)", "≥55%"],
            ["rgba(245,184,0,.35)",  "≥45%"],
            ["rgba(255,93,108,.40)", "<45%"],
            ["var(--surface-2,#131920)", "no data"],
          ].map(([bg, lbl]) => (
            <span key={lbl} style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: bg, display: "inline-block" }} />
              {lbl}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Streak tracker ───────────────────────────────────────────────────────────
// New metrics fields needed in /api/metrics response:
//   current_streak, longest_win_streak, longest_loss_streak,
//   recovery_factor, profit_factor, avg_hold_minutes
function StreakTracker({ metrics, items }) {
  const dots = useMemo(() =>
    items
      .filter(s => s.result_r != null)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
      .slice(-20),
    [items]
  );

  const streak = metrics?.current_streak ?? 0;

  return (
    <div className="panel">
      <div className="panel-hd">
        <div style={{ fontSize: 12, letterSpacing: ".1em", color: "var(--dim)", textTransform: "uppercase" }}>
          Trade streak
        </div>
        <span className="mono" style={{ fontSize: 11, color: streak >= 0 ? "var(--green)" : "var(--red)" }}>
          {streak >= 0 ? `+${streak}W` : `${streak}L`}
        </span>
      </div>
      <div className="panel-bd">
        <div style={{ fontSize: 10, color: "var(--dim)", marginBottom: 6 }}>
          Last {dots.length} resolved — green = win, red = loss
        </div>

        {/* Dot row */}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 12 }}>
          {dots.map((s, i) => (
            <div
              key={s.id}
              title={`${s.symbol} ${fmtR(s.result_r)}`}
              style={{
                width: 12, height: 12, borderRadius: "50%",
                background: s.result_r >= 0 ? "var(--green)" : "var(--red)",
                opacity: 0.55 + (i / Math.max(dots.length - 1, 1)) * 0.45,
              }}
            />
          ))}
          {dots.length === 0 && (
            <span style={{ fontSize: 11, color: "var(--dim)" }}>No resolved trades yet</span>
          )}
        </div>

        {/* Stats grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <MiniKpi label="Longest W streak"
                   value={metrics?.longest_win_streak  ?? "—"}
                   color="var(--green)" />
          <MiniKpi label="Longest L streak"
                   value={metrics?.longest_loss_streak ?? "—"}
                   color="var(--red)" />
          <MiniKpi label="Recovery factor"
                   value={metrics?.recovery_factor != null ? `${fmt(metrics.recovery_factor)}×` : "—"} />
          <MiniKpi label="Profit factor"
                   value={metrics?.profit_factor != null ? `${fmt(metrics.profit_factor)}×` : "—"}
                   color="var(--green)" />
        </div>
      </div>
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [metrics,     setMetrics]     = useState(null);
  const [signals,     setSignals]     = useState({ items: [], total: 0 });
  const [alerts,      setAlerts]      = useState([]);
  const [days,        setDays]        = useState(30);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [busy,        setBusy]        = useState(false);

  // Filters
  const [status,      setStatus]      = useState("");
  const [side,        setSide]        = useState("");
  const [tier,        setTier]        = useState("");
  const [setupType,   setSetupType]   = useState("");
  const [entryModel,  setEntryModel]  = useState("");
  const [htfBias,     setHtfBias]     = useState("");
  const [regime,      setRegime]      = useState("");
  const [symbol,      setSymbol]      = useState("");
  const [symSearch,   setSymSearch]   = useState("");

  // Derive top pairs from loaded signals for quick-pick pills
  const topPairs = useMemo(() => {
    const counts = {};
    signals.items.forEach(s => { counts[s.symbol] = (counts[s.symbol] || 0) + 1; });
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([sym]) => sym);
  }, [signals.items]);

  const filteredPairs = symSearch
    ? topPairs.filter(p => p.toLowerCase().includes(symSearch.toLowerCase()))
    : topPairs;

  // ── load ──────────────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    try {
      const [m, s] = await Promise.all([
        axios.get(`${API}/metrics`, { params: { days } }),
        axios.get(`${API}/signals`, {
          params: {
            limit: 100,
            status,
            side,
            tier,
            setup_type:  setupType,
            entry_model: entryModel,
            htf_bias:    htfBias,
            regime,
            symbol,
          },
        }),
      ]);
      setMetrics(m.data);
      setSignals(s.data);
      setAlerts(buildAlerts(m.data, s.data));
    } catch (e) {
      console.error(e);
    }
  }, [days, status, side, tier, setupType, entryModel, htfBias, regime, symbol]);

  useEffect(() => { load(); }, [load]);

  const runResolve = async () => {
    setBusy(true);
    try { await axios.post(`${API}/resolve`); await load(); }
    finally { setBusy(false); }
  };
  const runDigest = async () => {
    setBusy(true);
    try { await axios.post(`${API}/digest`); }
    finally { setBusy(false); }
  };

  // ── derived data ──────────────────────────────────────────────────────────
  const equityData = useMemo(
    () => (metrics?.equity || []).map((p, i) => ({ i, r: p.r })),
    [metrics]
  );
  const mfeData = metrics?.mfe_hist || [];
  const maeData = metrics?.mae_hist || [];

  const clearAllFilters = () => {
    setSymbol(""); setSymSearch(""); setStatus(""); setSide(""); setTier("");
    setSetupType(""); setEntryModel(""); setHtfBias(""); setRegime("");
  };

  const hasActiveFilters = symbol || status || side || tier || setupType || entryModel || htfBias || regime;

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "var(--bg)" }}>

      {/* ════════════════════════ SIDEBAR ════════════════════════ */}
      <div style={{
        width: sidebarOpen ? 192 : 40,
        flexShrink: 0,
        background: "var(--surface)",
        borderRight: "0.5px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        transition: "width .18s ease",
        overflow: "hidden",
      }}>
        {/* Toggle header */}
        <div style={{
          padding: "11px 10px", borderBottom: "0.5px solid var(--border)",
          display: "flex", alignItems: "center",
          justifyContent: sidebarOpen ? "space-between" : "center",
          flexShrink: 0,
        }}>
          {sidebarOpen && (
            <span style={{ fontSize: 10, letterSpacing: ".12em", color: "var(--dim)", textTransform: "uppercase" }}>
              Filters
            </span>
          )}
          <button
            onClick={() => setSidebarOpen(o => !o)}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--dim)", display: "flex" }}
            title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          >
            {sidebarOpen ? <PanelLeftClose size={14} /> : <PanelLeftOpen size={14} />}
          </button>
        </div>

        {/* Filter sections */}
        {sidebarOpen && (
          <div style={{ flex: 1, overflowY: "auto", padding: "12px 10px" }}>

            {/* ── Symbol ── */}
            <SidebarSection title="Symbol" defaultOpen>
              <div style={{ position: "relative", marginBottom: 6 }}>
                <Search size={10} style={{
                  position: "absolute", left: 7, top: "50%",
                  transform: "translateY(-50%)", color: "var(--dim)",
                }} />
                <input
                  value={symSearch}
                  onChange={e => {
                    setSymSearch(e.target.value);
                    setSymbol(e.target.value.toUpperCase());
                  }}
                  placeholder="Search e.g. BTCUSDT"
                  style={{
                    width: "100%", paddingLeft: 22, paddingRight: 6,
                    paddingTop: 4, paddingBottom: 4,
                    fontSize: 11, fontFamily: "inherit",
                    background: "var(--surface-2, #131920)",
                    border: "0.5px solid var(--border)",
                    borderRadius: 5, color: "var(--text)",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              {/* Quick-pair pills (derived from loaded signals) */}
              {filteredPairs.map(p => (
                <FPill
                  key={p}
                  label={p}
                  active={symbol === p}
                  onClick={() => {
                    if (symbol === p) { setSymbol(""); setSymSearch(""); }
                    else              { setSymbol(p); setSymSearch(""); }
                  }}
                />
              ))}
              {topPairs.length === 0 && (
                <div style={{ fontSize: 10, color: "var(--dim)", paddingTop: 2 }}>
                  Top pairs appear here after signals load
                </div>
              )}
              {symbol && (
                <button
                  onClick={() => { setSymbol(""); setSymSearch(""); }}
                  style={{
                    fontSize: 10, color: "var(--amber)", background: "none",
                    border: "none", cursor: "pointer", padding: "3px 0",
                    fontFamily: "inherit",
                  }}
                >
                  ✕ clear symbol
                </button>
              )}
            </SidebarSection>

            {/* ── Status ── */}
            <SidebarSection title="Status">
              {["OPEN","TP1","TP2","TP3","STOPPED","BE_STOP","EXPIRED"].map(s => (
                <FPill key={s} label={s} active={status === s}
                       onClick={() => setStatus(status === s ? "" : s)} />
              ))}
            </SidebarSection>

            {/* ── Side ── */}
            <SidebarSection title="Side">
              {["LONG","SHORT"].map(s => (
                <FPill key={s} label={s} active={side === s}
                       onClick={() => setSide(side === s ? "" : s)} />
              ))}
            </SidebarSection>

            {/* ── Tier ── */}
            <SidebarSection title="Tier">
              {["S","A","B","C"].map(t => (
                <FPill key={t} label={`Tier ${t}`} active={tier === t}
                       onClick={() => setTier(tier === t ? "" : t)} />
              ))}
            </SidebarSection>

            {/* ── Setup ── */}
            <SidebarSection title="Setup">
              {["sweep_reclaim","fvg_continuation","ob_reversal","deviation_breakout"].map(s => (
                <FPill key={s} label={s} active={setupType === s}
                       onClick={() => setSetupType(setupType === s ? "" : s)} />
              ))}
            </SidebarSection>

            {/* ── Entry Model ── */}
            <SidebarSection title="Entry model" defaultOpen={false}>
              {["aggressive","confirmation","reclaim"].map(m => (
                <FPill key={m} label={m} active={entryModel === m}
                       onClick={() => setEntryModel(entryModel === m ? "" : m)} />
              ))}
            </SidebarSection>

            {/* ── HTF Bias ── */}
            <SidebarSection title="HTF bias" defaultOpen={false}>
              {["bull","bear","neutral"].map(b => (
                <FPill key={b} label={b} active={htfBias === b}
                       onClick={() => setHtfBias(htfBias === b ? "" : b)} />
              ))}
            </SidebarSection>

            {/* ── Regime ── */}
            <SidebarSection title="Regime" defaultOpen={false}>
              {["trending","ranging","volatile","compressed"].map(r => (
                <FPill key={r} label={r} active={regime === r}
                       onClick={() => setRegime(regime === r ? "" : r)} />
              ))}
            </SidebarSection>

            {/* Clear all */}
            {hasActiveFilters && (
              <button
                onClick={clearAllFilters}
                style={{
                  width: "100%", marginTop: 2, padding: "5px 8px", fontSize: 11,
                  background: "rgba(255,93,108,.08)",
                  border: "0.5px solid rgba(255,93,108,.3)",
                  borderRadius: 5, color: "var(--red)",
                  cursor: "pointer", fontFamily: "inherit",
                }}
              >
                ✕ clear all filters
              </button>
            )}
          </div>
        )}
      </div>

      {/* ════════════════════════ MAIN ════════════════════════ */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

        {/* ── Top bar ── */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "9px 20px",
          background: "var(--surface)", borderBottom: "0.5px solid var(--border)",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <div style={{ fontSize: 18, fontWeight: 700, letterSpacing: "-0.02em" }}>
              MySetup<span style={{ color: "var(--amber)" }}> v15</span>
            </div>
            <span className="mono" style={{ color: "var(--dim)", fontSize: 11 }}>
              · signal performance tracker
            </span>
            {symbol && <Pill tone="amber">{symbol}</Pill>}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            {/* Day window */}
            {[[1,"24h"],[7,"7d"],[30,"30d"],[90,"90d"],[365,"1y"]].map(([d, lbl]) => (
              <button
                key={d}
                className={`btn${days === d ? " btn-primary" : ""}`}
                style={{ fontSize: 11, padding: "3px 7px" }}
                onClick={() => setDays(Number(d))}
              >
                {lbl}
              </button>
            ))}
            <div style={{ width: 1, height: 14, background: "var(--border)", margin: "0 3px" }} />
            <button className="btn" onClick={load} style={{ fontSize: 11 }}>
              <RefreshCw size={11} style={{ verticalAlign: "middle", marginRight: 4 }} />refresh
            </button>
            <button className="btn" onClick={runResolve} disabled={busy} style={{ fontSize: 11 }}>
              <Activity size={11} style={{ verticalAlign: "middle", marginRight: 4 }} />resolve
            </button>
            <button className="btn btn-primary" onClick={runDigest} disabled={busy} style={{ fontSize: 11 }}>
              <Send size={11} style={{ verticalAlign: "middle", marginRight: 4 }} />digest
            </button>
          </div>
        </div>

        {/* ── Scrollable body ── */}
        <div className="grid-bg" style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>

          {/* ── Alerts ── */}
          {alerts.length > 0 && (
            <div style={{ marginBottom: 14, display: "flex", flexDirection: "column", gap: 4 }}>
              {alerts.map((a, i) => (
                <div key={i} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "6px 10px", borderRadius: 6, fontSize: 11,
                  background: a.type === "warn"
                    ? "rgba(255,93,108,.07)"
                    : "rgba(245,184,0,.07)",
                  border: `0.5px solid ${a.type === "warn"
                    ? "rgba(255,93,108,.28)"
                    : "rgba(245,184,0,.28)"}`,
                  color: a.type === "warn" ? "var(--red)" : "var(--amber)",
                }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {a.type === "warn"
                      ? <AlertTriangle size={11} />
                      : <Info size={11} />}
                    {a.msg}
                  </span>
                  <button
                    onClick={() => setAlerts(prev => prev.filter((_, idx) => idx !== i))}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", display: "flex" }}
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* ── KPI row 1 (4 large cards) ── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 10 }}>
            <KpiCard
              label="Win Rate"
              value={fmtPct(metrics?.win_rate)}
              sub={`${metrics?.resolved ?? 0} resolved`}
              color={metrics?.win_rate >= 0.5 ? "var(--green)" : "var(--red)"}
              spark="0,28 10,22 20,24 30,14 40,10 50,16 60,8"
            />
            <KpiCard
              label="Total R"
              value={fmtR(metrics?.total_r)}
              sub={`expectancy ${fmtR(metrics?.expectancy)}`}
              color={(metrics?.total_r ?? 0) >= 0 ? "var(--green)" : "var(--red)"}
              spark="0,30 10,26 20,20 30,16 40,18 50,12 60,8"
            />
            {/* profit_factor: new field — add to /api/metrics backend */}
            <KpiCard
              label="Profit Factor"
              value={metrics?.profit_factor != null ? `${fmt(metrics.profit_factor)}×` : "—"}
              sub="gross win ÷ gross loss"
              color={(metrics?.profit_factor ?? 0) >= 1.5 ? "var(--green)" : (metrics?.profit_factor ?? 0) >= 1 ? "var(--amber)" : "var(--red)"}
            />
            {/* max_drawdown: new field — add to /api/metrics backend */}
            <KpiCard
              label="Max Drawdown"
              value={fmtR(metrics?.max_drawdown)}
              sub={metrics?.recovery_factor != null ? `recovery ${fmt(metrics.recovery_factor)}×` : "—"}
              color="var(--red)"
            />
          </div>

          {/* ── KPI row 2 (8 mini cards) ── */}
          {/* avg_hold_minutes, current_streak, longest_win/loss_streak: new fields in /api/metrics */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(8, 1fr)", gap: 8, marginBottom: 14 }}>
            <MiniKpi label="Avg Win"   value={fmtR(metrics?.avg_win)}  color="var(--green)" />
            <MiniKpi label="Avg Loss"  value={fmtR(metrics?.avg_loss)} color="var(--red)" />
            <MiniKpi
              label="Streak"
              value={metrics?.current_streak != null
                ? (metrics.current_streak >= 0 ? `+${metrics.current_streak}W` : `${metrics.current_streak}L`)
                : "—"}
              color={(metrics?.current_streak ?? 0) >= 0 ? "var(--green)" : "var(--red)"}
            />
            <MiniKpi label="Avg Hold"      value={fmtDur(metrics?.avg_hold_minutes)} />
            <MiniKpi label="Open"          value={metrics?.open  ?? "—"} color="var(--amber)" />
            <MiniKpi label={`Fired (${days}d)`} value={metrics?.fired ?? "—"} />
            <MiniKpi label="Best Setup"    value={metrics?.by_setup_type?.[0]?.key   ?? "—"} />
            <MiniKpi label="Best Session"  value={metrics?.by_session?.[0]?.key      ?? "—"} />
          </div>

          {/* ── Equity curve + Open positions ── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div className="panel">
              <div className="panel-hd">
                <div style={{ fontSize: 12, letterSpacing: ".1em", color: "var(--dim)", textTransform: "uppercase" }}>
                  Equity curve (cumulative R)
                </div>
                <Pill tone={(metrics?.total_r ?? 0) >= 0 ? "green" : "red"}>
                  {fmtR(metrics?.total_r)}
                </Pill>
              </div>
              <div className="panel-bd" style={{ height: 190 }}>
                <ResponsiveContainer>
                  <AreaChart data={equityData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <defs>
                      <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor="#f5b800" stopOpacity={0.18} />
                        <stop offset="95%" stopColor="#f5b800" stopOpacity={0}    />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#1f2630" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="i" hide />
                    <YAxis stroke="#5a6573" tick={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
                    <Tooltip
                      contentStyle={{ background: "#0d1117", border: "1px solid #2a3340", fontSize: 11 }}
                      labelStyle={{ color: "#8b95a5" }}
                    />
                    <ReferenceLine y={0} stroke="#2a3340" />
                    <Area
                      type="monotone" dataKey="r"
                      stroke="#f5b800" strokeWidth={2}
                      fill="url(#eqGrad)" dot={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <OpenPositions items={signals.items} />
          </div>

          {/* ── Session heatmap + Streak tracker ── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <SessionHeatmap data={metrics?.by_session_day} />
            <StreakTracker  metrics={metrics} items={signals.items} />
          </div>

          {/* ── MFE / MAE histograms ── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div className="panel">
              <div className="panel-hd">
                <div style={{ fontSize: 12, letterSpacing: ".1em", color: "var(--dim)", textTransform: "uppercase" }}>
                  MFE distribution
                </div>
                <Pill tone="green">favorable</Pill>
              </div>
              <div className="panel-bd" style={{ height: 190 }}>
                <ResponsiveContainer>
                  <BarChart data={mfeData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                    <CartesianGrid stroke="#1f2630" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="bucket" stroke="#5a6573" tick={{ fontSize: 9, fontFamily: "JetBrains Mono" }} />
                    <YAxis                  stroke="#5a6573" tick={{ fontSize: 9, fontFamily: "JetBrains Mono" }} />
                    <Tooltip contentStyle={{ background: "#0d1117", border: "1px solid #2a3340", fontSize: 11 }} />
                    <Bar dataKey="count" fill="#26d07c" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="panel">
              <div className="panel-hd">
                <div style={{ fontSize: 12, letterSpacing: ".1em", color: "var(--dim)", textTransform: "uppercase" }}>
                  MAE distribution
                </div>
                <Pill tone="red">adverse</Pill>
              </div>
              <div className="panel-bd" style={{ height: 190 }}>
                <ResponsiveContainer>
                  <BarChart data={maeData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                    <CartesianGrid stroke="#1f2630" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="bucket" stroke="#5a6573" tick={{ fontSize: 9, fontFamily: "JetBrains Mono" }} />
                    <YAxis                  stroke="#5a6573" tick={{ fontSize: 9, fontFamily: "JetBrains Mono" }} />
                    <Tooltip contentStyle={{ background: "#0d1117", border: "1px solid #2a3340", fontSize: 11 }} />
                    <Bar dataKey="count" fill="#ff5d6c" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* ── Breakdown tables ── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <GroupTable title="By Tier"            rows={metrics?.by_tier}           keyLabel="tier"    />
            <GroupTable title="By Entry Path"      rows={metrics?.by_path}           keyLabel="path"    />
            <GroupTable title="By Session"         rows={metrics?.by_session}        keyLabel="session" />
            <GroupTable title="By Regime"          rows={metrics?.by_regime}         keyLabel="regime"  />
            <GroupTable title="By Side"            rows={metrics?.by_side}           keyLabel="side"    />
            <GroupTable title="By Symbol (top 25)" rows={metrics?.by_symbol}         keyLabel="symbol"  />
            <GroupTable title="By Setup Type"      rows={metrics?.by_setup_type}     keyLabel="setup"   />
            <GroupTable title="By Entry Model"     rows={metrics?.by_entry_model}    keyLabel="model"   />
            <GroupTable title="By HTF Bias"        rows={metrics?.by_htf_bias}       keyLabel="bias"    />
            <GroupTable title="By Liquidity Event" rows={metrics?.by_liquidity_event} keyLabel="event"  />
          </div>

          {/* ── Signals table ── */}
          <div className="panel">
            <div className="panel-hd">
              <div style={{ fontSize: 12, letterSpacing: ".1em", color: "var(--dim)", textTransform: "uppercase" }}>
                Recent signals
                {symbol && <span style={{ color: "var(--amber)", marginLeft: 6 }}>· {symbol}</span>}
              </div>
              <span className="mono" style={{ fontSize: 11, color: "var(--dim)" }}>
                {signals.total} total
              </span>
            </div>
            <div className="panel-bd" style={{ padding: 0 }}>
              <div className="scroll" style={{ maxHeight: 520 }}>
                <table className="t" data-testid="table-signals">
                  <thead>
                    <tr>
                      <th>Time</th><th>Symbol</th><th>Side</th><th>Tier</th>
                      <th>Setup</th><th>Model</th><th>HTF</th><th>Path</th>
                      <th className="r">Entry</th><th className="r">SL</th><th className="r">TP1</th>
                      <th className="r">RR1</th><th>Status</th>
                      <th className="r">MFE</th><th className="r">MAE</th><th className="r">Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {signals.items.map((s) => (
                      <tr key={s.id}>
                        <td className="mono" style={{ color: "var(--dim)" }}>{shortTime(s.created_at)}</td>
                        <td className="mono">{s.symbol}</td>
                        <td>
                          <Pill tone={sideTone(s.side)}>
                            {s.side === "LONG"
                              ? <><TrendingUp   size={9} style={{ verticalAlign: "middle" }} /> LONG</>
                              : <><TrendingDown size={9} style={{ verticalAlign: "middle" }} /> SHORT</>}
                          </Pill>
                        </td>
                        <td>
                          <Pill tone={s.tier === "S" ? "amber" : s.tier === "A" ? "aqua" : "dim"}>
                            {s.tier}
                          </Pill>
                        </td>
                        <td className="mono" style={{ fontSize: 10, color: "var(--dim)" }}>{s.setup_type   || "—"}</td>
                        <td className="mono" style={{ fontSize: 10, color: "var(--dim)" }}>{s.entry_model  || "—"}</td>
                        <td className="mono" style={{
                          fontSize: 10,
                          color: s.htf_bias === "bull" ? "var(--green)" : s.htf_bias === "bear" ? "var(--red)" : "var(--dim)",
                        }}>
                          {s.htf_bias || "—"}
                        </td>
                        <td className="mono" style={{ fontSize: 10, color: "var(--dim)" }}>{s.entry_path || "—"}</td>
                        <td className="r num">{fmt(s.entry, 4)}</td>
                        <td className="r num" style={{ color: "var(--red)"   }}>{fmt(s.sl,  4)}</td>
                        <td className="r num" style={{ color: "var(--green)" }}>{fmt(s.tp1, 4)}</td>
                        <td className="r num">{fmt(s.rr1, 2)}</td>
                        <td>
                          <span className={`status-${s.status}`}>
                            {s.status}
                            {s.status === "OPEN" && (
                              <Clock size={9} style={{ verticalAlign: "middle", marginLeft: 3 }} />
                            )}
                          </span>
                        </td>
                        <td className="r num" style={{ color: "var(--green)" }}>{fmt(s.max_favorable_r, 2)}</td>
                        <td className="r num" style={{ color: "var(--red)"   }}>{fmt(s.max_adverse_r,   2)}</td>
                        <td className="r num" style={{ color: (s.result_r ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                          {s.result_r != null ? fmtR(s.result_r) : "—"}
                        </td>
                      </tr>
                    ))}
                    {signals.items.length === 0 && (
                      <tr>
                        <td colSpan={16} style={{ textAlign: "center", color: "var(--dim)", padding: 36 }}>
                          No signals yet · POST to{" "}
                          <span className="mono" style={{ color: "var(--amber)" }}>{API}/signals</span>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div style={{ marginTop: 16, textAlign: "center", color: "var(--dim)", fontSize: 10 }} className="mono">
            Auto-resolver every 15 min · Digest at 00:05 UTC · API: {API}
          </div>
        </div>
      </div>
    </div>
  );
}
