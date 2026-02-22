import { useState } from "react";

const NAV_STRUCTURE = [
  {
    section: "OVERVIEW",
    items: [
      {
        id: "dashboard",
        label: "Dashboard",
        icon: "⌂",
        badge: null,
        description: "KPIs, cost trends, fleet overview"
      }
    ]
  },
  {
    section: "COST INTELLIGENCE",
    items: [
      {
        id: "atharvaai",
        label: "AtharvaAI Optimizer",
        icon: "◈",
        badge: "ML",
        badgeColor: "#6366f1",
        description: "ML pool rankings & interruption heatmap",
        sub: [
          { id: "atharvaai-rankings", label: "Pool Rankings" },
          { id: "atharvaai-heatmap", label: "Interruption Heatmap" },
          { id: "atharvaai-rebalancing", label: "Rebalancing Timeline" }
        ]
      },
      {
        id: "rightsizing",
        label: "Right-Sizing",
        icon: "⇄",
        badge: null,
        description: "Manual & Karpenter auto-optimization",
        sub: [
          { id: "rs-manual", label: "Manual Mode" },
          { id: "rs-karpenter", label: "Karpenter Auto" },
          { id: "rs-savings", label: "Savings Tracker" }
        ]
      },
      {
        id: "resource-hygiene",
        label: "Resource Hygiene",
        icon: "⊘",
        badge: null,
        description: "Zombie detection & cleanup across 9 AWS resource types"
      },
      {
        id: "hibernation",
        label: "Hibernation",
        icon: "◑",
        badge: null,
        description: "Scheduled cluster sleep/wake strategies",
        sub: [
          { id: "hib-schedules", label: "Schedules" },
          { id: "hib-strategies", label: "Strategies" },
          { id: "hib-history", label: "Execution History" }
        ]
      }
    ]
  },

  {
    section: "INFRASTRUCTURE",
    items: [
      {
        id: "clusters",
        label: "Clusters",
        icon: "⬡",
        badge: null,
        description: "EKS clusters, nodes, policies"
      },
      {
        id: "templates",
        label: "Node Templates",
        icon: "◻",
        badge: null,
        description: "Instance family & architecture templates"
      }
    ]
  },
  {
    section: "GOVERNANCE",
    items: [
      {
        id: "approvals",
        label: "Approvals",
        icon: "✓",
        badge: "3",
        badgeColor: "#f59e0b",
        description: "JIT access requests & grants"
      },
      {
        id: "tagging",
        label: "Tagging Policies",
        icon: "◇",
        badge: null,
        description: "Tag enforcement & bulk tagging"
      },
      {
        id: "automation",
        label: "Automation",
        icon: "⚡",
        badge: null,
        description: "Autopilot rules & governance policies"
      }
    ]
  },
  {
    section: "ORGANIZATION",
    items: [
      {
        id: "teams",
        label: "Teams & Members",
        icon: "⊹",
        badge: null,
        description: "Members, roles & permissions"
      }
    ]
  },
  {
    section: "SYSTEM",
    items: [
      {
        id: "audit",
        label: "Audit Logs",
        icon: "≡",
        badge: null,
        description: "Tamper-evident activity trail"
      },
      {
        id: "settings",
        label: "Settings",
        icon: "◎",
        badge: null,
        description: "AWS integrations, billing, profile"
      }
    ]
  }
];

// Search index — all searchable terms mapped to nav ids
const SEARCH_INDEX = [
  // AtharvaAI
  { id: "atharvaai", terms: ["ml", "machine learning", "pool", "rankings", "onnx", "spot advisor", "interruption", "heatmap", "rebalancing", "blacklist", "capacity"] },
  // Right-Sizing
  { id: "rightsizing", terms: ["karpenter", "right sizing", "rightsizing", "downsize", "recommendations", "cpu", "memory", "utilization", "overprovisioned", "savings"] },
  // Resource Hygiene
  { id: "resource-hygiene", terms: ["zombie", "cleanup", "ebs", "ec2", "elastic ip", "s3", "snapshot", "stopped", "orphaned", "waste", "idle", "unused", "delete", "scan"] },
  // Hibernation
  { id: "hibernation", terms: ["sleep", "wake", "schedule", "namespace sleep", "nuclear", "snapshot restore", "cost schedule", "off hours", "weekends", "nights"] },
  // Clusters
  { id: "clusters", terms: ["cluster", "eks", "node", "nodegroup", "heartbeat", "agent", "spot ratio"] },
  // Templates
  { id: "templates", terms: ["template", "instance family", "architecture", "arm64", "amd64", "blacklist"] },
  // Approvals
  { id: "approvals", terms: ["approval", "jit", "access", "request", "grant", "permission", "revoke"] },
  // Tagging
  { id: "tagging", terms: ["tag", "tagging", "policy", "compliance", "bulk tag", "enforcement"] },
  // Automation
  { id: "automation", terms: ["autopilot", "automation", "governance", "rule", "auto cleanup"] },
  // Teams
  { id: "teams", terms: ["team", "member", "role", "invite", "organization", "permission", "rbac"] },
  // Audit
  { id: "audit", terms: ["audit", "log", "history", "event", "checksum", "activity", "diff"] },
  // Settings
  { id: "settings", terms: ["settings", "aws", "account", "integration", "billing", "profile", "password", "notification"] },
  // Dashboard
  { id: "dashboard", terms: ["dashboard", "kpi", "overview", "widget", "cost", "savings", "fleet", "home"] }
];

function searchNav(query) {
  if (!query.trim()) return [];
  const q = query.toLowerCase();
  const results = new Set();
  SEARCH_INDEX.forEach(({ id, terms }) => {
    if (terms.some(t => t.includes(q) || q.includes(t.split(" ")[0]))) {
      results.add(id);
    }
  });
  // Also search labels directly
  NAV_STRUCTURE.forEach(section => {
    section.items.forEach(item => {
      if (item.label.toLowerCase().includes(q)) results.add(item.id);
      (item.sub || []).forEach(s => {
        if (s.label.toLowerCase().includes(q)) results.add(item.id);
      });
    });
  });
  return [...results];
}

export default function SpotOptimizerSidebar() {
  const [active, setActive] = useState("dashboard");
  const [expanded, setExpanded] = useState(new Set(["atharvaai", "rightsizing", "hibernation"]));
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState(false);

  const searchResults = searchNav(search);

  const toggleExpand = (id) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const isHighlighted = (id) => search.trim() && searchResults.includes(id);
  const isVisible = (id) => !search.trim() || searchResults.includes(id);

  return (
    <div style={{
      display: "flex",
      height: "100vh",
      fontFamily: "'DM Sans', 'Outfit', system-ui, sans-serif",
      background: "#f0f2f5"
    }}>
      {/* SIDEBAR */}
      <nav style={{
        width: collapsed ? 60 : 260,
        minWidth: collapsed ? 60 : 260,
        height: "100vh",
        background: "#0f1117",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.22s cubic-bezier(.4,0,.2,1), min-width 0.22s",
        overflow: "hidden",
        position: "relative",
        boxShadow: "4px 0 24px rgba(0,0,0,0.18)"
      }}>
        {/* Header */}
        <div style={{
          padding: collapsed ? "20px 0" : "20px 16px",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          display: "flex",
          alignItems: "center",
          justifyContent: collapsed ? "center" : "space-between",
          flexShrink: 0
        }}>
          {!collapsed && (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{
                width: 30, height: 30, borderRadius: 8,
                background: "linear-gradient(135deg, #3b82f6, #6366f1)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, color: "#fff", fontWeight: 700, flexShrink: 0
              }}>S</div>
              <div>
                <div style={{ color: "#fff", fontWeight: 700, fontSize: 14, letterSpacing: "-0.3px" }}>Spot Optimizer</div>
                <div style={{ color: "#4b5563", fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase" }}>ORG_ADMIN</div>
              </div>
            </div>
          )}
          {collapsed && (
            <div style={{
              width: 30, height: 30, borderRadius: 8,
              background: "linear-gradient(135deg, #3b82f6, #6366f1)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14, color: "#fff", fontWeight: 700
            }}>S</div>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            style={{
              background: "rgba(255,255,255,0.06)", border: "none",
              borderRadius: 6, color: "#6b7280", cursor: "pointer",
              width: 24, height: 24, display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 11, flexShrink: 0,
              transition: "background 0.15s",
              marginLeft: collapsed ? 0 : 0
            }}
          >
            {collapsed ? "›" : "‹"}
          </button>
        </div>

        {/* Search */}
        {!collapsed && (
          <div style={{ padding: "12px 12px 8px", flexShrink: 0 }}>
            <div style={{ position: "relative" }}>
              <span style={{
                position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)",
                color: "#4b5563", fontSize: 12, pointerEvents: "none"
              }}>⌕</span>
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search features..."
                style={{
                  width: "100%", boxSizing: "border-box",
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 8, color: "#e5e7eb",
                  padding: "7px 10px 7px 28px",
                  fontSize: 12, outline: "none",
                  transition: "border-color 0.15s",
                  fontFamily: "inherit"
                }}
                onFocus={e => e.target.style.borderColor = "rgba(99,102,241,0.5)"}
                onBlur={e => e.target.style.borderColor = "rgba(255,255,255,0.08)"}
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  style={{
                    position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", color: "#6b7280",
                    cursor: "pointer", fontSize: 11, padding: 0, lineHeight: 1
                  }}
                >✕</button>
              )}
            </div>
            {search && searchResults.length > 0 && (
              <div style={{ color: "#4b5563", fontSize: 10, marginTop: 5, paddingLeft: 2 }}>
                {searchResults.length} result{searchResults.length !== 1 ? "s" : ""} for "{search}"
              </div>
            )}
            {search && searchResults.length === 0 && (
              <div style={{ color: "#ef4444", fontSize: 10, marginTop: 5, paddingLeft: 2 }}>
                No features found
              </div>
            )}
          </div>
        )}

        {/* Nav Sections */}
        <div style={{
          flex: 1, overflowY: "auto", overflowX: "hidden",
          padding: collapsed ? "8px 0" : "4px 8px 8px",
          scrollbarWidth: "none"
        }}>
          {NAV_STRUCTURE.map(section => {
            const visibleItems = section.items.filter(item => isVisible(item.id));
            if (search && visibleItems.length === 0) return null;

            return (
              <div key={section.section} style={{ marginBottom: 2 }}>
                {!collapsed && (
                  <div style={{
                    color: "#374151", fontSize: 9.5, fontWeight: 700,
                    letterSpacing: "0.1em", textTransform: "uppercase",
                    padding: "12px 8px 4px",
                    opacity: search && visibleItems.length === 0 ? 0.3 : 1
                  }}>
                    {section.section}
                  </div>
                )}
                {collapsed && <div style={{ height: 8 }} />}

                {section.items.map(item => {
                  const visible = isVisible(item.id);
                  const highlighted = isHighlighted(item.id);
                  const isActive = active === item.id || (item.sub || []).some(s => s.id === active);
                  const isOpen = expanded.has(item.id);
                  const hasSub = item.sub && item.sub.length > 0;

                  if (!visible && search) return null;

                  return (
                    <div key={item.id}>
                      {/* Main item */}
                      <button
                        onClick={() => {
                          if (hasSub) {
                            toggleExpand(item.id);
                            setActive(item.id);
                          } else {
                            setActive(item.id);
                          }
                        }}
                        title={collapsed ? item.label : undefined}
                        style={{
                          width: "100%", display: "flex", alignItems: "center",
                          gap: 9, padding: collapsed ? "9px 0" : "8px 10px",
                          justifyContent: collapsed ? "center" : "flex-start",
                          background: isActive
                            ? "rgba(59,130,246,0.12)"
                            : highlighted
                            ? "rgba(99,102,241,0.1)"
                            : "transparent",
                          border: "none",
                          borderRadius: 8,
                          cursor: "pointer",
                          position: "relative",
                          transition: "background 0.12s",
                          textAlign: "left",
                          outline: "none",
                          marginBottom: 1
                        }}
                        onMouseEnter={e => {
                          if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,0.04)";
                        }}
                        onMouseLeave={e => {
                          if (!isActive) e.currentTarget.style.background = highlighted ? "rgba(99,102,241,0.1)" : "transparent";
                        }}
                      >
                        {/* Active indicator */}
                        {isActive && (
                          <span style={{
                            position: "absolute", left: 0, top: "20%", bottom: "20%",
                            width: 3, borderRadius: "0 3px 3px 0",
                            background: "linear-gradient(180deg, #3b82f6, #6366f1)"
                          }} />
                        )}

                        {/* Icon */}
                        <span style={{
                          fontSize: 15,
                          color: isActive ? "#60a5fa" : highlighted ? "#818cf8" : "#6b7280",
                          width: 18, textAlign: "center", flexShrink: 0,
                          transition: "color 0.12s"
                        }}>
                          {item.icon}
                        </span>

                        {!collapsed && (
                          <>
                            <span style={{
                              color: isActive ? "#e5e7eb" : highlighted ? "#c7d2fe" : "#9ca3af",
                              fontSize: 13, fontWeight: isActive ? 600 : 400,
                              flex: 1, letterSpacing: "-0.1px",
                              transition: "color 0.12s"
                            }}>
                              {item.label}
                            </span>

                            {/* Badge */}
                            {item.badge && (
                              <span style={{
                                background: item.badgeColor || "#374151",
                                color: "#fff", fontSize: 9, fontWeight: 700,
                                padding: "1px 6px", borderRadius: 10,
                                letterSpacing: "0.04em"
                              }}>
                                {item.badge}
                              </span>
                            )}

                            {/* Chevron for expandable */}
                            {hasSub && (
                              <span style={{
                                color: "#4b5563", fontSize: 10,
                                transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
                                transition: "transform 0.18s",
                                marginLeft: item.badge ? 4 : 0
                              }}>›</span>
                            )}
                          </>
                        )}

                        {/* Collapsed badge dot */}
                        {collapsed && item.badge && (
                          <span style={{
                            position: "absolute", top: 5, right: 8,
                            width: 6, height: 6, borderRadius: "50%",
                            background: item.badgeColor || "#f59e0b"
                          }} />
                        )}
                      </button>

                      {/* Tooltip on hover when collapsed */}
                      {/* Sub-items */}
                      {!collapsed && hasSub && isOpen && (
                        <div style={{
                          paddingLeft: 26,
                          borderLeft: "1px solid rgba(255,255,255,0.06)",
                          marginLeft: 18,
                          marginBottom: 2,
                          marginTop: 1
                        }}>
                          {item.sub.map(sub => (
                            <button
                              key={sub.id}
                              onClick={() => setActive(sub.id)}
                              style={{
                                width: "100%", display: "flex", alignItems: "center",
                                gap: 6, padding: "6px 8px",
                                background: active === sub.id ? "rgba(59,130,246,0.1)" : "transparent",
                                border: "none", borderRadius: 6,
                                cursor: "pointer", textAlign: "left", outline: "none",
                                marginBottom: 1, transition: "background 0.12s"
                              }}
                              onMouseEnter={e => {
                                if (active !== sub.id) e.currentTarget.style.background = "rgba(255,255,255,0.03)";
                              }}
                              onMouseLeave={e => {
                                if (active !== sub.id) e.currentTarget.style.background = "transparent";
                              }}
                            >
                              <span style={{
                                width: 4, height: 4, borderRadius: "50%", flexShrink: 0,
                                background: active === sub.id ? "#60a5fa" : "#374151"
                              }} />
                              <span style={{
                                color: active === sub.id ? "#93c5fd" : "#6b7280",
                                fontSize: 12, fontWeight: active === sub.id ? 500 : 400
                              }}>
                                {sub.label}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{
          borderTop: "1px solid rgba(255,255,255,0.07)",
          padding: collapsed ? "12px 0" : "12px 12px",
          flexShrink: 0
        }}>
          {!collapsed ? (
            <div style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "6px 8px", borderRadius: 8,
              background: "rgba(255,255,255,0.04)"
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: "50%",
                background: "linear-gradient(135deg, #3b82f6, #6366f1)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12, color: "#fff", fontWeight: 700, flexShrink: 0
              }}>A</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: "#d1d5db", fontSize: 12, fontWeight: 500, truncate: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>ath@gmail.com</div>
                <div style={{ color: "#4b5563", fontSize: 10 }}>ORG_ADMIN</div>
              </div>
              <button style={{
                background: "none", border: "none", color: "#4b5563",
                cursor: "pointer", fontSize: 14, padding: 0
              }}>⇥</button>
            </div>
          ) : (
            <div style={{ display: "flex", justifyContent: "center" }}>
              <div style={{
                width: 28, height: 28, borderRadius: "50%",
                background: "linear-gradient(135deg, #3b82f6, #6366f1)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12, color: "#fff", fontWeight: 700
              }}>A</div>
            </div>
          )}
        </div>
      </nav>

      {/* MAIN CONTENT AREA — Preview */}
      <div style={{ flex: 1, padding: 32, overflowY: "auto" }}>
        <div style={{ maxWidth: 680 }}>
          <h2 style={{ fontFamily: "inherit", fontSize: 22, fontWeight: 700, color: "#111827", marginBottom: 6 }}>
            Sidebar Redesign
          </h2>
          <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 28, lineHeight: 1.6 }}>
            Navigation restructured into 7 logical sections. Use the search box to find any feature instantly — it searches labels, descriptions, and keywords (e.g. "zombie", "karpenter", "jit", "onnx").
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 24 }}>
            {[
              { before: "Dashboard, Approvals, Teams, Clusters (flat)", after: "Overview → Infrastructure → Organization", label: "Platform nav" },
              { before: "AtharvaAI, Right-Sizing, Resource Hygiene, Hibernation (flat)", after: "Cost Intelligence section with sub-items", label: "Core features" },
              { before: "Tagging & Templates scattered in Optimizations", after: "Governance + Infrastructure sections", label: "Structure" },
              { before: "No search — must scroll to find features", after: "Semantic search: 'zombie', 'jit', 'karpenter'", label: "Discovery" },
            ].map(row => (
              <div key={row.label} style={{
                background: "#fff", borderRadius: 10, padding: 16,
                border: "1px solid #e5e7eb"
              }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#6366f1", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  {row.label}
                </div>
                <div style={{ fontSize: 12, color: "#ef4444", marginBottom: 4, display: "flex", gap: 4 }}>
                  <span>✕</span><span style={{ color: "#6b7280" }}>{row.before}</span>
                </div>
                <div style={{ fontSize: 12, color: "#10b981", display: "flex", gap: 4 }}>
                  <span>✓</span><span style={{ color: "#6b7280" }}>{row.after}</span>
                </div>
              </div>
            ))}
          </div>

          <div style={{ background: "#fff", borderRadius: 10, padding: 20, border: "1px solid #e5e7eb" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 12 }}>Search examples to try</div>
            {[
              ["zombie", "→ Resource Hygiene"],
              ["karpenter", "→ Right-Sizing"],
              ["jit", "→ Approvals"],
              ["onnx", "→ AtharvaAI Optimizer"],
              ["sleep", "→ Hibernation"],
              ["multi-az", "→ RDS Analysis"],
            ].map(([term, result]) => (
              <div key={term} style={{ display: "flex", gap: 8, marginBottom: 6, fontSize: 12 }}>
                <code style={{ background: "#f3f4f6", padding: "2px 6px", borderRadius: 4, color: "#374151", fontFamily: "monospace" }}>{term}</code>
                <span style={{ color: "#6b7280" }}>{result}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}