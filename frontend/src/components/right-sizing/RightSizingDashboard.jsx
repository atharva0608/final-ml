import React, { useState, useEffect, useRef } from "react";
import { useSearchParams } from 'react-router-dom';
import { clusterAPI, karpenterAPI } from "../../services/api";
import { toast } from "react-hot-toast";
import { FiCheckCircle, FiAlertTriangle, FiAlertCircle, FiClock } from "react-icons/fi";

// Theme primitives
const T = {
  bg: "#f8f9fb",
  surface: "#ffffff",
  border: "#e5e7eb",
  borderLight: "#f3f4f6",
  text: "#111827",
  textMid: "#374151",
  textMuted: "#6b7280",
  textFaint: "#9ca3af",
  primary: "#4f46e5", // Indigo for primary action
  primaryLight: "#eef2ff",
  green: "#059669",
  greenLight: "#ecfdf5",
  greenBorder: "#bbf7d0",
  amber: "#d97706",
  amberLight: "#fffbeb",
  amberBorder: "#fde68a",
  red: "#dc2626",
  redLight: "#fef2f2",
  cyan: "#0891b2",
  cyanLight: "#ecfeff",
  greyLight: "#f9fafb",
  greyBorder: "#d1d5db",
  greyDark: "#4b5563",
  shadow: "0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04)",
  shadowMd: "0 4px 6px -1px rgba(0,0,0,.07), 0 2px 4px -1px rgba(0,0,0,.04)",
};

const Card = ({ children, style = {}, className = "" }) => (
  <div className={className} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, boxShadow: T.shadow, ...style }}>
    {children}
  </div>
);

const SectionLabel = ({ children }) => (
  <div style={{ fontSize: 11, fontWeight: 700, color: T.textFaint, letterSpacing: ".08em", textTransform: "uppercase", marginBottom: 14 }}>
    {children}
  </div>
);

function Badge({ children, color = T.primary, bg = T.primaryLight, style = {} }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", background: bg, color, fontSize: 10, fontWeight: 600, padding: "3px 8px", borderRadius: 4, letterSpacing: ".02em", whiteSpace: "nowrap", ...style }}>
      {children}
    </span>
  );
}

// Global Banner Component
function AutoModeBanner({ isAutoOn, isLoading }) {
  if (isLoading) return null;
  return (
    <div style={{
      marginBottom: 20, padding: "14px 20px", borderRadius: 8, display: "flex", alignItems: "center", gap: 12,
      background: isAutoOn ? T.greenLight : T.amberLight,
      border: `1px solid ${isAutoOn ? T.greenBorder : T.amberBorder}`
    }}>
      <div style={{ fontSize: 18 }}>{isAutoOn ? "⚡" : "⏸"}</div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 700, color: isAutoOn ? T.green : T.amber }}>
          {isAutoOn ? "Auto Rightsizing is ON" : "Auto Rightsizing is OFF"}
        </div>
        <div style={{ fontSize: 12, color: T.textMid, marginTop: 2 }}>
          {isAutoOn
            ? "Stateless nodes are automatically resized based on policy. Stateful actions remain entirely manual."
            : "Manual approval is currently required for all stateless resize actions. Automation is paused."}
        </div>
      </div>
    </div>
  );
}

// Cluster Health & Exposure Bar
function ClusterHealthExposureBar({ statelessCount, statefulCount, eligibleCount, cooldownCount }) {
  const totalCount = statelessCount + statefulCount;
  return (
    <div style={{ marginBottom: 20 }}>
      {/* Top Horizontal Panel: Cluster Overview */}
      <Card style={{ padding: "20px", marginBottom: 16 }}>
        <SectionLabel>Cluster Overview</SectionLabel>
        <div style={{ display: "flex", gap: 16 }}>
          <div style={{ flex: 1, padding: 12, borderRadius: 8, background: T.bg, border: `1px solid ${T.borderLight}` }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: T.text }}>{totalCount}</div>
            <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, marginTop: 4 }}>Total Nodes</div>
          </div>
          <div style={{ flex: 1, padding: 12, borderRadius: 8, background: T.bg, border: `1px solid ${T.borderLight}` }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: T.text }}>{statelessCount}</div>
            <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, marginTop: 4 }}>Stateless</div>
          </div>
          <div style={{ flex: 1, padding: 12, borderRadius: 8, background: T.bg, border: `1px solid ${T.borderLight}` }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: T.greyDark }}>{statefulCount}</div>
            <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, marginTop: 4 }}>Stateful</div>
          </div>
          <div style={{ flex: 1, padding: 12, borderRadius: 8, background: T.primaryLight, border: `1px solid ${T.borderLight}` }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: T.primary }}>{eligibleCount}</div>
            <div style={{ fontSize: 11, color: T.primary, fontWeight: 600, marginTop: 4 }}>Eligible for Resize</div>
          </div>
          <div style={{ flex: 1, padding: 12, borderRadius: 8, background: T.amberLight, border: `1px solid ${T.amberBorder}` }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: T.amber }}>{cooldownCount}</div>
            <div style={{ fontSize: 11, color: T.amber, fontWeight: 600, marginTop: 4 }}>In Cooldown</div>
          </div>
        </div>
      </Card>

      {/* Exposure Snapshot */}
      <Card style={{ padding: "20px" }}>
        <SectionLabel>Exposure Snapshot</SectionLabel>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24 }}>
          {/* Charts placeholders */}
          <div style={{ background: T.bg, borderRadius: 8, border: `1px solid ${T.borderLight}`, padding: "16px", display: "flex", flexDirection: "column", alignItems: "center" }}>
            <h4 style={{ margin: "0 0 12px", fontSize: 13, color: T.textMid }}>Spot vs On-Demand Gauge</h4>
            <div style={{ width: "100%", height: "100px", background: "#e5e7eb", borderRadius: "100px 100px 0 0", position: "relative", overflow: "hidden" }}>
              <div style={{ position: "absolute", bottom: 0, left: 0, width: "60%", height: "100%", background: T.primary, transformOrigin: "bottom center" }}></div>
            </div>
            <p style={{ fontSize: 12, color: T.textMuted, marginTop: 12 }}>Spot: 60% → 78% (Proj)</p>
          </div>
          <div style={{ background: T.bg, borderRadius: 8, border: `1px solid ${T.borderLight}`, padding: "16px", display: "flex", flexDirection: "column", alignItems: "center" }}>
            <h4 style={{ margin: "0 0 12px", fontSize: 13, color: T.textMid }}>AZ Distribution Pie</h4>
            <div style={{ width: "100px", height: "100px", background: "conic-gradient(#4f46e5 0% 33%, #0891b2 33% 66%, #10b981 66% 100%)", borderRadius: "50%" }}></div>
            <p style={{ fontSize: 12, color: T.textMuted, marginTop: 12 }}>Imbalance Risk: <span style={{ color: T.amber, fontWeight: 600 }}>MEDIUM</span></p>
          </div>
          <div style={{ background: T.bg, borderRadius: 8, border: `1px solid ${T.borderLight}`, padding: "16px", display: "flex", flexDirection: "column", alignItems: "center" }}>
            <h4 style={{ margin: "0 0 12px", fontSize: 13, color: T.textMid }}>Instance Family Bar</h4>
            <div style={{ width: "100%", display: "flex", alignItems: "flex-end", gap: 8, height: "100px", background: "transparent" }}>
              <div style={{ flex: 1, background: T.greyBorder, height: "40%" }}></div>
              <div style={{ flex: 1, background: T.primary, height: "70%" }}></div>
              <div style={{ flex: 1, background: T.cyan, height: "55%" }}></div>
              <div style={{ flex: 1, background: T.amber, height: "20%" }}></div>
            </div>
            <p style={{ fontSize: 12, color: T.textMuted, marginTop: 12 }}>ARM: 20% → 55% (Proj)</p>
          </div>
        </div>
      </Card>
    </div>
  );
}

// Guard Panel
function ResizeGuardMonitoringPanel() {
  return (
    <Card style={{ padding: "20px", marginBottom: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <SectionLabel>Guard &amp; Stability Panel</SectionLabel>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: T.textMuted }}>Cluster Safety Score:</span>
          <span style={{ background: T.greenLight, color: T.green, padding: "4px 8px", borderRadius: 12, fontSize: 14, fontWeight: 800 }}>98/100</span>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12 }}>
        <div style={{ padding: 12, borderRadius: 8, background: T.bg, border: `1px solid ${T.borderLight}` }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.text }}>0</div>
          <div style={{ fontSize: 10, color: T.textMuted, fontWeight: 600, marginTop: 4 }}>Rollbacks (24h)</div>
        </div>
        <div style={{ padding: 12, borderRadius: 8, background: T.bg, border: `1px solid ${T.borderLight}` }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.amber }}>2</div>
          <div style={{ fontSize: 10, color: T.textMuted, fontWeight: 600, marginTop: 4 }}>Guard Triggers</div>
        </div>
        <div style={{ padding: 12, borderRadius: 8, background: T.greenLight, border: `1px solid ${T.greenBorder}` }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: T.green, marginTop: 6 }}>HEALTHY</div>
          <div style={{ fontSize: 10, color: T.green, fontWeight: 600, marginTop: 4 }}>Circuit Breaker</div>
        </div>
        <div style={{ padding: 12, borderRadius: 8, background: T.bg, border: `1px solid ${T.borderLight}` }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.text }}>5</div>
          <div style={{ fontSize: 10, color: T.textMuted, fontWeight: 600, marginTop: 4 }}>Max Concurrent</div>
        </div>
        <div style={{ padding: 12, borderRadius: 8, background: T.bg, border: `1px solid ${T.borderLight}` }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.primary }}>1</div>
          <div style={{ fontSize: 10, color: T.textMuted, fontWeight: 600, marginTop: 4 }}>Currently Running</div>
        </div>
        <div style={{ padding: 12, borderRadius: 8, background: T.bg, border: `1px solid ${T.borderLight}` }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.text }}>3</div>
          <div style={{ fontSize: 10, color: T.textMuted, fontWeight: 600, marginTop: 4 }}>Queue Length</div>
        </div>
      </div>
    </Card>
  );
}

// Stateless Detail Modal
function StatelessDetailedDrawer({ node, onClose, isAutoOn }) {
  if (!node) return null;
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: T.surface, width: 600, borderRadius: 12, padding: "24px", boxShadow: "0 20px 40px rgba(0,0,0,.2)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
          <div>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: T.text, margin: 0, display: "flex", gap: 8, alignItems: "center" }}>
              {node.name}
              <Badge color={T.primary} bg={T.primaryLight}>Stateless</Badge>
            </h3>
            <p style={{ fontSize: 13, color: T.textMuted, margin: "4px 0 0" }}>{node.current} → {node.recommended}</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 24, cursor: "pointer", color: T.textFaint }}>&times;</button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
          <div style={{ padding: 16, background: T.bg, borderRadius: 8, border: `1px solid ${T.border}` }}>
            <div style={{ fontSize: 12, color: T.textMuted, fontWeight: 600 }}>Top Candidate Sizes</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginTop: 4 }}>1. {node.recommended}<br />2. {node.recommended.replace('large', 'xlarge')}<br />3. c6g.large</div>
          </div>
          <div style={{ padding: 16, background: T.bg, borderRadius: 8, border: `1px solid ${T.border}` }}>
            <div style={{ fontSize: 12, color: T.textMuted, fontWeight: 600 }}>Diversification Check</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.green, marginTop: 4 }}>Passed (Within Limits)</div>
          </div>
          <div style={{ padding: 16, background: T.bg, borderRadius: 8, border: `1px solid ${T.border}` }}>
            <div style={{ fontSize: 12, color: T.textMuted, fontWeight: 600 }}>Headroom / Volatility applied</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginTop: 4 }}>{node.cpu}% P95 CPU (1.2x headroom)<br />{node.confidence < 60 ? '1.5x Volatility' : 'Normal Volatility'} </div>
          </div>
          <div style={{ padding: 16, background: T.bg, borderRadius: 8, border: `1px solid ${T.border}` }}>
            <div style={{ fontSize: 12, color: T.textMuted, fontWeight: 600 }}>Capacity DryRun / Cooldown</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: node.cooldown ? T.amber : T.green, marginTop: 4 }}>
              {node.cooldown ? 'Wait 3h' : 'ICE Checked: Available'}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, justifyContent: "flex-end", marginTop: 24, paddingTop: 16, borderTop: `1px solid ${T.border}` }}>
          <button onClick={onClose} style={{ padding: "8px 16px", borderRadius: 6, border: `1px solid ${T.border}`, background: T.surface, color: T.textMid, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Close</button>
          {!isAutoOn && (
            <button style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: T.primary, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Apply Now (Manual Override)</button>
          )}
        </div>
      </div>
    </div>
  );
}

// Stateful Proposal Flow Modal
function StatefulProposalModal({ node, onClose }) {
  if (!node) return null;
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,.4)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: T.surface, width: 500, borderRadius: 12, padding: "24px", boxShadow: "0 20px 40px rgba(0,0,0,.2)", border: `2px solid ${T.greyBorder}` }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: T.text, margin: 0, display: "flex", gap: 8, alignItems: "center" }}>
              Submit Manual Resize
              <Badge color={T.greyDark} bg={T.greyLight} style={{ border: `1px solid ${T.border}` }}>Stateful</Badge>
            </h3>
            <p style={{ fontSize: 13, color: T.textMuted, margin: "4px 0 0" }}>Node: {node.name}</p>
          </div>
        </div>

        <div style={{ padding: "12px 16px", background: T.amberLight, borderRadius: 8, border: `1px solid ${T.amberBorder}`, marginBottom: 20 }}>
          <p style={{ fontSize: 13, color: T.amber, margin: 0, lineHeight: 1.5, fontWeight: 500 }}>
            Spot pools are strictly locked for stateful workloads. This node will be resized using On-Demand instances.
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "16px", background: T.bg, borderRadius: 8, border: `1px solid ${T.border}`, marginBottom: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <span style={{ color: T.textMuted }}>Current Type</span>
            <span style={{ fontWeight: 600 }}>{node.current}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <span style={{ color: T.textMuted }}>Proposed Type</span>
            <span style={{ fontWeight: 600, color: T.primary }}>{node.recommended}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <span style={{ color: T.textMuted }}>Estimated Savings</span>
            <span style={{ fontWeight: 600, color: T.green }}>${node.savings}/mo</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
            <span style={{ color: T.textMuted }}>Peak Buffer Margin</span>
            <span style={{ fontWeight: 600 }}>~35% headroom remaining</span>
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ padding: "8px 16px", borderRadius: 6, border: `1px solid ${T.border}`, background: T.surface, color: T.textMid, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Cancel</button>
          <button
            onClick={() => {
              karpenterAPI.applyRecommendation(node.id, {
                instance_id: node.name,
                recommended_type: node.recommended,
                is_stateful: true,
              }).then(() => {
                toast.success(`Resize queued: ${node.name} → ${node.recommended} (On-Demand)`);
                onClose();
              }).catch(() => toast.error('Submit failed — check permissions'));
            }}
            style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: T.greyDark, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            Submit for Approval
          </button>
        </div>
      </div>
    </div>
  );
}


// Stateless Section (Blue/Green Accent)
function StatelessSection({ nodes, isAutoOn }) {
  const [selectedNode, setSelectedNode] = useState(null);

  const eligibleNodes = nodes.filter(n => n.savings > 0 && n.cooldown !== true);
  const totalSavings = eligibleNodes.reduce((a, b) => a + Number(b.savings), 0);

  return (
    <div style={{ marginBottom: 32 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: T.text, margin: 0, display: "flex", alignItems: "center", gap: 10 }}>
            Stateless Nodes (Auto-Managed)
            {isAutoOn ? <Badge color={T.green} bg={T.greenLight}>AUTO ENABLED</Badge> : <Badge color={T.amber} bg={T.amberLight}>MANUAL MODE</Badge>}
          </h2>
          <p style={{ fontSize: 13, color: T.textMuted, margin: "4px 0 0" }}>Workloads safe for automatic vertically scaling and spot migration.</p>
        </div>
        {!isAutoOn && eligibleNodes.length > 0 && (
          <button onClick={() => toast.success("Applying all eligible stateless resizes...")} style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: T.primary, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", boxShadow: T.shadow }}>
            Apply All Eligible Resizes (${totalSavings}/mo)
          </button>
        )}
      </div>

      <div style={{ display: "flex", gap: 24, marginBottom: 20 }}>
        <div style={{ flex: 1, borderTop: `4px solid ${T.green}`, background: T.surface, padding: "16px", borderRadius: "0 0 8px 8px", boxShadow: T.shadow }}>
          <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, textTransform: "uppercase" }}>Projected Total Savings</div>
          <div style={{ fontSize: 24, fontWeight: 800, color: T.green, marginTop: 4 }}>${totalSavings}/mo</div>
        </div>
        <div style={{ flex: 1, borderTop: `4px solid ${T.primary}`, background: T.surface, padding: "16px", borderRadius: "0 0 8px 8px", boxShadow: T.shadow }}>
          <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, textTransform: "uppercase" }}>Safe to Execute</div>
          <div style={{ fontSize: 24, fontWeight: 800, color: T.text, marginTop: 4 }}>{eligibleNodes.length}</div>
        </div>
        <div style={{ flex: 1, borderTop: `4px solid ${T.amber}`, background: T.surface, padding: "16px", borderRadius: "0 0 8px 8px", boxShadow: T.shadow }}>
          <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, textTransform: "uppercase" }}>Blocked by Policy</div>
          <div style={{ fontSize: 24, fontWeight: 800, color: T.amber, marginTop: 4 }}>{nodes.filter(n => n.cooldown).length}</div>
        </div>
      </div>

      <Card>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
          <thead>
            <tr style={{ background: T.bg, borderBottom: `1px solid ${T.border}` }}>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Node</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Current Type</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>CPU / Mem</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Bin-Packed Size</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Optimal Action</th>
              {!isAutoOn && <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Best Spot Pool</th>}
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Savings</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>EV</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Status</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11, textAlign: "right" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {nodes.length === 0 ? (
              <tr><td colSpan={isAutoOn ? 9 : 10} style={{ padding: "24px", textAlign: "center", color: T.textMuted }}>No stateless nodes found.</td></tr>
            ) : nodes.map((n, i) => {
              const isSameType = n.recommended === n.current;
              const hasSpotPool = !!n.spot_pool;
              // Derive optimal action strategy badge
              const strategy = n.is_upsize
                ? { label: '⚠ Scale Up', color: T.red, bg: T.redLight }
                : (!isSameType && hasSpotPool)
                  ? { label: '✦ Resize + Spot', color: T.primary, bg: T.primaryLight }
                  : (!isSameType && !hasSpotPool)
                    ? { label: '↓ Resize Only', color: T.cyan, bg: T.cyanLight }
                    : (isSameType && hasSpotPool)
                      ? { label: '⟳ Spot Pool', color: '#7c3aed', bg: '#ede9fe' }
                      : { label: '✓ No Change', color: T.textMuted, bg: T.bg };
              return (
                <tr key={n.id} style={{ borderBottom: i === nodes.length - 1 ? "none" : `1px solid ${T.borderLight}`, background: T.surface, transition: "background 0.2s" }} onMouseEnter={e => e.currentTarget.style.background = T.bg} onMouseLeave={e => e.currentTarget.style.background = T.surface}>
                  <td style={{ padding: "12px 16px", fontWeight: 500, color: T.primary, cursor: "pointer" }} onClick={() => setSelectedNode(n)}>{n.name}</td>
                  <td style={{ padding: "12px 16px", color: T.textMid }}>{n.current}</td>
                  <td style={{ padding: "12px 16px", color: T.textMid }}>
                    <span style={{ color: n.cpu > 80 ? T.red : T.textMid }}>{n.cpu}%</span>
                    {' / '}
                    <span style={{ color: n.mem > 80 ? T.red : T.textMid }}>{n.mem}%</span>
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    {isSameType ? (
                      <span style={{ color: T.textMuted, fontSize: 12 }}>—</span>
                    ) : n.is_upsize ? (
                      <span style={{ fontWeight: 700, color: T.red }}>
                        {n.recommended}
                        <span style={{ fontSize: 11, color: T.red, marginLeft: 4 }}>(+${Math.abs(n.resize_savings)}/mo)</span>
                      </span>
                    ) : (
                      <span style={{ fontWeight: 700, color: T.green }}>
                        {n.recommended}
                        {n.resize_savings > 0 && <span style={{ fontSize: 11, color: T.textMuted, marginLeft: 4 }}>(−${n.resize_savings}/mo)</span>}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", background: strategy.bg, color: strategy.color, fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 4, whiteSpace: "nowrap" }}>
                      {strategy.label}
                    </span>
                  </td>
                  {!isAutoOn && (
                    <td style={{ padding: "12px 16px" }}>
                      {hasSpotPool ? (
                        <div>
                          <div style={{ fontWeight: 600, color: T.cyan, fontSize: 12 }}>{n.spot_pool.instance_type}</div>
                          <div style={{ fontSize: 11, color: T.textMuted }}>{n.spot_pool.az} · risk {n.spot_pool.risk_score}</div>
                          {n.spot_pool.predicted_savings_pct > 0 && (
                            <div style={{ fontSize: 11, color: T.green, fontWeight: 600 }}>−{n.spot_pool.predicted_savings_pct}% vs OD</div>
                          )}
                        </div>
                      ) : (
                        <span style={{ color: T.textMuted, fontSize: 12 }}>—</span>
                      )}
                    </td>
                  )}
                  <td style={{ padding: "12px 16px", fontWeight: 600 }}>
                    {n.is_upsize ? (
                      <span style={{ color: T.red }}>+${Math.abs(n.savings)}/mo</span>
                    ) : (
                      <div>
                        <span style={{ color: T.green }}>${n.savings}/mo</span>
                        {n.savings_pct > 0 && (
                          <span style={{ fontSize: 11, color: T.green, marginLeft: 4, fontWeight: 700 }}>({n.savings_pct}%)</span>
                        )}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    {n.is_upsize
                      ? <span style={{ color: T.red, fontWeight: 700 }}>—</span>
                      : <span style={{ color: n.ev_pct > 80 ? T.green : T.amber, fontWeight: 600 }}>{n.ev_pct}%</span>
                    }
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    {n.is_upsize ? (
                      <Badge color={T.red} bg={T.redLight}><FiAlertTriangle size={12} style={{ marginRight: 2 }} />Scale Up</Badge>
                    ) : n.cooldown ? (
                      <Badge color={T.amber} bg={T.amberLight}><FiClock size={12} style={{ marginRight: 2 }} />Cooldown</Badge>
                    ) : n.confidence < 60 ? (
                      <Badge color={T.red} bg={T.redLight}>High Volatility</Badge>
                    ) : (
                      <Badge color={T.green} bg={T.greenLight}>Ready</Badge>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px", textAlign: "right" }}>
                    {isAutoOn ? (
                      <span style={{ fontSize: 12, color: T.textFaint, fontStyle: "italic" }}>Auto-managed</span>
                    ) : (
                      <button
                        disabled={n.cooldown}
                        onClick={(e) => {
                          e.stopPropagation();
                          karpenterAPI.applyRecommendation(n.id, {
                            instance_id: n.name,
                            recommended_type: n.recommended,
                            spot_pool: n.spot_pool,
                          }).then(() => toast.success(`Queued: ${n.name} → ${n.recommended}${n.spot_pool ? ` + ${n.spot_pool.instance_type} spot` : ''}`))
                            .catch(() => toast.error('Apply failed — check permissions'));
                        }}
                        style={{ padding: "6px 12px", background: n.cooldown ? T.bg : n.is_upsize ? T.redLight : T.primaryLight, color: n.cooldown ? T.textMuted : n.is_upsize ? T.red : T.primary, border: `1px solid ${n.cooldown ? T.border : n.is_upsize ? T.red : T.primary}`, borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: n.cooldown ? "not-allowed" : "pointer" }}>
                        {n.is_upsize ? 'Scale Up' : n.spot_pool ? 'Optimize' : 'Apply'}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Card>

      {/* Execution Timeline preview */}
      <div style={{ marginTop: 16, padding: "16px 20px", background: T.bg, borderRadius: 8, border: `1px solid ${T.borderLight}`, fontSize: 12, color: T.textMuted }}>
        <strong style={{ color: T.textMid }}>Execution Timeline:</strong>
        <span style={{ marginLeft: 12 }}>✓ Resize proposed (14:30)</span>
        <span style={{ marginLeft: 12 }}>✓ PDB checks passed (14:32)</span>
        <span style={{ marginLeft: 12 }}>✓ Substitute provisioned &amp; attached (14:35)</span>
      </div>

      <StatelessDetailedDrawer node={selectedNode} onClose={() => setSelectedNode(null)} isAutoOn={isAutoOn} />
    </div>
  );
}


// Stateful Section (Grey Accent)
function StatefulSection({ nodes }) {
  const [selectedNode, setSelectedNode] = useState(null);

  const eligibleNodes = nodes.filter(n => n.savings > 0 && n.status !== "Blocked by Policy");

  return (
    <div style={{ marginBottom: 32 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: T.text, margin: 0, display: "flex", alignItems: "center", gap: 10 }}>
            Stateful Nodes (Manual Only)
            <Badge color={T.greyDark} bg={T.greyLight} style={{ border: `1px solid ${T.border}` }}>MANUAL ONLY</Badge>
          </h2>
          <p style={{ fontSize: 13, color: T.textMuted, margin: "4px 0 0" }}>Strictly isolated from automated resizing and spot pool logic.</p>
        </div>
      </div>

      <Card style={{ background: T.greyLight, border: `1px solid ${T.border}` }}>
        <div style={{ padding: "16px 20px", borderBottom: `1px solid ${T.border}`, display: "flex", gap: 32 }}>
          <div>
            <div style={{ fontSize: 11, color: T.textMuted, textTransform: "uppercase", fontWeight: 600 }}>Total Stateful Nodes</div>
            <div style={{ fontSize: 20, fontWeight: 800, color: T.greyDark, marginTop: 4 }}>{nodes.length}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: T.textMuted, textTransform: "uppercase", fontWeight: 600 }}>Eligible for Propose</div>
            <div style={{ fontSize: 20, fontWeight: 800, color: T.greyDark, marginTop: 4 }}>{eligibleNodes.length}</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: T.textMuted, textTransform: "uppercase", fontWeight: 600 }}>On-Demand Savings Potential</div>
            <div style={{ fontSize: 20, fontWeight: 800, color: T.green, marginTop: 4 }}>${nodes.reduce((a, b) => a + Number(b.savings), 0)}/mo</div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: T.textMuted, textTransform: "uppercase", fontWeight: 600 }}>Max Downscale Allowed</div>
            <div style={{ fontSize: 20, fontWeight: 800, color: T.amber, marginTop: 4 }}>50%</div>
          </div>
        </div>

        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
          <thead>
            <tr style={{ background: "#f0f2f5", borderBottom: `1px solid ${T.border}` }}>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Node</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Current Type</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>CPU / Mem</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Recommended</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>On-Demand Savings</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Policy Status</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11, textAlign: "right" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {nodes.length === 0 ? (
              <tr><td colSpan="7" style={{ padding: "24px", textAlign: "center", color: T.textMuted }}>No stateful nodes found.</td></tr>
            ) : nodes.map((n, i) => (
              <tr key={n.id} style={{ borderBottom: i === nodes.length - 1 ? "none" : `1px solid ${T.borderLight}`, background: T.surface }}>
                <td style={{ padding: "12px 16px", fontWeight: 500, color: T.text }}>{n.name}</td>
                <td style={{ padding: "12px 16px", color: T.textMid }}>{n.current}</td>
                <td style={{ padding: "12px 16px", color: T.textMid }}>{n.cpu}% / {n.mem}%</td>
                <td style={{ padding: "12px 16px", fontWeight: 600, color: T.text }}>{n.recommended}</td>
                <td style={{ padding: "12px 16px", fontWeight: 600 }}>
                  <span style={{ color: T.green }}>${n.savings}/mo</span>
                  {n.savings_pct > 0 && (
                    <span style={{ fontSize: 11, color: T.green, marginLeft: 4, fontWeight: 700 }}>({n.savings_pct}%)</span>
                  )}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  {n.status === "Blocked by Policy" ? (
                    <span style={{ fontSize: 12, color: T.amber }}>Blocked by Policy</span>
                  ) : (
                    <span style={{ fontSize: 12, color: T.green }}>Approved by Policy</span>
                  )}
                </td>
                <td style={{ padding: "12px 16px", textAlign: "right" }}>
                  {n.status === "Blocked by Policy" ? (
                    <span style={{ fontSize: 12, color: T.textFaint }}>Blocked</span>
                  ) : (
                    <button
                      onClick={() => setSelectedNode(n)}
                      style={{ padding: "6px 12px", background: T.amberLight, color: T.amber, border: `1px solid ${T.amberBorder}`, borderRadius: 6, fontSize: 12, fontWeight: 800, cursor: "pointer" }}>
                      Request Approval
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <StatefulProposalModal node={selectedNode} onClose={() => setSelectedNode(null)} />
    </div>
  );
}

// Karpenter Configuration Panel
function KarpenterConfigPanel({ clusterId, initialConfig, onSaved }) {
  const INSTANCE_FAMILIES = ['m5', 'm6i', 'c5', 'c6i', 't3', 't4g', 'c6g', 'm6g'];

  const [form, setForm] = useState({
    auto_rebalancing_enabled: initialConfig?.auto_rebalancing_enabled ?? false,
    auto_rightsizing_enabled: initialConfig?.auto_rightsizing_enabled ?? false,
    strategy: initialConfig?.strategy || 'balanced',
    spot_target_pct: initialConfig?.spot_target_pct ?? 75,
    buffer_pct: initialConfig?.buffer_pct ?? 30,
    instance_families: initialConfig?.instance_families || ['m5', 'm6i', 'c5', 'c6i', 't3', 't4g'],
    consolidation_enabled: initialConfig?.consolidation_enabled ?? true,
    consolidation_threshold: initialConfig?.consolidation_threshold ?? 80,
    stateful_max_downscale_pct: initialConfig?.stateful_max_downscale_pct ?? 50,
    stateful_od_rightsizing: initialConfig?.stateful_od_rightsizing ?? true,
  });
  const [saving, setSaving] = useState(false);

  const toggle = (field) => setForm(f => ({ ...f, [field]: !f[field] }));
  const set = (field, val) => setForm(f => ({ ...f, [field]: val }));
  const toggleFamily = (fam) => setForm(f => {
    const fams = f.instance_families.includes(fam)
      ? f.instance_families.filter(x => x !== fam)
      : [...f.instance_families, fam];
    return { ...f, instance_families: fams };
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      await karpenterAPI.updateConfig(clusterId, form);
      await karpenterAPI.switchMode(clusterId, form.auto_rebalancing_enabled ? 'auto' : 'dry_run');
      await clusterAPI.updateOptimizationSettings(clusterId, { auto_rightsizing_enabled: form.auto_rightsizing_enabled });
      toast.success('Karpenter configuration saved');
      if (onSaved) onSaved(form);
    } catch {
      toast.error('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const ToggleSwitch = ({ value, onToggle }) => (
    <div onClick={onToggle} style={{ width: 44, height: 24, borderRadius: 12, background: value ? T.green : T.border, cursor: 'pointer', position: 'relative', transition: 'background 0.2s', flexShrink: 0 }}>
      <div style={{ position: 'absolute', top: 3, left: value ? 23 : 3, width: 18, height: 18, borderRadius: 9, background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,.2)', transition: 'left 0.2s' }} />
    </div>
  );

  const ToggleRow = ({ label, desc, field }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 0', borderBottom: `1px solid ${T.borderLight}` }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{label}</div>
        {desc && <div style={{ fontSize: 12, color: T.textMuted, marginTop: 2 }}>{desc}</div>}
      </div>
      <ToggleSwitch value={form[field]} onToggle={() => toggle(field)} />
    </div>
  );

  return (
    <div style={{ display: 'flex', gap: 24 }}>
      {/* Left: Strategy (Auto toggles moved to Cluster Settings) */}
      <Card style={{ flex: 1, padding: '24px' }}>
        <div style={{ marginTop: 0 }}>
          <SectionLabel>Optimization Strategy</SectionLabel>
          <div style={{ display: 'flex', gap: 8 }}>
            {['balanced', 'cost-first', 'performance-first'].map(s => (
              <button key={s} onClick={() => set('strategy', s)} style={{ flex: 1, padding: '8px 0', borderRadius: 6, border: `1px solid ${form.strategy === s ? T.primary : T.border}`, background: form.strategy === s ? T.primaryLight : T.surface, color: form.strategy === s ? T.primary : T.textMid, fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                {s.replace('-', ' ')}
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 24 }}>
          <SectionLabel>Spot Target %</SectionLabel>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <input type="range" min="0" max="100" step="5" value={form.spot_target_pct} onChange={e => set('spot_target_pct', Number(e.target.value))} style={{ flex: 1 }} />
            <span style={{ fontSize: 14, fontWeight: 700, color: T.primary, minWidth: 40 }}>{form.spot_target_pct}%</span>
          </div>
          <div style={{ fontSize: 11, color: T.textMuted, marginTop: 4 }}>Target percentage of nodes on spot instances</div>
        </div>

        <div style={{ marginTop: 24 }}>
          <SectionLabel>Buffer % (Safety Headroom)</SectionLabel>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <input type="number" min="10" max="100" value={form.buffer_pct} onChange={e => set('buffer_pct', Number(e.target.value))} style={{ width: 80, padding: '6px 10px', border: `1px solid ${T.border}`, borderRadius: 6, fontSize: 14, fontWeight: 600, color: T.text }} />
            <span style={{ fontSize: 12, color: T.textMuted }}>% above P95 usage — applied during bin-packing</span>
          </div>
        </div>
      </Card>

      {/* Right: Instance families + Stateful policy */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 20 }}>
        <Card style={{ padding: '24px' }}>
          <SectionLabel>Allowed Instance Families</SectionLabel>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {INSTANCE_FAMILIES.map(fam => {
              const selected = form.instance_families.includes(fam);
              return (
                <div key={fam} onClick={() => toggleFamily(fam)} style={{ padding: '6px 14px', borderRadius: 6, cursor: 'pointer', background: selected ? T.primaryLight : T.bg, border: `1px solid ${selected ? T.primary : T.border}`, color: selected ? T.primary : T.textMid, fontSize: 13, fontWeight: 600 }}>
                  {fam}
                </div>
              );
            })}
          </div>
          <div style={{ fontSize: 11, color: T.textMuted, marginTop: 8 }}>Click to toggle. Bin-packing only considers selected families.</div>

          <div style={{ marginTop: 20 }}>
            <ToggleRow label="Consolidation" desc="Automatically consolidate underutilized nodes (Karpenter native)" field="consolidation_enabled" />
            {form.consolidation_enabled && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingTop: 12 }}>
                <span style={{ fontSize: 13, color: T.textMuted }}>Trigger threshold:</span>
                <input type="number" min="50" max="95" value={form.consolidation_threshold} onChange={e => set('consolidation_threshold', Number(e.target.value))} style={{ width: 70, padding: '5px 8px', border: `1px solid ${T.border}`, borderRadius: 6, fontSize: 13, fontWeight: 600 }} />
                <span style={{ fontSize: 12, color: T.textMuted }}>% utilization</span>
              </div>
            )}
          </div>
        </Card>

        <Card style={{ padding: '24px' }}>
          <SectionLabel>Stateful Node Policy</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: T.bg, borderRadius: 8, border: `1px solid ${T.borderLight}` }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>Max Downscale</div>
                <div style={{ fontSize: 11, color: T.textMuted }}>Maximum allowed instance size reduction per resize action</div>
              </div>
              <span style={{ fontSize: 16, fontWeight: 700, color: T.amber }}>{form.stateful_max_downscale_pct}%</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: T.bg, borderRadius: 8, border: `1px solid ${T.borderLight}` }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>Spot Migration</div>
                <div style={{ fontSize: 11, color: T.textMuted }}>Stateful nodes are never migrated to spot</div>
              </div>
              <Badge color={T.red} bg={T.redLight}>Always Disabled</Badge>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: T.bg, borderRadius: 8, border: `1px solid ${T.borderLight}` }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>On-Demand Rightsizing</div>
                <div style={{ fontSize: 11, color: T.textMuted }}>Propose smaller OD instance via bin-packing (no spot)</div>
              </div>
              <ToggleSwitch value={form.stateful_od_rightsizing} onToggle={() => toggle('stateful_od_rightsizing')} />
            </div>
          </div>
        </Card>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={handleSave} disabled={saving} style={{ padding: '10px 28px', borderRadius: 8, border: 'none', background: T.primary, color: '#fff', fontSize: 14, fontWeight: 600, cursor: saving ? 'wait' : 'pointer', opacity: saving ? 0.7 : 1, boxShadow: T.shadow }}>
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  );
}

// MAIN PAGE
export default function RightSizingMonitoringDashboard() {
  const [clusters, setClusters] = useState([]);
  const [selectedClusterId, setSelectedClusterId] = useState("all");
  const [autoState, setAutoState] = useState(false); // is auto rightsizing enabled?
  const [loading, setLoading] = useState(true);
  const [searchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'karpenter';

  // Data lists
  const [statelessNodes, setStatelessNodes] = useState([]);
  const [statefulNodes, setStatefulNodes] = useState([]);

  // Execution Plan and History state
  const [executionPlan, setExecutionPlan] = useState([]);
  const [historyData, setHistoryData] = useState({ history: [], kpis: { resizes_this_month: 0, net_savings_monthly: 0, success_rate_pct: 0 } });
  const [executionLoading, setExecutionLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Karpenter config state
  const [karpenterConfig, setKarpenterConfig] = useState(null);
  const [configLoading, setConfigLoading] = useState(false);

  // Fetch clusters list
  useEffect(() => {
    clusterAPI.listClusters().then(res => {
      const data = res.data?.items || res.data?.clusters || res.data || [];
      const cl = Array.isArray(data) ? data : [];
      setClusters(cl);
      if (cl.length > 0) setSelectedClusterId(cl[0].id);
    }).catch(console.error);
  }, []);

  // Fetch karpenter config when config tab is active
  useEffect(() => {
    if (activeTab !== 'config' || selectedClusterId === 'all' || !selectedClusterId) return;
    setConfigLoading(true);
    karpenterAPI.getConfig(selectedClusterId)
      .then(res => setKarpenterConfig(res.data || {}))
      .catch(() => setKarpenterConfig({}))
      .finally(() => setConfigLoading(false));
  }, [activeTab, selectedClusterId]);

  // Fetch execution plan and history when tab changes
  useEffect(() => {
    if (selectedClusterId === "all" || !selectedClusterId) return;
    if (activeTab === 'history') {
      setExecutionLoading(true);
      karpenterAPI.getExecutionPlan(selectedClusterId)
        .then(res => setExecutionPlan(res.data?.plan || []))
        .catch(() => setExecutionPlan([]))
        .finally(() => setExecutionLoading(false));
    } else if (activeTab === 'savings') {
      setHistoryLoading(true);
      karpenterAPI.getHistory(selectedClusterId)
        .then(res => setHistoryData({
          history: res.data?.history || [],
          kpis: res.data?.kpis || { resizes_this_month: 0, net_savings_monthly: 0, success_rate_pct: 0 }
        }))
        .catch(() => setHistoryData({ history: [], kpis: { resizes_this_month: 0, net_savings_monthly: 0, success_rate_pct: 0 } }))
        .finally(() => setHistoryLoading(false));
    }
  }, [activeTab, selectedClusterId]);

  // Fetch Unified Config and Recommendations when selected cluster changes
  useEffect(() => {
    if (selectedClusterId === "all" || !selectedClusterId) return;

    setLoading(true);
    Promise.all([
      clusterAPI.getOptimizationSettings(selectedClusterId).catch(() => ({ data: null })),
      karpenterAPI.getRecommendations(selectedClusterId).catch(() => ({ data: { recommendations: [] } }))
    ]).then(([configRes, recsRes]) => {
      // 1. Get Auto State
      const c = configRes.data;
      const isAuto = c?.automation_controls?.auto_rightsizing_enabled ?? false;
      setAutoState(isAuto);

      // 2. Map real recommendations into stateless (spot) / stateful (on-demand) buckets.
      const rawRecs = recsRes.data?.recommendations || [];

      let sNodes = [];
      let stNodes = [];

      if (rawRecs.length > 0) {
        sNodes = rawRecs
          .filter(r => r.node_type === 'stateless' || (r.current_lifecycle || '').includes('spot'))
          .map((r, i) => ({
            id: r.id || `stateless-${i}`,
            name: r.instance_id || `spot-node-${i}`,
            current: r.current_type || 'unknown',
            recommended: r.recommended_type || r.current_type || 'unknown',
            cpu: r.cpu ?? 0,
            mem: r.mem ?? 0,
            savings: Math.round(r.potential_savings || 0),
            savings_pct: r.savings_pct ?? 0,
            resize_savings: r.resize_savings ?? 0,          // can be negative (upsize)
            spot_pool: r.spot_pool || null,
            ev_pct: r.ev_pct ?? (r.risk_prob != null ? Math.max(0, 100 - r.risk_prob) : 85),
            confidence: r.risk_prob != null ? Math.max(0, 100 - r.risk_prob) : 85,
            impact: r.impact || 'Neutral',
            is_upsize: r.is_upsize || false,                // over-utilised node needs scale-up
            reason: r.reason || '',
            cooldown: false,
          }));

        stNodes = rawRecs
          .filter(r => r.node_type === 'stateful' && !(r.current_lifecycle || '').includes('spot'))
          .map((r, i) => ({
            id: r.id || `stateful-${i}`,
            name: r.instance_id || `od-node-${i}`,
            current: r.current_type || 'unknown',
            recommended: r.recommended_type || r.current_type || 'unknown',
            cpu: r.cpu ?? 0,
            mem: r.mem ?? 0,
            savings: Math.round(r.potential_savings || 0),
            savings_pct: r.savings_pct ?? 0,
            resize_savings: Math.round(r.resize_savings || 0),
            reason: r.reason || '',
            status: 'Ready',
          }));
      }
      // If rawRecs is empty, sNodes and stNodes stay [] — no mock fallback.

      setStatelessNodes(sNodes);
      setStatefulNodes(stNodes);
      setLoading(false);
    });
  }, [selectedClusterId]);

  return (
    <div style={{ fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif", color: T.text, padding: "24px 28px", maxWidth: 1440, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, color: T.text }}>Right-Sizing Monitoring</h1>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: T.textMid }}>Select Cluster:</span>
          <select
            value={selectedClusterId}
            onChange={e => setSelectedClusterId(e.target.value)}
            style={{ padding: "8px 32px 8px 12px", borderRadius: 8, border: `1px solid ${T.border}`, background: T.surface, fontSize: 13, fontWeight: 600, color: T.text, cursor: "pointer", appearance: "none" }}
          >
            <option value="all" disabled>Select a cluster...</option>
            {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      </div>

      {/* TOP TABS */}

      {!loading && selectedClusterId !== "all" && (
        <>
          <AutoModeBanner isAutoOn={autoState} isLoading={loading} />

          {activeTab === 'karpenter' && (
            <>
              <ClusterHealthExposureBar
                statelessCount={statelessNodes.length}
                statefulCount={statefulNodes.length}
                eligibleCount={statelessNodes.filter(n => n.savings > 0 && !n.cooldown).length}
                cooldownCount={statelessNodes.filter(n => n.cooldown).length}
              />

              <ResizeGuardMonitoringPanel />

              <StatelessSection nodes={statelessNodes} isAutoOn={autoState} />

              <StatefulSection nodes={statefulNodes} />
            </>
          )}

          {activeTab === 'history' && (
            <div style={{ marginBottom: 32 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <div>
                  <h2 style={{ fontSize: 18, fontWeight: 700, color: T.text, margin: 0 }}>Node-by-Node Execution Plan</h2>
                  <p style={{ fontSize: 13, color: T.textMuted, margin: "4px 0 0" }}>Pending rightsizing proposals awaiting execution.</p>
                </div>
              </div>

              <Card>
                {executionLoading ? (
                  <div style={{ padding: "40px", textAlign: "center", color: T.textMuted }}>Loading execution plan...</div>
                ) : executionPlan.length === 0 ? (
                  <div style={{ padding: "40px", textAlign: "center", color: T.textMuted }}>
                    <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>No pending execution items</div>
                    <div style={{ fontSize: 13 }}>Rightsizing proposals will appear here once generated by the optimizer.</div>
                  </div>
                ) : (
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
                    <thead>
                      <tr style={{ background: T.bg, borderBottom: `1px solid ${T.border}` }}>
                        <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Order</th>
                        <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Node</th>
                        <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Action</th>
                        <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Est Duration</th>
                        <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Rollback Plan</th>
                        <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Monthly Savings</th>
                        <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {executionPlan.map((item, i) => (
                        <tr key={item.proposal_id || i} style={{ borderBottom: i < executionPlan.length - 1 ? `1px solid ${T.borderLight}` : "none" }}>
                          <td style={{ padding: "12px 16px", fontWeight: 600 }}>{item.order}</td>
                          <td style={{ padding: "12px 16px", color: T.primary, fontWeight: 500 }}>{item.node}</td>
                          <td style={{ padding: "12px 16px", color: T.text }}>{item.action}</td>
                          <td style={{ padding: "12px 16px", color: T.textMid }}>{item.est_duration}</td>
                          <td style={{ padding: "12px 16px", color: T.textMid }}>{item.rollback_plan}</td>
                          <td style={{ padding: "12px 16px", color: T.green, fontWeight: 600 }}>${item.monthly_savings}/mo</td>
                          <td style={{ padding: "12px 16px" }}>
                            <Badge
                              color={item.status === 'APPROVED' ? T.primary : T.textMuted}
                              bg={item.status === 'APPROVED' ? T.primaryLight : T.bg}
                            >
                              {item.status === 'APPROVED' ? 'Next in line' : 'Pending'}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
            </div>
          )}

          {activeTab === 'config' && (
            <div style={{ marginBottom: 32 }}>
              <div style={{ marginBottom: 20 }}>
                <h2 style={{ fontSize: 18, fontWeight: 700, color: T.text, margin: 0 }}>Karpenter Configuration</h2>
                <p style={{ fontSize: 13, color: T.textMuted, margin: '4px 0 0' }}>
                  Strategy, instance families, stateful node policy, and bin-packing settings. Auto-mode toggles are managed in Cluster Settings.
                </p>
              </div>
              {configLoading ? (
                <div style={{ textAlign: 'center', padding: '40px', color: T.textMuted }}>Loading configuration...</div>
              ) : (
                <KarpenterConfigPanel
                  clusterId={selectedClusterId}
                  initialConfig={karpenterConfig || {}}
                  onSaved={(cfg) => setKarpenterConfig(cfg)}
                />
              )}
            </div>
          )}

          {activeTab === 'savings' && (
            <div style={{ marginBottom: 32 }}>
              {historyLoading ? (
                <div style={{ padding: "40px", textAlign: "center", color: T.textMuted }}>Loading history...</div>
              ) : (
                <>
                  <div style={{ display: "flex", gap: 24, marginBottom: 24 }}>
                    <Card style={{ flex: 1, padding: "20px" }}>
                      <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, textTransform: "uppercase" }}>Resizes this Month</div>
                      <div style={{ fontSize: 28, fontWeight: 800, color: T.text, marginTop: 4 }}>{historyData.kpis.resizes_this_month}</div>
                    </Card>
                    <Card style={{ flex: 1, padding: "20px" }}>
                      <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, textTransform: "uppercase" }}>Net Savings Generated</div>
                      <div style={{ fontSize: 28, fontWeight: 800, color: T.green, marginTop: 4 }}>${historyData.kpis.net_savings_monthly}/mo</div>
                    </Card>
                    <Card style={{ flex: 1, padding: "20px" }}>
                      <div style={{ fontSize: 11, color: T.textMuted, fontWeight: 600, textTransform: "uppercase" }}>Success Rate</div>
                      <div style={{ fontSize: 28, fontWeight: 800, color: T.primary, marginTop: 4 }}>{historyData.kpis.success_rate_pct}%</div>
                    </Card>
                  </div>

                  <Card>
                    <div style={{ padding: "16px 20px", borderBottom: `1px solid ${T.border}` }}>
                      <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Action History</h3>
                    </div>
                    {historyData.history.length === 0 ? (
                      <div style={{ padding: "40px", textAlign: "center", color: T.textMuted }}>
                        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>No resize history yet</div>
                        <div style={{ fontSize: 13 }}>Completed rightsizing actions will appear here.</div>
                      </div>
                    ) : (
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
                        <thead>
                          <tr style={{ background: T.bg, borderBottom: `1px solid ${T.border}` }}>
                            <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Executed At</th>
                            <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Node</th>
                            <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Before</th>
                            <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>After</th>
                            <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Time Taken</th>
                            <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Savings</th>
                            <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {historyData.history.map((item, i) => (
                            <tr key={i} style={{ borderBottom: i < historyData.history.length - 1 ? `1px solid ${T.borderLight}` : "none" }}>
                              <td style={{ padding: "12px 16px", color: T.textMid }}>{item.executed_at}</td>
                              <td style={{ padding: "12px 16px", color: T.primary, fontWeight: 500 }}>{item.node}</td>
                              <td style={{ padding: "12px 16px", color: T.textMid }}>{item.before}</td>
                              <td style={{ padding: "12px 16px", color: T.text }}>{item.after}</td>
                              <td style={{ padding: "12px 16px", color: T.textMid }}>{item.time_taken}</td>
                              <td style={{ padding: "12px 16px", color: T.green, fontWeight: 600 }}>${item.monthly_savings}/mo</td>
                              <td style={{ padding: "12px 16px" }}>
                                <Badge
                                  color={item.status === 'Success' ? T.green : T.amber}
                                  bg={item.status === 'Success' ? T.greenLight : T.amberLight}
                                >
                                  {item.status}
                                </Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </Card>
                </>
              )}
            </div>
          )}
        </>
      )}

      {loading && selectedClusterId !== "all" && (
        <div style={{ textAlign: "center", padding: "64px", color: T.textMuted }}>Loading optimization telemetry...</div>
      )}
    </div>
  );
}
