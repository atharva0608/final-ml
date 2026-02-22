import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDashboard } from '../../hooks/useDashboard';
import { auditAPI, clusterAPI, accountsAPI } from '../../services/api';
import api from '../../services/api';
import { useAuthStore } from '../../store/useStore';
import toast from 'react-hot-toast';

// Widgets
import ActivityFeed from './widgets/ActivityFeed';
import ClusterHealthCard from './widgets/ClusterHealthCard';
import FleetComposition from './widgets/FleetComposition';
import PendingApprovalsCard from './widgets/PendingApprovalsCard';
import AgentStatusWidget from './widgets/AgentStatusWidget';
import SpendForecastWidget from './widgets/SpendForecastWidget';

// Access Modal
import AccessRequestModal from '../approvals/AccessRequestModal';

// ─── PALETTE ────────────────────────────────────────────────────────────────
const C = {
  bg: "#f8f9fb",
  surface: "#ffffff",
  border: "#e8eaed",
  borderHover: "#d0d5de",
  text: "#0f1117",
  muted: "#6b7280",
  subtle: "#9ca3af",
  blue: "#2563eb",
  blueLight: "#eff6ff",
  green: "#059669",
  greenLight: "#ecfdf5",
  amber: "#d97706",
  amberLight: "#fffbeb",
  red: "#dc2626",
  redLight: "#fef2f2",
  purple: "#7c3aed",
  purpleLight: "#f5f3ff",
  indigo: "#4f46e5",
  indigoLight: "#eef2ff",
  teal: "#0d9488",
  tealLight: "#f0fdfa",
};

// ─── TINY COMPONENTS ────────────────────────────────────────────────────────
const Badge = ({ children, color = C.blue, bg, style = {} }) => (
  <span style={{
    display: "inline-flex", alignItems: "center",
    padding: "2px 8px", borderRadius: 20,
    fontSize: 11, fontWeight: 600,
    color, background: bg || color + "18",
    letterSpacing: "0.02em",
    ...style
  }}>{children}</span>
);

const Dot = ({ color }) => (
  <span style={{
    display: "inline-block", width: 7, height: 7,
    borderRadius: "50%", background: color, marginRight: 6, flexShrink: 0
  }} />
);

const SectionLabel = ({ children }) => (
  <div style={{
    fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em",
    textTransform: "uppercase", color: C.subtle,
    marginBottom: 10, marginTop: 4
  }}>{children}</div>
);

const EmptyChip = ({ text }) => (
  <div style={{
    display: "inline-flex", alignItems: "center", gap: 5,
    padding: "3px 10px", borderRadius: 6,
    background: "#f3f4f6", color: C.subtle, fontSize: 11
  }}>
    <span style={{ fontSize: 13 }}>○</span> {text}
  </div>
);

// Sparkline (SVG path)
const Sparkline = ({ data = [], color = C.blue, height = 32 }) => {
  const w = 80, h = height;
  if (!data.length) return <svg width={w} height={h} />;
  const max = Math.max(...data, 1);
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / max) * h}`).join(" ");
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

// KPI Card
const KpiCard = ({ label, value, sub, trend, color = C.blue, icon, onClick, style = {} }) => (
  <div onClick={onClick} style={{
    background: C.surface, border: `1px solid ${C.border}`,
    borderRadius: 12, padding: "18px 20px",
    cursor: onClick ? "pointer" : "default",
    transition: "box-shadow 0.15s, border-color 0.15s",
    ...style
  }}
    onMouseEnter={e => { if (onClick) { e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.08)"; e.currentTarget.style.borderColor = C.borderHover; } }}
    onMouseLeave={e => { e.currentTarget.style.boxShadow = "none"; e.currentTarget.style.borderColor = C.border; }}
  >
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
      <div style={{ flex: 1 }}>
        <div style={{ color: C.muted, fontSize: 12, marginBottom: 6 }}>{label}</div>
        <div style={{ color: C.text, fontSize: 22, fontWeight: 700, letterSpacing: "-0.5px", lineHeight: 1.1 }}>{value}</div>
        {sub && <div style={{ color: C.muted, fontSize: 12, marginTop: 5 }}>{sub}</div>}
      </div>
      {icon && (
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: color + "12",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 16, flexShrink: 0
        }}>{icon}</div>
      )}
    </div>
    {trend !== undefined && (
      <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 4 }}>
        <span style={{ color: trend >= 0 ? C.green : C.red, fontSize: 12, fontWeight: 600 }}>
          {trend >= 0 ? "↑" : "↓"} {Math.abs(trend)}%
        </span>
        <span style={{ color: C.subtle, fontSize: 11 }}>vs last month</span>
      </div>
    )}
  </div>
);

// Section Card wrapper
const Card = ({ children, style = {}, title, titleRight, noPad }) => (
  <div style={{
    background: C.surface, border: `1px solid ${C.border}`,
    borderRadius: 12, overflow: "hidden", ...style
  }}>
    {title && (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 18px", borderBottom: `1px solid ${C.border}`
      }}>
        <span style={{ fontWeight: 600, fontSize: 13, color: C.text }}>{title}</span>
        {titleRight}
      </div>
    )}
    <div style={noPad ? {} : { padding: "16px 18px" }}>{children}</div>
  </div>
);

// Health mini card (for RI/S3/RDS/Transfer - shown as dashboard widgets)
const HealthMiniCard = ({ icon, iconBg, title, status, detail, cta, onClick }) => (
  <div style={{
    background: C.surface, border: `1px solid ${C.border}`,
    borderRadius: 12, padding: "16px 18px",
    cursor: "pointer", transition: "box-shadow 0.15s, border-color 0.15s"
  }}
    onMouseEnter={e => { e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.07)"; e.currentTarget.style.borderColor = C.borderHover; }}
    onMouseLeave={e => { e.currentTarget.style.boxShadow = "none"; e.currentTarget.style.borderColor = C.border; }}
    onClick={onClick}
  >
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
      <div style={{
        width: 32, height: 32, borderRadius: 8,
        background: iconBg, display: "flex", alignItems: "center",
        justifyContent: "center", fontSize: 15, flexShrink: 0
      }}>{icon}</div>
      <span style={{ fontWeight: 600, fontSize: 13, color: C.text }}>{title}</span>
    </div>
    <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.5, marginBottom: 10 }}>{detail}</div>
    {cta && <span style={{ color: C.blue, fontSize: 11, fontWeight: 600 }}>{cta} →</span>}
  </div>
);

// Optimization Feature Row
const FeatureRow = ({ icon, iconBg, label, value, status, statusColor, cta, onClick }) => (
  <div onClick={onClick} style={{
    display: "flex", alignItems: "center", gap: 12,
    padding: "10px 0", borderBottom: `1px solid ${C.border}`,
    cursor: "pointer"
  }}
    onMouseEnter={e => e.currentTarget.style.background = "#f9fafb"}
    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
  >
    <div style={{
      width: 30, height: 30, borderRadius: 8, background: iconBg,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 14, flexShrink: 0
    }}>{icon}</div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontWeight: 500, fontSize: 13, color: C.text }}>{label}</div>
      <div style={{ color: C.muted, fontSize: 11, marginTop: 1 }}>{value}</div>
    </div>
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
      {status && <Badge color={statusColor || C.muted} bg={(statusColor || C.muted) + "14"}>{status}</Badge>}
      {cta && <span style={{ color: C.blue, fontSize: 11, fontWeight: 600 }}>{cta}</span>}
    </div>
  </div>
);

// ─── MAIN DASHBOARD ─────────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { dashboardKPIs, loading: dashboardLoading, refreshDashboard } = useDashboard();

  const [dataLoading, setDataLoading] = useState(true);
  const [accounts, setAccounts] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [activityFeed, setActivityFeed] = useState([]);
  const [showAccessModal, setShowAccessModal] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");

  // Health Data States
  const [riHealth, setRiHealth] = useState({ status: "no_data", waste_pct: 0, savings_potential: 0 });
  const [s3Health, setS3Health] = useState({ status: "no_data", buckets: 0, savings: 0 });
  const [rdsHealth, setRdsHealth] = useState({ status: "no_data", instances: 0, savings: 0 });
  const [transferHealth, setTransferHealth] = useState({ status: "no_data", cost: 0 });

  useEffect(() => {
    const fetchData = async () => {
      setDataLoading(true);
      try {
        const logsRes = await auditAPI.list({ limit: 5 });
        const logs = logsRes.data.logs || [];
        setActivityFeed(logs.map(log => ({
          id: log.id,
          action: log.event_name || log.event || log.action,
          resource: log.resource_id || log.resource_type || 'System',
          status: (log.status || log.outcome) === 'success' ? 'success' : (log.status || log.outcome) === 'error' ? 'error' : 'info',
          time: new Date(log.created_at || log.timestamp)
        })));

        const clustersRes = await clusterAPI.listClusters();
        setClusters(clustersRes.data.clusters || []);

        const accountsRes = await accountsAPI.list();
        setAccounts(accountsRes.data || []);

        // Fetch health stats
        try {
          const ri = await api.get('/api/v1/ri/overview');
          setRiHealth({ status: ri.data.health_status || "no_data", waste_pct: 0, savings_potential: ri.data.wasted_spend_monthly || 0, detail: `${ri.data.total_ris || 0} RIs found.` });
        } catch (e) { }

        try {
          const s3 = await api.get('/api/v1/s3/overview');
          setS3Health({ status: s3.data.health_status || "no_data", buckets: s3.data.total_buckets || 0, savings: s3.data.potential_savings || 0, detail: `${s3.data.total_buckets || 0} buckets analyzed.` });
        } catch (e) { }

        try {
          const rds = await api.get('/api/v1/rds/overview');
          setRdsHealth({ status: rds.data.health_status || "no_data", instances: rds.data.total_instances || 0, savings: rds.data.potential_savings || 0, detail: `${rds.data.total_instances || 0} instances found.` });
        } catch (e) { }

        try {
          const transfer = await api.get('/api/v1/data-transfer/overview');
          setTransferHealth({ status: transfer.data.health_status || "no_data", cost: transfer.data.total_transfer_cost || 0, detail: `Total transfer cost: $${transfer.data.total_transfer_cost || 0}` });
        } catch (e) { }

      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setDataLoading(false);
      }
    };
    fetchData();
  }, []);

  const hasNoData = !dashboardLoading && !dataLoading && accounts.length === 0 && user?.role !== 'SUPER_ADMIN';

  const handleConnectClick = () => {
    const allowedRoles = ['ORG_ADMIN', 'CLIENT', 'TEAM_LEAD'];
    if (allowedRoles.includes(user?.role)) {
      navigate('/onboarding');
    } else {
      setShowAccessModal(true);
    }
  };


  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "cost", label: "Cost Intelligence" },
    { id: "infra", label: "Infrastructure" },
    { id: "governance", label: "Governance" },
  ];

  return (
    <div style={{
      minHeight: "100vh", background: C.bg,
      fontFamily: "'DM Sans', 'Outfit', system-ui, sans-serif",
      color: C.text
    }}>
      {/* ── TOP BAR — floating glass pill ── */}
      <div style={{
        position: "sticky", top: 0, zIndex: 20,
        padding: "10px 28px",
        background: "rgba(248,249,251,0.7)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderBottom: "1px solid rgba(232,234,237,0.6)",
      }}>
        <div style={{
          display: "flex", alignItems: "center",
          background: "rgba(255,255,255,0.88)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          border: "1px solid rgba(255,255,255,0.95)",
          borderRadius: 16,
          boxShadow: "0 2px 20px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.04)",
          height: 52,
          padding: "0 6px",
          gap: 2,
          maxWidth: 1400,
          margin: "0 auto",
        }}>
          {/* Title */}
          <div style={{
            paddingLeft: 14, paddingRight: 18,
            borderRight: "1px solid #e8eaed",
            marginRight: 4, height: 28,
            display: "flex", alignItems: "center", flexShrink: 0,
          }}>
            <h1 style={{
              fontSize: 15, fontWeight: 800, margin: 0,
              letterSpacing: "-0.4px", color: C.text,
            }}>Dashboard</h1>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", gap: 2, flex: 1 }}>
            {tabs.map(t => {
              const isActive = activeTab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  style={{
                    padding: "6px 16px", borderRadius: 10, border: "none",
                    background: isActive
                      ? "linear-gradient(135deg, #2563eb 0%, #4f46e5 100%)"
                      : "transparent",
                    color: isActive ? "#fff" : C.muted,
                    fontWeight: isActive ? 600 : 400,
                    fontSize: 13, cursor: "pointer",
                    transition: "all 0.18s cubic-bezier(.4,0,.2,1)",
                    letterSpacing: "-0.1px",
                    fontFamily: "inherit",
                    boxShadow: isActive
                      ? "0 2px 8px rgba(37,99,235,0.28), inset 0 1px 0 rgba(255,255,255,0.15)"
                      : "none",
                    whiteSpace: "nowrap",
                  }}
                  onMouseEnter={e => {
                    if (!isActive) { e.currentTarget.style.background = "#f3f4f6"; e.currentTarget.style.color = C.text; }
                  }}
                  onMouseLeave={e => {
                    if (!isActive) { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = C.muted; }
                  }}
                >{t.label}</button>
              );
            })}
          </div>

          {/* Actions */}
          <div style={{ display: "flex", gap: 6, paddingRight: 6, flexShrink: 0 }}>
            <button
              onClick={refreshDashboard}
              style={{
                padding: "6px 16px", borderRadius: 9, border: "none",
                background: "linear-gradient(135deg, #2563eb 0%, #4f46e5 100%)",
                color: "#fff", fontSize: 12, fontWeight: 600,
                cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                fontFamily: "inherit",
                boxShadow: "0 2px 8px rgba(37,99,235,0.32), inset 0 1px 0 rgba(255,255,255,0.15)",
                transition: "all 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.boxShadow = "0 4px 14px rgba(37,99,235,0.44)"; e.currentTarget.style.transform = "translateY(-1px)"; }}
              onMouseLeave={e => { e.currentTarget.style.boxShadow = "0 2px 8px rgba(37,99,235,0.32), inset 0 1px 0 rgba(255,255,255,0.15)"; e.currentTarget.style.transform = "translateY(0)"; }}
            >
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                <path d="M7 1.5v3M7 1.5L5 3.5M7 1.5L9 3.5M1.5 7h11M10.5 4.5A5.5 5.5 0 1 1 3.5 4.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Refresh
            </button>
          </div>
        </div>
      </div>

      <div style={{ padding: "24px 28px", maxWidth: 1400, margin: "0 auto" }}>

        <AccessRequestModal
          isOpen={showAccessModal}
          onClose={() => setShowAccessModal(false)}
          resourceName="Add AWS Account"
          actionType="CONNECT_AWS_ACCOUNT"
          onSuccess={() => {
            setShowAccessModal(false);
            toast.success("Request sent to Team Lead");
          }}
        />

        {/* ── ONBOARDING BANNER (shown when no AWS account) ── */}
        {hasNoData && (
          <div style={{
            background: "linear-gradient(135deg, #1d4ed8 0%, #4f46e5 100%)",
            borderRadius: 12, padding: "18px 24px", marginBottom: 24,
            display: "flex", alignItems: "center", justifyContent: "space-between"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div style={{ fontSize: 22 }}>ⓘ</div>
              <div>
                <div style={{ color: "#fff", fontWeight: 600, fontSize: 14 }}>Connect your AWS account to get started</div>
                <div style={{ color: "rgba(255,255,255,0.75)", fontSize: 12, marginTop: 2 }}>
                  Discover clusters, optimize costs, and track savings across your infrastructure
                </div>
              </div>
            </div>
            <button onClick={handleConnectClick} style={{
              padding: "8px 18px", borderRadius: 8,
              background: "#fff", border: "none",
              color: C.indigo, fontWeight: 700, fontSize: 13,
              cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit"
            }}>Connect AWS Account →</button>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════════════════
            OVERVIEW TAB
        ════════════════════════════════════════════════════════════════════ */}
        {activeTab === "overview" && (
          <div>
            {/* ── ROW 1: Core KPIs (4 cards) ── */}
            <SectionLabel>Spend & Savings</SectionLabel>
            <div className="grid grid-cols-4 gap-3 mb-5">
              <KpiCard label="Monthly Spend" value={`$${(dashboardKPIs?.total_cost || 0).toFixed(2)}`} sub="0% vs last month" trend={0} icon="$" color={C.blue} />
              <KpiCard label="Net Savings" value={`$${(dashboardKPIs?.estimated_savings || 0).toFixed(2)}`} sub="0.0% savings rate" trend={0} icon="↓" color={C.green} />
              <KpiCard label="Spot Ratio" value={`${(dashboardKPIs?.optimization_rate || 0).toFixed(0)}%`} sub="Calculated across all connected clusters" icon="◎" color={C.purple} />
              <KpiCard label="Total Nodes" value={clusters.reduce((acc, c) => acc + (c.nodes || c.node_count || 0), 0)} sub={`${clusters.length} clusters connected`} icon="⬡" color={C.teal} />
            </div>

            {/* ── ROW 2: Forecast + Agent Status + Cluster Health ── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
              <SpendForecastWidget widgetKey="spend_forecast" />
              <AgentStatusWidget widgetKey="agent_status" />
              <ClusterHealthCard widgetKey="cluster_health" data={{ clusters }} />
            </div>

            {/* ── ROW 3: Fleet Composition + Activity Feed ── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
              <FleetComposition widgetKey="fleet_composition" data={{}} />
              <div className="md:col-span-2">
                <ActivityFeed widgetKey="activity_feed" data={{ activities: activityFeed }} />
              </div>
            </div>

            {/* ── ROW 4: Pending Approvals ── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="md:col-span-3">
                <PendingApprovalsCard widgetKey="pending_approvals" data={{ data: [] }} />
              </div>
            </div>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════════════════
            COST INTELLIGENCE TAB — everything cost-related in one place
        ════════════════════════════════════════════════════════════════════ */}
        {activeTab === "cost" && (
          <div>
            <SectionLabel>Optimization Features</SectionLabel>

            {/* ── Feature status overview row ── */}
            <div className="grid grid-cols-3 gap-3 mb-5">
              {/* Right-Sizing */}
              <Card style={{ borderTop: `3px solid ${C.blue}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: C.blueLight, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>⇄</div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Right-Sizing</div>
                    <Badge color={C.muted} bg="#f3f4f6" style={{ marginTop: 2 }}>No data yet</Badge>
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                  {[
                    { label: "Overprov. instances", value: "0" },
                    { label: "Potential savings", value: "$0/mo" },
                    { label: "Optimization score", value: "—" },
                    { label: "Instances analyzed", value: "0" },
                  ].map(s => (
                    <div key={s.label} style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 10px" }}>
                      <div style={{ fontSize: 10, color: C.subtle, marginBottom: 2 }}>{s.label}</div>
                      <div style={{ fontWeight: 700, fontSize: 15 }}>{s.value}</div>
                    </div>
                  ))}
                </div>
                <button onClick={() => navigate('/right-sizing/manual')} style={{
                  width: "100%", padding: "7px 0", borderRadius: 8,
                  border: `1px solid ${C.blue}`, background: "transparent",
                  color: C.blue, fontWeight: 600, fontSize: 12, cursor: "pointer", fontFamily: "inherit"
                }}>Go to Right-Sizing →</button>
              </Card>

              {/* AtharvaAI */}
              <Card style={{ borderTop: `3px solid ${C.indigo}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: C.indigoLight, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>◈</div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>AtharvaAI</div>
                    <Badge color={C.indigo} bg={C.indigoLight} style={{ marginTop: 2 }}>ML Scoring</Badge>
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                  {[
                    { label: "ML status", value: "Healthy" },
                    { label: "Pools ranked", value: "0" },
                    { label: "Top savings", value: "—" },
                    { label: "Blacklisted", value: "0" },
                  ].map(s => (
                    <div key={s.label} style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 10px" }}>
                      <div style={{ fontSize: 10, color: C.subtle, marginBottom: 2 }}>{s.label}</div>
                      <div style={{ fontWeight: 700, fontSize: 15, color: s.value === "Healthy" ? C.green : C.text }}>{s.value}</div>
                    </div>
                  ))}
                </div>
                <button onClick={() => navigate('/atharvaai/rankings')} style={{
                  width: "100%", padding: "7px 0", borderRadius: 8,
                  border: `1px solid ${C.indigo}`, background: "transparent",
                  color: C.indigo, fontWeight: 600, fontSize: 12, cursor: "pointer", fontFamily: "inherit"
                }}>Run Pool Rankings →</button>
              </Card>

              {/* Hibernation */}
              <Card style={{ borderTop: `3px solid ${C.teal}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: C.tealLight, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>◑</div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Hibernation</div>
                    <Badge color={C.muted} bg="#f3f4f6" style={{ marginTop: 2 }}>0 active schedules</Badge>
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                  {[
                    { label: "Sleep hrs/week", value: "0h" },
                    { label: "Monthly savings", value: "$0" },
                    { label: "Active schedules", value: "0" },
                    { label: "Clusters covered", value: "0" },
                  ].map(s => (
                    <div key={s.label} style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 10px" }}>
                      <div style={{ fontSize: 10, color: C.subtle, marginBottom: 2 }}>{s.label}</div>
                      <div style={{ fontWeight: 700, fontSize: 15 }}>{s.value}</div>
                    </div>
                  ))}
                </div>
                <button onClick={() => navigate('/hibernation/schedules')} style={{
                  width: "100%", padding: "7px 0", borderRadius: 8,
                  border: `1px solid ${C.teal}`, background: "transparent",
                  color: C.teal, fontWeight: 600, fontSize: 12, cursor: "pointer", fontFamily: "inherit"
                }}>Manage Schedules →</button>
              </Card>
            </div>

            {/* ── Resource Hygiene full-width ── */}
            <SectionLabel>Resource Hygiene</SectionLabel>
            <Card style={{ marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
                <div style={{ display: "flex", gap: 24 }}>
                  {[
                    { label: "Safe to Delete", value: "0", color: C.red },
                    { label: "Orphaned", value: "0", color: C.amber },
                    { label: "Potential Savings", value: "$0/mo", color: C.green },
                    { label: "Last Scan", value: "Never", color: C.muted },
                  ].map(s => (
                    <div key={s.label}>
                      <div style={{ fontSize: 11, color: C.subtle, marginBottom: 2 }}>{s.label}</div>
                      <div style={{ fontWeight: 700, fontSize: 18, color: s.color }}>{s.value}</div>
                    </div>
                  ))}
                </div>
                <button onClick={() => navigate('/resource-hygiene')} style={{
                  padding: "8px 18px", borderRadius: 8,
                  border: `1px solid ${C.border}`, background: C.surface,
                  color: C.text, fontWeight: 600, fontSize: 12, cursor: "pointer", fontFamily: "inherit"
                }}>⊘ Run Scan →</button>
              </div>
            </Card>

            {/* ── Cost Health widgets (RI, S3, RDS, Transfer) ── */}
            <SectionLabel>AWS Cost Health Checks</SectionLabel>
            <div className="grid grid-cols-4 gap-3">
              <HealthMiniCard
                icon="$" iconBg="#f5f3ff"
                title="RI Health"
                detail={riHealth.detail || "Connect AWS to analyze RI utilization."}
                cta="Analyze RIs"
                onClick={() => navigate('/ri-analysis')}
              />
              <HealthMiniCard
                icon="⬡" iconBg="#eff6ff"
                title="S3 Health"
                detail={s3Health.detail || "Connect AWS to detect tiering savings."}
                cta="Analyze S3"
                onClick={() => navigate('/s3-analysis')}
              />
              <HealthMiniCard
                icon="⊞" iconBg="#ecfdf5"
                title="RDS Health"
                detail={rdsHealth.detail || "Connect AWS to detect Multi-AZ savings."}
                cta="Analyze RDS"
                onClick={() => navigate('/rds-analysis')}
              />
              <HealthMiniCard
                icon="⇅" iconBg="#fff7ed"
                title="Data Transfer"
                detail={transferHealth.detail || "No significant transfer costs detected yet."}
                cta="Analyze Transfer"
                onClick={() => navigate('/data-transfer')}
              />
            </div>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════════════════
            INFRASTRUCTURE TAB
        ════════════════════════════════════════════════════════════════════ */}
        {activeTab === "infra" && (
          <div>
            {/* ── Cluster KPIs ── */}
            <SectionLabel>Cluster Overview</SectionLabel>
            <div className="grid grid-cols-4 gap-3 mb-5">
              <KpiCard label="Total Cost" value={`$${(dashboardKPIs?.total_cost || 0).toFixed(2)}`} icon="$" color={C.blue} />
              <KpiCard label="Total Nodes" value={clusters.reduce((acc, c) => acc + (c.nodes || c.node_count || 0), 0)} sub="0 spot / 0 on-demand" icon="⬡" color={C.teal} />
              <KpiCard label="Total vCPU" value="0" icon="◻" color={C.purple} />
              <KpiCard label="Total Memory" value="0 GB" icon="▣" color={C.green} />
            </div>

            {/* ── Clusters + Node Templates side by side ── */}
            <div className="grid grid-cols-3 gap-3">
              <div className="md:col-span-2">
                <Card title="Clusters" titleRight={
                  <div style={{ display: "flex", gap: 8 }}>
                    <button style={{ fontSize: 11, color: C.muted, background: "none", border: `1px solid ${C.border}`, borderRadius: 6, padding: "3px 10px", cursor: "pointer" }}>⟳ Discover</button>
                    <button onClick={() => navigate('/clusters')} style={{ fontSize: 11, color: C.blue, background: "none", border: "none", cursor: "pointer" }}>View all →</button>
                  </div>
                } noPad>
                  <div style={{ padding: "32px 18px", textAlign: "center", color: C.subtle, fontSize: 12 }}>
                    No clusters connected. Install the agent to start monitoring.
                  </div>
                </Card>
              </div>

              <div>
                <Card title="Node Templates" titleRight={
                  <button onClick={() => navigate('/templates')} style={{ fontSize: 11, color: C.blue, background: "none", border: "none", cursor: "pointer" }}>Manage →</button>
                }>
                  <div style={{ color: C.subtle, fontSize: 12, marginBottom: 12 }}>
                    Templates filter instance pools for AtharvaAI rankings.
                  </div>
                  <button onClick={() => navigate('/templates')} style={{
                    width: "100%", padding: "7px 0", borderRadius: 8,
                    border: `1px dashed ${C.border}`, background: "transparent",
                    color: C.muted, fontSize: 12, cursor: "pointer", fontFamily: "inherit"
                  }}>+ Create Template</button>
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* ════════════════════════════════════════════════════════════════════
            GOVERNANCE TAB
        ════════════════════════════════════════════════════════════════════ */}
        {activeTab === "governance" && (
          <div>
            <SectionLabel>Access & Approvals</SectionLabel>
            <div className="grid grid-cols-3 gap-3 mb-5">
              {[
                { label: "Pending Requests", value: 0, color: C.amber, icon: "⏳", sub: "Require your approval" },
                { label: "Active Grants", value: 0, color: C.green, icon: "✓", sub: "Currently active JIT sessions" },
                { label: "Awaiting Consent", value: 0, color: C.purple, icon: "◌", sub: "Need your acceptance" },
              ].map(item => (
                <KpiCard key={item.label} label={item.label} value={item.value} sub={item.sub} icon={item.icon} color={item.color} />
              ))}
            </div>

            <div className="grid grid-cols-2 gap-3">
              {/* Governance Features */}
              <Card title="Governance Features">
                {[
                  { icon: "◇", iconBg: "#fef3c7", label: "Tagging Policies", value: "Enforce tag compliance across resources", status: "Configure", statusColor: C.amber, cta: "→", link: '/tagging' },
                  { icon: "⚡", iconBg: "#eff6ff", label: "Automation Settings", value: "Autopilot rules & cleanup governance", status: "Configure", statusColor: C.blue, cta: "→", link: '/automation' },
                  { icon: "✓", iconBg: C.greenLight, label: "Approvals", value: "JIT access requests & grants", status: "View", statusColor: C.green, cta: "→", link: '/approvals' },
                ].map((f, i) => (
                  <FeatureRow key={i} {...f} onClick={() => navigate(f.link)} />
                ))}
              </Card>

              {/* Teams */}
              <Card title="Teams & Members">
                <div style={{ color: C.subtle, fontSize: 12, marginBottom: 16 }}>
                  Manage team members, roles, and permissions.
                </div>
                {[
                  { label: "Members", icon: "⊹", value: "0 active members", iconBg: "#f0fdf4" },
                  { label: "Teams", icon: "◻", value: "0 teams created", iconBg: "#f5f3ff" },
                  { label: "Roles & Policies", icon: "◎", value: "3 system roles", iconBg: "#eff6ff" },
                ].map((r, i) => (
                  <FeatureRow key={i} icon={r.icon} iconBg={r.iconBg} label={r.label} value={r.value} cta="→" onClick={() => navigate('/teams')} />
                ))}
              </Card>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
