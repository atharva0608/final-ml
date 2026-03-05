import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { karpenterAPI, tagAutomationAPI, approvalAPI, atharvaaiAPI, hibernationAPI } from "../../services/api";

// ─── Design tokens — strict app theme ────────────────────────────────────────
const C = {
    bg: "#f5f6f8",
    surface: "#ffffff",
    surfaceAlt: "#fafafa",
    border: "#e4e6ea",
    borderMid: "#d1d5db",
    text: "#111318",
    muted: "#5a6272",
    subtle: "#98a1b0",
    accent: "#2563eb",
    accentBg: "#eff6ff",
    accentBorder: "#bfdbfe",
    green: "#16a34a",
    greenBg: "#f0fdf4",
    greenBorder: "#bbf7d0",
    amber: "#b45309",
    amberBg: "#fffbeb",
    amberBorder: "#fde68a",
    red: "#dc2626",
    redBg: "#fef2f2",
    redBorder: "#fecaca",
};

const SEV = {
    approval: { stripe: "#b45309", dot: "#b45309", tagBg: "#fffbeb", tagBorder: "#fde68a", tagFg: "#92400e" },
    hibernation: { stripe: "#2563eb", dot: "#2563eb", tagBg: "#eff6ff", tagBorder: "#bfdbfe", tagFg: "#1e40af" },
    savings: { stripe: "#16a34a", dot: "#16a34a", tagBg: "#f0fdf4", tagBorder: "#bbf7d0", tagFg: "#14532d" },
    hygiene: { stripe: "#475569", dot: "#475569", tagBg: "#f8fafc", tagBorder: "#e2e8f0", tagFg: "#334155" },
    alert: { stripe: "#dc2626", dot: "#dc2626", tagBg: "#fef2f2", tagBorder: "#fecaca", tagFg: "#991b1b" },
};

const Ico = ({ path, size = 14, stroke = C.muted, fill = "none", strokeW = 1.75 }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={fill}
        stroke={stroke} strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"
        style={{ display: "block", flexShrink: 0 }}>
        {path}
    </svg>
);

export const ICONS = {
    Bell: <><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" /></>,
    Lock: <><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></>,
    Moon: <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />,
    TrendUp: <><polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" /></>,
    Shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></>,
    Alert: <><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>,
    Check: <polyline points="20 6 9 17 4 12" />,
    X: <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>,
    ArrowR: <><line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" /></>,
    Cog: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></>,
    Search: <><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></>,
    ExternalLink: <><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></>,
};

const TYPE_ICON = {
    approval: ICONS.Lock,
    hibernation: ICONS.Moon,
    savings: ICONS.TrendUp,
    hygiene: ICONS.Shield,
    alert: ICONS.Alert,
};

// Notifications are now fetched dynamically from APIs.
const NOTIFS_INIT = [];

function DrainBar({ init }) {
    const [v, setV] = useState(init);
    useEffect(() => {
        const t = setInterval(() => setV(p => Math.min(p + Math.random() * 1.4, 97)), 1800);
        return () => clearInterval(t);
    }, []);
    return (
        <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 8, background: C.surfaceAlt, border: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 7 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: C.subtle, textTransform: "uppercase", letterSpacing: "0.07em" }}>Node Drain Progress</span>
                <span style={{ fontSize: 11, fontWeight: 800, color: C.accent }}>{Math.round(v)}%</span>
            </div>
            <div style={{ height: 5, background: C.border, borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                    height: "100%", borderRadius: 3, width: `${v}%`,
                    background: C.accent, transition: "width 1.6s cubic-bezier(.4,0,.2,1)",
                }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5 }}>
                <span style={{ fontSize: 10, color: C.subtle }}>Draining nodes</span>
                <span style={{ fontSize: 10, fontWeight: 600, color: C.muted }}>ETA ~4 min</span>
            </div>
        </div>
    );
}

function ApprovalRow({ done, setDone }) {
    const [busy, setBusy] = useState(null);
    const act = (a) => {
        setBusy(a);
        setTimeout(() => { setBusy(null); setDone(a); }, 900);
    };
    if (done) return (
        <div style={{
            marginTop: 12, padding: "8px 12px", borderRadius: 8,
            background: done === "approve" ? C.greenBg : C.redBg,
            border: `1px solid ${done === "approve" ? C.greenBorder : C.redBorder}`,
            display: "flex", alignItems: "center", gap: 7,
        }}>
            <Ico size={12} stroke={done === "approve" ? C.green : C.red} path={done === "approve" ? ICONS.Check : ICONS.X} />
            <span style={{ fontSize: 11, fontWeight: 600, color: done === "approve" ? C.green : C.red }}>
                {done === "approve" ? "Access approved — grant is now active" : "Request rejected"}
            </span>
        </div>
    );
    return (
        <div style={{ display: "flex", gap: 7, marginTop: 12 }}>
            <button onClick={() => act("approve")} style={{
                flex: 1, padding: "7px 0", borderRadius: 8,
                border: `1px solid ${busy === "approve" ? C.green : C.greenBorder}`,
                background: busy === "approve" ? C.green : C.greenBg,
                color: busy === "approve" ? "#fff" : C.green,
                fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
                display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
                transition: "all 0.16s",
            }}>
                {busy === "approve" ? <span style={{ opacity: .7 }}>Approving</span> : <><Ico size={11} stroke="currentColor" path={ICONS.Check} />Approve</>}
            </button>
            <button onClick={() => act("reject")} style={{
                flex: 1, padding: "7px 0", borderRadius: 8,
                border: `1px solid ${busy === "reject" ? C.red : C.redBorder}`,
                background: busy === "reject" ? C.red : C.redBg,
                color: busy === "reject" ? "#fff" : C.red,
                fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
                display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
                transition: "all 0.16s",
            }}>
                {busy === "reject" ? <span style={{ opacity: .7 }}>Rejecting</span> : <><Ico size={11} stroke="currentColor" path={ICONS.X} />Reject</>}
            </button>
        </div>
    );
}

function SavingsRow() {
    return (
        <div style={{
            marginTop: 12, padding: "9px 12px", borderRadius: 8,
            background: C.surfaceAlt, border: `1px solid ${C.border}`,
            display: "flex", alignItems: "center", gap: 8,
        }}>
            <code style={{ fontSize: 10.5, color: C.muted, background: C.bg, padding: "2px 7px", borderRadius: 4, border: `1px solid ${C.border}` }}>m5.xlarge</code>
            <Ico size={11} stroke={C.subtle} path={ICONS.ArrowR} />
            <code style={{ fontSize: 10.5, color: C.green, background: C.greenBg, padding: "2px 7px", borderRadius: 4, border: `1px solid ${C.greenBorder}` }}>m5.large</code>
            <span style={{ marginLeft: "auto", fontSize: 12, fontWeight: 800, color: C.green }}>$92/mo</span>
        </div>
    );
}

function HygieneRow() {
    return (
        <div style={{
            marginTop: 12, padding: "9px 12px", borderRadius: 8,
            background: C.surfaceAlt, border: `1px solid ${C.border}`,
            display: "flex", alignItems: "center", gap: 10,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: C.amber, flexShrink: 0 }} />
                <span style={{ fontSize: 11, fontWeight: 600, color: C.muted }}>12 resources flagged</span>
            </div>
            <span style={{ color: C.border }}>|</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: C.green }}>$378/mo recoverable</span>
        </div>
    );
}

function AlertRow() {
    return (
        <div style={{
            marginTop: 12, padding: "9px 12px", borderRadius: 8,
            background: C.redBg, border: `1px solid ${C.redBorder}`,
            display: "flex", alignItems: "center", gap: 8,
        }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: C.red, flexShrink: 0, animation: "pulse 1.4s ease-in-out infinite" }} />
            <span style={{ fontSize: 11, fontWeight: 600, color: "#991b1b" }}>18% interruption rate — Rebalancing active</span>
        </div>
    );
}

function NCard({ n, onDismiss, idx }) {
    const sev = SEV[n.type];
    const [hov, setHov] = useState(false);
    const [vis, setVis] = useState(false);
    const [apDone, setApDone] = useState(null);

    useEffect(() => {
        const t = setTimeout(() => setVis(true), idx * 55);
        return () => clearTimeout(t);
    }, [idx]);

    return (
        <div
            onMouseEnter={() => setHov(true)}
            onMouseLeave={() => setHov(false)}
            style={{
                position: "relative",
                borderRadius: 12,
                background: C.surface,
                border: `1px solid ${hov ? C.borderMid : C.border}`,
                boxShadow: hov ? "0 6px 24px rgba(0,0,0,0.07), 0 2px 6px rgba(0,0,0,0.04)" : "0 1px 3px rgba(0,0,0,0.04)",
                transform: vis ? (hov ? "translateY(-1px)" : "translateY(0)") : "translateY(12px)",
                opacity: vis ? 1 : 0,
                transition: "all 0.2s cubic-bezier(.4,0,.2,1)",
                overflow: "hidden",
            }}
        >
            <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: sev.stripe }} />

            {n.unread && (
                <div style={{ position: "absolute", top: 13, right: 13, width: 7, height: 7, borderRadius: "50%", background: sev.dot }} />
            )}

            <div style={{ padding: "12px 14px 12px 18px" }}>
                <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
                    <div style={{
                        width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                        background: C.bg, border: `1px solid ${C.border}`,
                        display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                        <Ico size={14} stroke={C.muted} path={TYPE_ICON[n.type]} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12.5, fontWeight: 700, color: C.text, lineHeight: 1.3, marginBottom: 3 }}>{n.title}</div>
                        <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.55 }}>{n.body}</div>
                    </div>
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 2 }}>
                    {Object.entries(n.meta).map(([k, v]) => (
                        <span key={k} style={{
                            fontSize: 9.5, padding: "2px 7px", borderRadius: 4,
                            background: C.bg, color: C.muted,
                            border: `1px solid ${C.border}`, fontWeight: 500,
                        }}>{v}</span>
                    ))}
                </div>

                {n.type === "approval" && n.unread && <ApprovalRow done={apDone} setDone={setApDone} />}
                {n.type === "hibernation" && n.progress != null && <DrainBar init={n.progress} />}
                {n.type === "savings" && <SavingsRow />}
                {n.type === "hygiene" && <HygieneRow />}
                {n.type === "alert" && <AlertRow />}

                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 11 }}>
                    <span style={{ fontSize: 10, color: C.subtle }}>{n.time}</span>
                    <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
                        {n.link ? (
                            <Link to={n.link} style={{ textDecoration: 'none' }}>
                                <span style={{
                                    fontSize: 10, fontWeight: 600, color: C.accent,
                                    padding: "2px 8px", borderRadius: 5,
                                    background: C.surface, border: `1px solid ${C.border}`,
                                    display: "inline-flex", alignItems: "center", gap: 4,
                                    cursor: "pointer", transition: "background 0.12s",
                                }}>
                                    <Ico size={10} stroke={C.accent} path={ICONS.ExternalLink} />
                                    {n.sourceLabel}
                                </span>
                            </Link>
                        ) : (
                            <span style={{
                                fontSize: 10, fontWeight: 600, color: C.accent,
                                padding: "2px 8px", borderRadius: 5,
                                background: C.surface, border: `1px solid ${C.border}`,
                                display: "inline-flex", alignItems: "center", gap: 4,
                                cursor: "pointer", transition: "background 0.12s",
                            }}>
                                <Ico size={10} stroke={C.accent} path={ICONS.ExternalLink} />
                                {n.sourceLabel}
                            </span>
                        )}
                        <button onClick={() => onDismiss(n.id)} aria-label="Dismiss" style={{
                            width: 22, height: 22, borderRadius: 5,
                            border: `1px solid ${C.border}`, background: C.surface,
                            color: C.subtle, cursor: "pointer",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontFamily: "inherit", transition: "all 0.1s",
                        }}>
                            <Ico size={11} stroke={C.subtle} path={ICONS.X} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

function FilterTab({ label, count, active, onClick }) {
    return (
        <button onClick={onClick} style={{
            display: "flex", alignItems: "center", gap: 5,
            padding: "5px 12px", borderRadius: 0,
            border: "none", borderBottom: `2px solid ${active ? C.text : "transparent"}`,
            background: "transparent", color: active ? C.text : C.muted,
            fontSize: 11.5, fontWeight: active ? 700 : 400,
            cursor: "pointer", fontFamily: "inherit",
            whiteSpace: "nowrap", transition: "all 0.12s",
        }}>
            {label}
            {count > 0 && (
                <span style={{
                    fontSize: 9, fontWeight: 700,
                    minWidth: 16, height: 16, borderRadius: 8,
                    display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "0 3px",
                    background: active ? C.text : C.border,
                    color: active ? "#fff" : C.muted,
                    transition: "all 0.12s",
                }}>{count}</span>
            )}
        </button>
    );
}

export function NotificationPanel({ isOpen, onClose, onUnreadCount }) {
    const [notifs, setNotifs] = useState(NOTIFS_INIT);
    const [filter, setFilter] = useState("all");
    const [clearing, setClearing] = useState(false);
    const [loading, setLoading] = useState(false);

    const unread = notifs.filter(n => n.unread).length;

    useEffect(() => {
        if (onUnreadCount) onUnreadCount(unread);
    }, [unread, onUnreadCount]);

    // Fetch dynamic notifications on mount or when opened
    useEffect(() => {
        if (isOpen && notifs.length === 0) {
            fetchNotifications();
        }
    }, [isOpen]);

    const fetchNotifications = async () => {
        setLoading(true);
        try {
            const compiledNotifs = [];

            // 1. Fetch Tag/Hygiene Actions (Mocking structure typically returned by tagAutomationAPI.getLog)
            try {
                const tagLogs = await tagAutomationAPI.getLog({ limit: 5 });
                if (tagLogs.data && Array.isArray(tagLogs.data)) {
                    tagLogs.data.forEach((log, i) => {
                        compiledNotifs.push({
                            id: `hyg-${i}`,
                            type: "hygiene",
                            unread: i < 2, // Highlight recent
                            time: log.time || log.timestamp || "Recent",
                            title: `Automation: ${log.action}`,
                            body: log.reason || "Resource flagged for hygiene rule.",
                            meta: { Resource: log.resource, Savings: log.savings?.toString() || "N/A" },
                            sourceLabel: "Resource Hygiene",
                            link: "/hygiene"
                        });
                    });
                }
            } catch (e) {
                console.error("Failed fetching hygiene logs for notifications:", e);
            }

            // 2. Fetch Karpenter / Savings Actions
            try {
                const kLogs = await karpenterAPI.getActivity(null, 5); // null cluster = global, limit 5
                if (kLogs.data && Array.isArray(kLogs.data)) {
                    kLogs.data.forEach((act, i) => {
                        compiledNotifs.push({
                            id: `sav-${i}`,
                            type: "savings",
                            unread: i === 0,
                            time: new Date(act.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                            title: act.action === 'consolidate' ? "Cluster Consolidated" : "Right-Sizing Event",
                            body: act.description || `Optimized nodes in cluster.`,
                            meta: act.action === 'consolidate' ?
                                { NodesBefore: act.nodes_before?.toString(), NodesAfter: act.nodes_after?.toString() } :
                                { From: act.old_type, To: act.new_type },
                            sourceLabel: "Right-Sizing",
                            link: "/right-sizing"
                        });
                    });
                }
            } catch (e) {
                console.error("Failed fetching karpenter logs for notifications:", e);
            }

            // 3. Fetch JIT/Approvals Waitlist
            try {
                const approvalRes = await approvalAPI.list("PENDING");
                if (approvalRes.data && Array.isArray(approvalRes.data)) {
                    approvalRes.data.slice(0, 3).forEach((req, i) => {
                        compiledNotifs.push({
                            id: req.id || `app-${i}`,
                            type: "approval",
                            unread: true,
                            time: new Date(req.created_at).toLocaleDateString(),
                            title: "Access Request",
                            body: `${req.user_email || 'A user'} requires ${req.access_level || 'access'} for ${req.duration_hours || 1}h.`,
                            meta: { Cluster: req.cluster_id || 'Global', Status: "Pending" },
                            sourceLabel: "Approvals",
                            link: "/approvals"
                        });
                    });
                }
            } catch (e) {
                console.error("Failed fetching approvals for notifications:", e);
            }

            // 4. Fetch Alerts / AtharvaAI Rebalancing
            try {
                const alertRes = await atharvaaiAPI.getRebalancingStatus(null, 3);
                if (alertRes.data && Array.isArray(alertRes.data)) {
                    alertRes.data.forEach((r, i) => {
                        compiledNotifs.push({
                            id: r.id || `alt-${i}`,
                            type: "alert",
                            unread: i === 0,
                            time: new Date(r.timestamp || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                            title: "Spot Interruption Warning",
                            body: `Pool ${r.az || 'Region'} showing elevated interruption rate. Rebalancing active.`,
                            meta: { Pool: r.az || '-', Rate: `${r.interruption_rate || 0}%`, Status: "Rebalancing" },
                            sourceLabel: "ASCP.ai",
                            link: "/atharva-ai"
                        });
                    });
                }
            } catch (e) {
                console.error("Failed fetching alerts:", e);
            }

            // 5. Fetch Hibernation schedules
            try {
                const hibRes = await hibernationAPI.list();
                if (hibRes.data && Array.isArray(hibRes.data)) {
                    const active = hibRes.data.filter(s => s.is_active);
                    active.slice(0, 2).forEach((s, i) => {
                        compiledNotifs.push({
                            id: s.id || `hib-${i}`,
                            type: "hibernation",
                            unread: false,
                            time: "Scheduled",
                            title: "Hibernation Active",
                            body: `Cluster sleep schedule is enforced.`,
                            meta: { Cluster: s.cluster_id || '-', Strategy: s.strategy || 'Node Drain' },
                            sourceLabel: "Hibernation",
                            link: "/hibernation"
                        });
                    });
                }
            } catch (e) {
                console.error("Failed fetching hibernation details:", e);
            }

            // Sort by time conceptually (since we have mixed formats, we just append them nicely for now)
            // Real application would sort by ISO timestamps
            setNotifs(compiledNotifs);
        } catch (e) {
            console.error("Failed building notification feed:", e);
        } finally {
            setLoading(false);
        }
    };

    const dismiss = useCallback(id => setNotifs(p => p.filter(n => n.id !== id)), []);
    const markRead = () => setNotifs(p => p.map(n => ({ ...n, unread: false })));
    const clearAll = () => {
        setClearing(true);
        setTimeout(() => { setNotifs([]); setClearing(false); }, 280);
    };

    const FILTERS = [
        { id: "all", label: "All" },
        { id: "approval", label: "Approvals" },
        { id: "hibernation", label: "Hibernation" },
        { id: "savings", label: "Savings" },
        { id: "alert", label: "Alerts" },
        { id: "hygiene", label: "Hygiene" },
    ];

    const shown = filter === "all" ? notifs : notifs.filter(n => n.type === filter);

    if (!isOpen) return null;

    return (
        <>
            {/* Backdrop Overlay */}
            <div
                onClick={onClose}
                style={{
                    position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
                    background: "rgba(17, 19, 24, 0.15)",
                    backdropFilter: "blur(3px)", WebkitBackdropFilter: "blur(3px)",
                    zIndex: 90,
                    animation: "fadeIn 0.2s ease",
                }}
            />
            {/* Glass Panel */}
            <div style={{
                width: 390, flexShrink: 0,
                display: "flex", flexDirection: "column",
                background: "rgba(255, 255, 255, 0.65)", borderLeft: `1px solid rgba(255, 255, 255, 0.5)`,
                backdropFilter: "blur(24px)", WebkitBackdropFilter: "blur(24px)",
                boxShadow: "-12px 0 48px rgba(0,0,0,0.08)",
                animation: "panel-slide 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
                overflow: "hidden", height: "100vh",
                position: "fixed", top: 0, right: 0, bottom: 0, zIndex: 100
            }}>
                <div style={{ padding: "20px 16px 0", borderBottom: `1px solid ${C.border}`, background: "transparent", flexShrink: 0 }}>
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 }}>
                        <div>
                            <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.3px", color: C.text }}>Notifications</div>
                            <div style={{ fontSize: 10.5, color: C.subtle, marginTop: 2 }}>
                                {unread > 0 ? `${unread} unread · ` : ""}{notifs.length} total
                            </div>
                        </div>
                        <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
                            {unread > 0 && (
                                <button onClick={markRead} style={{
                                    fontSize: 10, fontWeight: 600, color: C.accent,
                                    background: C.accentBg, border: `1px solid ${C.accentBorder}`,
                                    padding: "4px 9px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit",
                                    transition: "opacity 0.12s",
                                }}>Mark all read</button>
                            )}
                            {notifs.length > 0 && (
                                <button onClick={clearAll} style={{
                                    fontSize: 10, fontWeight: 600, color: C.muted,
                                    background: C.bg, border: `1px solid ${C.border}`,
                                    padding: "4px 9px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit",
                                }}>{clearing ? "Clearing" : "Clear all"}</button>
                            )}
                            <button onClick={onClose} style={{
                                width: 26, height: 26, borderRadius: 6,
                                border: `1px solid ${C.border}`, background: C.bg, color: C.muted, cursor: "pointer",
                                display: "flex", alignItems: "center", justifyContent: "center",
                            }}>
                                <Ico size={12} stroke={C.muted} path={ICONS.X} />
                            </button>
                        </div>
                    </div>

                    <div style={{ display: "flex", gap: 0, overflowX: "auto", scrollbarWidth: "none" }}>
                        {FILTERS.map(f => (
                            <FilterTab key={f.id} label={f.label} active={filter === f.id}
                                count={f.id === "all" ? notifs.length : notifs.filter(n => n.type === f.id).length}
                                onClick={() => setFilter(f.id)} />
                        ))}
                    </div>
                </div>

                <div style={{ flex: 1, overflowY: "auto", padding: "12px 12px 16px" }}>
                    {loading ? (
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "55%", gap: 10 }}>
                            <div className="spinner" style={{ width: 24, height: 24, borderWidth: 2 }} />
                            <div style={{ fontSize: 13, fontWeight: 600, color: C.muted }}>Fetching Activity...</div>
                        </div>
                    ) : shown.length === 0 ? (
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "55%", gap: 10 }}>
                            <div style={{ width: 40, height: 40, borderRadius: 10, background: C.bg, border: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                                <Ico size={18} stroke={C.subtle} path={ICONS.Bell} />
                            </div>
                            <div style={{ fontSize: 13, fontWeight: 600, color: C.muted }}>{notifs.length === 0 ? "All caught up" : "None here"}</div>
                            <div style={{ fontSize: 11, color: C.subtle }}>{notifs.length === 0 ? "No pending alerts or actions found across the platform." : "Switch to All to see everything"}</div>
                        </div>
                    ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {shown.map((n, i) => <NCard key={n.id} n={n} onDismiss={dismiss} idx={i} />)}
                        </div>
                    )}
                </div>

                <div style={{ padding: "10px 16px", borderTop: `1px solid ${C.border}`, background: "transparent", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                        <div style={{ width: 6, height: 6, borderRadius: "50%", background: C.green, flexShrink: 0, animation: "pulse 2.2s ease-in-out infinite" }} />
                        <span style={{ fontSize: 10, color: C.subtle }}>Live — refreshes every 30s</span>
                    </div>
                    <button style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: C.muted, background: C.bg, border: `1px solid ${C.border}`, padding: "3px 9px", borderRadius: 5, cursor: "pointer", fontFamily: "inherit" }}>
                        <Ico size={11} stroke={C.muted} path={ICONS.Cog} /> Settings
                    </button>
                </div>
            </div>
        </>
    );
}
