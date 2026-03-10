import React, { useState, useEffect, useMemo } from 'react';
import { hygieneAPI, accountsAPI } from '../../services/api';
import toast from 'react-hot-toast';

// Wizards
import RIWizard from './wizards/RIWizard';
import S3Wizard from './wizards/S3Wizard';
import RDSWizard from './wizards/RDSWizard';
import BulkTagWizard from './BulkTagWizard';

// Filter Panel
import FilterPanel from './layout/FilterPanel';
import SavingsGauge from './summary/SavingsGauge';


// ─── DESIGN TOKENS ────────────────────────────────────────────────────────────
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
  // Status colors — used on dots/bars/borders ONLY, not font color
  green: "#16a34a", greenBg: "#f0fdf4", greenBorder: "#bbf7d0",
  amber: "#b45309", amberBg: "#fffbeb", amberBorder: "#fde68a",
  red: "#dc2626", redBg: "#fef2f2", redBorder: "#fecaca",
  orange: "#c2410c", orangeBg: "#fff7ed", orangeBorder: "#fed7aa",
  blue: "#1d4ed8", blueBg: "#eff6ff", blueBorder: "#bfdbfe",
  purple: "#6d28d9", purpleBg: "#f5f3ff", purpleBorder: "#ddd6fe",
};

// --- STATUS META ---
const STATUS_META = {
  SAFE_TO_DELETE: { label: "Safe to Delete", dot: C.green, bg: C.greenBg, border: C.greenBorder },
  ORPHANED: { label: "Orphaned", dot: C.amber, bg: C.amberBg, border: C.amberBorder },
  STOPPED: { label: "Stopped", dot: C.blue, bg: C.blueBg, border: C.blueBorder },
  RISK: { label: "Risk", dot: C.red, bg: C.redBg, border: C.redBorder },
  UNAUTHORIZED: { label: "Unauthorized", dot: C.purple, bg: C.purpleBg, border: C.purpleBorder },
  NOT_COMPLIANT: { label: "Not Compliant", dot: C.orange, bg: C.orangeBg, border: C.orangeBorder },
};

// ─── TINY COMPONENTS ─────────────────────────────────────────────────────────
const StatusPill = ({ status }) => {
  const m = STATUS_META[status];
  if (!m) return null;
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "2px 8px", borderRadius: 5,
      background: m.bg, border: `1px solid ${m.border}`,
      fontSize: 10.5, fontWeight: 500, color: C.muted,
    }}>
      <div style={{ width: 5, height: 5, borderRadius: "50%", background: m.dot, flexShrink: 0 }} />
      {m.label}
    </div>
  );
};

const SectionLabel = ({ children }) => (
  <div style={{
    fontSize: 9.5, fontWeight: 700, letterSpacing: "0.1em",
    textTransform: "uppercase", color: C.subtle,
    marginBottom: 8, paddingBottom: 6,
    borderBottom: `1px solid ${C.border}`,
  }}>{children}</div>
);

const KpiCard = ({ label, value, sub, accentColor, accentBg, accentBorder, right }) => (
  <div style={{
    background: C.surface, border: `1px solid ${accentBorder || C.border}`,
    borderRadius: 11, padding: "14px 16px",
    display: "flex", flexDirection: "column", justifyContent: "space-between",
    borderLeft: `3px solid ${accentColor || C.border}`,
  }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
      <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 500, marginBottom: 6 }}>{label}</div>
      {right}
    </div>
    <div style={{ fontSize: 22, fontWeight: 800, color: C.text, letterSpacing: "-0.5px", lineHeight: 1 }}>{value}</div>
    {sub && <div style={{ fontSize: 11, color: C.subtle, marginTop: 4 }}>{sub}</div>}
  </div>
);

const Checkbox = ({ checked, onChange, indeterminate }) => (
  <div
    onClick={onChange}
    style={{
      width: 15, height: 15, borderRadius: 4, flexShrink: 0,
      border: `1.5px solid ${checked ? C.accent : C.border}`,
      background: checked ? C.accent : "#fff",
      display: "flex", alignItems: "center", justifyContent: "center",
      cursor: "pointer", transition: "all 0.12s",
    }}
  >
    {(checked || indeterminate) && (
      <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
        {indeterminate && !checked
          ? <line x1="1.5" y1="3.5" x2="7.5" y2="3.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          : <polyline points="1,3.5 3.5,6 8,1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        }
      </svg>
    )}
  </div>
);

// ─── SIDEBAR ─────────────────────────────────────────────────────────────────
const Sidebar = ({ activeType, onSelect, categories }) => {
  const [expanded, setExpanded] = useState(
    Object.fromEntries(categories.map(c => [c.id, c.expanded]))
  );

  const totalCost = categories.flatMap(c => c.types).reduce((s, t) => s + t.cost, 0);

  return (
    <div style={{
      width: 220, flexShrink: 0,
      borderRight: `1px solid ${C.border}`,
      background: "#fafafa",
      display: "flex", flexDirection: "column",
      overflowY: "auto",
    }}>
      {/* Header */}
      <div style={{ padding: "14px 14px 10px", borderBottom: `1px solid ${C.border}` }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: C.subtle, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
          Resources
        </div>
        <div style={{ fontSize: 11, color: C.muted }}>
          Total discovered: <strong style={{ color: C.text, fontWeight: 700 }}>${totalCost}/mo</strong>
        </div>
      </div>

      {/* Category list */}
      <div style={{ flex: 1, padding: "8px 8px 12px" }}>
        {categories.map(cat => {
          const isOpen = expanded[cat.id];
          const catCost = cat.types.reduce((s, t) => s + t.cost, 0);
          const catCount = cat.types.reduce((s, t) => s + t.count, 0);
          return (
            <div key={cat.id} style={{ marginBottom: 4 }}>
              {/* Category header */}
              <button
                onClick={() => setExpanded(e => ({ ...e, [cat.id]: !e[cat.id] }))}
                style={{
                  width: "100%", display: "flex", alignItems: "center",
                  padding: "6px 8px", borderRadius: 7,
                  border: "none", background: "transparent",
                  cursor: "pointer", fontFamily: "inherit",
                  gap: 6,
                }}
                onMouseEnter={e => e.currentTarget.style.background = "#f0f0f3"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
              >
                <span style={{
                  fontSize: 9, fontWeight: 700, letterSpacing: "0.08em",
                  textTransform: "uppercase", color: C.subtle, flex: 1, textAlign: "left",
                }}>{cat.label}</span>
                <span style={{ fontSize: 10, color: C.subtle }}>{catCount}</span>
                <svg
                  width="10" height="10" viewBox="0 0 10 10" fill="none"
                  style={{ transform: isOpen ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.15s", flexShrink: 0 }}
                >
                  <polyline points="3,2 7,5 3,8" stroke={C.subtle} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {/* Resource types */}
              {isOpen && (
                <div style={{ paddingLeft: 4, marginTop: 2 }}>
                  {cat.types.map(t => {
                    const isActive = activeType === t.id;
                    return (
                      <button
                        key={t.id}
                        onClick={() => onSelect(t.id)}
                        style={{
                          width: "100%", display: "flex", alignItems: "center",
                          padding: "5px 10px 5px 12px", borderRadius: 7, marginBottom: 1,
                          border: `1.5px solid ${isActive ? C.accent : "transparent"}`,
                          background: isActive ? C.accentLight : "transparent",
                          cursor: "pointer", fontFamily: "inherit", gap: 6,
                          transition: "all 0.12s",
                        }}
                        onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = "#ededf0"; } }}
                        onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = "transparent"; } }}
                      >
                        <span style={{
                          fontSize: 12, flex: 1, textAlign: "left",
                          color: isActive ? C.accent : C.muted,
                          fontWeight: isActive ? 600 : 400,
                        }}>{t.label}</span>
                        {t.count > 0 && (
                          <span style={{
                            fontSize: 10, fontWeight: 600,
                            color: isActive ? C.accent : C.subtle,
                            background: isActive ? C.accent + "18" : "#ebebee",
                            padding: "1px 5px", borderRadius: 4,
                          }}>{t.count}</span>
                        )}
                        {t.cost > 0 && (
                          <span style={{ fontSize: 9, color: C.subtle }}>${t.cost}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ─── RESOURCE TABLE ───────────────────────────────────────────────────────────
const ResourceTable = ({ resources, selected, onSelect, onSelectAll }) => {
  const allSelected = resources.length > 0 && resources.every(r => selected.has(r.id));
  const someSelected = resources.some(r => selected.has(r.id)) && !allSelected;

  const cols = [
    { key: "check", w: 36, label: "" },
    { key: "name", w: "2fr", label: "Resource" },
    { key: "type", w: "1fr", label: "Type" },
    { key: "region", w: 100, label: "Region" },
    { key: "status", w: 140, label: "Status" },
    { key: "tags", w: 80, label: "Tags" },
    { key: "cost", w: 90, label: "Cost/mo" },
    { key: "reason", w: "1.5fr", label: "Reason" },
    { key: "actions", w: 130, label: "" },
  ];

  const gridTemplate = cols.map(c => typeof c.w === "number" ? `${c.w}px` : c.w).join(" ");

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Table header */}
      <div style={{
        display: "grid", gridTemplateColumns: gridTemplate,
        padding: "0 16px",
        borderBottom: `1px solid ${C.border}`,
        background: "#f8f8fa",
        alignItems: "center",
        minHeight: 36,
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <Checkbox
            checked={allSelected}
            indeterminate={someSelected}
            onChange={() => onSelectAll(allSelected ? [] : resources.map(r => r.id))}
          />
        </div>
        {cols.slice(1).map(col => (
          <div key={col.key} style={{
            fontSize: 10, fontWeight: 700, color: C.subtle,
            letterSpacing: "0.07em", textTransform: "uppercase",
            padding: "0 6px",
          }}>{col.label}</div>
        ))}
      </div>

      {/* Table body */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {resources.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 10 }}>
            <div style={{ fontSize: 32, opacity: 0.15 }}>✓</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: C.muted }}>No issues found</div>
            <div style={{ fontSize: 12, color: C.subtle }}>Your infrastructure looks clean for this category.</div>
          </div>
        ) : resources.map((r, i) => {
          const isSelected = selected.has(r.id);
          return (
            <div
              key={r.id}
              style={{
                display: "grid", gridTemplateColumns: gridTemplate,
                padding: "0 16px",
                borderBottom: `1px solid ${i === resources.length - 1 ? "transparent" : C.border}`,
                background: isSelected ? C.accentLight : i % 2 === 0 ? C.surface : "#fafafa",
                alignItems: "center",
                minHeight: 46,
                transition: "background 0.1s",
              }}
              onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = "#f5f6f8"; }}
              onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = i % 2 === 0 ? C.surface : "#fafafa"; }}
            >
              {/* Checkbox */}
              <div style={{ display: "flex", alignItems: "center" }}>
                <Checkbox checked={isSelected} onChange={() => onSelect(r.id)} />
              </div>

              {/* Resource name + id */}
              <div style={{ padding: "0 6px" }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.text, marginBottom: 1 }}>
                  {r.name !== "-" ? r.name : <span style={{ color: C.subtle }}>—</span>}
                  {r.authorized && (
                    <span style={{
                      marginLeft: 6, fontSize: 9, fontWeight: 600,
                      color: C.green, background: C.greenBg,
                      border: `1px solid ${C.greenBorder}`,
                      padding: "1px 5px", borderRadius: 3,
                    }}>Authorized</span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: C.subtle, fontFamily: "monospace" }}>{r.id}</div>
              </div>

              {/* Type */}
              <div style={{ padding: "0 6px" }}>
                <span style={{
                  fontSize: 10.5, color: C.muted,
                  background: "#f0f1f3", padding: "2px 7px", borderRadius: 4,
                }}>{r.type}</span>
              </div>

              {/* Region */}
              <div style={{ padding: "0 6px", fontSize: 11, color: C.muted }}>{r.region}</div>

              {/* Status */}
              <div style={{ padding: "0 6px" }}>
                <StatusPill status={r.status} />
              </div>

              {/* Tags */}
              <div style={{ padding: "0 6px" }}>
                {r.missingTags.length > 0 ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <div style={{ width: 5, height: 5, borderRadius: "50%", background: C.amber }} />
                    <span style={{ fontSize: 10, color: C.muted }}>{r.missingTags.length} missing</span>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <div style={{ width: 5, height: 5, borderRadius: "50%", background: C.green }} />
                    <span style={{ fontSize: 10, color: C.muted }}>Complete</span>
                  </div>
                )}
              </div>

              {/* Cost */}
              <div style={{ padding: "0 6px", fontSize: 12, fontWeight: r.cost > 50 ? 700 : 400, color: C.text }}>
                {r.cost > 0 ? `$${r.cost}` : <span style={{ color: C.subtle }}>—</span>}
              </div>

              {/* Reason */}
              <div style={{ padding: "0 6px", fontSize: 11, color: C.muted, lineHeight: 1.4 }}>{r.reason}</div>

              {/* Actions */}
              <div style={{ padding: "0 6px", display: "flex", gap: 4 }}>
                {!r.authorized ? (
                  <button style={{
                    padding: "3px 9px", borderRadius: 6, fontSize: 10.5, fontWeight: 500,
                    border: `1px solid ${C.border}`, background: C.surface,
                    color: C.muted, cursor: "pointer", fontFamily: "inherit",
                    transition: "all 0.12s",
                  }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = C.green; e.currentTarget.style.color = C.green; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.color = C.muted; }}
                  >Authorize</button>
                ) : (
                  <button style={{
                    padding: "3px 9px", borderRadius: 6, fontSize: 10.5, fontWeight: 500,
                    border: `1px solid ${C.border}`, background: C.surface,
                    color: C.muted, cursor: "pointer", fontFamily: "inherit",
                  }}>Unauthorize</button>
                )}
                {(r.status === "SAFE_TO_DELETE" && !r.authorized) && (
                  <button style={{
                    padding: "3px 9px", borderRadius: 6, fontSize: 10.5, fontWeight: 500,
                    border: `1px solid ${C.redBorder}`, background: C.redBg,
                    color: C.red, cursor: "pointer", fontFamily: "inherit",
                    transition: "all 0.12s",
                  }}
                    onMouseEnter={e => { e.currentTarget.style.background = C.red; e.currentTarget.style.color = "#fff"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = C.redBg; e.currentTarget.style.color = C.red; }}
                  >Delete</button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

function AnimatedNum({ target, duration = 900 }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    let start = null;
    const step = (ts) => {
      if (!start) start = ts;
      const pct = Math.min((ts - start) / duration, 1);
      const ease = 1 - Math.pow(1 - pct, 3);
      setVal(Math.round(ease * target));
      if (pct < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target]);
  return <>{val.toLocaleString()}</>;
}

function RingGauge({ pct, size = 60, stroke = 5, color }) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const dash = ((isNaN(pct) ? 0 : pct) / 100) * circ;
  return (
    <svg width={size} height={size} style={{ display: "block", flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f3f4f6" strokeWidth={stroke} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth={stroke}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dasharray 1s cubic-bezier(.4,0,.2,1)" }}
      />
      <text x={size / 2} y={size / 2 + 4.5} textAnchor="middle"
        style={{ fontSize: 12, fontWeight: 700, fill: C.text, fontFamily: "inherit" }}>
        {pct}%
      </text>
    </svg>
  );
}

function SparkBars({ values }) {
  const max = Math.max(...values, 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 24, opacity: 0.7 }}>
      {values.map((v, i) => (
        <div key={i} style={{
          width: 4, borderRadius: "2px 2px 0 0",
          height: `${Math.max((v / max) * 100, 10)}%`,
          background: i === values.length - 1 ? C.text : "#d1d5db",
        }} />
      ))}
    </div>
  );
}

// ─── MAIN PAGE ────────────────────────────────────────────────────────────────
export default function CleanupDashboard() {

  const [activeType, setActiveType] = useState("instance");
  const [selected, setSelected] = useState(new Set());
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch] = useState("");






  // -- API State --
  const [loading, setLoading] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [selectedRegion, setSelectedRegion] = useState('ALL');
  const [scanResult, setScanResult] = useState(null);
  const [scanHistory, setScanHistory] = useState([]);

  const [totalCost, setTotalCost] = useState(null);
  const [totalCostLoading, setTotalCostLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // -- Wizards --
  const [showRIWizard, setShowRIWizard] = useState(false);
  const [showS3Wizard, setShowS3Wizard] = useState(false);
  const [showRDSWizard, setShowRDSWizard] = useState(false);
  const [showBulkTagWizard, setShowBulkTagWizard] = useState(false);

  const regionsList = [
    { id: 'ALL', name: 'All Regions (Global)' },
    { id: 'us-east-1', name: 'US East (N. Virginia)' },
    { id: 'us-east-2', name: 'US East (Ohio)' },
    { id: 'us-west-1', name: 'US West (N. California)' },
    { id: 'us-west-2', name: 'US West (Oregon)' },
    { id: 'eu-west-1', name: 'Europe (Ireland)' },
    { id: 'eu-central-1', name: 'Europe (Frankfurt)' },
    { id: 'ap-south-1', name: 'Asia Pacific (Mumbai)' },
    { id: 'ap-northeast-1', name: 'Asia Pacific (Tokyo)' },
    { id: 'ap-southeast-1', name: 'Asia Pacific (Singapore)' },
    { id: 'ap-southeast-2', name: 'Asia Pacific (Sydney)' },
    { id: 'sa-east-1', name: 'South America (São Paulo)' },
  ];

  // -- Effects --
  useEffect(() => {
    fetchAccounts();
    fetchTotalCost();
  }, []);

  useEffect(() => {
    if (selectedAccount) {
      handleScan(false);
      fetchTotalCost();
    }
  }, [selectedAccount, selectedRegion]);

  // -- API Calls --
  const fetchAccounts = async () => {
    try {
      const res = await accountsAPI.list();
      setAccounts(res.data);
      if (res.data.length > 0) setSelectedAccount(res.data[0].id);
    } catch (err) { console.error("Failed to load accounts", err); }
  };

  const handleScan = async (forceRefresh = false) => {
    if (!selectedAccount) return;
    setLoading(true);
    try {
      const [res, historyRes] = await Promise.all([
        hygieneAPI.scan(selectedAccount, {
          regions: selectedRegion === 'ALL' ? ['ALL'] : [selectedRegion],
          force_refresh: forceRefresh
        }),
        hygieneAPI.getScanHistory(selectedAccount)
      ]);
      setScanResult(res.data);
      setScanHistory(historyRes.data || []);
      setSelected(new Set());
      if (forceRefresh) {
        toast.success("Scan refreshed successfully");
        fetchTotalCost();
      }
    } catch (err) {
      console.error("Scan failed", err);
      if (!scanResult) setScanResult(null);
      if (!scanHistory.length) setScanHistory([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchTotalCost = async () => {
    setTotalCostLoading(true);
    try {
      const res = await hygieneAPI.getTotalCost(selectedAccount || undefined);
      setTotalCost(res.data);
    } catch (err) {
      console.error("Failed to fetch total cost", err);
      setTotalCost(null);
    } finally {
      setTotalCostLoading(false);
    }
  };

  const handleAction = async (actionType) => {
    if (selected.size === 0) return;
    // fix_A1: group by resource.region so we never send 'global' to backend
    const regionGroups = {};
    for (const obj of selectedResourceObjects) {
      const rgn = obj.region || (selectedRegion !== 'ALL' ? selectedRegion : null);
      if (!rgn) continue;
      if (!regionGroups[rgn]) regionGroups[rgn] = [];
      regionGroups[rgn].push(obj.id);
    }
    if (Object.keys(regionGroups).length === 0) {
      toast.error('Cannot determine region for selected resources. Filter by a specific region first.');
      return;
    }
    setActionLoading(true);
    try {
      const results = await Promise.all(
        Object.entries(regionGroups).map(([rgn, ids]) =>
          hygieneAPI.execute({ action_type: actionType, resource_ids: ids, region: rgn }, selectedAccount)
            .then(res => ({ ok: true, data: res.data, rgn, ids }))
            .catch(err => ({ ok: false, error: err, rgn, ids }))
        )
      );
      // fix_A2 (HYGIENE-TOAST-01): status-aware toasts instead of optimistic success
      let successCount = 0, skippedCount = 0, approvalIds = [], errors = [];
      for (const r of results) {
        if (!r.ok) { errors.push(r.error?.response?.data?.detail || `Error in ${r.rgn}`); continue; }
        const d = r.data;
        // fix_A5: 202 pending_approval now includes approval_id
        if (d.status === 'pending_approval') approvalIds.push(d.approval_id || d.message);
        else if (d.skipped) skippedCount++;
        else successCount++;
      }
      if (approvalIds.length) toast(`Approval required — ticket created`, { icon: 'ℹ️' });
      if (skippedCount) toast(`${skippedCount} resource(s) already gone — skipped`, { icon: '⚠️' });
      if (successCount) toast.success(`${actionType} applied to ${successCount} resource(s)`);
      if (errors.length) toast.error(errors[0]);
      if (!errors.length) { handleScan(true); setSelected(new Set()); }
    } catch (e) {
      toast.error(`Failed to execute ${actionType}`);
    } finally {
      setActionLoading(false);
    }
  };

  // Convert API resources to flat list for table UI
  const rawResources = scanResult?.resources || [];

  // Transform API data to match frontend requirements
  const allResources = useMemo(() => {
    return rawResources.map(r => ({
      ...r,
      id: r.id,
      name: r.name || '-',
      type: r.type,
      region: r.region,
      status: r.status,
      cost: r.cost_per_month || 0,
      authorized: r.is_authorized,
      reason: r.reason || '',
      tags: r.metadata?.tags ? Object.keys(r.metadata.tags).length : 0,
      missingTags: r.missing_tags || []
    }));
  }, [rawResources]);

  const filteredResources = useMemo(() => {
    return allResources.filter(r => {
      // Filter by active type mapped from Sidebar to API ResourceType
      const typeMap = {
        'instance': 'INSTANCE',
        'reserved': 'RI_WASTE',
        'eks': 'EKS_CLUSTER',
        'ecs': 'ECS_CLUSTER',
        'asg': 'AUTO_SCALING_GROUP',
        'volume': 'VOLUME',
        'snapshot': 'SNAPSHOT',
        's3': 'S3_BUCKET',
        's3lc': 'S3_LIFECYCLE',
        'efs': 'EFS_FILE_SYSTEM',
        'eip': 'ELASTIC_IP',
        'lb': 'LOAD_BALANCER',
        'nat': 'NAT_GATEWAY',
        'eni': 'NETWORK_INTERFACE',
        'rds': 'RDS_DB',
        'dynamo': 'DYNAMODB_TABLE',
        'elastic': 'ELASTICACHE_CLUSTER',
        'kms': 'KMS_KEY',
        'secrets': 'SECRETS_MANAGER',
        'cwlg': 'CLOUDWATCH_LOG_GROUP',
        'cwa': 'CLOUDWATCH_ALARM',
        'lambda': 'LAMBDA_FUNCTION',
        'eb': 'EVENTBRIDGE_RULE',
        'iam': 'IAM_USER',
        'iamkey': 'IAM_KEY'
      };
      if (typeMap[activeType] && r.type !== typeMap[activeType]) return false;

      if (statusFilter !== "ALL" && r.status !== statusFilter) return false;
      if (search && !r.name.toLowerCase().includes(search.toLowerCase()) &&
        !r.id.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [allResources, statusFilter, search, activeType]);

  const handleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleSelectAll = (ids) => {
    setSelected(new Set(ids));
  };

  const selectedCount = selected.size;
  const selectedCost = filteredResources.filter(r => selected.has(r.id)).reduce((s, r) => s + r.cost, 0);
  const selectedResourceObjects = allResources.filter(r => selected.has(r.id));

  const STATUS_FILTERS = [
    { key: "ALL", label: "All" },
    { key: "SAFE_TO_DELETE", label: "Safe to Delete" },
    { key: "ORPHANED", label: "Orphaned" },
    { key: "STOPPED", label: "Stopped" },
    { key: "RISK", label: "Risk" },
    { key: "NOT_COMPLIANT", label: "Not Compliant" },
  ];

  // Aggregate KPIs based on API data
  // Use scan result's total_discovered_cost (sum of cost_per_month across ALL resources found)
  // This matches the sidebar total and is the authoritative figure from the hygiene scan.
  const TOTAL_DISCOVERED = scanResult?.summary?.total_discovered_cost
    ? Number(scanResult.summary.total_discovered_cost.toFixed(2))
    : Number(allResources.reduce((s, r) => s + (r.cost || 0), 0).toFixed(2));
  const TOTAL_POTENTIAL = scanResult?.summary?.total_potential_savings ? Number(scanResult.summary.total_potential_savings.toFixed(2)) : 0;
  const UNTAGGED = allResources.filter(r => r.missingTags.length > 0).length;
  const TAG_HEALTH_PCT = allResources.length > 0 ? Math.round((1 - UNTAGGED / allResources.length) * 100) : 100;
  const SAFETY_SAFE = allResources.filter(r => r.status === "SAFE_TO_DELETE" || r.status === "STOPPED").length;
  const SAFETY_REVIEW = allResources.filter(r => r.status === "ORPHANED" || r.status === "NOT_COMPLIANT").length;
  const SAFETY_RISKY = allResources.filter(r => r.status === "RISK" || r.status === "UNAUTHORIZED").length;

  const SIDEBAR_CATEGORIES = [
    {
      id: "compute", label: "Compute", expanded: true,
      types: [
        { id: "instance", label: "Instances", count: allResources.filter(r => r.type === "INSTANCE").length, cost: allResources.filter(r => r.type === "INSTANCE").reduce((s, r) => s + r.cost, 0) },
        { id: "reserved", label: "Reserved Instances", count: allResources.filter(r => r.type === "RI_WASTE").length, cost: allResources.filter(r => r.type === "RI_WASTE").reduce((s, r) => s + r.cost, 0) },
        { id: "eks", label: "EKS Clusters", count: allResources.filter(r => r.type === "EKS_CLUSTER").length, cost: allResources.filter(r => r.type === "EKS_CLUSTER").reduce((s, r) => s + r.cost, 0) },
        { id: "ecs", label: "ECS Clusters", count: allResources.filter(r => r.type === "ECS_CLUSTER").length, cost: allResources.filter(r => r.type === "ECS_CLUSTER").reduce((s, r) => s + r.cost, 0) },
        { id: "asg", label: "Auto Scaling Groups", count: allResources.filter(r => r.type === "AUTO_SCALING_GROUP").length, cost: allResources.filter(r => r.type === "AUTO_SCALING_GROUP").reduce((s, r) => s + r.cost, 0) },
      ],
    },
    {
      id: "storage", label: "Storage", expanded: true,
      types: [
        { id: "volume", label: "EBS Volumes", count: allResources.filter(r => r.type === "VOLUME").length, cost: allResources.filter(r => r.type === "VOLUME").reduce((s, r) => s + r.cost, 0) },
        { id: "snapshot", label: "Snapshots", count: allResources.filter(r => r.type === "SNAPSHOT").length, cost: allResources.filter(r => r.type === "SNAPSHOT").reduce((s, r) => s + r.cost, 0) },
        { id: "s3", label: "S3 Buckets", count: allResources.filter(r => r.type === "S3_BUCKET").length, cost: allResources.filter(r => r.type === "S3_BUCKET").reduce((s, r) => s + r.cost, 0) },
        { id: "s3lc", label: "S3 Lifecycle", count: allResources.filter(r => r.type === "S3_LIFECYCLE").length, cost: allResources.filter(r => r.type === "S3_LIFECYCLE").reduce((s, r) => s + r.cost, 0) },
        { id: "efs", label: "EFS File Systems", count: allResources.filter(r => r.type === "EFS_FILE_SYSTEM").length, cost: allResources.filter(r => r.type === "EFS_FILE_SYSTEM").reduce((s, r) => s + r.cost, 0) },
      ],
    },
    {
      id: "network", label: "Network", expanded: false,
      types: [
        { id: "eip", label: "Elastic IPs", count: allResources.filter(r => r.type === "ELASTIC_IP").length, cost: allResources.filter(r => r.type === "ELASTIC_IP").reduce((s, r) => s + r.cost, 0) },
        { id: "lb", label: "Load Balancers", count: allResources.filter(r => r.type === "LOAD_BALANCER").length, cost: allResources.filter(r => r.type === "LOAD_BALANCER").reduce((s, r) => s + r.cost, 0) },
        { id: "nat", label: "NAT Gateways", count: allResources.filter(r => r.type === "NAT_GATEWAY").length, cost: allResources.filter(r => r.type === "NAT_GATEWAY").reduce((s, r) => s + r.cost, 0) },
        { id: "eni", label: "Network Interfaces", count: allResources.filter(r => r.type === "NETWORK_INTERFACE").length, cost: allResources.filter(r => r.type === "NETWORK_INTERFACE").reduce((s, r) => s + r.cost, 0) },
      ],
    },
    {
      id: "database", label: "Databases", expanded: false,
      types: [
        { id: "rds", label: "RDS Instances", count: allResources.filter(r => r.type === "RDS_DB").length, cost: allResources.filter(r => r.type === "RDS_DB").reduce((s, r) => s + r.cost, 0) },
        { id: "dynamo", label: "DynamoDB Tables", count: allResources.filter(r => r.type === "DYNAMODB_TABLE").length, cost: allResources.filter(r => r.type === "DYNAMODB_TABLE").reduce((s, r) => s + r.cost, 0) },
        { id: "elastic", label: "ElastiCache", count: allResources.filter(r => r.type === "ELASTICACHE_CLUSTER").length, cost: allResources.filter(r => r.type === "ELASTICACHE_CLUSTER").reduce((s, r) => s + r.cost, 0) },
      ],
    },
    {
      id: "security", label: "Security", expanded: false,
      types: [
        { id: "kms", label: "KMS Keys", count: allResources.filter(r => r.type === "KMS_KEY").length, cost: allResources.filter(r => r.type === "KMS_KEY").reduce((s, r) => s + r.cost, 0) },
        { id: "secrets", label: "Secrets Manager", count: allResources.filter(r => r.type === "SECRETS_MANAGER").length, cost: allResources.filter(r => r.type === "SECRETS_MANAGER").reduce((s, r) => s + r.cost, 0) },
      ],
    },
    {
      id: "mgmt", label: "Management", expanded: false,
      types: [
        { id: "cwlg", label: "CW Log Groups", count: allResources.filter(r => r.type === "CLOUDWATCH_LOG_GROUP").length, cost: allResources.filter(r => r.type === "CLOUDWATCH_LOG_GROUP").reduce((s, r) => s + r.cost, 0) },
        { id: "cwa", label: "CW Alarms", count: allResources.filter(r => r.type === "CLOUDWATCH_ALARM").length, cost: allResources.filter(r => r.type === "CLOUDWATCH_ALARM").reduce((s, r) => s + r.cost, 0) },
        { id: "lambda", label: "Lambda Functions", count: allResources.filter(r => r.type === "LAMBDA_FUNCTION").length, cost: allResources.filter(r => r.type === "LAMBDA_FUNCTION").reduce((s, r) => s + r.cost, 0) },
        { id: "eb", label: "EventBridge Rules", count: allResources.filter(r => r.type === "EVENTBRIDGE_RULE").length, cost: allResources.filter(r => r.type === "EVENTBRIDGE_RULE").reduce((s, r) => s + r.cost, 0) },
      ],
    },
    {
      id: "identity", label: "Identity", expanded: false,
      types: [
        { id: "iam", label: "IAM Users", count: allResources.filter(r => r.type === "IAM_USER").length, cost: allResources.filter(r => r.type === "IAM_USER").reduce((s, r) => s + r.cost, 0) },
        { id: "iamkey", label: "IAM Keys", count: allResources.filter(r => r.type === "IAM_KEY").length, cost: allResources.filter(r => r.type === "IAM_KEY").reduce((s, r) => s + r.cost, 0) },
      ],
    },
  ];

  const cardStyle = {
    background: C.surface,
    border: `1px solid ${C.border}`,
    borderRadius: 12,
    overflow: "hidden",
  };

  const labelStyle = {
    fontSize: 10.5,
    fontWeight: 600,
    color: C.subtle,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    marginBottom: 10,
  };

  const valueStyle = {
    fontSize: 26,
    fontWeight: 800,
    letterSpacing: "-0.8px",
    color: C.text,
    lineHeight: 1,
  };

  const sparkbarValues = scanHistory && scanHistory.length > 0
    ? scanHistory.map(h => h.resources_discovered || 0).reverse()
    : [0, 0, 0, 0, 0, 0, TOTAL_DISCOVERED]; // Empty state padding with current reading

  return (
    <div style={{
      minHeight: "100vh", background: C.bg,
      fontFamily: "'DM Sans', system-ui, sans-serif",
      color: C.text, display: "flex", flexDirection: "column",
    }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Replace the hardcoded topbar UI with FilterPanel */}
      <div style={{ position: "sticky", top: 0, zIndex: 20 }}>
        <FilterPanel
          accounts={accounts}
          selectedAccount={selectedAccount}
          onAccountChange={setSelectedAccount}
          selectedRegion={selectedRegion}
          onRegionChange={setSelectedRegion}
          regionsList={regionsList}
          onRefresh={() => handleScan(true)}
          loading={loading}
          lastScan={scanResult?.metadata?.scan_time}
        />
      </div>

      {/* ── KPI STRIP ── */}
      <div style={{ padding: "16px 24px 0", display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1.1fr", gap: 10 }}>

        {/* ── 1. Total Discovered Cost ── */}
        <div style={cardStyle}>
          <div style={{ padding: "16px 18px" }}>
            <div style={labelStyle}>Total Discovered Cost</div>
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
              <div>
                <div style={valueStyle}>
                  $<AnimatedNum target={TOTAL_DISCOVERED} /><span style={{ fontSize: 14, fontWeight: 500, color: C.muted }}>/mo</span>
                </div>
                <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 5 }}>
                  <div style={{ width: 5, height: 5, borderRadius: "50%", background: C.blue }} />
                  <span style={{ fontSize: 11, color: C.muted }}>{allResources.length} resources found</span>
                </div>
              </div>
              <SparkBars values={sparkbarValues} />
            </div>
          </div>
        </div>

        {/* ── 2. Potential Savings ── */}
        <div style={cardStyle}>
          <div style={{ padding: "16px 18px" }}>
            <div style={labelStyle}>Potential Savings</div>
            <div style={valueStyle}>
              $<AnimatedNum target={TOTAL_POTENTIAL} /><span style={{ fontSize: 14, fontWeight: 500, color: C.muted }}>/mo</span>
            </div>
            <div style={{ marginTop: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                <span style={{ fontSize: 11, color: C.muted }}>{TOTAL_DISCOVERED > 0 ? Math.round((TOTAL_POTENTIAL / TOTAL_DISCOVERED) * 100) : 0}% of total cost recoverable</span>
                <span style={{ fontSize: 11, color: C.muted }}>{SAFETY_SAFE} deletable</span>
              </div>
              <div style={{ height: 4, background: "#f3f4f6", borderRadius: 2 }}>
                <div style={{
                  width: `${TOTAL_DISCOVERED > 0 ? Math.round((TOTAL_POTENTIAL / TOTAL_DISCOVERED) * 100) : 0}%`, height: 4,
                  background: C.green,
                  borderRadius: 2,
                  transition: "width 1.2s cubic-bezier(.4,0,.2,1)",
                }} />
              </div>
            </div>
          </div>
        </div>

        {/* ── 3. Tag Health ── */}
        <div style={cardStyle}>
          <div style={{ padding: "16px 18px" }}>
            <div style={labelStyle}>Tag Health</div>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <RingGauge pct={TAG_HEALTH_PCT} size={58} stroke={5} color={TAG_HEALTH_PCT > 80 ? C.green : C.amber} />
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                  {TAG_HEALTH_PCT === 100 ? "Healthy" : "Needs Attention"}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <div style={{ width: 5, height: 5, borderRadius: "50%", background: C.amber }} />
                    <span style={{ fontSize: 11, color: C.muted }}>{UNTAGGED} untagged</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <div style={{ width: 5, height: 5, borderRadius: "50%", background: C.subtle }} />
                    <span style={{ fontSize: 11, color: C.muted }}>{allResources.length - UNTAGGED} tagged</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── 4. Safety Analysis ── */}
        <div style={cardStyle}>
          <div style={{ padding: "16px 18px" }}>
            <div style={labelStyle}>Safety Analysis</div>
            <div style={{ display: "flex" }}>
              {[
                { label: "Safe", value: SAFETY_SAFE, color: C.green, desc: "No action" },
                { label: "Review", value: SAFETY_REVIEW, color: C.amber, desc: "Check needed" },
                { label: "Risky", value: SAFETY_RISKY, color: C.red, desc: "Act now" },
              ].map((s, i) => (
                <div key={s.label} style={{
                  flex: 1,
                  paddingRight: i < 2 ? 14 : 0,
                  marginRight: i < 2 ? 14 : 0,
                  borderRight: i < 2 ? `1px solid ${C.border}` : "none",
                }}>
                  <div style={{ fontSize: 24, fontWeight: 800, color: C.text, letterSpacing: "-0.5px", lineHeight: 1, marginBottom: 5 }}>
                    <AnimatedNum target={s.value} duration={700 + i * 100} />
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 2 }}>
                    <div style={{ width: 5, height: 5, borderRadius: "50%", background: s.color }} />
                    <span style={{ fontSize: 11, fontWeight: 500, color: C.muted }}>{s.label}</span>
                  </div>
                  <div style={{ fontSize: 10, color: C.subtle }}>{s.desc}</div>
                </div>
              ))}
            </div>
            {/* Proportion bar */}
            <div style={{ marginTop: 12, display: "flex", height: 3, borderRadius: 2, overflow: "hidden", gap: 1.5 }}>
              {[
                { pct: allResources.length > 0 ? (SAFETY_SAFE / allResources.length) * 100 : 50, c: C.green },
                { pct: allResources.length > 0 ? (SAFETY_REVIEW / allResources.length) * 100 : 33, c: C.amber },
                { pct: allResources.length > 0 ? (SAFETY_RISKY / allResources.length) * 100 : 17, c: C.red }
              ].map((b, i) => (
                b.pct > 0 && <div key={i} style={{ width: `${b.pct}%`, height: 3, background: b.c, borderRadius: 2 }} />
              ))}
            </div>
          </div>
        </div>

      </div>

      {/* ── MAIN CONTENT: Sidebar + Table ── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", margin: "14px 24px 24px", gap: 12, minHeight: 0 }}>

        {/* Sidebar */}
        <div style={{
          background: C.surface, borderRadius: 12,
          border: `1px solid ${C.border}`,
          overflow: "hidden", flexShrink: 0,
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        }}>
          <Sidebar activeType={activeType} onSelect={setActiveType} categories={SIDEBAR_CATEGORIES} />
        </div>

        {/* Main panel */}
        <div style={{
          flex: 1, background: C.surface,
          borderRadius: 12, border: `1px solid ${C.border}`,
          display: "flex", flexDirection: "column",
          overflow: "hidden",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        }}>

          {/* Panel header */}
          <div style={{
            padding: "14px 16px", borderBottom: `1px solid ${C.border}`,
            display: "flex", alignItems: "center", gap: 10, flexShrink: 0,
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginBottom: 2 }}>Compute Instances</div>
              <div style={{ fontSize: 11, color: C.subtle }}>Review and action logical resources.</div>
            </div>
            {/* Status filter tabs */}
            <div style={{ display: "flex", gap: 3, background: "#f3f4f6", padding: 3, borderRadius: 9 }}>
              {STATUS_FILTERS.map(f => (
                <button
                  key={f.key}
                  onClick={() => setStatusFilter(f.key)}
                  style={{
                    padding: "4px 10px", borderRadius: 6, fontSize: 11,
                    border: "none",
                    background: statusFilter === f.key ? C.surface : "transparent",
                    color: statusFilter === f.key ? C.text : C.muted,
                    fontWeight: statusFilter === f.key ? 600 : 400,
                    cursor: "pointer", fontFamily: "inherit",
                    boxShadow: statusFilter === f.key ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                    transition: "all 0.12s",
                  }}
                >{f.label}</button>
              ))}
            </div>
          </div>

          {/* Bulk action bar — shown when rows selected */}
          {selectedCount > 0 && (
            <div style={{
              padding: "8px 16px", borderBottom: `1px solid ${C.border}`,
              background: C.accentLight,
              display: "flex", alignItems: "center", gap: 10, flexShrink: 0,
            }}>
              <span style={{ fontSize: 12, color: C.accent, fontWeight: 600 }}>
                {selectedCount} resource{selectedCount !== 1 ? "s" : ""} selected
                {selectedCost > 0 && ` · $${selectedCost}/mo`}
              </span>
              <div style={{ flex: 1 }} />
              {[
                {
                  label: "Authorize",
                  color: C.green,
                  onClick: () => handleAction('AUTHORIZE')
                },
                {
                  label: "Unauthorize",
                  color: C.muted,
                  onClick: () => handleAction('UNAUTHORIZE')
                },
                {
                  label: "Tag",
                  color: C.accent,
                  onClick: () => setShowBulkTagWizard(true)
                },
                {
                  label: "Cleanup",
                  color: C.red,
                  onClick: () => handleAction('TERMINATE')
                },
              ].map(a => (
                <button key={a.label} onClick={actionLoading ? undefined : a.onClick} disabled={actionLoading} style={{
                  padding: "5px 12px", borderRadius: 7,
                  border: `1px solid ${a.color}30`,
                  background: a.color === C.red ? C.redBg : C.surface,
                  color: a.color, fontSize: 11.5, fontWeight: 500,
                  cursor: actionLoading ? "not-allowed" : "pointer", fontFamily: "inherit",
                  transition: "all 0.12s", opacity: actionLoading ? 0.6 : 1,
                  display: "flex", alignItems: "center", gap: 5,
                }}
                  onMouseEnter={e => { if (!actionLoading) { e.currentTarget.style.background = a.color; e.currentTarget.style.color = "#fff"; } }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = a.color === C.red ? C.redBg : C.surface;
                    e.currentTarget.style.color = a.color;
                  }}
                >
                  {actionLoading && (
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" style={{ animation: "spin 0.8s linear infinite" }}>
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="31.4 31.4" />
                    </svg>
                  )}
                  {a.label}
                </button>
              ))}
              <button
                onClick={() => setSelected(new Set())}
                style={{
                  padding: "5px 10px", borderRadius: 7,
                  border: `1px solid ${C.border}`, background: C.surface,
                  color: C.muted, fontSize: 11, cursor: "pointer", fontFamily: "inherit",
                }}
              >✕ Clear</button>
            </div>
          )}

          {/* Search bar */}
          <div style={{ padding: "10px 16px", borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8,
              background: "#f8f8fa", border: `1px solid ${C.border}`,
              borderRadius: 8, padding: "6px 10px",
            }}>
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <circle cx="6.5" cy="6.5" r="5" stroke={C.subtle} strokeWidth="1.4" />
                <path d="M10.5 10.5L14 14" stroke={C.subtle} strokeWidth="1.4" strokeLinecap="round" />
              </svg>
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search by resource name or ID…"
                style={{
                  border: "none", outline: "none", background: "transparent",
                  fontSize: 12, color: C.text, width: "100%", fontFamily: "inherit",
                }}
              />
              {search && (
                <button onClick={() => setSearch("")} style={{ border: "none", background: "none", cursor: "pointer", color: C.subtle, padding: 0, fontSize: 14, lineHeight: 1 }}>✕</button>
              )}
              <span style={{ fontSize: 10, color: C.subtle, flexShrink: 0 }}>{filteredResources.length} results</span>
            </div>
          </div>

          {/* Table */}
          <ResourceTable
            resources={filteredResources}
            selected={selected}
            onSelect={handleSelect}
            onSelectAll={handleSelectAll}
          />

          {/* Footer: status legend */}
          <div style={{
            padding: "8px 16px", borderTop: `1px solid ${C.border}`,
            display: "flex", gap: 14, alignItems: "center", flexShrink: 0, background: "#fafafa",
          }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: C.subtle, letterSpacing: "0.07em", textTransform: "uppercase" }}>Status</span>
            {Object.entries(STATUS_META).map(([key, m]) => (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: m.dot }} />
                <span style={{ fontSize: 10, color: C.muted }}>{m.label}</span>
              </div>
            ))}
            <div style={{ flex: 1 }} />
            <span style={{ fontSize: 10, color: C.subtle }}>
              Showing {filteredResources.length} of {allResources.length} resources
            </span>
          </div>
        </div>
      </div>

      <RIWizard
        isOpen={showRIWizard}
        onClose={() => setShowRIWizard(false)}
        selectedResources={selectedResourceObjects}
      />
      <S3Wizard
        isOpen={showS3Wizard}
        onClose={() => setShowS3Wizard(false)}
        selectedResources={selectedResourceObjects}
      />
      <RDSWizard
        isOpen={showRDSWizard}
        onClose={() => setShowRDSWizard(false)}
        selectedResources={selectedResourceObjects}
      />
      {showBulkTagWizard && (
        <BulkTagWizard
          isOpen={showBulkTagWizard}
          onClose={() => setShowBulkTagWizard(false)}
          selectedResources={selectedResourceObjects}
          onComplete={() => handleScan(true)}
          accountId={selectedAccount}
          regionId={selectedRegion}
        />
      )}
    </div>
  );
}