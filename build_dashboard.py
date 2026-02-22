import re

with open("changelogic.md", "r") as f:
    changelogic = f.read()

# Split the file to get just the JS code
# The code is basically the whole file, but let's extract from "// ─── MOCK DATA" to the end
idx = changelogic.find("// ─── MOCK DATA")
if idx == -1:
    print("MOCK DATA not found")
    exit(1)

new_dashboard = changelogic[idx:]

final_content = """import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDashboard } from '../../hooks/useDashboard';
import { auditAPI, clusterAPI, accountsAPI, approvalsAPI, metricsAPI } from '../../services/api';
import api from '../../services/api'; // For RI, S3, RDS, Transfer
import { useAuthStore } from '../../store/useStore';
import toast from 'react-hot-toast';

// Widgets
import ActivityFeed from './widgets/ActivityFeed';
import ClusterHealthCard from './widgets/ClusterHealthCard';
import FleetComposition from './widgets/FleetComposition';
import PendingApprovalsCard from './widgets/PendingApprovalsCard';
import CostKPICard from './widgets/CostKPICard';
import SavingsKPICard from './widgets/SavingsKPICard';
import SavingsChart from './widgets/SavingsChart';
import AgentStatusWidget from './widgets/AgentStatusWidget';
import SpendForecastWidget from './widgets/SpendForecastWidget';
import RIHealthCard from '../ri/RIHealthCard';
import S3HealthCard from '../s3/S3HealthCard';
import RDSHealthCard from '../rds/RDSHealthCard';
import TransferHealthCard from '../transfer/TransferHealthCard';

// Access Modal
import AccessRequestModal from '../approvals/AccessRequestModal';

"""

new_dashboard = new_dashboard.replace("export default function Dashboard() {", """export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { dashboardKPIs, loading: dashboardLoading, refreshDashboard } = useDashboard();
  
  const [dataLoading, setDataLoading] = useState(true);
  const [accounts, setAccounts] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [activityFeed, setActivityFeed] = useState([]);
  const [showAccessModal, setShowAccessModal] = useState(false);

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
        } catch (e) {}

        try {
            const s3 = await api.get('/api/v1/s3/overview');
            setS3Health({ status: s3.data.health_status || "no_data", buckets: s3.data.total_buckets || 0, savings: s3.data.potential_savings || 0, detail: `${s3.data.total_buckets || 0} buckets analyzed.` });
        } catch (e) {}
        
        try {
            const rds = await api.get('/api/v1/rds/overview');
            setRdsHealth({ status: rds.data.health_status || "no_data", instances: rds.data.total_instances || 0, savings: rds.data.potential_savings || 0, detail: `${rds.data.total_instances || 0} instances found.` });
        } catch (e) {}

        try {
            const transfer = await api.get('/api/v1/data-transfer/overview');
            setTransferHealth({ status: transfer.data.health_status || "no_data", cost: transfer.data.total_transfer_cost || 0, detail: `Total transfer cost: $${transfer.data.total_transfer_cost || 0}` });
        } catch (e) {}

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
""")

# Fix formatCurrency usage
new_dashboard = new_dashboard.replace('label="Monthly Spend" value="$0.00"', 'label="Monthly Spend" value={`$${(dashboardKPIs?.total_cost || 0).toFixed(2)}`}')
new_dashboard = new_dashboard.replace('label="Net Savings" value="$0.00"', 'label="Net Savings" value={`$${(dashboardKPIs?.estimated_savings || 0).toFixed(2)}`}')
new_dashboard = new_dashboard.replace('label="Spot Ratio" value="0%"', 'label="Spot Ratio" value={`${(dashboardKPIs?.optimization_rate || 0).toFixed(0)}%`}')
new_dashboard = new_dashboard.replace('sub="0 spot / 0 on-demand nodes"', 'sub="Calculated across all connected clusters"')
new_dashboard = new_dashboard.replace('label="Total Nodes" value="0"', 'label="Total Nodes" value={clusters.reduce((acc, c) => acc + (c.nodes || c.node_count || 0), 0)}')
new_dashboard = new_dashboard.replace('sub="0 clusters connected"', 'sub={`${clusters.length} clusters connected`}')

# Replace hardcoded widgets with real widgets
new_dashboard = new_dashboard.replace("""              {/* Spend Forecast */}
              <Card title="Spend Forecast" titleRight={<Badge color={C.green}>6 days left</Badge>}>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div>
                    <div style={{ fontSize: 11, color: C.muted, marginBottom: 2 }}>Current Spend (MTD)</div>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>$0.00</div>
                  </div>
                  <div style={{ height: 1, background: C.border }} />
                  <div>
                    <div style={{ fontSize: 11, color: C.muted, marginBottom: 2 }}>Projected (EOM)</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: C.green }}>$0.00</div>
                  </div>
                  <Sparkline data={[0, 0, 0, 0, 0, 0, 0]} color={C.blue} />
                </div>
              </Card>""", """              <SpendForecastWidget widgetKey="spend_forecast" />""")

new_dashboard = new_dashboard.replace("""              {/* Agent Status */}
              <Card title="Agent Status">
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {[
                    { label: "Healthy", count: 0, color: C.green },
                    { label: "Warning", count: 0, color: C.amber },
                    { label: "Stale", count: 0, color: C.red },
                  ].map(row => (
                    <div key={row.label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", alignItems: "center" }}>
                        <Dot color={row.color} />
                        <span style={{ fontSize: 13, color: C.muted }}>{row.label}</span>
                      </div>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{row.count}</span>
                    </div>
                  ))}
                  <div style={{ marginTop: 8, padding: "8px 10px", background: "#f9fafb", borderRadius: 8, textAlign: "center" }}>
                    <div style={{ fontSize: 11, color: C.subtle }}>Install agents on clusters to monitor health</div>
                  </div>
                </div>
              </Card>""", """              <AgentStatusWidget widgetKey="agent_status" />""")

new_dashboard = new_dashboard.replace("""              {/* Cluster Health */}
              <Card title="Cluster Health" titleRight={
                <button style={{ fontSize: 11, color: C.blue, background: "none", border: "none", cursor: "pointer" }}>View all →</button>
              }>
                <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  <div style={{
                    padding: "20px 0", textAlign: "center",
                    color: C.subtle, fontSize: 12
                  }}>
                    No clusters connected. <span style={{ color: C.blue, cursor: "pointer" }}>Connect AWS →</span>
                  </div>
                </div>
              </Card>""", """              <ClusterHealthCard widgetKey="cluster_health" data={{clusters}} />""")

new_dashboard = new_dashboard.replace("""{/* Fleet Composition */}
              <Card title="Fleet Composition">
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {[
                    { label: "Spot", pct: 0, color: C.green },
                    { label: "On-Demand", pct: 100, color: C.blue },
                  ].map(row => (
                    <div key={row.label}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <div style={{ display: "flex", alignItems: "center" }}><Dot color={row.color} /><span style={{ fontSize: 12 }}>{row.label}</span></div>
                        <span style={{ fontSize: 12, fontWeight: 600 }}>{row.pct}%</span>
                      </div>
                      <div style={{ height: 6, background: "#f3f4f6", borderRadius: 3 }}>
                        <div style={{ height: 6, width: `${row.pct}%`, background: row.color, borderRadius: 3, transition: "width 0.4s" }} />
                      </div>
                    </div>
                  ))}
                  <div style={{ marginTop: 4, padding: "6px 0", borderTop: `1px solid ${C.border}` }}>
                    <div style={{ fontSize: 11, color: C.subtle, textAlign: "center" }}>Connect clusters to see real fleet data</div>
                  </div>
                </div>
              </Card>""", """<FleetComposition widgetKey="fleet_composition" data={{}} />""")

new_dashboard = new_dashboard.replace("""              {/* Activity Feed */}
              <Card title="Recent Activity" titleRight={
                <button style={{ fontSize: 11, color: C.blue, background: "none", border: "none", cursor: "pointer" }}>View audit logs →</button>
              }>
                <div style={{ color: C.subtle, fontSize: 12, textAlign: "center", padding: "20px 0" }}>
                  No recent activity. Events will appear here once AWS is connected.
                </div>
              </Card>""", """              <ActivityFeed widgetKey="activity_feed" data={{activities: activityFeed}} />""")

new_dashboard = new_dashboard.replace("""            {/* ── ROW 4: Pending Approvals ── */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              {[
                { label: "Pending Requests", value: 0, color: C.amber, icon: "⏳" },
                { label: "Active Grants", value: 0, color: C.green, icon: "✓" },
                { label: "Awaiting Consent", value: 0, color: C.purple, icon: "◌" },
              ].map(item => (
                <div key={item.label} style={{
                  background: C.surface, border: `1px solid ${C.border}`,
                  borderRadius: 12, padding: "14px 18px",
                  display: "flex", alignItems: "center", gap: 12, cursor: "pointer"
                }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 10,
                    background: item.color + "14",
                    display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16
                  }}>{item.icon}</div>
                  <div>
                    <div style={{ color: C.muted, fontSize: 11 }}>{item.label}</div>
                    <div style={{ fontWeight: 700, fontSize: 20 }}>{item.value}</div>
                  </div>
                </div>
              ))}
            </div>""", """<PendingApprovalsCard widgetKey="pending_approvals" data={{}} />""")


new_dashboard = new_dashboard.replace("""<div style={{ padding: "24px 28px", maxWidth: 1400, margin: "0 auto" }}>

        {/* ── ONBOARDING BANNER (shown when no AWS account) ── */}
        <div style={{
          background: "linear-gradient(135deg, #1d4ed8 0%, #4f46e5 100%)",
          borderRadius: 12, padding: "18px 24px", marginBottom: 24,
          display: "flex", alignItems: "center", justifyContent: "space-between"
        }}>""", """<div style={{ padding: "24px 28px", maxWidth: 1400, margin: "0 auto" }}>

        {/* Access Modal */}
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
        }}>""")

new_dashboard = new_dashboard.replace("""<button style={{
            padding: "8px 18px", borderRadius: 8,
            background: "#fff", border: "none",
            color: C.indigo, fontWeight: 700, fontSize: 13,
            cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit"
          }}>Connect AWS Account →</button>
        </div>""", """<button onClick={handleConnectClick} style={{
            padding: "8px 18px", borderRadius: 8,
            background: "#fff", border: "none",
            color: C.indigo, fontWeight: 700, fontSize: 13,
            cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit"
          }}>Connect AWS Account →</button>
        </div>
        )}""")


# Real data for RI etc
new_dashboard = new_dashboard.replace("""detail="No Reserved Instances found. Connect AWS to analyze RI utilization."
                cta="Analyze RIs"
              />""", """detail={riHealth.detail || "Connect AWS to analyze RI utilization."}
                cta="Analyze RIs"
                onClick={() => navigate('/ri-analysis')}
              />""")

new_dashboard = new_dashboard.replace("""detail="No S3 buckets analyzed. Connect AWS to detect tiering savings."
                cta="Analyze S3"
              />""", """detail={s3Health.detail || "Connect AWS to detect tiering savings."}
                cta="Analyze S3"
                onClick={() => navigate('/s3-analysis')}
              />""")

new_dashboard = new_dashboard.replace("""detail="No RDS instances found. Connect AWS to detect Multi-AZ savings."
                cta="Analyze RDS"
              />""", """detail={rdsHealth.detail || "Connect AWS to detect Multi-AZ savings."}
                cta="Analyze RDS"
                onClick={() => navigate('/rds-analysis')}
              />""")

new_dashboard = new_dashboard.replace("""detail="No significant transfer costs detected yet."
                cta="Analyze Transfer"
              />""", """detail={transferHealth.detail || "No significant transfer costs detected yet."}
                cta="Analyze Transfer"
                onClick={() => navigate('/data-transfer')}
              />""")

final_content = final_content + new_dashboard

# We might also need to replace the bottom annotations/what's missing block because that's just notes
# However the user might actually want to see them as part of the display. Let's keep them and let the user remove later if they want.

with open("frontend/src/components/dashboard/Dashboard.jsx", "w", encoding="utf-8") as f:
    f.write(final_content)

print("Dashboard rewritten successfully")
