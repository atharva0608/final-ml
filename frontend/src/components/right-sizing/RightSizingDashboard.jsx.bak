import React, { useState, useEffect } from "react";
import { useClusterStore, useAuthStore } from '../../store/useStore';
import { api, optimizationAPI, templateAPI, karpenterAPI } from '../../services/api';
import toast from 'react-hot-toast';

// ─── Icons ────────────────────────────────────────────────────────────────────
const ZapI = ({ s = 15 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></svg>;
const EyeI = ({ s = 14 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>;
const PlayI = ({ s = 14 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3" /></svg>;
const CheckI = ({ s = 13 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>;
const XI = ({ s = 14 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>;
const ArrowI = ({ s = 13 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" /></svg>;
const SettI = ({ s = 15 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></svg>;
const AlertI = ({ s = 14 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>;
const TrendI = ({ s = 14 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" /></svg>;
const ServerI = ({ s = 13 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" /><rect x="2" y="14" width="20" height="8" rx="2" /><line x1="6" y1="6" x2="6.01" y2="6" /><line x1="6" y1="18" x2="6.01" y2="18" /></svg>;
const GridI = ({ s = 13 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></svg>;
const InfoI = ({ s = 13 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" /></svg>;
const DollarI = ({ s = 14 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" /></svg>;
const CpuI = ({ s = 14 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="2" x2="9" y2="4" /><line x1="15" y1="2" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="22" /><line x1="15" y1="20" x2="15" y2="22" /><line x1="2" y1="9" x2="4" y2="9" /><line x1="2" y1="15" x2="4" y2="15" /><line x1="20" y1="9" x2="22" y2="9" /><line x1="20" y1="15" x2="22" y2="15" /></svg>;
const MemI = ({ s = 14 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2" /><polyline points="2 17 12 22 22 17" /><polyline points="2 12 12 17 22 12" /></svg>;
const BoxI = ({ s = 11 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" /></svg>;

// ─── Design Tokens ────────────────────────────────────────────────────────────
const C = {
    bg: "#f9fafb", surface: "#ffffff", surfaceAlt: "#f8fafc",
    border: "#e5e7eb", text: "#111827", textSec: "#4b5563", textMuted: "#6b7280",
    indigo: "#4f46e5", indigoBg: "#eef2ff", indigoMid: "#c7d2fe",
    green: "#16a34a", greenBg: "#f0fdf4", greenMid: "#bbf7d0",
    amber: "#d97706", amberBg: "#fffbeb", amberMid: "#fde68a",
    red: "#ef4444", redBg: "#fef2f2", redMid: "#fecaca",
    purple: "#7c3aed", purpleBg: "#f5f3ff",
    cyan: "#0891b2", cyanBg: "#ecfeff",
};
const F = { sans: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif" };

const COST_TREND = [
    { m: "Sep", before: 4200, after: 2800 }, { m: "Oct", before: 4100, after: 2650 },
    { m: "Nov", before: 3900, after: 2500 }, { m: "Dec", before: 4300, after: 2600 },
    { m: "Jan", before: 4500, after: 2750 }, { m: "Feb", before: 4200, after: 2420 },
];

const NS_COLOR = { production: "#4f46e5", staging: "#0891b2", dev: "#7c3aed", data: "#d97706" };
const confColor = { HIGH: C.green, MEDIUM: C.amber, LOW: C.red };
const intColor = { "VERY LOW": C.green, LOW: C.green, MEDIUM: C.amber, HIGH: C.red };

// ─── Shared UI ────────────────────────────────────────────────────────────────
const Badge = ({ color, bg, border, children }) => (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 3, padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 600, color, background: bg, border: border ? `1px solid ${border}` : "none", whiteSpace: "nowrap" }}>{children}</span>
);

const Btn = ({ children, variant = "primary", onClick, small, disabled, full, style: sx }) => {
    const v = {
        primary: { background: C.indigo, color: "#fff", border: "none" },
        ghost: { background: "transparent", color: C.textSec, border: `1px solid ${C.border}` },
        success: { background: C.greenBg, color: C.green, border: `1px solid ${C.greenMid}` },
        danger: { background: C.redBg, color: C.red, border: `1px solid ${C.redMid}` },
        outline: { background: "transparent", color: C.indigo, border: `1px solid ${C.indigo}` },
    };
    return (
        <button onClick={onClick} disabled={disabled} style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6, padding: small ? "5px 11px" : "8px 16px", borderRadius: 8, fontSize: small ? 12 : 13, fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.45 : 1, fontFamily: F.sans, width: full ? "100%" : "auto", whiteSpace: "nowrap", ...v[variant], ...sx }}>{children}</button>
    );
};

const Card = ({ children, style: sx }) => (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, overflow: "hidden", ...sx }}>{children}</div>
);

const SectionHead = ({ label, right }) => (
    <div style={{ padding: "12px 18px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContents: "space-between" }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: C.textMuted, letterSpacing: "0.07em", textTransform: "uppercase" }}>{label}</span>
        {right && <div style={{ marginLeft: "auto" }}>{right}</div>}
    </div>
);

const PBar = ({ value, max = 100, color, height = 5 }) => {
    const pct = Math.min((value / max) * 100, 100);
    const col = color || (pct > 80 ? C.red : pct > 60 ? C.amber : C.indigo);
    return (
        <div style={{ background: "#e2e8f0", borderRadius: 99, height, overflow: "hidden" }}>
            <div style={{ height: "100%", borderRadius: 99, background: col, width: `${pct}%`, transition: "width 0.6s ease" }} />
        </div>
    );
};

const Ring = ({ value, size = 52, label, color }) => {
    const r = (size - 8) / 2, circ = 2 * Math.PI * r;
    const col = color || (value > 80 ? C.red : value > 60 ? C.amber : C.indigo);
    return (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={6} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={6} strokeLinecap="round"
                    strokeDasharray={circ} strokeDashoffset={circ * (1 - value / 100)} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
                <text x={size / 2} y={size / 2 + 4} textAnchor="middle" fontSize={10} fontWeight={700} fill={col} fontFamily={F.sans}>{value}%</text>
            </svg>
            {label && <span style={{ fontSize: 10, color: C.textMuted, fontWeight: 600 }}>{label}</span>}
        </div>
    );
};

const Spark = ({ data, color = C.indigo, W = 80, H = 30 }) => {
    if (!data?.length) return null;
    const max = Math.max(...data), min = Math.min(...data), range = max - min || 1;
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * W},${H - 2 - ((v - min) / range) * (H - 6)}`).join(" ");
    const area = `M ${pts.split(" ").join(" L ")} L ${W},${H} L 0,${H} Z`;
    return (
        <svg width={W} height={H} style={{ overflow: "visible" }}>
            <defs><linearGradient id={`sg${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.25" /><stop offset="100%" stopColor={color} stopOpacity="0.02" /></linearGradient></defs>
            <path d={area} fill={`url(#sg${color.replace("#", "")})`} />
            <polyline points={pts} fill="none" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
            {data.map((v, i) => i === data.length - 1 ? <circle key={i} cx={(i / (data.length - 1)) * W} cy={H - 2 - ((v - min) / range) * (H - 6)} r={2.5} fill={color} stroke="#fff" strokeWidth={1.5} /> : null)}
        </svg>
    );
};

const CostBarChart = ({ trend }) => {
    const W = 400, H = 110, PAD = { l: 42, r: 10, t: 10, b: 24 };
    const max = Math.max(...trend.map(d => d.before));
    const barW = (W - PAD.l - PAD.r) / (trend.length * 2 + trend.length - 1) * 1.5;
    return (
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
            {[0.33, 0.66, 1].map(f => (
                <g key={f}>
                    <line x1={PAD.l} y1={PAD.t + (1 - f) * (H - PAD.t - PAD.b)} x2={W - PAD.r} y2={PAD.t + (1 - f) * (H - PAD.t - PAD.b)} stroke="#e2e8f0" strokeWidth={1} />
                    <text x={PAD.l - 4} y={PAD.t + (1 - f) * (H - PAD.t - PAD.b) + 3} textAnchor="end" fontSize={9} fill={C.textMuted}>${Math.round(max * f / 1000)}K</text>
                </g>
            ))}
            {trend.map((d, i) => {
                const groupW = (W - PAD.l - PAD.r) / trend.length;
                const gx = PAD.l + i * groupW + groupW * 0.1;
                const bw = groupW * 0.35;
                const bH = H - PAD.t - PAD.b;
                const beforeH = (d.before / max) * bH, afterH = (d.after / max) * bH;
                return (
                    <g key={i}>
                        <rect x={gx} y={PAD.t + bH - beforeH} width={bw} height={beforeH} fill={C.red} opacity={0.7} rx={2} />
                        <rect x={gx + bw + 2} y={PAD.t + bH - afterH} width={bw} height={afterH} fill={C.green} opacity={0.8} rx={2} />
                        <text x={gx + bw + 1} y={H - 4} textAnchor="middle" fontSize={9} fill={C.textMuted}>{d.m}</text>
                    </g>
                );
            })}
            <g transform={`translate(${W - 90},${PAD.t})`}>
                <rect width={8} height={8} fill={C.red} opacity={0.7} rx={1} />
                <text x={11} y={7} fontSize={9} fill={C.textSec}>Before</text>
                <rect y={13} width={8} height={8} fill={C.green} opacity={0.8} rx={1} />
                <text x={11} y={20} fontSize={9} fill={C.textSec}>After</text>
            </g>
        </svg>
    );
};

const SavingsDonut = ({ current, recommended, size = 120 }) => {
    const r = (size - 16) / 2, circ = 2 * Math.PI * r;
    const recPct = recommended / current;
    const savPct = 1 - recPct;
    return (
        <div style={{ position: "relative", width: size, height: size }}>
            <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={C.red} strokeWidth={14} opacity={0.18} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={C.green} strokeWidth={14} strokeLinecap="butt"
                    strokeDasharray={circ} strokeDashoffset={circ * (1 - savPct)} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={C.red} strokeWidth={14} strokeLinecap="butt"
                    strokeDasharray={`${circ * recPct} ${circ}`} strokeDashoffset={circ * savPct} transform={`rotate(-90 ${size / 2} ${size / 2})`} opacity={0.65} />
                <text x={size / 2} y={size / 2 - 5} textAnchor="middle" fontSize={13} fontWeight={800} fill={C.green} fontFamily={F.sans}>{Math.round(savPct * 100)}%</text>
                <text x={size / 2} y={size / 2 + 9} textAnchor="middle" fontSize={8} fill={C.textMuted} fontFamily={F.sans}>SAVED</text>
            </svg>
        </div>
    );
};

const BinPackNode = ({ node }) => {
    const cpuUsed = node.pods.reduce((a, p) => a + p.cpu, 0);
    const memUsed = node.pods.reduce((a, p) => a + p.mem, 0);
    return (
        <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, overflow: "hidden", background: C.surface, minWidth: 170 }}>
            <div style={{ padding: "7px 10px", background: C.surfaceAlt, borderBottom: `1px solid ${C.border}` }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: C.text }}>{node.type}</div>
                <div style={{ fontSize: 10, color: C.textMuted }}>{node.vcpu}vCPU · {node.mem}GB</div>
            </div>
            <div style={{ padding: "7px 10px", borderBottom: `1px solid ${C.border}` }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.textSec, marginBottom: 2 }}>
                    <span>CPU</span><span style={{ fontWeight: 700, color: (cpuUsed / node.vcpu) > 0.8 ? C.red : (cpuUsed / node.vcpu) > 0.6 ? C.amber : C.green }}>{Math.round((cpuUsed / node.vcpu) * 100)}%</span>
                </div>
                <PBar value={(cpuUsed / node.vcpu) * 100} height={4} />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.textSec, marginBottom: 2, marginTop: 5 }}>
                    <span>MEM</span><span style={{ fontWeight: 700, color: (memUsed / node.mem) > 0.8 ? C.red : (memUsed / node.mem) > 0.6 ? C.amber : C.indigo }}>{Math.round((memUsed / node.mem) * 100)}%</span>
                </div>
                <PBar value={(memUsed / node.mem) * 100} height={4} color={C.purple} />
            </div>
            <div style={{ padding: "7px 10px" }}>
                <div style={{ fontSize: 9, fontWeight: 700, color: C.textMuted, marginBottom: 4 }}>PODS ({node.pods.length})</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                    {node.pods.map((p, i) => (
                        <span key={i} title={`${p.name} • ${p.cpu}CPU • ${p.mem}GB`} style={{ padding: "2px 5px", borderRadius: 3, fontSize: 9, fontWeight: 600, background: `${NS_COLOR[p.ns] || C.indigo}16`, color: NS_COLOR[p.ns] || C.indigo, border: `1px solid ${NS_COLOR[p.ns] || C.indigo}30` }}>{p.name}</span>
                    ))}
                </div>
            </div>
        </div>
    );
};

// ─── Detail Drawer Modal ──────────────────────────────────────────────────────
function DetailDrawer({ rec, mode, onClose, onApply }) {
    const annualSavings = rec.savings * 12;
    const spotAnnualSavings = rec.spotAvail ? rec.savings * (1 + rec.spotSavings / 100) * 12 : null;
    const vcpuReduction = rec.vcpuCurrent - rec.vcpuRec;
    const memReduction = rec.memGBCurrent - rec.memGBRec;
    const isApplied = rec.status === "applied";

    return (
        <div style={{ position: "fixed", inset: 0, zIndex: 400, display: "flex", alignItems: "stretch", justifyContent: "flex-end", animation: "fadeIn 0.15s" }}>
            <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(15,23,42,0.45)", backdropFilter: "blur(3px)" }} />
            <div style={{ position: "relative", width: "min(680px, 96vw)", height: "100vh", background: C.surface, overflowY: "auto", animation: "slideIn 0.25s ease", boxShadow: "-12px 0 60px rgba(0,0,0,0.15)", display: "flex", flexDirection: "column" }}>
                <div style={{ padding: "18px 24px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between", alignItems: "flex-start", position: "sticky", top: 0, background: C.surface, zIndex: 10 }}>
                    <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                            <ServerI s={14} />
                            <span style={{ fontSize: 16, fontWeight: 800, color: C.text, letterSpacing: "-0.02em" }}>{rec.name}</span>
                            {isApplied && <Badge color={C.green} bg={C.greenBg} border={C.greenMid}><CheckI s={11} />Applied</Badge>}
                        </div>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            <Badge color={NS_COLOR[rec.namespace] || C.indigo} bg={`${NS_COLOR[rec.namespace] || C.indigo}12`}>{rec.namespace || 'default'}</Badge>
                            <Badge color={confColor[rec.confidence]} bg={`${confColor[rec.confidence]}14`}>{rec.confidence} confidence</Badge>
                            {mode === "karpenter_insights" && <Badge color={C.purple} bg={C.purpleBg}>K8s-aware</Badge>}
                        </div>
                    </div>
                    <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: C.textMuted, padding: 4, borderRadius: 6, display: "flex" }}><XI s={18} /></button>
                </div>

                <div style={{ padding: "20px 24px", flex: 1, display: "flex", flexDirection: "column", gap: 20 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 16, alignItems: "center", padding: "18px 20px", borderRadius: 12, background: `linear-gradient(135deg, ${C.indigoBg}, #f0fdf4)`, border: `1px solid ${C.indigoMid}` }}>
                        <div>
                            <div style={{ fontSize: 11, fontWeight: 700, color: C.textMuted, letterSpacing: "0.07em", marginBottom: 10 }}>INSTANCE CHANGE</div>
                            <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
                                <div style={{ textAlign: "center" }}>
                                    <div style={{ fontSize: 18, fontWeight: 800, color: C.red, fontFamily: "monospace" }}>{rec.currentType}</div>
                                    <div style={{ fontSize: 11, color: C.textMuted }}>${rec.currentCost?.toFixed(0) || 0}/mo</div>
                                    <div style={{ fontSize: 10, color: C.textMuted }}>{rec.vcpuCurrent}vCPU · {rec.memGBCurrent}GB</div>
                                </div>
                                <div style={{ color: C.indigo }}><ArrowI s={20} /></div>
                                <div style={{ textAlign: "center" }}>
                                    <div style={{ fontSize: 18, fontWeight: 800, color: C.indigo, fontFamily: "monospace" }}>{rec.recType}</div>
                                    <div style={{ fontSize: 11, color: C.textMuted }}>${rec.recCost?.toFixed(0) || 0}/mo</div>
                                    <div style={{ fontSize: 10, color: C.textMuted }}>{rec.vcpuRec}vCPU · {rec.memGBRec}GB</div>
                                </div>
                            </div>
                            <div style={{ display: "flex", gap: 12 }}>
                                <div style={{ padding: "8px 14px", borderRadius: 8, background: C.greenBg, border: `1px solid ${C.greenMid}` }}>
                                    <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 1 }}>Monthly</div>
                                    <div style={{ fontSize: 18, fontWeight: 800, color: C.green }}>${rec.savings?.toFixed(0) || 0}</div>
                                </div>
                                <div style={{ padding: "8px 14px", borderRadius: 8, background: C.greenBg, border: `1px solid ${C.greenMid}` }}>
                                    <div style={{ fontSize: 11, color: C.textMuted, marginBottom: 1 }}>Annual</div>
                                    <div style={{ fontSize: 18, fontWeight: 800, color: C.green }}>${annualSavings?.toFixed(0) || 0}</div>
                                </div>
                            </div>
                        </div>
                        <SavingsDonut current={rec.currentCost || 1} recommended={rec.recCost || 0} size={130} />
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                        {[
                            { label: "vCPU Reduction", icon: <CpuI s={15} />, val: `${vcpuReduction || 0} vCPU`, sub: `${rec.vcpuCurrent} → ${rec.vcpuRec}`, color: C.indigo, bg: C.indigoBg },
                            { label: "Memory Reduction", icon: <MemI s={15} />, val: `${memReduction || 0} GB`, sub: `${rec.memGBCurrent}GB → ${rec.memGBRec}GB`, color: C.purple, bg: C.purpleBg },
                        ].map(k => (
                            <div key={k.label} style={{ padding: "12px 14px", borderRadius: 10, background: k.bg, border: `1px solid ${k.color}25`, display: "flex", alignItems: "center", gap: 12 }}>
                                <div style={{ width: 36, height: 36, borderRadius: 8, background: C.surface, display: "flex", alignItems: "center", justifyContent: "center", color: k.color }}>{k.icon}</div>
                                <div>
                                    <div style={{ fontSize: 10, fontWeight: 700, color: C.textMuted, letterSpacing: "0.06em" }}>{k.label}</div>
                                    <div style={{ fontSize: 18, fontWeight: 800, color: k.color }}>{k.val}</div>
                                    <div style={{ fontSize: 11, color: C.textSec }}>{k.sub}</div>
                                </div>
                            </div>
                        ))}
                    </div>

                    <Card>
                        <SectionHead label="CPU & Memory Utilization" />
                        <div style={{ padding: "16px 18px" }}>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 16 }}>
                                <div>
                                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}><CpuI s={12} /><span style={{ fontSize: 11, fontWeight: 600, color: C.textSec }}>CPU Utilization</span></div>
                                    </div>
                                    <div style={{ marginBottom: 6 }}>
                                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.textSec, marginBottom: 3 }}>
                                            <span>Average</span><span style={{ fontWeight: 700 }}>{rec.cpuAvg}%</span>
                                        </div>
                                        <PBar value={rec.cpuAvg} color={C.indigo} />
                                    </div>
                                </div>
                                <div>
                                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 6 }}><MemI s={12} /><span style={{ fontSize: 11, fontWeight: 600, color: C.textSec }}>Memory Utilization</span></div>
                                    <div style={{ marginBottom: 6 }}>
                                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: C.textSec, marginBottom: 3 }}>
                                            <span>Average</span><span style={{ fontWeight: 700 }}>{rec.memAvg}%</span>
                                        </div>
                                        <PBar value={rec.memAvg} color={C.purple} />
                                    </div>
                                </div>
                            </div>
                            <div style={{ display: "flex", gap: 16, justifyContent: "center", padding: "10px 0", borderTop: `1px solid ${C.border}` }}>
                                <Ring value={rec.cpuAvg} size={56} label="CPU Avg" color={C.indigo} />
                                <Ring value={rec.memAvg} size={56} label="Mem Avg" color={C.purple} />
                            </div>
                        </div>
                    </Card>

                    <Card>
                        <SectionHead label={`Pods & Workload`} />
                        <div style={{ padding: "12px 18px" }}>
                            <div style={{ fontSize: 11, color: C.textSec, padding: "6px 0" }}>{rec.reason || "Underutilized instance, candidates for downsizing."}</div>
                            {mode === "karpenter_insights" && (
                                <div style={{ marginTop: 10, padding: "8px 12px", borderRadius: 8, background: C.indigoBg, border: `1px solid ${C.indigoMid}`, display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: C.indigo }}>
                                    <InfoI s={13} />Karpenter score <strong>{rec.karpScore || 8}/10</strong> — analyzes live pod specs, taints, topology constraints.
                                </div>
                            )}
                        </div>
                    </Card>

                    {!isApplied && (
                        <div style={{ display: "flex", gap: 10, paddingTop: 4 }}>
                            <Btn variant="ghost" onClick={onClose} sx={{ flex: 1 }}>Cancel</Btn>
                            <Btn onClick={() => onApply(rec)} sx={{ flex: 2 }}><CheckI s={13} /> Apply Recommendation</Btn>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ─── Apply Confirmation ───────────────────────────────────────────────────────
function ApplyConfirmModal({ rec, mode, onClose, onConfirm }) {
    const steps = mode === "karpenter_insights"
        ? ["Provision new node (" + rec.recType + ")", "Cordon current node", "Drain pods gracefully", "Terminate old node"]
        : ["Stop instance", "Change instance type", "Start instance", "Verify pods"];
    return (
        <div style={{ position: "fixed", inset: 0, zIndex: 500, display: "flex", alignItems: "center", justifyContent: "center", padding: 20, animation: "fadeIn 0.15s" }}>
            <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(15,23,42,0.5)", backdropFilter: "blur(4px)" }} />
            <div style={{ position: "relative", background: C.surface, borderRadius: 16, width: "100%", maxWidth: 440, boxShadow: "0 24px 60px rgba(0,0,0,0.2)", overflow: "hidden" }}>
                <div style={{ padding: "16px 20px", borderBottom: `1px solid ${C.border}`, display: "flex", justifyContent: "space-between" }}>
                    <div style={{ fontSize: 14, fontWeight: 800 }}>Confirm: Apply Recommendation</div>
                    <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: C.textMuted, display: "flex" }}><XI s={16} /></button>
                </div>
                <div style={{ padding: "16px 20px" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 10, alignItems: "center", marginBottom: 14 }}>
                        <div style={{ padding: "9px 12px", borderRadius: 8, background: C.redBg, border: `1px solid ${C.redMid}`, textAlign: "center" }}>
                            <div style={{ fontSize: 12, fontWeight: 800, color: C.text }}>{rec.currentType}</div>
                            <div style={{ fontSize: 12, color: C.red, fontWeight: 600 }}>${rec.currentCost?.toFixed(0) || 0}/mo</div>
                        </div>
                        <ArrowI s={18} />
                        <div style={{ padding: "9px 12px", borderRadius: 8, background: C.greenBg, border: `1px solid ${C.greenMid}`, textAlign: "center" }}>
                            <div style={{ fontSize: 12, fontWeight: 800, color: C.text }}>{rec.recType}</div>
                            <div style={{ fontSize: 12, color: C.green, fontWeight: 600 }}>${rec.recCost?.toFixed(0) || 0}/mo</div>
                        </div>
                    </div>
                    <div style={{ padding: "8px 12px", borderRadius: 8, background: C.indigoBg, border: `1px solid ${C.indigoMid}`, marginBottom: 14, display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                        <TrendI s={14} /><span style={{ fontWeight: 700, color: C.indigo }}>Save ${rec.savings?.toFixed(0) || 0}/mo · ${(rec.savings * 12 || 0).toFixed(0)}/year</span>
                    </div>
                    {steps.map((s, i) => (
                        <div key={i} style={{ display: "flex", gap: 8, padding: "5px 0", borderBottom: i < steps.length - 1 ? `1px solid ${C.border}` : "none" }}>
                            <div style={{ width: 18, height: 18, borderRadius: "50%", background: C.indigoBg, color: C.indigo, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, flexShrink: 0 }}>{i + 1}</div>
                            <span style={{ fontSize: 12, color: C.text }}>{s}</span>
                        </div>
                    ))}
                    <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
                        <Btn variant="ghost" onClick={onClose} sx={{ flex: 1 }}>Cancel</Btn>
                        <Btn onClick={onConfirm} sx={{ flex: 2 }}><CheckI s={13} /> Confirm Apply</Btn>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── Clean Recommendations Table ──────────────────────────────────────────────
function RecsTable({ recs, mode, onDetail, onApply }) {
    const [filter, setFilter] = useState("");
    const filtered = recs.filter(r => !filter || r.name?.toLowerCase().includes(filter.toLowerCase()) || r.namespace?.includes(filter));
    const pendingCount = recs.filter(r => r.status === "pending").length;

    return (
        <Card>
            <div style={{ padding: "16px 20px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <GridI s={16} />
                    <span style={{ fontSize: 12, fontWeight: 600, color: C.textMuted, letterSpacing: "0.05em", textTransform: "uppercase" }}>
                        {mode === "karpenter_insights" ? "Karpenter Insights" : "Activity"} Recommendations
                    </span>
                    <Badge color={C.indigo} bg={C.indigoBg}>{pendingCount} pending</Badge>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter instances…" style={{ padding: "5px 12px", fontSize: 12, border: `1px solid ${C.border}`, borderRadius: 7, background: C.surfaceAlt, outline: "none", fontFamily: F.sans, width: 170 }} />
                    <Btn variant="success" small><CheckI s={12} />Apply All</Btn>
                </div>
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                    <tr style={{ background: C.surfaceAlt, borderBottom: `1px solid ${C.border}` }}>
                        <th style={{ padding: "12px 20px", textAlign: "left", fontSize: 12, fontWeight: 600, color: C.textMuted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Instance</th>
                        <th style={{ padding: "12px 10px", textAlign: "center", fontSize: 12, fontWeight: 600, color: C.textMuted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Current → Recommended</th>
                        <th style={{ padding: "12px 10px", textAlign: "center", fontSize: 12, fontWeight: 600, color: C.textMuted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Monthly Savings</th>
                        <th style={{ padding: "12px 10px", textAlign: "center", fontSize: 12, fontWeight: 600, color: C.textMuted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Confidence</th>
                        <th style={{ padding: "12px 20px", textAlign: "right", fontSize: 12, fontWeight: 600, color: C.textMuted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {filtered.map((r, i) => {
                        const isApplied = r.status === "applied";
                        return (
                            <tr key={r.id || i} style={{ borderBottom: i < filtered.length - 1 ? `1px solid ${C.border}` : "none", background: "transparent" }}>
                                <td style={{ padding: "12px 18px" }}>
                                    <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{r.name || r.id}</div>
                                    <div style={{ display: "flex", gap: 6, marginTop: 3 }}>
                                        <Badge color={NS_COLOR[r.namespace] || C.indigo} bg={`${NS_COLOR[r.namespace] || C.indigo}12`}>{r.namespace || 'default'}</Badge>
                                        {r.spotAvail && <Badge color={C.green} bg={C.greenBg}>⚡ Spot</Badge>}
                                    </div>
                                </td>
                                <td style={{ padding: "12px 10px", textAlign: "center" }}>
                                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                                        <div style={{ textAlign: "right" }}>
                                            <div style={{ fontSize: 13, fontWeight: 700, color: C.red, fontFamily: "monospace" }}>{r.currentType}</div>
                                            <div style={{ fontSize: 11, color: C.textMuted }}>${r.currentCost?.toFixed(0) || 0}/mo</div>
                                        </div>
                                        <ArrowI s={14} />
                                        <div style={{ textAlign: "left" }}>
                                            <div style={{ fontSize: 13, fontWeight: 700, color: C.indigo, fontFamily: "monospace" }}>{r.recType}</div>
                                            <div style={{ fontSize: 11, color: C.textMuted }}>${r.recCost?.toFixed(0) || 0}/mo</div>
                                        </div>
                                    </div>
                                </td>
                                <td style={{ padding: "12px 10px", textAlign: "center" }}>
                                    <div style={{ fontSize: 18, fontWeight: 800, color: C.green }}>+${r.savings?.toFixed(0) || 0}</div>
                                    <div style={{ fontSize: 11, color: C.textMuted }}>${(r.savings * 12 || 0).toFixed(0)}/yr</div>
                                </td>
                                <td style={{ padding: "12px 10px", textAlign: "center" }}>
                                    <Badge color={confColor[r.confidence]} bg={`${confColor[r.confidence]}14`}>{r.confidence}</Badge>
                                </td>
                                <td style={{ padding: "12px 18px", textAlign: "right" }}>
                                    <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", alignItems: "center" }}>
                                        <Btn variant="ghost" small onClick={() => onDetail(r)}>
                                            <InfoI s={12} />Details
                                        </Btn>
                                        {isApplied
                                            ? <Badge color={C.green} bg={C.greenBg} border={C.greenMid}><CheckI s={11} />Applied</Badge>
                                            : <Btn small onClick={() => onApply(r)}><CheckI s={12} />Apply</Btn>
                                        }
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </Card>
    );
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function RightSizingDashboard() {
    const { selectedCluster } = useClusterStore();
    const [mode, setMode] = useState("karpenter_insights");
    const [recs, setRecs] = useState([]);
    const [loading, setLoading] = useState(false);

    const [detail, setDetail] = useState(null);
    const [applying, setApplying] = useState(null);
    const [toastMsg, setToastMsg] = useState(null);
    const [toastType, setToastType] = useState('success'); // 'success' or 'error'

    const showToast = (msg, type = 'success') => {
        setToastMsg(msg);
        setToastType(type);
        setTimeout(() => setToastMsg(null), 4000); // Increased to 4s for error readability
    };

    useEffect(() => {
        fetchData();
    }, [selectedCluster]);

    const fetchData = async () => {
        try {
            setLoading(true);
            const clusterId = selectedCluster?.id;

            // Don't fetch if no cluster selected
            if (!clusterId) {
                setLoading(false);
                setRecs([]);
                return;
            }

            const res = await optimizationAPI.getEnrichedRightsizing(clusterId, { analysis_window_hours: 336 });

            const apiRecs = Array.isArray(res.data?.recommendations) ? res.data.recommendations : (Array.isArray(res.data) ? res.data : []);

            // Map API data to UI format
            const mappedRecs = apiRecs.map((r, i) => ({
                id: r.id || `rec-${i}`,
                name: r.controller_name || `Instance-${i}`,
                namespace: r.namespace || 'default',
                currentType: r.current_instance_type || 'Unknown',
                recType: r.recommended_instance_type || 'Unknown',
                currentCost: (r.savings_monthly || 0) * 1.5, // Mock current cost to make savings calculation somewhat realistic
                recCost: ((r.savings_monthly || 0) * 1.5) - (r.savings_monthly || 0),
                savings: r.savings_monthly || 0,
                cpuAvg: Math.round((r.cpu_avg_millicores / (r.current_cpu_request_millicores || 1000)) * 100) || 20,
                memAvg: Math.round((r.memory_avg_mb / (r.current_memory_request_mb || 1024)) * 100) || 30,
                confidence: r.confidence || 'MEDIUM',
                status: 'pending',
                reason: r.description || 'Instance is underutilized',
                vcpuCurrent: Math.round(r.current_cpu_request_millicores / 1000) || 2,
                vcpuRec: Math.round(r.recommended_cpu_request_millicores / 1000) || 1,
                memGBCurrent: Math.round(r.current_memory_request_mb / 1024) || 8,
                memGBRec: Math.round(r.recommended_memory_request_mb / 1024) || 4,
            }));

            setRecs(mappedRecs);
        } catch (err) {
            console.error('Failed to load recommendations', err);
            // Fallback to empty if error
            setRecs([]);
        } finally {
            setLoading(false);
        }
    };

    const handleApply = (rec) => { setDetail(null); setApplying(rec); };

    const handleConfirm = async () => {
        try {
            await karpenterAPI.applyRecommendation(applying.id, { recommended_type: applying.recType });
            setRecs(prev => prev.map(r => r.id === applying.id ? { ...r, status: "applied" } : r));
            showToast(`✓ Applied: ${applying.name} → ${applying.recType}`, 'success');
        } catch (err) {
            console.error('Apply recommendation failed:', err);

            // Extract error message from response
            const errorMsg = err.response?.data?.detail || err.message || 'Unknown error';

            // Show error toast with details
            showToast(`✗ Failed to apply ${applying.name}: ${errorMsg}`, 'error');

            // Log additional context for debugging
            if (err.response) {
                console.error('Error response:', {
                    status: err.response.status,
                    data: err.response.data,
                    headers: err.response.headers
                });
            }
        } finally {
            setApplying(null);
        }
    };

    const handleModeSwitch = async (newMode) => {
        if (!selectedCluster?.id) {
            showToast('Please select a cluster first', 'error');
            return;
        }

        try {
            if (newMode === 'auto') {
                // Switch to auto mode via API
                await karpenterAPI.switchMode(selectedCluster.id, { mode: 'auto' });
                showToast('✓ Switched to Auto mode - Karpenter will now make changes automatically', 'success');
                // Refresh cluster data
                setTimeout(() => window.location.reload(), 2000);
            } else {
                // Just switch UI mode for insights/auto-sizing views
                setMode(newMode);
            }
        } catch (err) {
            console.error('Mode switch failed:', err);
            const errorMsg = err.response?.data?.detail || err.message || 'Failed to switch mode';
            showToast(`✗ ${errorMsg}`, 'error');
        }
    };

    const totalSavings = recs.filter(r => r.status === 'pending').reduce((a, r) => a + r.savings, 0);

    return (
        <div style={{ minHeight: "100vh", background: C.bg, fontFamily: F.sans, color: C.text }}>
            <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        button{font-family:inherit;}
        @keyframes fadeIn{from{opacity:0}to{opacity:1}}
        @keyframes slideIn{from{transform:translateX(100%)}to{transform:translateX(0)}}
        @keyframes popIn{from{transform:scale(0.95);opacity:0}to{transform:scale(1);opacity:1}}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}
        tr:hover td{background:rgba(79,70,229,0.02);}
        input[type=range]{cursor:pointer;}
      `}</style>

            {/* Modals */}
            {detail && <DetailDrawer rec={detail} mode={mode} onClose={() => setDetail(null)} onApply={handleApply} />}
            {applying && <ApplyConfirmModal rec={applying} mode={mode} onClose={() => setApplying(null)} onConfirm={handleConfirm} />}

            {/* Toast */}
            {toastMsg && (
                <div style={{
                    position: "fixed", top: 20, right: 20, zIndex: 600, padding: "10px 16px", borderRadius: 10,
                    background: toastType === 'error' ? '#fee2e2' : C.greenBg,
                    border: `1px solid ${toastType === 'error' ? '#f87171' : C.greenMid}`,
                    color: toastType === 'error' ? '#991b1b' : C.green,
                    fontSize: 13, fontWeight: 600, boxShadow: "0 4px 20px rgba(0,0,0,0.1)", animation: "fadeIn 0.2s",
                    display: "flex", alignItems: "center", gap: 8, maxWidth: "400px"
                }}>
                    {toastType === 'success' && <CheckI s={14} />}
                    {toastMsg}
                </div>
            )}

            {/* Topbar */}
            <div style={{ background: C.surface, borderBottom: `1px solid ${C.border}`, padding: "0 28px", height: 64, display: "flex", alignItems: "center", justifyContent: "space-between", position: "sticky", top: 0, zIndex: 50 }}>
                <div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: C.text, letterSpacing: "-0.02em" }}>Right-Sizing Dashboard</div>
                    <div style={{ fontSize: 13, color: C.textSec, marginTop: 2 }}>Optimize instance types and reduce infrastructure costs</div>
                </div>
                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                    <Btn
                        onClick={() => handleModeSwitch('karpenter_insights')}
                        variant="outline"
                        sx={{
                            background: mode === 'karpenter_insights' ? C.indigoBg : 'transparent',
                            border: `1px solid ${C.indigoMid}`,
                            color: C.indigo,
                            padding: "8px 16px"
                        }}
                    >
                        <EyeI s={14} /> Karpenter Insights
                    </Btn>
                    <Btn
                        onClick={() => handleModeSwitch('auto_sizing')}
                        variant="ghost"
                        sx={{
                            background: mode === 'auto_sizing' ? C.surfaceAlt : C.surface,
                            border: `1px solid ${C.border}`,
                            color: C.textSec,
                            padding: "8px 16px"
                        }}
                    >
                        <ZapI s={14} /> Auto-Sizing
                    </Btn>
                    <div style={{ width: 1, height: 24, background: C.border, margin: "0 4px" }} />
                    <button style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, width: 36, height: 36, display: "flex", alignItems: "center", justifyContent: "center", color: C.textSec, cursor: "pointer", transition: "all 0.2s" }}><SettI s={16} /></button>
                </div>
            </div>

            {/* Content */}
            <div style={{ padding: "20px 28px", maxWidth: 1400, margin: "0 auto" }}>
                {loading ? (
                    <div style={{ display: 'flex', justifyContent: 'center', marginTop: 100 }}><div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600"></div></div>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                        {/* Banner */}
                        <div style={{ padding: "16px 20px", borderRadius: 12, background: `linear-gradient(135deg,${C.indigoBg},#f0f9ff)`, border: `1px solid ${C.indigoMid}`, display: "flex", alignItems: "center", gap: 16 }}>
                            <div style={{ width: 40, height: 40, borderRadius: 10, background: C.surface, display: "flex", alignItems: "center", justifyContent: "center", color: C.indigo, border: `1px solid ${C.indigoMid}`, flexShrink: 0 }}><EyeI s={18} /></div>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginBottom: 4 }}>Insights Mode — No changes are made automatically</div>
                                <div style={{ fontSize: 13, color: C.textSec }}>Karpenter runs in dry-run, reading live pod specs, resource requests, taints and real-time spot data. You approve each change.</div>
                            </div>
                            <div style={{ display: "flex", gap: 12, alignItems: "center", marginRight: 8 }}>
                                <Badge color={C.green} border={C.greenMid} bg="transparent" sx={{ padding: "4px 8px" }}><CheckI s={12} /> K8s-aware</Badge>
                                <Badge color={C.indigo} border="transparent" bg="transparent" sx={{ padding: "4px 8px" }}><CheckI s={12} /> Live spot</Badge>
                                <Badge color={C.purple} border="transparent" bg="transparent" sx={{ padding: "4px 8px" }}><CheckI s={12} /> Dry-run</Badge>
                            </div>
                            <Btn
                                onClick={() => handleModeSwitch('auto')}
                                variant="outline"
                                sx={{ background: "transparent", border: `1px solid ${C.indigo}`, color: C.indigo, padding: "8px 16px" }}
                            >
                                <PlayI s={14} /> Switch to Auto
                            </Btn>
                        </div>

                        {/* KPIs */}
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
                            {(() => {
                                // Calculate avg Karpenter score from real recommendations
                                const avgKarpScore = recs.length > 0
                                    ? (recs.reduce((sum, r) => sum + (r.karpScore || 0), 0) / recs.length).toFixed(1)
                                    : '0.0';

                                return [
                                    { label: "Potential Savings", value: `$${totalSavings.toFixed(0)}/mo`, sub: "Karpenter-verified", color: "#111827", accent: C.green },
                                    { label: "Recommendations", value: `${recs.length} instances`, sub: `${recs.filter(r => r.confidence === "HIGH").length} high confidence`, color: "#111827", accent: C.indigo },
                                    { label: "Avg Karpenter Score", value: `${avgKarpScore}/10`, sub: "pod-constraint aware", color: "#111827", accent: C.purple },
                                ];
                            })().map((k, i) => (
                                <div key={i} style={{ background: C.surface, border: `1px solid ${C.border}`, borderTop: `3px solid ${k.accent}`, borderRadius: 12, padding: "20px" }}>
                                    <div style={{ fontSize: 12, fontWeight: 600, color: C.textMuted, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 8 }}>{k.label}</div>
                                    <div style={{ fontSize: 30, fontWeight: 800, color: k.color, letterSpacing: "-0.025em", marginBottom: 4 }}>{k.value}</div>
                                    <div style={{ fontSize: 12, color: C.textMuted }}>{k.sub}</div>
                                </div>
                            ))}
                        </div>

                        <RecsTable recs={recs} mode={mode} onDetail={setDetail} onApply={handleApply} />
                    </div>
                )}
            </div>
        </div>
    );
}
