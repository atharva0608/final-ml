import { useState, useMemo } from "react";

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
  green: "#16a34a",   greenBg: "#f0fdf4",  greenBorder: "#bbf7d0",
  amber: "#b45309",   amberBg: "#fffbeb",  amberBorder: "#fde68a",
  red: "#dc2626",     redBg: "#fef2f2",    redBorder: "#fecaca",
  orange: "#c2410c",  orangeBg: "#fff7ed", orangeBorder: "#fed7aa",
  blue: "#1d4ed8",    blueBg: "#eff6ff",   blueBorder: "#bfdbfe",
  purple: "#6d28d9",  purpleBg: "#f5f3ff", purpleBorder: "#ddd6fe",
};

// ─── MOCK DATA ────────────────────────────────────────────────────────────────
const STATUS_META = {
  SAFE_TO_DELETE: { label: "Safe to Delete", dot: C.green,  bg: C.greenBg,  border: C.greenBorder },
  ORPHANED:       { label: "Orphaned",        dot: C.amber,  bg: C.amberBg,  border: C.amberBorder },
  STOPPED:        { label: "Stopped",         dot: C.blue,   bg: C.blueBg,   border: C.blueBorder  },
  RISK:           { label: "Risk",            dot: C.red,    bg: C.redBg,    border: C.redBorder   },
  UNAUTHORIZED:   { label: "Unauthorized",    dot: C.purple, bg: C.purpleBg, border: C.purpleBorder},
  NOT_COMPLIANT:  { label: "Not Compliant",   dot: C.orange, bg: C.orangeBg, border: C.orangeBorder},
};

const SIDEBAR_CATEGORIES = [
  {
    id: "compute", label: "Compute", expanded: true,
    types: [
      { id: "instance",  label: "Instances",          count: 8,  cost: 142 },
      { id: "reserved",  label: "Reserved Instances",  count: 2,  cost: 0   },
      { id: "eks",       label: "EKS Clusters",        count: 1,  cost: 38  },
      { id: "ecs",       label: "ECS Clusters",        count: 2,  cost: 12  },
      { id: "asg",       label: "Auto Scaling Groups", count: 3,  cost: 0   },
    ],
  },
  {
    id: "storage", label: "Storage", expanded: true,
    types: [
      { id: "volume",    label: "EBS Volumes",         count: 14, cost: 89  },
      { id: "snapshot",  label: "Snapshots",           count: 31, cost: 44  },
      { id: "s3",        label: "S3 Buckets",          count: 6,  cost: 22  },
      { id: "s3lc",      label: "S3 Lifecycle",        count: 3,  cost: 0   },
      { id: "efs",       label: "EFS File Systems",    count: 2,  cost: 18  },
    ],
  },
  {
    id: "network", label: "Network", expanded: false,
    types: [
      { id: "eip",       label: "Elastic IPs",         count: 5,  cost: 18  },
      { id: "lb",        label: "Load Balancers",       count: 2,  cost: 32  },
      { id: "nat",       label: "NAT Gateways",         count: 1,  cost: 45  },
      { id: "eni",       label: "Network Interfaces",   count: 4,  cost: 0   },
    ],
  },
  {
    id: "database", label: "Databases", expanded: false,
    types: [
      { id: "rds",       label: "RDS Instances",        count: 3,  cost: 210 },
      { id: "dynamo",    label: "DynamoDB Tables",       count: 7,  cost: 8   },
      { id: "elastic",   label: "ElastiCache",          count: 1,  cost: 55  },
    ],
  },
  {
    id: "security", label: "Security", expanded: false,
    types: [
      { id: "kms",       label: "KMS Keys",             count: 4,  cost: 6   },
      { id: "secrets",   label: "Secrets Manager",      count: 9,  cost: 14  },
    ],
  },
  {
    id: "mgmt", label: "Management", expanded: false,
    types: [
      { id: "cwlg",      label: "CW Log Groups",        count: 22, cost: 8   },
      { id: "cwa",       label: "CW Alarms",            count: 7,  cost: 2   },
      { id: "lambda",    label: "Lambda Functions",     count: 5,  cost: 3   },
      { id: "eb",        label: "EventBridge Rules",    count: 3,  cost: 0   },
    ],
  },
  {
    id: "identity", label: "Identity", expanded: false,
    types: [
      { id: "iam",       label: "IAM Users",            count: 6,  cost: 0   },
      { id: "iamkey",    label: "IAM Keys",             count: 4,  cost: 0   },
    ],
  },
];

const MOCK_RESOURCES = [
  { id: "i-0a1b2c3d4e", name: "old-worker-node-3", type: "EC2 Instance", region: "us-east-1", status: "SAFE_TO_DELETE", cost: 48, authorized: false, reason: "Stopped for 38 days", tags: 2, missingTags: ["env","owner"], age: "38d" },
  { id: "vol-0x9y8z7w", name: "unattached-data-01", type: "EBS Volume", region: "us-east-1", status: "SAFE_TO_DELETE", cost: 12, authorized: false, reason: "Unattached for 62 days", tags: 0, missingTags: ["env","project","owner"], age: "62d" },
  { id: "snap-abc123de", name: "snapshot-old-2023", type: "Snapshot",    region: "us-west-2", status: "ORPHANED",       cost: 4,  authorized: false, reason: "No associated volume",   tags: 1, missingTags: ["owner"], age: "180d" },
  { id: "eip-192168010", name: "-",                 type: "Elastic IP",  region: "eu-west-1", status: "SAFE_TO_DELETE", cost: 4,  authorized: false, reason: "Unassociated Elastic IP", tags: 0, missingTags: ["env","owner"], age: "15d" },
  { id: "i-0f1e2d3c4b", name: "staging-api-server", type: "EC2 Instance", region: "us-east-1", status: "STOPPED", cost: 32, authorized: false, reason: "Instance stopped", tags: 3, missingTags: [], age: "12d" },
  { id: "rds-db-legacy", name: "mysql-legacy-db",  type: "RDS Instance", region: "us-east-1", status: "RISK",           cost: 210,authorized: false, reason: "No backups in 30d",      tags: 2, missingTags: ["env"], age: "200d" },
  { id: "s3-old-backups", name: "company-backups-2021", type: "S3 Bucket", region: "us-east-1", status: "ORPHANED",    cost: 22, authorized: true,  reason: "No access in 90 days",  tags: 1, missingTags: ["project"], age: "365d" },
  { id: "kms-disabled-1", name: "deprecated-key",  type: "KMS Key",     region: "ap-south-1", status: "SAFE_TO_DELETE", cost: 1, authorized: false, reason: "Key is pending deletion", tags: 0, missingTags: ["env","owner"], age: "90d" },
  { id: "lambda-unused", name: "test-func-2022",   type: "Lambda",      region: "us-east-1", status: "ORPHANED",       cost: 0,  authorized: false, reason: "0 invocations in 30d",   tags: 0, missingTags: ["owner","project"], age: "120d" },
  { id: "cwlg-empty-01", name: "/aws/empty-app",   type: "CW Log Group", region: "us-east-1", status: "SAFE_TO_DELETE", cost: 0, authorized: false, reason: "Empty log group",        tags: 0, missingTags: [], age: "45d" },
  { id: "nat-unused-01", name: "nat-gw-stale",     type: "NAT Gateway", region: "eu-west-1", status: "RISK",           cost: 45, authorized: false, reason: "No traffic in 30d",      tags: 0, missingTags: ["env","owner"], age: "30d" },
  { id: "iam-stale-key", name: "dev-svc-account",  type: "IAM Key",     region: "global",    status: "NOT_COMPLIANT",  cost: 0,  authorized: false, reason: "Key unused 120+ days",   tags: 0, missingTags: [], age: "120d" },
];

// Aggregate KPIs
const TOTAL_DISCOVERED = MOCK_RESOURCES.reduce((s, r) => s + r.cost, 0);
const TOTAL_POTENTIAL  = MOCK_RESOURCES.filter(r => r.status === "SAFE_TO_DELETE" && !r.authorized).reduce((s, r) => s + r.cost, 0);
const UNTAGGED         = MOCK_RESOURCES.filter(r => r.missingTags.length > 0).length;
const TAG_HEALTH_PCT   = Math.round((1 - UNTAGGED / MOCK_RESOURCES.length) * 100);
const SAFETY_SAFE      = MOCK_RESOURCES.filter(r => r.status === "SAFE_TO_DELETE" || r.status === "STOPPED").length;
const SAFETY_REVIEW    = MOCK_RESOURCES.filter(r => r.status === "ORPHANED" || r.status === "NOT_COMPLIANT").length;
const SAFETY_RISKY     = MOCK_RESOURCES.filter(r => r.status === "RISK" || r.status === "UNAUTHORIZED").length;

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
const Sidebar = ({ activeType, onSelect }) => {
  const [expanded, setExpanded] = useState(
    Object.fromEntries(SIDEBAR_CATEGORIES.map(c => [c.id, c.expanded]))
  );

  const totalCost = SIDEBAR_CATEGORIES.flatMap(c => c.types).reduce((s, t) => s + t.cost, 0);

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
        {SIDEBAR_CATEGORIES.map(cat => {
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
    { key: "check",  w: 36,  label: "" },
    { key: "name",   w: "2fr", label: "Resource" },
    { key: "type",   w: "1fr", label: "Type" },
    { key: "region", w: 100, label: "Region" },
    { key: "status", w: 140, label: "Status" },
    { key: "tags",   w: 80,  label: "Tags" },
    { key: "cost",   w: 90,  label: "Cost/mo" },
    { key: "reason", w: "1.5fr", label: "Reason" },
    { key: "actions",w: 130, label: "" },
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

// ─── MAIN PAGE ────────────────────────────────────────────────────────────────
export default function ResourceHygiene() {
  const [activeType, setActiveType]     = useState("instance");
  const [selected, setSelected]         = useState(new Set());
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch]             = useState("");
  const [sidebarCats, setSidebarCats]   = useState(
    Object.fromEntries(SIDEBAR_CATEGORIES.map(c => [c.id, c.expanded]))
  );

  const filteredResources = useMemo(() => {
    return MOCK_RESOURCES.filter(r => {
      if (statusFilter !== "ALL" && r.status !== statusFilter) return false;
      if (search && !r.name.toLowerCase().includes(search.toLowerCase()) &&
          !r.id.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [statusFilter, search]);

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

  const STATUS_FILTERS = [
    { key: "ALL",           label: "All" },
    { key: "SAFE_TO_DELETE",label: "Safe to Delete" },
    { key: "ORPHANED",      label: "Orphaned" },
    { key: "STOPPED",       label: "Stopped" },
    { key: "RISK",          label: "Risk" },
    { key: "NOT_COMPLIANT", label: "Not Compliant" },
  ];

  return (
    <div style={{
      minHeight: "100vh", background: C.bg,
      fontFamily: "'DM Sans', system-ui, sans-serif",
      color: C.text, display: "flex", flexDirection: "column",
    }}>

      {/* ── TOP BAR ── */}
      <div style={{
        position: "sticky", top: 0, zIndex: 20,
        padding: "10px 24px",
        background: "rgba(245,246,248,0.8)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderBottom: "1px solid rgba(228,230,234,0.7)",
      }}>
        <div style={{
          display: "flex", alignItems: "center",
          background: "rgba(255,255,255,0.9)",
          border: "1px solid rgba(255,255,255,0.95)",
          borderRadius: 14,
          boxShadow: "0 2px 16px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04)",
          height: 50, padding: "0 6px", gap: 0,
        }}>
          {/* Title */}
          <div style={{ paddingLeft: 14, paddingRight: 18, borderRight: `1px solid ${C.border}`, height: 26, display: "flex", alignItems: "center", flexShrink: 0, marginRight: 4 }}>
            <h1 style={{ fontSize: 15, fontWeight: 800, margin: 0, letterSpacing: "-0.4px" }}>Resource Hygiene</h1>
          </div>

          {/* Account + Region selectors */}
          {[
            { label: "prod-account (123456789012)", icon: "⬡" },
            { label: "All Regions (Global)", icon: "◎" },
          ].map((s, i) => (
            <div key={i} style={{ padding: "0 12px", borderRight: `1px solid #f0f0f0`, flexShrink: 0 }}>
              <button style={{
                display: "flex", alignItems: "center", gap: 5,
                border: "none", background: "transparent",
                fontSize: 11.5, color: C.muted, cursor: "pointer",
                fontFamily: "inherit", padding: 0,
              }}>
                <span style={{ color: C.subtle, fontSize: 12 }}>{s.icon}</span>
                {s.label}
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <polyline points="2,3.5 5,6.5 8,3.5" stroke={C.subtle} strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ))}

          {/* Filters pill */}
          <div style={{ padding: "0 12px", borderRight: `1px solid #f0f0f0`, flexShrink: 0 }}>
            <button style={{
              display: "flex", alignItems: "center", gap: 5,
              border: "none", background: "transparent",
              fontSize: 11.5, color: C.muted, cursor: "pointer", fontFamily: "inherit",
            }}>
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                <line x1="1" y1="4" x2="13" y2="4" stroke={C.subtle} strokeWidth="1.4" strokeLinecap="round" />
                <line x1="3" y1="7" x2="11" y2="7" stroke={C.subtle} strokeWidth="1.4" strokeLinecap="round" />
                <line x1="5" y1="10" x2="9" y2="10" stroke={C.subtle} strokeWidth="1.4" strokeLinecap="round" />
              </svg>
              Filters
            </button>
          </div>

          {/* Last scan */}
          <div style={{ padding: "0 12px", flexShrink: 0 }}>
            <span style={{ fontSize: 11, color: C.subtle }}>Last scan: <strong style={{ color: C.muted, fontWeight: 500 }}>10 min ago</strong></span>
          </div>

          <div style={{ flex: 1 }} />

          {/* Action buttons */}
          <div style={{ display: "flex", gap: 6, paddingRight: 6, alignItems: "center" }}>
            <button style={{
              padding: "5px 12px", borderRadius: 8,
              border: `1px solid ${C.border}`, background: C.surface,
              fontSize: 11.5, color: C.muted, cursor: "pointer", fontFamily: "inherit",
              display: "flex", alignItems: "center", gap: 5,
            }}>
              <svg width="11" height="11" viewBox="0 0 14 14" fill="none">
                <path d="M7 1.5v3M7 1.5L5 3.5M7 1.5L9 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                <circle cx="7" cy="8.5" r="4.5" stroke="currentColor" strokeWidth="1.4" />
              </svg>
              Refresh
            </button>
            <button style={{
              padding: "6px 16px", borderRadius: 9, border: "none",
              background: "linear-gradient(135deg, #2563eb, #4f46e5)",
              color: "#fff", fontSize: 12, fontWeight: 600,
              cursor: "pointer", fontFamily: "inherit",
              boxShadow: "0 2px 8px rgba(37,99,235,0.28)",
              display: "flex", alignItems: "center", gap: 6,
              transition: "all 0.15s",
            }}
              onMouseEnter={e => { e.currentTarget.style.boxShadow = "0 4px 14px rgba(37,99,235,0.4)"; e.currentTarget.style.transform = "translateY(-1px)"; }}
              onMouseLeave={e => { e.currentTarget.style.boxShadow = "0 2px 8px rgba(37,99,235,0.28)"; e.currentTarget.style.transform = "translateY(0)"; }}
            >
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="5.5" stroke="white" strokeWidth="1.4" />
                <path d="M4.5 7L6.5 9L9.5 5" stroke="white" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Run Scan
            </button>
          </div>
        </div>
      </div>

      {/* ── KPI STRIP ── */}
      <div style={{ padding: "16px 24px 0", display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1.4fr", gap: 10 }}>
        {/* Total Discovered */}
        <KpiCard
          label="Total Discovered Cost"
          value={`$${TOTAL_DISCOVERED}/mo`}
          sub={`${MOCK_RESOURCES.length} resources found`}
          accentColor={C.accent}
          accentBorder={C.blueBorder}
        />

        {/* Potential Savings */}
        <KpiCard
          label="Potential Savings"
          value={`$${TOTAL_POTENTIAL}/mo`}
          sub="From safe-to-delete resources"
          accentColor={C.green}
          accentBorder={C.greenBorder}
        />

        {/* Tag Health */}
        <div style={{
          background: C.surface, border: `1px solid ${C.border}`,
          borderLeft: `3px solid ${TAG_HEALTH_PCT > 80 ? C.green : C.amber}`,
          borderRadius: 11, padding: "14px 16px",
        }}>
          <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 500, marginBottom: 6 }}>Tag Health</div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8, marginBottom: 10 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: C.text, letterSpacing: "-0.5px" }}>{TAG_HEALTH_PCT}%</div>
            <div style={{ fontSize: 11, color: C.subtle, marginBottom: 2 }}>{UNTAGGED} resources untagged</div>
          </div>
          {/* Bar */}
          <div style={{ height: 5, background: "#eef0f3", borderRadius: 3 }}>
            <div style={{
              width: `${TAG_HEALTH_PCT}%`, height: 5,
              background: `linear-gradient(90deg, ${TAG_HEALTH_PCT > 80 ? C.green : C.amber}90, ${TAG_HEALTH_PCT > 80 ? C.green : C.amber})`,
              borderRadius: 3,
            }} />
          </div>
        </div>

        {/* Safety Analysis */}
        <div style={{
          background: C.surface, border: `1px solid ${C.border}`,
          borderRadius: 11, padding: "14px 16px",
        }}>
          <div style={{ fontSize: 10.5, color: C.muted, fontWeight: 500, marginBottom: 10 }}>Safety Analysis</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
            {[
              { label: "Safe",   value: SAFETY_SAFE,   dot: C.green  },
              { label: "Review", value: SAFETY_REVIEW, dot: C.amber  },
              { label: "Risky",  value: SAFETY_RISKY,  dot: C.red    },
            ].map(s => (
              <div key={s.label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 20, fontWeight: 800, color: C.text, letterSpacing: "-0.5px" }}>{s.value}</div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginTop: 3 }}>
                  <div style={{ width: 5, height: 5, borderRadius: "50%", background: s.dot }} />
                  <span style={{ fontSize: 10.5, color: C.muted }}>{s.label}</span>
                </div>
              </div>
            ))}
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
          <Sidebar activeType={activeType} onSelect={setActiveType} />
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
                { label: "Authorize",   color: C.green  },
                { label: "Unauthorize", color: C.muted  },
                { label: "Tag",         color: C.accent },
                { label: "Cleanup",     color: C.red    },
              ].map(a => (
                <button key={a.label} style={{
                  padding: "5px 12px", borderRadius: 7,
                  border: `1px solid ${a.color}30`,
                  background: a.color === C.red ? C.redBg : C.surface,
                  color: a.color, fontSize: 11.5, fontWeight: 500,
                  cursor: "pointer", fontFamily: "inherit",
                  transition: "all 0.12s",
                }}
                  onMouseEnter={e => { e.currentTarget.style.background = a.color; e.currentTarget.style.color = "#fff"; }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = a.color === C.red ? C.redBg : C.surface;
                    e.currentTarget.style.color = a.color;
                  }}
                >{a.label}</button>
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
              Showing {filteredResources.length} of {MOCK_RESOURCES.length} resources
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}