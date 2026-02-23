import React, { useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useClusterStore } from '../../store/useStore';
import { api, clusterAPI, optimizationAPI, karpenterAPI, metricsAPI } from '../../services/api';
import toast from 'react-hot-toast';

// ─── PALETTE ─────────────────────────────────────────────────────────────────
const C = {
  bg: "#f5f6f8",
  surface: "#ffffff",
  surfaceHover: "#fafafa",
  border: "#e4e6ea",
  borderHover: "#c8cdd6",
  text: "#111318",
  muted: "#5a6272",
  subtle: "#98a1b0",
  accent: "#2563eb",
  accentLight: "#eff6ff",
  green: "#16a34a", greenBg: "#f0fdf4", greenBorder: "#bbf7d0",
  amber: "#b45309", amberBg: "#fffbeb", amberBorder: "#fde68a",
  red: "#dc2626", redBg: "#fef2f2", redBorder: "#fecaca",
  purple: "#6d28d9", purpleBg: "#f5f3ff", purpleBorder: "#ddd6fe",
  teal: "#0f766e", tealBg: "#f0fdfa", tealBorder: "#99f6e4",
  blue: "#2563eb", blueBg: "#eff6ff", blueBorder: "#bfdbfe",
};

const utilColor = (p) => p >= 85 ? C.red : p >= 65 ? C.amber : p >= 30 ? C.green : C.accent;

// ─── SVG ICONS ───────────────────────────────────────────────────────────────
const Svg = ({ s = 14, stroke = C.muted, children, style = {} }) => (
  <svg width={s} height={s} viewBox="0 0 24 24" fill="none"
    stroke={stroke} strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round"
    style={{ flexShrink: 0, display: "block", ...style }}>
    {children}
  </svg>
);
const Icons = {
  Eye: (p) => <Svg {...p}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></Svg>,
  Zap: (p) => <Svg {...p}><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" /></Svg>,
  Bar: (p) => <Svg {...p}><path d="M18 20V10M12 20V4M6 20v-6" /></Svg>,
  Refresh: (p) => <Svg {...p}><path d="M23 4v6h-6" /><path d="M1 20v-6h6" /><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" /></Svg>,
  Settings: (p) => <Svg {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" /></Svg>,
  Check: (p) => <Svg {...p}><path d="M20 6L9 17l-5-5" /></Svg>,
  X: (p) => <Svg {...p}><path d="M18 6L6 18M6 6l12 12" /></Svg>,
  Alert: (p) => <Svg {...p}><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><path d="M12 9v4M12 17h.01" /></Svg>,
  Arrow: (p) => <Svg {...p}><path d="M5 12h14M12 5l7 7-7 7" /></Svg>,
  Download: (p) => <Svg {...p}><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><path d="M7 10l5 5 5-5M12 15V3" /></Svg>,
  Pause: (p) => <Svg {...p}><path d="M6 4h4v16H6zM14 4h4v16h-4z" /></Svg>,
  ChevD: (p) => <Svg {...p}><path d="M6 9l6 6 6-6" /></Svg>,
  ChevR: (p) => <Svg {...p}><path d="M9 18l6-6-6-6" /></Svg>,
  History: (p) => <Svg {...p}><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></Svg>,
  Server: (p) => <Svg {...p}><rect x="2" y="2" width="20" height="8" rx="2" /><rect x="2" y="14" width="20" height="8" rx="2" /><line x1="6" y1="6" x2="6.01" y2="6" /><line x1="6" y1="18" x2="6.01" y2="18" /></Svg>,
  Layers: (p) => <Svg {...p}><polygon points="12 2 2 7 12 12 22 7 12 2" /><polyline points="2 17 12 22 22 17" /><polyline points="2 12 12 17 22 12" /></Svg>,
  TrendUp: (p) => <Svg {...p}><polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" /></Svg>,
  Box: (p) => <Svg {...p}><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" /></Svg>,
  Cpu: (p) => <Svg {...p}><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" /></Svg>,
};

// ─── PRIMITIVES ───────────────────────────────────────────────────────────────
const Dot = ({ color, pulse = false }) => (
  <span style={{
    display: "inline-block", width: 6, height: 6,
    borderRadius: "50%", background: color, flexShrink: 0,
    boxShadow: pulse ? `0 0 0 3px ${color}30` : "none",
  }} />
);

const Tag = ({ children, color, bg }) => (
  <span style={{
    display: "inline-flex", alignItems: "center",
    padding: "2px 7px", borderRadius: 5,
    fontSize: 10, fontWeight: 500, color: C.muted,
    background: bg || "#f0f1f3",
    border: `1px solid ${color ? color + "25" : C.border}`,
  }}>{children}</span>
);

const MetricBox = ({ label, value, sub, accentBorder }) => (
  <div style={{
    background: C.surface, border: `1px solid ${C.border}`,
    borderLeft: accentBorder ? `3px solid ${accentBorder}` : `1px solid ${C.border}`,
    borderRadius: 10, padding: "12px 14px",
  }}>
    <div style={{ fontSize: 11, color: C.muted, marginBottom: 4, fontWeight: 500 }}>{label}</div>
    <div style={{ fontSize: 19, fontWeight: 700, letterSpacing: "-0.4px", color: C.text }}>{value}</div>
    {sub && <div style={{ fontSize: 11, color: C.subtle, marginTop: 3 }}>{sub}</div>}
  </div>
);

const MiniBar = ({ pct, color }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1 }}>
    <div style={{ flex: 1, height: 5, background: "#f0f0f0", borderRadius: 3 }}>
      <div style={{
        width: `${Math.min(pct, 100)}%`, height: 5,
        background: color || utilColor(pct), borderRadius: 3,
        transition: "width 0.4s cubic-bezier(.4,0,.2,1)",
      }} />
    </div>
    <span style={{ fontSize: 10, color: C.muted, width: 26, textAlign: "right", flexShrink: 0 }}>{pct}%</span>
  </div>
);

const SectionHeader = ({ children }) => (
  <div style={{
    fontSize: 10, fontWeight: 700, letterSpacing: "0.1em",
    textTransform: "uppercase", color: C.subtle,
    marginBottom: 10, marginTop: 22, paddingBottom: 7,
    borderBottom: `1px solid ${C.border}`,
  }}>{children}</div>
);

const ScoreRing = ({ score, size = 60, max = 10 }) => {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (score / max) * circ;
  const color = score >= 7 ? C.green : score >= 5 ? C.amber : C.red;
  return (
    <svg width={size} height={size} style={{ display: "block", flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f0f0f0" strokeWidth={6} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={6}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray 0.6s cubic-bezier(.4,0,.2,1)" }} />
      <text x={size / 2} y={size / 2 + 5} textAnchor="middle"
        style={{ fontSize: 13, fontWeight: 800, fill: C.text, fontFamily: "inherit" }}>
        {score.toFixed(1)}
      </text>
    </svg>
  );
};

const Sparkline = ({ data, color = C.green, h = 36, w = 80 }) => {
  if (!data?.length) return null;
  const max = Math.max(...data), min = Math.min(...data);
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / ((max - min) || 1)) * (h - 4) - 2;
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg width={w} height={h} style={{ overflow: "visible", display: "block" }}>
      <polyline points={pts} fill="none" stroke={color}
        strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
};

const Chip = ({ children, active, onClick }) => (
  <button onClick={onClick} style={{
    padding: "3px 9px", borderRadius: 6, fontFamily: "inherit",
    fontSize: 10, fontWeight: active ? 600 : 400, cursor: "pointer",
    background: active ? "#0f1117" : C.surface,
    color: active ? "#fff" : C.muted,
    border: `1px solid ${active ? "#0f1117" : C.border}`,
    transition: "all 0.12s",
  }}>{children}</button>
);

const Btn = ({ children, onClick, variant = "default", size = "md", disabled = false }) => {
  const vs = {
    default: { background: C.surface, border: `1px solid ${C.border}`, color: C.muted },
    accent: { background: C.accent, border: `1px solid ${C.accent}`, color: "#fff" },
    purple: { background: C.purple, border: `1px solid ${C.purple}`, color: "#fff" },
    dark: { background: "#0f1117", border: "1px solid #0f1117", color: "#fff" },
    ghost: { background: "transparent", border: `1px solid ${C.border}`, color: C.muted },
    green: { background: C.green, border: `1px solid ${C.green}`, color: "#fff" },
    danger: { background: C.red, border: `1px solid ${C.red}`, color: "#fff" },
  };
  const ss = {
    sm: { padding: "5px 11px", fontSize: 11 },
    md: { padding: "7px 14px", fontSize: 12 },
  };
  return (
    <button onClick={onClick} disabled={disabled} style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      borderRadius: 9, fontFamily: "inherit", fontWeight: 600,
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.4 : 1,
      transition: "opacity 0.12s",
      ...vs[variant], ...ss[size],
    }}>{children}</button>
  );
};

// Toggle switch
const Toggle = ({ on, onChange, color = C.purple }) => (
  <button onClick={() => onChange(!on)} style={{
    width: 36, height: 20, borderRadius: 10, border: "none", cursor: "pointer",
    background: on ? color : "#d1d5db",
    position: "relative", transition: "background 0.2s", flexShrink: 0,
    padding: 0,
  }}>
    <div style={{
      position: "absolute", top: 2, left: on ? 18 : 2,
      width: 16, height: 16, borderRadius: "50%",
      background: "#fff", transition: "left 0.2s",
      boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
    }} />
  </button>
);

const TH = {
  padding: "8px 12px", textAlign: "left", fontSize: 10, fontWeight: 700,
  color: C.subtle, letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap"
};
const TD = { padding: "10px 12px", verticalAlign: "middle" };

// Mock data removed in favor of real API calls, but kept POD_COLORS


const POD_COLORS = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#06b6d4", "#84cc16"];

// ═══════════════════════════════════════════════════════════════════════════════
// ROOT
// ═══════════════════════════════════════════════════════════════════════════════
export default function RightSizingDashboard() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryParams = new URLSearchParams(location.search);
  const tabFromUrl = queryParams.get("tab") || "karpenter";

  const [nav, setNav] = useState(tabFromUrl);

  useEffect(() => {
    if (tabFromUrl !== nav) setNav(tabFromUrl);
  }, [tabFromUrl]);

  const [clusters, setClusters] = useState([]);
  const [clustersLoading, setClustersLoading] = useState(true);

  useEffect(() => {
    clusterAPI.listClusters()
      .then(res => {
        const data = res.data?.items || res.data?.clusters || res.data || [];
        setClusters(Array.isArray(data) ? data : []);
      })
      .catch(err => { console.error('Failed to load clusters', err); })
      .finally(() => setClustersLoading(false));
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: C.bg, fontFamily: "'DM Sans', system-ui, sans-serif", color: C.text }}>
      {/* ── Global Nav ── */}
      <div style={{
        background: C.surface, borderBottom: `1px solid ${C.border}`,
        padding: "0 24px",
        display: "flex", alignItems: "stretch",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        {/* Brand */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 0", marginRight: 32, borderRight: `1px solid ${C.border}`, paddingRight: 24 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: "#0f1117", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icons.Layers s={14} stroke="#fff" />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text, letterSpacing: "-0.3px" }}>NodeOps</div>
            <div style={{ fontSize: 9, color: C.subtle, marginTop: -1 }}>Right-Sizing Platform</div>
          </div>
        </div>

        {/* Spacer */}
        <div style={{ display: "flex", flex: 1 }} />

        {/* Right actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 16, borderLeft: `1px solid ${C.border}` }}>
          <Btn size="sm"><Icons.Refresh s={12} stroke={C.muted} /> Refresh</Btn>
          <div style={{ display: "flex", alignItems: "center", gap: 5, padding: "4px 10px", borderRadius: 20, background: C.greenBg, border: `1px solid ${C.greenBorder}` }}>
            <Dot color={C.green} pulse />
            <span style={{ fontSize: 10, fontWeight: 500, color: C.muted }}>3 clusters connected</span>
          </div>
        </div>
      </div>

      {/* ── Content ── */}
      <div style={{ padding: "22px 24px", maxWidth: 1340, margin: "0 auto" }}>
        {nav === "karpenter" && <KarpenterSection clusters={clusters} />}
        {nav === "config" && <ConfigSection clusters={clusters} />}
        {nav === "history" && <HistorySection />}
        {nav === "savings" && <SavingsTracker />}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// KARPENTER SECTION
// ═══════════════════════════════════════════════════════════════════════════════
function KarpenterSection({ clusters = [] }) {
  const [selectedCluster, setSelectedCluster] = useState("all");
  const [globalAuto, setGlobalAuto] = useState(false);
  const [nodeAutoMap, setNodeAutoMap] = useState({});
  const [expanded, setExpanded] = useState(null);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const [nodes, setNodes] = useState([]);
  const [loadingNodes, setLoadingNodes] = useState(true);

  useEffect(() => {
    setLoadingNodes(true);
    karpenterAPI.getRecommendations(selectedCluster === "all" ? null : selectedCluster)
      .then(res => {
        const recs = res.data?.recommendations || [];
        const mapped = recs.map((r, i) => {
          const d = r.details || {};
          return {
            id: r.id || `node-${i}`,
            name: r.current_instances?.[0] || 'Unknown Node',
            cluster: r.cluster_name || r.cluster_id || 'unknown',
            cur: d.current_type || r.current_instances?.[0] || 'unknown',
            rec: d.projected_type || r.recommended_instances?.[0] || 'unknown',
            curCpu: 4, // Stub for now, real instance types dictates this
            recCpu: 2,
            curMem: 16,
            recMem: 8,
            cpuAvg: d.current_utilization_avg || d.cpu_utilization || 0,
            cpuPeak: d.current_utilization_avg ? d.current_utilization_avg + 20 : 0,
            memAvg: d.memory_utilization || 0,
            memPeak: d.memory_utilization ? d.memory_utilization + 15 : 0,
            savings: r.potential_savings_monthly || 0,
            conf: r.confidence === "high" ? "High" : r.confidence === "medium" ? "Medium" : "Low",
            pool: r.risk_level === "low" ? "Healthy" : r.risk_level === "medium" ? "Unknown" : "Risky",
            autoMode: false,
            pods: Array.from({ length: d.affected_pods || 3 }).map((_, pi) => ({
              name: `workload-${pi}`, cpu: 0.5, mem: 1.2
            }))
          };
        });
        setNodes(mapped);
      })
      .catch(err => console.error("Docs fetch error:", err))
      .finally(() => setLoadingNodes(false));
  }, [selectedCluster]);

  const setNodeAuto = (id, val) => setNodeAutoMap(p => ({ ...p, [id]: val }));
  const isAuto = (id) => nodeAutoMap[id] ?? globalAuto;

  const filteredNodes = nodes.filter(n => {
    if (selectedCluster !== "all" && n.cluster !== selectedCluster) return false;
    if (filter === "high" && n.conf !== "High") return false;
    if (filter === "risky" && n.pool !== "Risky" && n.pool !== "Unknown") return false;
    if (search && !n.name.includes(search) && !n.id.includes(search)) return false;
    return true;
  });

  const totalSavings = filteredNodes.reduce((s, n) => s + n.savings, 0);
  const confColor = { High: C.green, Medium: C.amber, Low: C.red };
  const poolColor = { Healthy: C.green, Risky: C.red, Unknown: C.subtle };

  return (
    <div>
      {/* Page header */}
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 3px", color: C.text, letterSpacing: "-0.3px" }}>
          Karpenter Optimization
        </h2>
        <p style={{ fontSize: 12, color: C.subtle, margin: 0 }}>
          Review unoptimized nodes across clusters · Insights mode by default · Enable Auto per node or globally
        </p>
      </div>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 16 }}>
        <MetricBox label="Total Potential Savings" value={`$${totalSavings.toLocaleString()}`} sub="Filtered view" accentBorder={C.green} />
        <MetricBox label="Nodes to Optimize" value={`${filteredNodes.length}`} sub="Across selected clusters" accentBorder={C.amber} />
        <MetricBox label="Fleet Score" value="7.1 / 10" sub="Weighted average" accentBorder={C.accent} />
        <MetricBox label="Auto-Managed Nodes" value={`${Object.values(nodeAutoMap).filter(Boolean).length}${globalAuto ? " + all" : ""}`} sub="Running automatically" accentBorder={C.purple} />
      </div>

      {/* Global auto banner + cluster selector */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, marginBottom: 16 }}>
        {/* Cluster selector */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: 11, color: C.subtle, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em" }}>Cluster:</span>
          {[{ id: "all", name: "All Clusters" }, ...clusters].map(c => {
            const active = selectedCluster === c.id;
            return (
              <button key={c.id} onClick={() => setSelectedCluster(c.id)} style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "5px 12px", borderRadius: 8, fontSize: 11,
                fontWeight: active ? 600 : 400, cursor: "pointer",
                background: active ? "#0f1117" : C.surface,
                color: active ? "#fff" : C.muted,
                border: `1px solid ${active ? "#0f1117" : C.border}`,
                fontFamily: "inherit", transition: "all 0.12s",
              }}>
                {c.id !== "all" && <Dot color={c.status === "healthy" ? C.green : C.amber} />}
                {c.name || c.id}
                {c.id !== "all" && <span style={{ opacity: 0.5, fontSize: 10 }}>{c.region || "us-east-1"}</span>}
              </button>
            );
          })}
        </div>
        {/* Global auto toggle */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "10px 16px", background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 10,
        }}>
          <div style={{ width: 3, height: 28, borderRadius: 2, background: globalAuto ? C.purple : C.border }} />
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, color: C.text }}>Global Auto Mode</div>
            <div style={{ fontSize: 10, color: C.subtle }}>
              {globalAuto ? "All nodes automated" : "Insights only — no changes applied"}
            </div>
          </div>
          <Toggle on={globalAuto} onChange={setGlobalAuto} color={C.purple} />
        </div>
      </div>

      {/* Node table */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10 }}>
        {/* Toolbar */}
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "12px 16px", borderBottom: `1px solid ${C.border}`,
        }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>Unoptimized Nodes</span>
          <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 20, background: C.amberBg, border: `1px solid ${C.amberBorder}` }}>
            <Dot color={C.amber} />
            <span style={{ fontSize: 10, fontWeight: 500, color: C.muted }}>{filteredNodes.length} nodes</span>
          </div>
          <div style={{ flex: 1 }} />
          {[["all", "All"], ["high", "High Conf"], ["risky", "Risky / Unknown"]].map(([id, label]) => (
            <Chip key={id} active={filter === id} onClick={() => setFilter(id)}>{label}</Chip>
          ))}
          <div style={{ display: "flex", alignItems: "center", gap: 6, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "5px 10px" }}>
            <svg width={11} height={11} viewBox="0 0 16 16" fill="none">
              <circle cx="6.5" cy="6.5" r="5" stroke={C.subtle} strokeWidth="1.5" />
              <path d="M10.5 10.5L14 14" stroke={C.subtle} strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search nodes..."
              style={{ border: "none", outline: "none", background: "transparent", fontSize: 12, color: C.text, width: 130, fontFamily: "inherit" }} />
          </div>
          <Btn size="sm"><Icons.Download s={12} stroke={C.muted} /> Export</Btn>
        </div>

        {/* Table */}
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#fafafa", borderBottom: `1px solid ${C.border}` }}>
                {["Node", "Cluster", "Current → Recommended", "vCPU", "Memory", "CPU Avg", "Mem Avg", "Conf", "Pool", "Savings/mo", "Auto", ""].map((h, i) => (
                  <th key={i} style={TH}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredNodes.map((n) => {
                const isExp = expanded === n.id;
                const auto = isAuto(n.id);
                return (
                  <>
                    <tr key={n.id}
                      onClick={() => setExpanded(isExp ? null : n.id)}
                      style={{
                        background: isExp ? C.surfaceHover : C.surface,
                        borderBottom: isExp ? "none" : `1px solid ${C.border}`,
                        cursor: "pointer", transition: "background 0.1s",
                      }}
                      onMouseEnter={e => { if (!isExp) e.currentTarget.style.background = C.surfaceHover; }}
                      onMouseLeave={e => { if (!isExp) e.currentTarget.style.background = isExp ? C.surfaceHover : C.surface; }}>

                      <td style={TD}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <div style={{ color: C.subtle, transition: "transform 0.2s", transform: isExp ? "rotate(90deg)" : "none" }}>
                            <Icons.ChevR s={12} stroke={C.subtle} />
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, fontSize: 12, color: C.text }}>{n.name}</div>
                            <div style={{ fontSize: 10, fontFamily: "monospace", color: C.subtle, marginTop: 1 }}>{n.id}</div>
                          </div>
                        </div>
                      </td>
                      <td style={TD}>
                        <span style={{ fontSize: 10, background: "#f0f1f3", padding: "2px 7px", borderRadius: 4, color: C.muted, fontFamily: "monospace" }}>{n.cluster}</span>
                      </td>
                      <td style={TD}>
                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                          <code style={{ fontSize: 10, background: "#f0f1f3", color: C.muted, padding: "2px 6px", borderRadius: 4 }}>{n.cur}</code>
                          <Icons.Arrow s={10} stroke={C.subtle} />
                          <code style={{ fontSize: 10, background: C.greenBg, color: C.green, border: `1px solid ${C.greenBorder}`, padding: "2px 6px", borderRadius: 4 }}>{n.rec}</code>
                        </div>
                      </td>
                      <td style={TD}>
                        <div style={{ fontSize: 11, color: C.muted }}>
                          <span style={{ fontWeight: 600, color: C.text }}>{n.curCpu}</span> → <span style={{ fontWeight: 600, color: C.green }}>{n.recCpu}</span>
                          <span style={{ color: C.subtle }}> vCPU</span>
                        </div>
                      </td>
                      <td style={TD}>
                        <div style={{ fontSize: 11, color: C.muted }}>
                          <span style={{ fontWeight: 600, color: C.text }}>{n.curMem}</span> → <span style={{ fontWeight: 600, color: C.green }}>{n.recMem}</span>
                          <span style={{ color: C.subtle }}> GB</span>
                        </div>
                      </td>
                      <td style={{ ...TD, width: 100 }}>
                        <MiniBar pct={n.cpuAvg} color={utilColor(n.cpuAvg)} />
                      </td>
                      <td style={{ ...TD, width: 100 }}>
                        <MiniBar pct={n.memAvg} color={C.accent} />
                      </td>
                      <td style={TD}>
                        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <Dot color={confColor[n.conf]} />
                          <span style={{ fontSize: 11, color: C.muted }}>{n.conf}</span>
                        </div>
                      </td>
                      <td style={TD}>
                        <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 20, background: "#f0f1f3", border: `1px solid ${C.border}`, width: "fit-content" }}>
                          <Dot color={poolColor[n.pool]} />
                          <span style={{ fontSize: 10, color: C.muted }}>{n.pool}</span>
                        </div>
                      </td>
                      <td style={TD}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: C.text }}>${n.savings}</span>
                        <div style={{ fontSize: 10, color: C.subtle }}>/ month</div>
                      </td>
                      <td style={TD} onClick={e => e.stopPropagation()}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <Toggle on={auto} onChange={v => setNodeAuto(n.id, v)} />
                          <span style={{ fontSize: 10, color: auto ? C.purple : C.subtle }}>
                            {auto ? "Auto" : "Manual"}
                          </span>
                        </div>
                      </td>
                      <td style={TD} onClick={e => e.stopPropagation()}>
                        {auto
                          ? <Btn size="sm" variant="purple"><Icons.Zap s={11} stroke="#fff" /> Scheduled</Btn>
                          : <Btn size="sm" variant="accent">Apply</Btn>}
                      </td>
                    </tr>

                    {/* Expanded detail */}
                    {isExp && (
                      <tr key={`${n.id}-exp`} style={{ borderBottom: `1px solid ${C.border}` }}>
                        <td colSpan={12} style={{ padding: "0 16px 16px" }}>
                          <NodeDetail node={n} />
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── NODE DETAIL PANEL ────────────────────────────────────────────────────────
function NodeDetail({ node }) {
  const cpu14d = [28, 32, 35, 29, 31, 34, 33, 38, 36, 34, 32, 30, 34, node.cpuAvg];
  const mem14d = [24, 26, 28, 25, 27, 29, 28, 31, 30, 27, 26, 25, 28, node.memAvg];
  const totalPodCpu = node.pods.reduce((s, p) => s + p.cpu, 0);
  const totalPodMem = node.pods.reduce((s, p) => s + p.mem, 0);

  // Bin packing: how pods fill current vs recommended node
  const curCpuPct = (totalPodCpu / node.curCpu) * 100;
  const recCpuPct = (totalPodCpu / node.recCpu) * 100;
  const curMemPct = (totalPodMem / node.curMem) * 100;
  const recMemPct = (totalPodMem / node.recMem) * 100;

  return (
    <div style={{ marginTop: 8, background: "#fafafa", border: `1px solid ${C.border}`, borderRadius: 10, padding: "16px 18px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20 }}>

        {/* ── Metrics + Sparklines ── */}
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.subtle, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>14-Day Usage</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <div style={{ fontSize: 10, color: C.muted, marginBottom: 5 }}>CPU Utilization</div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
                <Sparkline data={cpu14d} color={C.green} w={90} />
                <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.9 }}>
                  <div>Avg <strong style={{ color: C.text }}>{node.cpuAvg}%</strong></div>
                  <div>Peak <strong style={{ color: C.text }}>{node.cpuPeak}%</strong></div>
                </div>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: C.muted, marginBottom: 5 }}>Memory Utilization</div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
                <Sparkline data={mem14d} color={C.accent} w={90} />
                <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.9 }}>
                  <div>Avg <strong style={{ color: C.text }}>{node.memAvg}%</strong></div>
                  <div>Peak <strong style={{ color: C.text }}>{node.memPeak}%</strong></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Bin Packing Visualization ── */}
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.subtle, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>
            Bin Packing — Current vs Recommended
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {[
              { label: node.cur, cpuTotal: node.curCpu, memTotal: node.curMem, cpuUsed: totalPodCpu, memUsed: totalPodMem },
              { label: node.rec, cpuTotal: node.recCpu, memTotal: node.recMem, cpuUsed: totalPodCpu, memUsed: totalPodMem },
            ].map((inst, idx) => {
              const cpuFill = Math.min((inst.cpuUsed / inst.cpuTotal) * 100, 100);
              const memFill = Math.min((inst.memUsed / inst.memTotal) * 100, 100);
              const isRec = idx === 1;
              return (
                <div key={idx} style={{
                  border: `1.5px solid ${isRec ? C.greenBorder : C.border}`,
                  borderRadius: 8, padding: "10px 10px 8px",
                  background: isRec ? C.greenBg : C.surface,
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                    <code style={{ fontSize: 9, fontWeight: 600, color: isRec ? C.green : C.muted }}>{inst.label}</code>
                    {isRec && <span style={{ fontSize: 8, fontWeight: 700, color: C.green, background: "#dcfce7", padding: "1px 5px", borderRadius: 4 }}>RECOMMENDED</span>}
                  </div>
                  {/* CPU bar segmented by pod */}
                  <div style={{ marginBottom: 6 }}>
                    <div style={{ fontSize: 9, color: C.subtle, marginBottom: 3 }}>CPU · {inst.cpuTotal} vCPU</div>
                    <div style={{ height: 14, borderRadius: 4, background: "#ececec", overflow: "hidden", display: "flex" }}>
                      {node.pods.map((p, i) => {
                        const w = (p.cpu / inst.cpuTotal) * 100;
                        return <div key={i} title={`${p.name}: ${p.cpu.toFixed(1)} vCPU`} style={{
                          width: `${w}%`, height: "100%", background: POD_COLORS[i % POD_COLORS.length],
                          opacity: 0.85,
                        }} />;
                      })}
                    </div>
                    <div style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{cpuFill.toFixed(0)}% filled</div>
                  </div>
                  {/* Memory bar */}
                  <div>
                    <div style={{ fontSize: 9, color: C.subtle, marginBottom: 3 }}>Memory · {inst.memTotal} GB</div>
                    <div style={{ height: 14, borderRadius: 4, background: "#ececec", overflow: "hidden", display: "flex" }}>
                      {node.pods.map((p, i) => {
                        const w = (p.mem / inst.memTotal) * 100;
                        return <div key={i} title={`${p.name}: ${p.mem.toFixed(1)} GB`} style={{
                          width: `${w}%`, height: "100%", background: POD_COLORS[i % POD_COLORS.length],
                          opacity: 0.85,
                        }} />;
                      })}
                    </div>
                    <div style={{ fontSize: 9, color: C.muted, marginTop: 2 }}>{memFill.toFixed(0)}% filled</div>
                  </div>
                  {/* Pod legend */}
                  <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {node.pods.map((p, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "center", gap: 3 }}>
                        <div style={{ width: 6, height: 6, borderRadius: 2, background: POD_COLORS[i % POD_COLORS.length] }} />
                        <span style={{ fontSize: 8, color: C.subtle }}>{p.name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Savings Comparison ── */}
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: C.subtle, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>Savings Breakdown</div>
          {/* Monthly/annual */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
            <div style={{ background: C.greenBg, border: `1px solid ${C.greenBorder}`, borderRadius: 8, padding: "10px 12px" }}>
              <div style={{ fontSize: 10, color: C.muted, marginBottom: 3 }}>Monthly savings</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: C.text }}>${node.savings}</div>
              <div style={{ fontSize: 10, color: C.subtle }}>per month</div>
            </div>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px 12px" }}>
              <div style={{ fontSize: 10, color: C.muted, marginBottom: 3 }}>Annual projection</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: C.text }}>${(node.savings * 12).toLocaleString()}</div>
              <div style={{ fontSize: 10, color: C.subtle }}>per year</div>
            </div>
          </div>
          {/* Comparison bars */}
          {[
            { label: "vCPU", cur: node.curCpu, rec: node.recCpu, unit: "cores" },
            { label: "Memory", cur: node.curMem, rec: node.recMem, unit: "GB" },
          ].map(item => (
            <div key={item.label} style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: C.muted, marginBottom: 5 }}>{item.label}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 9, color: C.subtle, width: 28, textAlign: "right", flexShrink: 0 }}>Now</span>
                  <div style={{ flex: 1, height: 10, background: "#f0f0f0", borderRadius: 4 }}>
                    <div style={{ width: "100%", height: "100%", background: "#e5e7eb", borderRadius: 4 }} />
                  </div>
                  <span style={{ fontSize: 9, color: C.muted, width: 40, flexShrink: 0 }}>{item.cur} {item.unit}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 9, color: C.subtle, width: 28, textAlign: "right", flexShrink: 0 }}>Rec</span>
                  <div style={{ flex: 1, height: 10, background: "#f0f0f0", borderRadius: 4 }}>
                    <div style={{ width: `${(item.rec / item.cur) * 100}%`, height: "100%", background: C.green, borderRadius: 4, transition: "width 0.6s" }} />
                  </div>
                  <span style={{ fontSize: 9, color: C.green, fontWeight: 600, width: 40, flexShrink: 0 }}>{item.rec} {item.unit}</span>
                </div>
              </div>
              <div style={{ fontSize: 9, color: C.muted, marginTop: 3 }}>
                ↓ {((1 - item.rec / item.cur) * 100).toFixed(0)}% reduction
              </div>
            </div>
          ))}
          {/* Confidence reasoning */}
          <div style={{ marginTop: 4 }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: C.muted, marginBottom: 6 }}>Reasoning</div>
            {[
              [node.cpuAvg < 60, `CPU avg ${node.cpuAvg}% < 60% threshold`],
              [node.memAvg < 60, `Memory avg ${node.memAvg}% < 60% threshold`],
              [node.cpuPeak < 80, `Peak CPU ${node.cpuPeak}% below 80%`],
              [node.pool === "Healthy", `Pool health: ${node.pool}`],
            ].map(([ok, text], i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: C.muted, marginBottom: 4 }}>
                <Dot color={ok ? C.green : C.amber} />
                <span>{text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONFIGURATION SECTION
// ═══════════════════════════════════════════════════════════════════════════════
function ConfigSection({ clusters = [] }) {
  const [sel, setSel] = useState(clusters[0]?.id || "");
  const [cfg, setCfgState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!sel) return;
    setLoading(true);
    karpenterAPI.getConfig(sel)
      .then(res => {
        setCfgState({
          refreshInterval: 15,
          headroom: 20,
          maxSpotPct: res.data?.spot_target_pct ?? 80,
          strategy: res.data?.strategy || "balanced",
          autoApply: false,
          excludePeakAbove: 80,
          minDataDays: 14,
          onlyTemplateFamilies: true,
          nodepoolScope: "all",
          dryRunFirst: true,
          alertOnRevert: true,
          instanceFamilies: res.data?.instance_families || ["m5", "c5", "r5", "t3"],
          excludeFamilies: [],
        });
      })
      .catch(err => console.error("Failed to load config", err))
      .finally(() => setLoading(false));
  }, [sel]);

  const setCfg = (key, val) => setCfgState(p => ({ ...p, [key]: val }));

  const handleSave = () => {
    setSaving(true);
    karpenterAPI.updateConfig(sel, {
      strategy: cfg.strategy,
      spot_target_pct: cfg.maxSpotPct,
      instance_families: cfg.instanceFamilies,
    })
      .then(() => toast.success("Configuration saved"))
      .catch((err) => toast.error("Failed to save configuration"))
      .finally(() => setSaving(false));
  };

  const strategies = [
    { id: "balanced", label: "Balanced", desc: "Even spread across AZs & families" },
    { id: "cost-first", label: "Cost-First", desc: "Maximize spot usage, bin-pack tightly" },
    { id: "reliability", label: "Reliability-First", desc: "Prefer on-demand, conservative changes" },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 3px", color: C.text, letterSpacing: "-0.3px" }}>Configuration</h2>
        <p style={{ fontSize: 12, color: C.subtle, margin: 0 }}>Per-cluster Karpenter settings · refresh intervals · optimization strategies</p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 16 }}>
        {/* Cluster list sidebar */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" }}>
          <div style={{ padding: "12px 14px", borderBottom: `1px solid ${C.border}` }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>Clusters</span>
          </div>
          {clusters.map(c => (
            <div key={c.id} onClick={() => setSel(c.id)} style={{
              padding: "12px 14px", cursor: "pointer",
              borderBottom: `1px solid ${C.border}`,
              background: sel === c.id ? C.accentLight : "transparent",
              borderLeft: `3px solid ${sel === c.id ? C.accent : "transparent"}`,
              transition: "all 0.12s",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                <Dot color={c.status === "healthy" ? C.green : C.amber} />
                <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{c.name || c.id}</span>
              </div>
              <div style={{ fontSize: 10, color: C.subtle }}>{c.region || "us-east-1"} · {c.nodes || 0} nodes</div>
            </div>
          ))}
        </div>

        {/* Config form */}
        <div>
          {loading || !cfg ? (
            <div style={{ padding: 40, textAlign: "center", color: C.subtle, fontSize: 12 }}>Loading configuration...</div>
          ) : (
            <>
              {/* Strategy */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, marginBottom: 12, overflow: "hidden" }}>
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}` }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>Optimization Strategy</span>
                </div>
                <div style={{ padding: "14px 16px", display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
                  {strategies.map(s => (
                    <div key={s.id} onClick={() => setCfg("strategy", s.id)} style={{
                      padding: "12px 14px", border: `1.5px solid ${cfg.strategy === s.id ? C.accent : C.border}`,
                      borderRadius: 9, cursor: "pointer",
                      background: cfg.strategy === s.id ? C.accentLight : C.surface,
                      transition: "all 0.13s",
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{s.label}</span>
                        <div style={{ width: 14, height: 14, borderRadius: "50%", border: `2px solid ${cfg.strategy === s.id ? C.accent : C.border}`, background: cfg.strategy === s.id ? C.accent : "transparent", display: "flex", alignItems: "center", justifyContent: "center" }}>
                          {cfg.strategy === s.id && <div style={{ width: 5, height: 5, borderRadius: "50%", background: "#fff" }} />}
                        </div>
                      </div>
                      <p style={{ fontSize: 11, color: C.subtle, margin: 0, lineHeight: 1.6 }}>{s.desc}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Timing & Thresholds */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, marginBottom: 12, overflow: "hidden" }}>
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}` }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>Timing & Thresholds</span>
                </div>
                <div style={{ padding: "14px 16px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
                  {[
                    { label: "Refresh Interval (min)", key: "refreshInterval", min: 5, max: 120, step: 5, unit: "min" },
                    { label: "Headroom Buffer (%)", key: "headroom", min: 0, max: 50, step: 5, unit: "%" },
                    { label: "Exclude Peak CPU Above (%)", key: "excludePeakAbove", min: 60, max: 100, step: 5, unit: "%" },
                    { label: "Max Spot Percentage", key: "maxSpotPct", min: 0, max: 100, step: 10, unit: "%" },
                    { label: "Min Data Days", key: "minDataDays", min: 3, max: 30, step: 1, unit: "days" },
                  ].map(f => (
                    <div key={f.key}>
                      <div style={{ fontSize: 11, fontWeight: 500, color: C.muted, marginBottom: 6 }}>{f.label}</div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <input type="range" min={f.min} max={f.max} step={f.step} value={cfg[f.key]}
                          onChange={e => setCfg(f.key, Number(e.target.value))}
                          style={{ flex: 1, accentColor: C.accent }} />
                        <div style={{ fontSize: 13, fontWeight: 700, color: C.text, width: 42, textAlign: "right" }}>
                          {cfg[f.key]}<span style={{ fontSize: 9, fontWeight: 400, color: C.subtle }}>{f.unit}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Toggles */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, marginBottom: 12, overflow: "hidden" }}>
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}` }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>Behavior Flags</span>
                </div>
                <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 0 }}>
                  {[
                    { key: "autoApply", label: "Auto-Apply Recommendations", desc: "Changes are applied without manual approval" },
                    { key: "onlyTemplateFamilies", label: "Restrict to Template Instance Families", desc: "Only recommend instances in approved families" },
                    { key: "dryRunFirst", label: "Dry-Run Before Applying", desc: "Simulate change for 30 min before committing" },
                    { key: "alertOnRevert", label: "Alert on Auto-Revert", desc: "Notify when an applied change is rolled back" },
                  ].map((f, i, arr) => (
                    <div key={f.key} style={{
                      display: "flex", alignItems: "flex-start", justifyContent: "space-between",
                      padding: "12px 0", borderBottom: i < arr.length - 1 ? `1px solid ${C.border}` : "none",
                    }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 500, color: C.text }}>{f.label}</div>
                        <div style={{ fontSize: 11, color: C.subtle, marginTop: 2 }}>{f.desc}</div>
                      </div>
                      <Toggle on={cfg[f.key]} onChange={v => setCfg(f.key, v)} color={C.accent} />
                    </div>
                  ))}
                </div>
              </div>

              {/* Instance family allowlist */}
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, marginBottom: 12, overflow: "hidden" }}>
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}` }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>Allowed Instance Families</span>
                </div>
                <div style={{ padding: "14px 16px" }}>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {["m5", "m6i", "c5", "c6i", "r5", "r6i", "t3", "t3a", "x2i", "inf2"].map(fam => {
                      const active = cfg.instanceFamilies.includes(fam);
                      return (
                        <button key={fam} onClick={() => setCfg("instanceFamilies", active
                          ? cfg.instanceFamilies.filter(f => f !== fam)
                          : [...cfg.instanceFamilies, fam]
                        )} style={{
                          padding: "4px 12px", borderRadius: 6, cursor: "pointer",
                          fontFamily: "monospace", fontSize: 11,
                          background: active ? "#0f1117" : C.surface,
                          color: active ? "#fff" : C.muted,
                          border: `1px solid ${active ? "#0f1117" : C.border}`,
                          fontWeight: active ? 600 : 400, transition: "all 0.12s",
                        }}>{fam}.*</button>
                      );
                    })}
                  </div>
                  <div style={{ marginTop: 8, fontSize: 11, color: C.subtle }}>
                    {cfg.instanceFamilies.length} families selected · click to toggle
                  </div>
                </div>
              </div>

              {/* Save */}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <Btn size="md">Reset to defaults</Btn>
                <Btn size="md" variant="accent" onClick={handleSave} disabled={saving}>
                  {saving ? "Saving..." : <><Icons.Check s={13} stroke="#fff" /> Save Configuration</>}
                </Btn>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// OPTIMIZATION HISTORY SECTION
// ═══════════════════════════════════════════════════════════════════════════════
function HistorySection() {
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState(null);

  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    karpenterAPI.getActivity()
      .then(res => {
        const events = res.data?.events || [];
        const mapped = events.map((e, idx) => ({
          id: e.id || idx,
          date: new Date(e.timestamp).toLocaleDateString(),
          node: e.title?.split(" ")[0] || 'Node',
          cluster: e.cluster || 'Unknown',
          from: e.details?.[0]?.split(" → ")[0] || "Old",
          to: e.details?.[0]?.split(" → ")[1] || "New",
          mode: e.mode === "auto" ? "Auto" : "Manual",
          savings: e.savings_daily ? e.savings_daily * 30 : (e.potential_savings_monthly || 0),
          cpuBefore: e.utilization_after ? e.utilization_after - 20 : 30,
          cpuAfter: e.utilization_after || 60,
          memBefore: 40,
          memAfter: 68,
          ok: !e.action_required, // Simplify logic for status
          binBefore: [{ name: "workload", pct: 30 }, { name: "free", pct: 70 }],
          binAfter: [{ name: "workload", pct: 70 }, { name: "free", pct: 30 }]
        }));
        setHistory(mapped);
      })
      .catch(err => console.error("Failed to fetch history", err))
      .finally(() => setLoading(false));
  }, []);

  const filtered = history.filter(h => {
    if (filter === "manual" && h.mode !== "Manual") return false;
    if (filter === "auto" && h.mode !== "Auto") return false;
    if (filter === "ok" && !h.ok) return false;
    if (filter === "failed" && h.ok) return false;
    return true;
  });

  const totalSaved = history.filter(h => h.ok).reduce((s, h) => s + h.savings, 0);

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 3px", color: C.text, letterSpacing: "-0.3px" }}>Optimization History</h2>
        <p style={{ fontSize: 12, color: C.subtle, margin: 0 }}>All applied changes · bin packing comparison · CPU/memory before & after</p>
      </div>

      {/* KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 16 }}>
        <MetricBox label="Total Realized" value={`$${totalSaved.toLocaleString()}`} sub="All time" accentBorder={C.green} />
        <MetricBox label="Changes Applied" value={`${history.filter(h => h.ok).length}`} sub="Successful" accentBorder={C.accent} />
        <MetricBox label="Reverted" value={`${history.filter(h => !h.ok).length}`} sub="Auto-rolled back" accentBorder={C.red} />
        <MetricBox label="Auto-Applied" value={`${history.filter(h => h.mode === "Auto").length}`} sub="By Karpenter" accentBorder={C.purple} />
      </div>

      {/* Filter bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {[["all", "All"], ["manual", "Manual"], ["auto", "Auto"], ["ok", "Successful"], ["failed", "Reverted"]].map(([id, label]) => (
          <Chip key={id} active={filter === id} onClick={() => setFilter(id)}>{label}</Chip>
        ))}
      </div>

      {/* History entries */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {filtered.map(h => {
          const isExp = expanded === h.id;
          return (
            <div key={h.id} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden" }}>
              {/* Row header */}
              <div onClick={() => setExpanded(isExp ? null : h.id)}
                style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "12px 16px",
                  cursor: "pointer", background: isExp ? "#fafafa" : C.surface, transition: "background 0.1s",
                }}
                onMouseEnter={e => { if (!isExp) e.currentTarget.style.background = C.surfaceHover; }}
                onMouseLeave={e => { if (!isExp) e.currentTarget.style.background = C.surface; }}>

                <div style={{ color: C.subtle, transition: "transform 0.2s", transform: isExp ? "rotate(90deg)" : "none" }}>
                  <Icons.ChevR s={12} stroke={C.subtle} />
                </div>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: h.ok ? C.green : C.red, flexShrink: 0 }} />
                <span style={{ fontSize: 11, color: C.subtle, width: 90 }}>{h.date}</span>
                <span style={{ fontSize: 13, fontWeight: 600, color: C.text, width: 140 }}>{h.node}</span>
                <span style={{ fontSize: 10, fontFamily: "monospace", background: "#f0f1f3", color: C.muted, padding: "2px 7px", borderRadius: 4 }}>{h.cluster}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <code style={{ fontSize: 10, background: "#f0f1f3", color: C.muted, padding: "2px 6px", borderRadius: 4 }}>{h.from}</code>
                  <Icons.Arrow s={10} stroke={C.subtle} />
                  <code style={{ fontSize: 10, background: C.greenBg, color: C.green, border: `1px solid ${C.greenBorder}`, padding: "2px 6px", borderRadius: 4 }}>{h.to}</code>
                </div>
                <div style={{ flex: 1 }} />
                <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 20, background: h.mode === "Auto" ? C.purpleBg : "#f0f1f3", border: `1px solid ${h.mode === "Auto" ? C.purpleBorder : C.border}` }}>
                  {h.mode === "Auto" ? <Icons.Zap s={10} stroke={C.purple} /> : <Icons.Eye s={10} stroke={C.muted} />}
                  <span style={{ fontSize: 10, color: C.muted }}>{h.mode}</span>
                </div>
                <span style={{ fontSize: 13, fontWeight: 700, color: h.ok ? C.text : C.subtle }}>
                  {h.ok ? `$${h.savings}/mo` : "Reverted"}
                </span>
              </div>

              {/* Expanded detail */}
              {isExp && (
                <div style={{ padding: "0 16px 16px", borderTop: `1px solid ${C.border}` }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 18, marginTop: 16 }}>

                    {/* CPU / Mem comparison */}
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: C.subtle, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>Usage Comparison</div>
                      {[
                        { label: "CPU Utilization", before: h.cpuBefore, after: h.cpuAfter },
                        { label: "Memory Utilization", before: h.memBefore, after: h.memAfter },
                      ].map(metric => (
                        <div key={metric.label} style={{ marginBottom: 14 }}>
                          <div style={{ fontSize: 11, fontWeight: 500, color: C.muted, marginBottom: 6 }}>{metric.label}</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 9, color: C.subtle, width: 32 }}>Before</span>
                              <div style={{ flex: 1, height: 10, background: "#f0f0f0", borderRadius: 4, overflow: "hidden" }}>
                                <div style={{ width: `${metric.before}%`, height: "100%", background: "#e5e7eb", borderRadius: 4 }} />
                              </div>
                              <span style={{ fontSize: 10, fontWeight: 600, color: C.muted, width: 32 }}>{metric.before}%</span>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 9, color: C.subtle, width: 32 }}>After</span>
                              <div style={{ flex: 1, height: 10, background: "#f0f0f0", borderRadius: 4, overflow: "hidden" }}>
                                <div style={{ width: `${metric.after}%`, height: "100%", background: metric.after > 80 ? C.red : C.green, borderRadius: 4, transition: "width 0.6s" }} />
                              </div>
                              <span style={{ fontSize: 10, fontWeight: 600, color: C.green, width: 32 }}>{metric.after}%</span>
                            </div>
                          </div>
                          <div style={{ fontSize: 9, color: C.muted, marginTop: 4 }}>
                            Efficiency ↑ {metric.after - metric.before} pp (same workload, smaller node)
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Bin packing before / after */}
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: C.subtle, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>Bin Packing Before / After</div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                        {[{ label: "Before", data: h.binBefore, color: "#e5e7eb" }, { label: "After", data: h.binAfter, color: C.green }].map(({ label, data, color }) => (
                          <div key={label} style={{ border: `1px solid ${C.border}`, borderRadius: 8, padding: "10px" }}>
                            <div style={{ fontSize: 10, fontWeight: 600, color: C.muted, marginBottom: 8 }}>{label}</div>
                            {/* Vertical bin */}
                            <div style={{ height: 100, background: "#f5f6f8", borderRadius: 6, overflow: "hidden", display: "flex", flexDirection: "column-reverse", marginBottom: 6 }}>
                              {data.filter(d => d.name !== "free").map((d, i) => (
                                <div key={i} title={`${d.name}: ${d.pct}%`} style={{
                                  width: "100%", height: `${d.pct}%`,
                                  background: POD_COLORS[i % POD_COLORS.length],
                                  opacity: 0.85,
                                  display: "flex", alignItems: "center", justifyContent: "center",
                                  fontSize: 8, color: "#fff", fontWeight: 600, overflow: "hidden",
                                }}>
                                  {d.pct > 15 ? d.name : ""}
                                </div>
                              ))}
                            </div>
                            <div style={{ fontSize: 9, color: C.muted }}>
                              {(100 - (data.find(d => d.name === "free")?.pct || 0))}% used
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Savings detail */}
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: C.subtle, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12 }}>Financial Impact</div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        <div style={{ background: h.ok ? C.greenBg : C.redBg, border: `1px solid ${h.ok ? C.greenBorder : C.redBorder}`, borderRadius: 8, padding: "12px 14px" }}>
                          <div style={{ fontSize: 10, color: C.muted }}>Monthly savings</div>
                          <div style={{ fontSize: 22, fontWeight: 800, color: C.text, letterSpacing: "-0.5px" }}>
                            {h.ok ? `$${h.savings}` : "—"}
                          </div>
                          <div style={{ fontSize: 10, color: C.subtle }}>
                            {h.ok ? `$${(h.savings * 12).toLocaleString()} / year` : "Change reverted"}
                          </div>
                        </div>
                        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "12px 14px" }}>
                          <div style={{ fontSize: 10, color: C.muted, marginBottom: 8 }}>Change details</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, color: C.muted }}>
                            <div>Node: <strong style={{ color: C.text }}>{h.node}</strong></div>
                            <div>Mode: <strong style={{ color: C.text }}>{h.mode}</strong></div>
                            <div>Status: <strong style={{ color: h.ok ? C.green : C.red }}>{h.ok ? "Applied" : "Reverted"}</strong></div>
                            <div>Date: <strong style={{ color: C.text }}>{h.date}</strong></div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SAVINGS TRACKER SECTION
// ═══════════════════════════════════════════════════════════════════════════════
function SavingsTracker() {
  const [period, setPeriod] = useState("6m");

  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      karpenterAPI.getStats(period),
      karpenterAPI.getActivity()
    ])
      .then(([statsRes, actRes]) => {
        setStats(statsRes.data);

        const events = actRes.data?.events || [];
        const mapped = events.map((e, idx) => ({
          id: e.id || idx,
          date: new Date(e.timestamp).toLocaleDateString(),
          node: e.cluster || 'Unknown',
          from: e.details?.[0]?.split(" → ")[0] || "Old",
          to: e.details?.[0]?.split(" → ")[1] || "New",
          mode: e.mode === "auto" ? "Auto" : "Manual",
          savings: e.savings_daily ? e.savings_daily * 30 : (e.potential_savings_monthly || 0),
          ok: !e.action_required
        }));
        setHistory(mapped);
      })
      .catch(err => console.error("Failed to load savings data", err))
      .finally(() => setLoading(false));
  }, [period]);

  const monthly = [
    { m: "Sep", real: 1240, pot: 5800 },
    { m: "Oct", real: 1890, pot: 5600 },
    { m: "Nov", real: 2340, pot: 5400 },
    { m: "Dec", real: 2100, pot: 5200 },
    { m: "Jan", real: 2780, pot: 4900 },
    { m: "Feb", real: stats?.cost_saved || 3150, pot: stats?.cost_saved ? stats.cost_saved + 1500 : 4820 },
  ];
  const display = period === "1m" ? monthly.slice(-1) : period === "3m" ? monthly.slice(-3) : monthly;
  const maxV = Math.max(...display.map(d => d.pot)) + 1000;

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 3px", color: C.text, letterSpacing: "-0.3px" }}>Savings Tracker</h2>
        <p style={{ fontSize: 12, color: C.subtle, margin: 0 }}>Realized vs potential savings over time · cluster breakdown · fleet score</p>
      </div>

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 16 }}>
        <MetricBox label="Total Realized" value={`$${(stats?.total_saved || 13500).toLocaleString()}`} sub="All time" accentBorder={C.green} />
        <MetricBox label="Total Saved" value={`$${(stats?.cost_saved || 3150).toLocaleString()}`} sub="Selected period" accentBorder={C.green} />
        <MetricBox label="Avg Utilization" value={`${stats?.avg_utilization_pct || 78}%`} sub="Across fleet" accentBorder={C.amber} />
        <MetricBox label="Optimizations Run" value={`${stats?.optimizations_count || 47}`} sub="Actions performed" accentBorder={C.accent} />
      </div>

      {/* Bar chart */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "18px 20px", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>Realized vs Potential Savings</div>
            <div style={{ fontSize: 11, color: C.subtle, marginTop: 2 }}>Monthly cost reduction from applied recommendations</div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            {[["1m", "1M"], ["3m", "3M"], ["6m", "6M"]].map(([id, label]) => (
              <Chip key={id} active={period === id} onClick={() => setPeriod(id)}>{label}</Chip>
            ))}
            <Btn size="sm"><Icons.Download s={12} stroke={C.muted} /></Btn>
          </div>
        </div>

        <div style={{ position: "relative" }}>
          <div style={{ position: "absolute", left: 0, top: 0, bottom: 28, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            {["$6k", "$4k", "$2k", "$0"].map(l => (
              <span key={l} style={{ fontSize: 9, color: C.subtle }}>{l}</span>
            ))}
          </div>
          <div style={{ marginLeft: 28, position: "relative" }}>
            {[0, 1, 2, 3].map(i => (
              <div key={i} style={{ position: "absolute", left: 0, right: 0, top: `${(i / 3) * 100}%`, borderTop: `1px solid ${C.border}` }} />
            ))}
            <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 180, paddingBottom: 28 }}>
              {display.map((d, i) => (
                <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", height: "100%", justifyContent: "flex-end" }}>
                  <div style={{ width: "100%", display: "flex", gap: 3, alignItems: "flex-end", height: "calc(100% - 20px)" }}>
                    <div style={{ flex: 1, borderRadius: "3px 3px 0 0", minHeight: 4, height: `${(d.pot / maxV) * 100}%`, background: "#eef0f3", transition: "height 0.6s cubic-bezier(.4,0,.2,1)" }} title={`$${d.pot.toLocaleString()} potential`} />
                    <div style={{ flex: 1, borderRadius: "3px 3px 0 0", minHeight: 4, height: `${(d.real / maxV) * 100}%`, background: C.green, transition: "height 0.6s cubic-bezier(.4,0,.2,1)" }} title={`$${d.real.toLocaleString()} realized`} />
                  </div>
                  <span style={{ fontSize: 10, color: C.subtle, marginTop: 6 }}>{d.m}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 18, marginTop: 8 }}>
          {[["Realized savings", C.green, null], ["Remaining potential", "#eef0f3", C.border]].map(([l, bg, border]) => (
            <div key={l} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 12, height: 12, borderRadius: 3, background: bg, border: border ? `1px solid ${border}` : "none" }} />
              <span style={{ fontSize: 11, color: C.muted }}>{l}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 14 }}>
        {/* Applied table */}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10 }}>
          <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>Applied Optimizations</span>
            <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 20, background: C.greenBg, border: `1px solid ${C.greenBorder}` }}>
              <Dot color={C.green} />
              <span style={{ fontSize: 10, fontWeight: 500, color: C.muted }}>{history.filter(h => h.ok).length} successful</span>
            </div>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#fafafa", borderBottom: `1px solid ${C.border}` }}>
                {["Date", "Node", "Change", "Monthly Saving", "Mode", "Status"].map(h => (
                  <th key={h} style={TH}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map((h, i) => (
                <tr key={h.id}
                  style={{ borderBottom: i < history.length - 1 ? `1px solid ${C.border}` : "none", transition: "background 0.1s" }}
                  onMouseEnter={e => e.currentTarget.style.background = C.surfaceHover}
                  onMouseLeave={e => e.currentTarget.style.background = C.surface}>
                  <td style={TD}><span style={{ fontSize: 11, color: C.subtle }}>{h.date.replace(", 2026", "")}</span></td>
                  <td style={TD}><span style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{h.node}</span></td>
                  <td style={TD}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <code style={{ fontSize: 10, background: "#f0f1f3", color: C.muted, padding: "2px 6px", borderRadius: 4 }}>{h.from}</code>
                      <Icons.Arrow s={10} stroke={C.subtle} />
                      <code style={{ fontSize: 10, background: C.greenBg, color: C.green, border: `1px solid ${C.greenBorder}`, padding: "2px 6px", borderRadius: 4 }}>{h.to}</code>
                    </div>
                  </td>
                  <td style={TD}><span style={{ fontSize: 13, fontWeight: 700, color: h.ok ? C.text : C.subtle }}>{h.ok ? `$${h.savings}` : "—"}</span></td>
                  <td style={TD}>
                    <div style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 7px", borderRadius: 20, background: h.mode === "Auto" ? C.purpleBg : "#f0f1f3", border: `1px solid ${h.mode === "Auto" ? C.purpleBorder : C.border}`, width: "fit-content" }}>
                      <span style={{ fontSize: 10, color: C.muted }}>{h.mode}</span>
                    </div>
                  </td>
                  <td style={TD}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <Dot color={h.ok ? C.green : C.red} />
                      <span style={{ fontSize: 11, color: C.muted }}>{h.ok ? "Applied" : "Reverted"}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Right side */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "14px 16px" }}>
            <SectionHeader>Savings by Cluster</SectionHeader>
            {[{ name: "prod-cluster", val: 2100, pct: 67 }, { name: "data-cluster", val: 720, pct: 23 }, { name: "staging-cluster", val: 330, pct: 10 }].map(c => (
              <div key={c.name} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 11, fontWeight: 500, color: C.text }}>{c.name}</span>
                  <span style={{ fontSize: 11, color: C.muted, fontFamily: "monospace" }}>${c.val.toLocaleString()}</span>
                </div>
                <MiniBar pct={c.pct} color={C.green} />
              </div>
            ))}
          </div>

          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "14px 16px" }}>
            <SectionHeader>By Instance Family</SectionHeader>
            {[{ fam: "m5", n: 18, v: "$1,240" }, { fam: "c5", n: 12, v: "$980" }, { fam: "t3", n: 9, v: "$420" }, { fam: "r5", n: 5, v: "$510" }].map((f, i) => (
              <div key={f.fam} style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "8px 0", borderBottom: i < 3 ? `1px solid ${C.border}` : "none",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <code style={{ fontSize: 10, background: "#f0f1f3", color: C.muted, padding: "2px 7px", borderRadius: 4 }}>{f.fam}.*</code>
                  <span style={{ fontSize: 10, color: C.subtle }}>{f.n} instances</span>
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color: C.text }}>{f.v}</span>
              </div>
            ))}
          </div>

          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 10, padding: "14px 16px" }}>
            <SectionHeader>Fleet Score</SectionHeader>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <ScoreRing score={6.4} size={56} />
              <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.8 }}>
                <div>23 of 148 instances over-provisioned</div>
                <div style={{ marginTop: 4, fontSize: 10, color: C.subtle }}>
                  Full optimization → <strong style={{ color: C.text }}>8.9 / 10</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}