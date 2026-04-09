import React, { useEffect, useState, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useDashboard } from '../../hooks/useDashboard';
import { auditAPI, clusterAPI, accountsAPI, karpenterAPI, ascpaiAPI, hibernationAPI, hygieneAPI, approvalsAPI, teamAPI, userAPI, multiClusterAPI } from '../../services/api';
import api from '../../services/api';
import { useAuthStore, useHeaderStore } from '../../store/useStore';
import toast from 'react-hot-toast';

// Widgets
import ActivityFeed from './widgets/ActivityFeed';
import ClusterHealthCard from './widgets/ClusterHealthCard';
import FleetComposition from './widgets/FleetComposition';
import PendingApprovalsCard from './widgets/PendingApprovalsCard';
import AgentStatusWidget from './widgets/AgentStatusWidget';
import SpendForecastWidget from './widgets/SpendForecastWidget';
import TrendsChart from './widgets/TrendsChart';

// Access Modal
import AccessRequestModal from '../approvals/AccessRequestModal';

// Shared
import ErrorBoundary from '../shared/ErrorBoundary';

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
  const maxVal = Math.max(...data);
  const max = maxVal > 0 ? maxVal : 1; // Prevent NaN on 0 division
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
  const headerStore = useHeaderStore();
  const { dashboardKPIs, loading: dashboardLoading, refreshDashboard } = useDashboard();

  const [dataLoading, setDataLoading] = useState(true);
  const [accounts, setAccounts] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [activityFeed, setActivityFeed] = useState([]);
  const [showAccessModal, setShowAccessModal] = useState(false);

  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const tabFromUrl = queryParams.get("tab") || "overview";

  const [activeTab, setActiveTab] = useState(tabFromUrl);

  useEffect(() => {
    if (tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
  }, [tabFromUrl]);

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`/dashboard?tab=${tabId}`);
  };

  // Health Data States
  const [riHealth, setRiHealth] = useState({ status: "no_data", waste_pct: 0, savings_potential: 0 });
  const [s3Health, setS3Health] = useState({ status: "no_data", buckets: 0, savings: 0 });
  const [rdsHealth, setRdsHealth] = useState({ status: "no_data", instances: 0, savings: 0 });
  const [transferHealth, setTransferHealth] = useState({ status: "no_data", cost: 0 });

  // Feature Card States (Tasks 8.5, 8.6, 9.7)
  const [rightsizingData, setRightsizingData] = useState({
    count: 0,
    topSavings: 0,
    clusterCount: 0,
    lastRecommendation: null
  });
  const [ascpaiData, setAscpaiData] = useState({
    poolsAnalyzed: 0,
    topScore: 0,
    regions: 0,
    lastRun: null,
    status: 'fetching' // 'fetching', 'healthy', 'degraded', 'error'
  });
  const [hibernationData, setHibernationData] = useState({
    hoursSlept: 0,
    totalSavings: 0,
    activeSchedules: 0,
    clustersOnSchedule: 0,
    isHibernatingNow: false
  });

  // Governance & Hygiene Data States
  const [hygieneData, setHygieneData] = useState({
    safeToDelete: 0,
    orphaned: 0,
    potentialSavings: 0,
    lastScan: null
  });
  const [approvalsData, setApprovalsData] = useState({
    pending: 0,
    active: 0,
    awaitingConsent: 0
  });
  const [teamsData, setTeamsData] = useState({
    members: 0,
    teams: 0,
    roles: 3 // System default
  });

  const [fleetData, setFleetData] = useState(null);
  const [fleetLoading, setFleetLoading] = useState(true);

  // Issue #30/#32: serial counters — each effect has its own ref to avoid cross-invalidation
  const _fleetSeq = useRef(0);
  const _dataSeq = useRef(0);

  useEffect(() => {
    // Issue #30: AbortController so navigation away cancels in-flight request
    const ctrl = new AbortController();
    const seq = ++_fleetSeq.current;
    setFleetLoading(true);
    multiClusterAPI.getSummary()
      .then(res => {
        if (seq !== _fleetSeq.current) return; // #32: stale response guard
        // Issue #31: ID-based merge so rapid refreshes don't flicker
        setFleetData(prev => {
          const incoming = res.data;
          if (!prev || !prev.clusters || !incoming) return incoming;
          const existing = Object.fromEntries((prev.clusters || []).map(c => [c.id, c]));
          const merged = (incoming.clusters || []).map(c => ({ ...existing[c.id], ...c }));
          return { ...incoming, clusters: merged };
        });
      })
      .catch(e => { if (e.name !== 'AbortError') console.error('[Dashboard] fleetData', e); })
      .finally(() => { if (seq === _fleetSeq.current) setFleetLoading(false); });
    return () => ctrl.abort();
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    const seq = ++_dataSeq.current;
    const fetchData = async () => {
      setDataLoading(true);
      try {
        const logsRes = await auditAPI.list({ limit: 5 });
        const logs = logsRes.data.logs || [];
        const baseFeed = logs.map(log => ({
          id: log.id,
          action: log.event_name || log.event || log.action,
          resource: log.resource_id || log.resource_type || 'System',
          status: (log.status || log.outcome) === 'success' ? 'success' : (log.status || log.outcome) === 'error' ? 'error' : 'info',
          time: new Date(log.created_at || log.timestamp)
        }));

        try {
          const actsRes = await multiClusterAPI.getActions(5);
          const acts = actsRes.data.actions || [];
          const actFeed = acts.map(a => ({
            id: a.id,
            action: a.trigger === 'spot_interruption' ? 'Spot Interruption' : 'Optimization',
            resource: a.cluster_name || a.cluster_id,
            status: a.status === 'completed' ? 'success' : a.status === 'failed' ? 'error' : 'info',
            time: new Date(a.created_at)
          }));
          const combined = [...actFeed, ...baseFeed].sort((a, b) => b.time - a.time).slice(0, 10);
          setActivityFeed(combined);
        } catch (e) {
          setActivityFeed(baseFeed);
        }

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
          const transfer = await api.get('/api/v1/transfer/overview');
          setTransferHealth({ status: transfer.data.health_status || "no_data", cost: transfer.data.total_transfer_cost || 0, detail: `Total transfer cost: $${transfer.data.total_transfer_cost || 0}` });
        } catch (e) { }

        // Fetch Right-Sizing Data (Task 8.5)
        try {
          const rsRes = await karpenterAPI.getRecommendations();
          const recs = rsRes.data.recommendations || [];
          const topSavings = recs.reduce((max, r) => Math.max(max, r.estimated_savings_monthly || 0), 0);
          const uniqueClusters = new Set(recs.map(r => r.cluster_id)).size;
          const lastRec = recs.length > 0 ? new Date(Math.max(...recs.map(r => new Date(r.created_at || r.updated_at).getTime()))) : null;
          setRightsizingData({
            count: recs.length,
            topSavings,
            clusterCount: uniqueClusters,
            lastRecommendation: lastRec
          });
        } catch (e) {
          console.error("RightSizing fetch error", e);
        }

        // Fetch ASCP.AI Data
        try {
          const [globalRes, hrRes] = await Promise.allSettled([
            api.get('/api/v1/ascpai/v3/global-intelligence/status'),
            ascpaiAPI.getHealth(),
          ]);

          const d = globalRes.status === 'fulfilled' ? (globalRes.value.data || {}) : {};
          const hr = hrRes.status === 'fulfilled' ? (hrRes.value.data || {}) : {};

          setAscpaiData({
            poolsAnalyzed: d.pools_evaluated || d.pools_analyzed_count || 0,
            topScore: d.capacity_validated_count || 0,
            regions: d.active_clusters || 1,
            lastRun: d.last_ranking_timestamp ? new Date(d.last_ranking_timestamp) : null,
            status: hr.ml_degraded ? 'degraded' : 'healthy',
          });
        } catch (e) {
          console.error("ASCP.AI fetch error", e);
          setAscpaiData(prev => ({ ...prev, status: 'error' }));
        }

        // Fetch Hibernation Data (Task 9.7)
        try {
          const histRes = await api.get('/api/v1/hibernation/savings/history');
          const schedRes = await hibernationAPI.list();
          const activeSchedules = schedRes.data.schedules?.filter(s => s.is_active) || [];
          const activeStatusRes = await api.get('/api/v1/hibernation/status/active');

          const history = histRes.data.history || [];
          const hoursSlept = history.reduce((sum, h) => sum + (h.sleep_hours || 0), 0);
          const totalSavings = history.reduce((sum, h) => sum + (h.savings_realized || 0), 0);
          const uniqueClusters = new Set(activeSchedules.map(s => s.cluster_id)).size;

          setHibernationData({
            hoursSlept,
            totalSavings,
            activeSchedules: activeSchedules.length,
            clustersOnSchedule: uniqueClusters,
            isHibernatingNow: (activeStatusRes.data.active_operations || []).length > 0
          });
        } catch (e) {
          console.error("Hibernation fetch error", e);
        }

        // Fetch Hygiene Data
        try {
          if (accountsRes.data?.length > 0) {
            const scanRes = await hygieneAPI.scan(accountsRes.data[0].id);
            const resources = scanRes.data?.details?.resources || [];

            setHygieneData({
              safeToDelete: resources.filter(r => r.confidence_score >= 90).length,
              orphaned: resources.filter(r => r.status === 'orphaned').length || resources.length,
              potentialSavings: scanRes.data?.summary?.total_savings_amount || 0,
              lastScan: new Date()
            });
          }
        } catch (e) {
          console.error("Hygiene fetch error", e);
        }

        // Fetch Approvals & Governance Data
        try {
          // Approvals
          const pendingRes = await approvalsAPI.list('PENDING');
          const activeRes = await approvalsAPI.getActiveWindow();
          const pendingData = pendingRes.data?.data || pendingRes.data || [];

          let awaitingConsent = 0;
          try {
            // See if I have invites
            const invitesRes = await api.get('/api/v1/teams/invites').catch(() => ({ data: [] }));
            awaitingConsent = (invitesRes.data?.data || invitesRes.data || []).length;
          } catch (e) { }

          setApprovalsData({
            pending: Array.isArray(pendingData) ? pendingData.length : 0,
            active: activeRes.data ? 1 : 0, // usually just one active session returned
            awaitingConsent
          });

          // Teams
          let membersCount = 0;
          let teamsCount = 0;
          try {
            const tRes = await teamAPI.list();
            const teamsList = tRes.data?.data || tRes.data || [];
            teamsCount = teamsList.length;
            membersCount = teamsList.reduce((acc, t) => acc + (t.members || []).length, 0);
          } catch (e) { }

          let rolesCount = 3;
          try {
            const roleRes = await api.get('/api/v1/roles');
            rolesCount = (roleRes.data?.data || roleRes.data || []).length;
          } catch (e) { }

          setTeamsData({
            members: membersCount,
            teams: teamsCount,
            roles: rolesCount
          });

        } catch (e) {
          console.error("Approvals fetch error", e);
        }

      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setDataLoading(false);
      }
    };
    // Issue #32: stale-response guard — only apply if this is still the latest fetch
    if (seq === _dataSeq.current) {
      fetchData();
    }
    return () => ctrl.abort();
  }, []);

  // Sync refresh action to global header
  useEffect(() => {
    headerStore.setRefreshAction({
      onClick: refreshDashboard,
      loading: dashboardLoading || dataLoading,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboardLoading, dataLoading]);

  // Cleanup header on unmount only
  useEffect(() => {
    return () => headerStore.clearHeader();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
              <KpiCard label="Monthly Spend" value={`$${(dashboardKPIs?.total_cost || 0).toFixed(2)}`} sub="This month's AWS spend" trend={0} icon="$" color={C.blue} />
              <KpiCard label="Net Savings" value={`$${(dashboardKPIs?.estimated_savings || 0).toFixed(2)}`} sub={`${(dashboardKPIs?.savings_percentage || 0).toFixed(1)}% savings rate`} trend={dashboardKPIs?.savings_percentage || 0} icon="↑" color={C.green} />
              <KpiCard label="Spot Ratio" value={`${(fleetData?.summary?.spot_ratio_pct ?? dashboardKPIs?.optimization_rate ?? 0).toFixed(0)}%`} sub="Calculated across all connected clusters" icon="◎" color={C.purple} />
              <KpiCard label="Total Nodes" value={fleetData?.summary?.total_nodes ?? clusters.reduce((acc, c) => acc + (c.nodes || c.node_count || 0), 0)} sub={`${clusters.length} clusters connected`} icon="⬡" color={C.teal} />
            </div>

            {/* ── ROW 2: Fleet Overview ── */}
            <SectionLabel>Fleet Overview</SectionLabel>
            <ErrorBoundary label="Fleet Overview">
            <div className="mb-5">
              <Card>
                {fleetLoading ? (
                  <div style={{ textAlign: 'center', color: C.subtle, padding: '24px 0', fontSize: 13 }}>Loading fleet data…</div>
                ) : !fleetData ? (
                  <div style={{ textAlign: 'center', color: C.subtle, padding: '24px 0', fontSize: 13 }}>No fleet data available</div>
                ) : (
                  <div>
                    {/* Summary KPIs */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 16 }}>
                      {[
                        { label: 'Active Clusters', value: fleetData.summary?.active_clusters ?? '—', color: C.teal },
                        { label: 'Spot Nodes', value: fleetData.summary?.spot_nodes ?? '—', color: C.green },
                        { label: 'OD Nodes', value: fleetData.summary?.od_nodes ?? '—', color: C.blue },
                        { label: 'Spot Ratio', value: `${fleetData.summary?.spot_ratio_pct ?? 0}%`, color: C.purple },
                        { label: 'Est. Monthly Savings', value: `$${(fleetData.summary?.monthly_savings_est || 0).toFixed(0)}`, color: C.green },
                      ].map(kpi => (
                        <div key={kpi.label} style={{ background: '#f9fafb', borderRadius: 8, padding: '10px 12px', borderTop: `2px solid ${kpi.color}` }}>
                          <div style={{ fontSize: 10, color: C.subtle, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{kpi.label}</div>
                          <div style={{ fontWeight: 700, fontSize: 18, color: kpi.color }}>{kpi.value}</div>
                        </div>
                      ))}
                    </div>

                    {/* Per-cluster table */}
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                            {['Cluster', 'Region', 'Mode', 'Spot', 'OD', 'Spot %', 'Pending', 'Done 24h', 'Savings/mo'].map(h => (
                              <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 600, color: C.muted, whiteSpace: 'nowrap' }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(fleetData.clusters || []).map(c => (
                            <tr key={c.id}
                              onClick={() => navigate(`/clusters/${c.id}`)}
                              onMouseEnter={e => e.currentTarget.style.background = '#f9fafb'}
                              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                              style={{ borderBottom: `1px solid ${C.border}`, cursor: 'pointer', transition: 'background 0.1s' }}>
                              <td style={{ padding: '7px 10px', fontWeight: 600 }}>{c.name}</td>
                              <td style={{ padding: '7px 10px', color: C.muted }}>{c.region || '—'}</td>
                              <td style={{ padding: '7px 10px' }}>
                                {c.karpenter_mode ? (
                                  <Badge color={c.karpenter_mode === 'auto' ? C.green : C.amber} bg={c.karpenter_mode === 'auto' ? C.greenLight : C.amberLight}>
                                    {c.karpenter_mode === 'auto' ? 'Auto' : 'Insights'}
                                  </Badge>
                                ) : <span style={{ color: C.subtle }}>—</span>}
                              </td>
                              <td style={{ padding: '7px 10px', color: C.green, fontWeight: 600 }}>{c.spot_nodes}</td>
                              <td style={{ padding: '7px 10px', color: C.blue }}>{c.od_nodes}</td>
                              <td style={{ padding: '7px 10px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                  <div style={{ flex: 1, height: 6, borderRadius: 3, background: C.border, overflow: 'hidden' }}>
                                    <div style={{ width: `${c.spot_ratio_pct}%`, height: '100%', background: C.green, borderRadius: 3 }} />
                                  </div>
                                  <span style={{ fontSize: 11, color: C.muted, minWidth: 32 }}>{c.spot_ratio_pct}%</span>
                                </div>
                              </td>
                              <td style={{ padding: '7px 10px' }}>
                                {(c.pending_actions + c.in_progress_actions) > 0 ? (
                                  <Badge color={C.amber} bg={C.amberLight}>{c.pending_actions + c.in_progress_actions}</Badge>
                                ) : <span style={{ color: C.subtle }}>—</span>}
                              </td>
                              <td style={{ padding: '7px 10px', color: C.muted }}>{c.completed_actions_24h}</td>
                              <td style={{ padding: '7px 10px', color: C.green, fontWeight: 600 }}>${(c.monthly_savings_est || 0).toFixed(0)}</td>
                            </tr>
                          ))}
                          {fleetData.clusters.length === 0 && (
                            <tr>
                              <td colSpan={9} style={{ padding: '16px 10px', textAlign: 'center', color: C.subtle }}>No clusters connected</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </Card>
            </div>
            </ErrorBoundary>

            {/* ── ROW 3: Forecast + Agent Status + Cluster Health ── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
              <div className="md:col-span-2">
                <TrendsChart widgetKey="trends_chart" />
              </div>
              <ClusterHealthCard widgetKey="cluster_health" data={{ clusters }} />
            </div>

            {/* ── ROW 4: Fleet Composition + Activity Feed ── */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
              <FleetComposition widgetKey="fleet_composition" />
              <div className="md:col-span-2">
                <ActivityFeed widgetKey="activity_feed" data={{ activities: activityFeed }} />
              </div>
            </div>

            {/* ── ROW 5: Pending Approvals ── */}
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
                    <Badge color={C.muted} bg="#f3f4f6" style={{ marginTop: 2 }}>{rightsizingData.count > 0 ? `${rightsizingData.count} recommendations` : "No data yet"}</Badge>
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                  {[
                    { label: "Overprov. instances", value: rightsizingData.count.toString() },
                    { label: "Potential savings", value: `$${rightsizingData.topSavings}/mo` },
                    { label: "Clusters analyzed", value: rightsizingData.clusterCount.toString() },
                    { label: "Last recommendation", value: rightsizingData.lastRecommendation ? new Date(rightsizingData.lastRecommendation).toLocaleDateString() : "—" },
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

              {/* ASCP.AI */}
              <Card style={{ borderTop: `3px solid ${C.indigo}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: C.indigoLight, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>◈</div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
                      Balancekube.ai
                      {ascpaiData.status === 'healthy' && <Dot color={C.green} />}
                      {ascpaiData.status === 'degraded' && <Dot color={C.amber} />}
                      {ascpaiData.status === 'error' && <Dot color={C.red} />}
                    </div>
                    <Badge color={C.indigo} bg={C.indigoLight} style={{ marginTop: 2 }}>ML Scoring</Badge>
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                  {[
                    { label: "ML status", value: ascpaiData.status === 'healthy' ? "Healthy" : ascpaiData.status === 'degraded' ? "Degraded" : "Error" },
                    { label: "Pools ranked", value: ascpaiData.poolsAnalyzed.toString() },
                    { label: "Top score", value: ascpaiData.topScore.toString() },
                    { label: "Regions covered", value: ascpaiData.regions.toString() },
                  ].map(s => (
                    <div key={s.label} style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 10px" }}>
                      <div style={{ fontSize: 10, color: C.subtle, marginBottom: 2 }}>{s.label}</div>
                      <div style={{ fontWeight: 700, fontSize: 15, color: s.value === "Healthy" ? C.green : s.value === "Degraded" ? C.amber : s.value === "Error" ? C.red : C.text }}>{s.value}</div>
                    </div>
                  ))}
                </div>
                <button onClick={() => navigate('/ascpai/rankings')} style={{
                  width: "100%", padding: "7px 0", borderRadius: 8,
                  border: `1px solid ${C.indigo}`, background: "transparent",
                  color: C.indigo, fontWeight: 600, fontSize: 12, cursor: "pointer", fontFamily: "inherit"
                }}>View ML Rankings →</button>
              </Card>

              {/* Hibernation */}
              <Card style={{ borderTop: `3px solid ${C.purple}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 8, background: C.purpleLight, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>☾</div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>Hibernation</div>
                    {hibernationData.isHibernatingNow ? (
                      <Badge color={C.purple} bg={C.purpleLight} style={{ marginTop: 2 }}>Hibernating Now</Badge>
                    ) : (
                      <Badge color={C.muted} bg="#f3f4f6" style={{ marginTop: 2 }}>{hibernationData.activeSchedules} active schedules</Badge>
                    )}
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                  {[
                    { label: "Hours slept", value: hibernationData.hoursSlept.toString() },
                    { label: "Savings", value: `$${hibernationData.totalSavings}` },
                    { label: "Active schedules", value: hibernationData.activeSchedules.toString() },
                    { label: "Clusters", value: hibernationData.clustersOnSchedule.toString() },
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
            <ErrorBoundary label="Resource Hygiene">
            <Card style={{ marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
                <div style={{ display: "flex", gap: 24 }}>
                  {[
                    { label: "Safe to Delete", value: hygieneData.safeToDelete.toString(), color: C.red },
                    { label: "Orphaned", value: hygieneData.orphaned.toString(), color: C.amber },
                    { label: "Potential Savings", value: `$${(hygieneData?.potentialSavings || 0).toFixed(2)}/mo`, color: C.green },
                    { label: "Last Scan", value: hygieneData.lastScan ? hygieneData.lastScan.toLocaleDateString() : "Never", color: C.muted },
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
            </ErrorBoundary>

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
                  {clusters.length === 0 ? (
                    <div style={{ padding: "32px 18px", textAlign: "center", color: C.subtle, fontSize: 12 }}>
                      No clusters connected. Install the agent to start monitoring.
                    </div>
                  ) : (
                    <div>
                      {clusters.map((c, i) => (
                        <div key={c.id} onClick={() => navigate(`/clusters`)} style={{
                          display: "flex", alignItems: "center", gap: 12,
                          padding: "11px 16px", cursor: "pointer",
                          borderBottom: i < clusters.length - 1 ? `1px solid ${C.border}` : "none",
                          transition: "background 0.1s",
                        }}
                          onMouseEnter={e => e.currentTarget.style.background = C.bg}
                          onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                        >
                          <div style={{ width: 8, height: 8, borderRadius: "50%", background: c.status === "ACTIVE" ? C.green : C.amber, flexShrink: 0 }} />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontWeight: 600, fontSize: 13, color: C.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.name}</div>
                            <div style={{ fontSize: 11, color: C.subtle, marginTop: 1 }}>{c.region} · {c.node_count || c.nodes || 0} nodes</div>
                          </div>
                          <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
                            {c.agent_installed && <span style={{ fontSize: 10, fontWeight: 600, color: C.green, background: C.greenLight, padding: "2px 7px", borderRadius: 10 }}>Agent</span>}
                            <span style={{ fontSize: 10, fontWeight: 600, color: c.status === "ACTIVE" ? C.green : C.amber, background: c.status === "ACTIVE" ? C.greenLight : C.amberLight, padding: "2px 7px", borderRadius: 10 }}>{c.status}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </Card>
              </div>

              <div>
                <Card title="Node Templates" titleRight={
                  <button onClick={() => navigate('/ascp-ai?tab=rankings')} style={{ fontSize: 11, color: C.blue, background: "none", border: "none", cursor: "pointer" }}>Manage →</button>
                }>
                  <div style={{ color: C.subtle, fontSize: 12, marginBottom: 12 }}>
                    Templates filter instance pools for Balancekube.ai rankings.
                  </div>
                  <button onClick={() => navigate('/ascp-ai?tab=rankings')} style={{
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
                { label: "Pending Requests", value: approvalsData.pending, color: C.amber, icon: "⏳", sub: "Require your approval" },
                { label: "Active Grants", value: approvalsData.active, color: C.green, icon: "✓", sub: "Currently active JIT sessions" },
                { label: "Awaiting Consent", value: approvalsData.awaitingConsent, color: C.purple, icon: "◌", sub: "Need your acceptance" },
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
                  { label: "Members", icon: "⊹", value: `${teamsData.members} active members`, iconBg: "#f0fdf4" },
                  { label: "Teams", icon: "◻", value: `${teamsData.teams} teams created`, iconBg: "#f5f3ff" },
                  { label: "Roles & Policies", icon: "◎", value: `${teamsData.roles} system roles`, iconBg: "#eff6ff" },
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
