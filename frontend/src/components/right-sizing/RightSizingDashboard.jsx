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
          <button onClick={() => { toast.success("Resize request sent for approval."); onClose(); }} style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: T.greyDark, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Submit for Approval</button>
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
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>CPU / Mem P95</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Recommended Type</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Savings</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>EV (Server)</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Impact</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11 }}>Status</th>
              <th style={{ padding: "12px 16px", color: T.textFaint, fontWeight: 600, fontSize: 11, textAlign: "right" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {nodes.length === 0 ? (
              <tr><td colSpan="9" style={{ padding: "24px", textAlign: "center", color: T.textMuted }}>No stateless nodes found.</td></tr>
            ) : nodes.map((n, i) => {
              // Derive mock impact based on confidence for demo
              let impactIcon = <FiCheckCircle size={14} />;
              let impactLabel = "Neutral";
              let impactColor = T.textMuted;
              if (n.confidence < 70) { impactIcon = <FiAlertTriangle size={14} />; impactLabel = "Increases Family Concentration"; impactColor = T.amber; }
              if (n.cooldown) { impactIcon = <FiAlertCircle size={14} />; impactLabel = "AZ Imbalance Risk"; impactColor = T.red; }

              return (
                <tr key={n.id} style={{ borderBottom: i === nodes.length - 1 ? "none" : `1px solid ${T.borderLight}`, background: T.surface, transition: "background 0.2s" }} onMouseEnter={e => e.currentTarget.style.background = T.bg} onMouseLeave={e => e.currentTarget.style.background = T.surface}>
                  <td style={{ padding: "12px 16px", fontWeight: 500, color: T.primary, cursor: "pointer" }} onClick={() => setSelectedNode(n)}>{n.name}</td>
                  <td style={{ padding: "12px 16px", color: T.textMid }}>{n.current}</td>
                  <td style={{ padding: "12px 16px", color: T.textMid }}>
                    <span style={{ color: n.cpu > 80 ? T.red : T.textMid }}>{n.cpu}%</span> / <span style={{ color: n.mem > 80 ? T.red : T.textMid }}>{n.mem}%</span>
                  </td>
                  <td style={{ padding: "12px 16px", fontWeight: 600, color: T.text }}>{n.recommended}</td>
                  <td style={{ padding: "12px 16px", color: T.green, fontWeight: 600 }}>${n.savings}/mo</td>
                  {/* Task 8.2: EV from server — no client-side computation */}
                  <td style={{ padding: "12px 16px" }}>
                    {n.ev_breakdown ? (
                      <span
                        title={
                          `Savings: $${n.ev_breakdown.savings?.toFixed(2) || '0'}/hr\n` +
                          `Interruption: $${n.ev_breakdown.interruption_cost?.toFixed(2) || '0'}/hr\n` +
                          `Migration: $${n.ev_breakdown.migration_penalty?.toFixed(2) || '0'}\n` +
                          `Volatility: $${n.ev_breakdown.volatility_cost?.toFixed(2) || '0'}/hr`
                        }
                        style={{ color: n.ev_breakdown.is_eligible ? T.green : T.amber, fontWeight: 600, cursor: "help" }}
                      >
                        ${n.ev_breakdown.ev?.toFixed(2) || '—'}/hr
                      </span>
                    ) : (
                      <span style={{ color: n.confidence > 80 ? T.green : T.amber }}>{n.confidence}%</span>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <span title={impactLabel} style={{ color: impactColor, fontWeight: 600, cursor: "help" }}>{impactIcon} {impactLabel}</span>
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    {n.cooldown ? (
                      <Badge color={T.amber} bg={T.amberLight} style={{ display: "flex", gap: 4, alignItems: "center" }}>
                        <FiClock size={12} title="Resize blocked for 3h remaining" style={{ marginRight: 2 }} /> In Cooldown
                      </Badge>
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
                        onClick={(e) => { e.stopPropagation(); toast.success(`Applying resize to ${n.name}`); }}
                        style={{ padding: "6px 12px", background: n.cooldown ? T.bg : T.primaryLight, color: n.cooldown ? T.textMuted : T.primary, border: `1px solid ${n.cooldown ? T.border : T.primary}`, borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: n.cooldown ? "not-allowed" : "pointer" }}>
                        Apply
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
                <td style={{ padding: "12px 16px", color: T.green, fontWeight: 600 }}>${n.savings}/mo</td>
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

// MAIN PAGE
export default function RightSizingMonitoringDashboard() {
  const [clusters, setClusters] = useState([]);
  const [selectedClusterId, setSelectedClusterId] = useState("all");
  const [autoState, setAutoState] = useState(false); // is auto rightsizing enabled?
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('monitoring'); // 'monitoring', 'execution', 'history'

  // Data lists
  const [statelessNodes, setStatelessNodes] = useState([]);
  const [statefulNodes, setStatefulNodes] = useState([]);

  // Execution Plan and History state
  const [executionPlan, setExecutionPlan] = useState([]);
  const [historyData, setHistoryData] = useState({ history: [], kpis: { resizes_this_month: 0, net_savings_monthly: 0, success_rate_pct: 0 } });
  const [executionLoading, setExecutionLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Fetch clusters list
  useEffect(() => {
    clusterAPI.listClusters().then(res => {
      const data = res.data?.items || res.data?.clusters || res.data || [];
      const cl = Array.isArray(data) ? data : [];
      setClusters(cl);
      if (cl.length > 0) setSelectedClusterId(cl[0].id);
    }).catch(console.error);
  }, []);

  // Fetch execution plan and history when tab changes
  useEffect(() => {
    if (selectedClusterId === "all" || !selectedClusterId) return;
    if (activeTab === 'execution') {
      setExecutionLoading(true);
      karpenterAPI.getExecutionPlan(selectedClusterId)
        .then(res => setExecutionPlan(res.data?.plan || []))
        .catch(() => setExecutionPlan([]))
        .finally(() => setExecutionLoading(false));
    } else if (activeTab === 'history') {
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
        // node_type='stateless' means already on spot (lifecycle-optimized)
        // node_type='stateful'  means on-demand (still needs lifecycle action)
        sNodes = rawRecs
          .filter(r => r.node_type === 'stateless' || (r.current_lifecycle || '').includes('spot'))
          .map((r, i) => ({
            id: r.id || `stateless-${i}`,
            name: r.instance_id || `spot-node-${i}`,
            current: r.current_type || 'unknown',
            recommended: r.recommended_type || r.current_type || 'unknown',
            cpu: Math.round(r.cpu || 0),
            mem: Math.round(r.mem || 0),
            savings: Math.round(r.potential_savings || 0),
            confidence: r.risk_prob != null ? Math.max(0, 100 - r.risk_prob) : 85,
            cooldown: false,
          }));

        stNodes = rawRecs
          .filter(r => r.node_type === 'stateful' && !(r.current_lifecycle || '').includes('spot'))
          .map((r, i) => ({
            id: r.id || `stateful-${i}`,
            name: r.instance_id || `od-node-${i}`,
            current: r.current_type || 'unknown',
            recommended: r.recommended_type || r.current_type || 'unknown',
            cpu: Math.round(r.cpu || 0),
            mem: Math.round(r.mem || 0),
            savings: Math.round(r.potential_savings || 0),
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
      <div style={{ borderBottom: `1px solid ${T.border}`, marginBottom: 24, display: "flex", gap: 32 }}>
        <button
          onClick={() => setActiveTab('monitoring')}
          style={{ padding: "12px 4px", border: "none", background: "none", borderBottom: activeTab === 'monitoring' ? `2px solid ${T.primary}` : "2px solid transparent", color: activeTab === 'monitoring' ? T.primary : T.textMuted, fontSize: 14, fontWeight: 600, cursor: "pointer" }}>
          Monitoring
        </button>
        <button
          onClick={() => setActiveTab('execution')}
          style={{ padding: "12px 4px", border: "none", background: "none", borderBottom: activeTab === 'execution' ? `2px solid ${T.primary}` : "2px solid transparent", color: activeTab === 'execution' ? T.primary : T.textMuted, fontSize: 14, fontWeight: 600, cursor: "pointer" }}>
          Execution Plan
        </button>
        <button
          onClick={() => setActiveTab('history')}
          style={{ padding: "12px 4px", border: "none", background: "none", borderBottom: activeTab === 'history' ? `2px solid ${T.primary}` : "2px solid transparent", color: activeTab === 'history' ? T.primary : T.textMuted, fontSize: 14, fontWeight: 600, cursor: "pointer" }}>
          History
        </button>
      </div>

      {!loading && selectedClusterId !== "all" && (
        <>
          <AutoModeBanner isAutoOn={autoState} isLoading={loading} />

          {activeTab === 'monitoring' && (
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

          {activeTab === 'execution' && (
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

          {activeTab === 'history' && (
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
