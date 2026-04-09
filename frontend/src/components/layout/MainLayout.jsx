import React, { useState, useEffect } from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useHeaderStore } from '../../store/useStore';
import { clusterAPI, ascpaiAPI, approvalsAPI } from '../../services/api';
import { FiHome, FiServer, FiFileText, FiSettings, FiTarget, FiClock, FiBarChart2, FiUsers, FiActivity, FiLogOut, FiClipboard, FiBriefcase, FiCheckSquare, FiShield, FiLock, FiTag, FiZap, FiCpu } from 'react-icons/fi';
import { NotificationPanel, ICONS } from '../shared/NotificationPanel';

// Pending Approvals Badge — polls for real-time count
const PendingApprovalsBadge = () => {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await approvalsAPI.list('PENDING');
        const items = res.data?.approvals || res.data || [];
        setCount(Array.isArray(items) ? items.length : 0);
      } catch (e) {
        // silently fail
      }
    };
    fetch();
    const interval = setInterval(fetch, 30000);
    return () => clearInterval(interval);
  }, []);

  if (!count) return null;
  return (
    <span style={{
      background: "#f59e0b", color: "#fff", fontSize: 9, fontWeight: 700,
      padding: "1px 6px", borderRadius: 10, letterSpacing: "0.04em"
    }}>
      {count}
    </span>
  );
};

// Cluster Notification Badge Component
const ClusterBadge = () => {
  const [clusterStats, setClusterStats] = useState({ discovered: 0, errors: 0, potentialSavings: 0 });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await clusterAPI.list({});
        const clusters = res.data?.clusters || [];
        const discovered = clusters.filter(c => c.status === 'DISCOVERED').length;
        const errors = clusters.filter(c => c.status === 'ERROR').length;
        const potentialSavings = clusters
          .filter(c => c.status === 'DISCOVERED')
          .reduce((sum, c) => sum + (c.potential_savings_monthly || c.estimated_savings || 0), 0);
        setClusterStats({ discovered, errors, potentialSavings });
      } catch (e) {
        console.error('Failed to fetch cluster stats for badge', e);
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  if (clusterStats.errors > 0) {
    return (
      <span
        className="ml-auto bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center"
        title={`${clusterStats.errors} clusters with errors`}
      >
        {clusterStats.errors}
      </span>
    );
  }

  if (clusterStats.discovered > 0) {
    return (
      <span
        className="ml-auto bg-blue-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center animate-pulse"
        title={`${clusterStats.discovered} new clusters detected - Potential Savings: $${clusterStats.potentialSavings.toFixed(0)}/mo`}
      >
        {clusterStats.discovered}
      </span>
    );
  }

  return null;
};

const routeMap = {
  "dashboard": "/dashboard",
  "dashboard-overview": "/dashboard?tab=overview",
  "dashboard-cost": "/dashboard?tab=cost",
  "dashboard-infra": "/dashboard?tab=infra",
  "dashboard-gov": "/dashboard?tab=governance",
  "ascpai": "/ascp-ai",
  "ascpai-dashboard": "/ascp-ai?tab=dashboard",
  "ascpai-decision-engine-v3": "/ascp-ai?tab=decision-engine-v3",
  "ascpai-rankings": "/ascp-ai?tab=rankings",
  "ascpai-heatmap": "/ascp-ai?tab=heatmap",
  "ascpai-rebalancing": "/ascp-ai?tab=rebalancing",
  "rightsizing": "/right-sizing",
  "rs-karpenter": "/right-sizing?tab=karpenter",
  "rs-config": "/right-sizing?tab=config",
  "rs-history": "/right-sizing?tab=history",
  "rs-savings": "/right-sizing?tab=savings",
  "resource-hygiene": "/hygiene",
  "hibernation": "/hibernation",
  "hib-schedules": "/hibernation?tab=schedules",
  "hib-strategies": "/hibernation?tab=strategies",
  "hib-history": "/hibernation?tab=history",
  "clusters": "/clusters",
  "node-templates": "/node-templates",
  "approvals": "/approvals",
  "tag-governance": "/tagging-policies",
  "tag-policies": "/tagging-policies?tab=policies",
  "tag-templates": "/tagging-policies?tab=templates",
  "tag-scoring": "/tagging-policies?tab=scoring",
  "tag-automation": "/tagging-policies?tab=automation",
  "tag-monitor": "/tagging-policies?tab=monitor",
  "teams": "/teams",
  "audit": "/audit",
  "settings": "/settings"
};

const NAV_STRUCTURE = [
  {
    section: "OVERVIEW",
    items: [
      {
        id: "dashboard",
        label: "Dashboard",
        icon: "⌂",
        badge: null,
        description: "KPIs, cost trends, fleet overview",
        sub: [
          { id: "dashboard-overview", label: "Overview" },
          { id: "dashboard-cost", label: "Cost Intelligence" },
          { id: "dashboard-infra", label: "Infrastructure" },
          { id: "dashboard-gov", label: "Governance" }
        ]
      }
    ]
  },
  {
    section: "COST INTELLIGENCE",
    items: [
      {
        id: "ascpai",
        label: "Balancekube.ai",
        icon: "◈",
        badge: "ML",
        badgeColor: "#6366f1",
        description: "ML pool rankings & interruption heatmap",
        sub: [
          { id: "ascpai-dashboard", label: "Dashboard" },
          { id: "ascpai-decision-engine-v3", label: "Decision Engine v3" },
          { id: "ascpai-rankings", label: "Pool Rankings" },
          { id: "ascpai-heatmap", label: "Interruption Heatmap" },
          { id: "ascpai-rebalancing", label: "Rebalancing" }
        ]
      },
      {
        id: "rightsizing",
        label: "Right-Sizing",
        icon: "⇄",
        badge: null,
        description: "Manual & Karpenter auto-optimization",
        sub: [
          { id: "rs-karpenter", label: "Karpenter" },
          { id: "rs-config", label: "Configuration" },
          { id: "rs-history", label: "Optimization History" },
          { id: "rs-savings", label: "Savings Tracker" }
        ]
      },
      {
        id: "node-templates",
        label: "Node Templates",
        icon: "◻",
        badge: null,
        description: "Cluster constraints & architecture templates"
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
        badge: null,
        badgeColor: "#f59e0b",
        description: "JIT access requests & grants"
      },
      {
        id: "tag-governance",
        label: "Tag Governance",
        icon: "◇",
        badge: null,
        description: "Tag policies, templates & automation",
        sub: [
          { id: "tag-policies", label: "Governance Policies" },
          { id: "tag-templates", label: "Tag Templates" },
          { id: "tag-scoring", label: "Scoring Engine" },
          { id: "tag-automation", label: "Automation Rules" },
          { id: "tag-monitor", label: "Compliance Monitor" }
        ]
      },
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

const SEARCH_INDEX = [
  { id: "ascpai", terms: ["ml", "machine learning", "pool", "rankings", "onnx", "spot advisor", "interruption", "heatmap", "rebalancing", "blacklist", "capacity", "balancekube.ai", "balancekube"] },
  { id: "rightsizing", terms: ["karpenter", "right sizing", "rightsizing", "downsize", "recommendations", "cpu", "memory", "utilization", "overprovisioned", "savings"] },
  { id: "resource-hygiene", terms: ["zombie", "cleanup", "ebs", "ec2", "elastic ip", "s3", "snapshot", "stopped", "orphaned", "waste", "idle", "unused", "delete", "scan"] },
  { id: "hibernation", terms: ["sleep", "wake", "schedule", "namespace sleep", "nuclear", "snapshot restore", "cost schedule", "off hours", "weekends", "nights"] },
  { id: "clusters", terms: ["cluster", "eks", "node", "nodegroup", "heartbeat", "agent", "spot ratio"] },
  { id: "node-templates", terms: ["template", "instance family", "architecture", "arm64", "amd64", "blacklist"] },
  { id: "approvals", terms: ["approval", "jit", "access", "request", "grant", "permission", "revoke"] },
  { id: "tag-governance", terms: ["tag", "tagging", "policy", "compliance", "bulk tag", "enforcement", "template", "automation", "scoring"] },
  { id: "teams", terms: ["team", "member", "role", "invite", "organization", "permission", "rbac"] },
  { id: "audit", terms: ["audit", "log", "history", "event", "checksum", "activity", "diff"] },
  { id: "settings", terms: ["settings", "aws", "account", "integration", "billing", "profile", "password", "notification"] },
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

const MainLayout = () => {
  const { user, logout } = useAuth();
  const headerStore = useHeaderStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isNotifOpen, setIsNotifOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [bellAnim, setBellAnim] = useState(false);

  useEffect(() => {
    if (unreadCount > 0) {
      setBellAnim(true);
      const timer = setTimeout(() => setBellAnim(false), 700);
      return () => clearTimeout(timer);
    }
  }, [unreadCount]);

  const [volatilityStatus, setVolatilityStatus] = useState({ regime: 'NORMAL' });
  const [healthStatus, setHealthStatus] = useState('Green');

  const isSuperAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'super_admin';

  // Navigation active state determined by current pathname and hash
  const currentPath = location.pathname;
  let activeId = "dashboard";
  for (const [id, route] of Object.entries(routeMap)) {
    const basePath = route.split("?")[0];
    // Exact match or sub-route match (e.g., /hibernation/123 matches /hibernation)
    const matchesPath = currentPath === basePath || currentPath.startsWith(basePath + '/');
    const matchesSearch = route.includes("?") ? location.search.includes(route.split("?")[1]) : true;

    if (matchesPath && matchesSearch) {
      activeId = id;
    }
  }

  // Pre-expand sections
  const [expanded, setExpanded] = useState(new Set(["ascpai", "rightsizing", "hibernation"]));
  const [search, setSearch] = useState("");

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

  const adminNavigation = [
    { name: 'Command Center', path: '/admin', icon: FiActivity },
    { name: 'Organizations', path: '/admin/organizations', icon: FiBriefcase },
    { name: 'Clients', path: '/admin/clients', icon: FiUsers },
    { name: 'System Health', path: '/admin/health', icon: FiServer },
    { name: 'Experiments', path: '/admin/experiments', icon: FiTarget },
    { name: 'Configuration', path: '/admin/config', icon: FiSettings },
    { name: 'Billing', path: '/admin/billing', icon: FiBarChart2 },
  ];

  const isActive = (path) => location.pathname === path;

  if (isSuperAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 flex">
        <div className={`fixed inset-y-0 left-0 bg-white border-r border-gray-200 transition-all duration-300 z-30 ${isSidebarOpen ? 'w-64' : 'w-0 -translate-x-full'}`}>
          <div className="h-16 flex items-center px-6 border-b border-gray-200 justify-between">
            <h1 className="text-xl font-bold text-gray-900 truncate">Admin Console</h1>
          </div>
          <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto h-[calc(100vh-8rem)]">
            {adminNavigation.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors relative ${isActive(item.path)
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-700 hover:bg-gray-50'
                    }`}
                >
                  <Icon className="w-5 h-5 mr-3 flex-shrink-0" />
                  <span className="truncate">{item.name}</span>
                </Link>
              );
            })}
            <div className="mt-8 px-4">
              <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                <p className="text-xs text-yellow-800 font-medium truncate">Client View Hidden</p>
                <p className="text-xs text-yellow-700 mt-1">Use "Clients" page to impersonate users.</p>
              </div>
            </div>
          </nav>
          <div className="absolute bottom-0 w-full p-4 border-t border-gray-200 bg-white">
            <div className="flex items-center justify-between">
              <div className="flex items-center overflow-hidden">
                <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0">
                  <span className="text-white text-sm font-medium">
                    {user?.email?.[0].toUpperCase()}
                  </span>
                </div>
                <div className="ml-3 truncate">
                  <p className="text-sm font-medium text-gray-900 truncate">{user?.email}</p>
                  <p className="text-xs text-gray-500 truncate">{user?.role}</p>
                </div>
              </div>
              <button onClick={logout} className="p-2 text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0">
                <FiLogOut className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
        <div className={`flex-1 flex flex-col min-w-0 transition-all duration-300 ${isSidebarOpen ? 'pl-64' : 'pl-0'}`}>
          <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-4 sm:px-6 lg:px-8 z-20">
            <div className="flex items-center gap-4">
              <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 -ml-2 text-gray-500 hover:text-gray-700 rounded-md hover:bg-gray-100 focus:outline-none">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
              <h2 className="text-lg font-semibold text-gray-900">
                {adminNavigation.find(item => isActive(item.path))?.name || 'Dashboard'}
              </h2>
            </div>
          </header>
          <main className="flex-1 overflow-y-auto">
            <div className="p-8 h-full">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      display: "flex",
      height: "100vh",
      fontFamily: "'DM Sans', 'Outfit', system-ui, sans-serif",
      background: "#f0f2f5"
    }}>
      {/* SIDEBAR */}
      <nav style={{
        width: !isSidebarOpen ? 60 : 260,
        minWidth: !isSidebarOpen ? 60 : 260,
        height: "100vh",
        background: "#0f1117",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.22s cubic-bezier(.4,0,.2,1), min-width 0.22s",
        overflow: "hidden",
        position: "relative",
        boxShadow: "4px 0 24px rgba(0,0,0,0.18)",
        zIndex: 30
      }}>
        {/* Header */}
        <div style={{
          padding: !isSidebarOpen ? "20px 0" : "20px 16px",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          display: "flex",
          alignItems: "center",
          justifyContent: !isSidebarOpen ? "center" : "space-between",
          flexShrink: 0
        }}>
          {isSidebarOpen && (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{
                width: 30, height: 30, borderRadius: 8,
                background: "linear-gradient(135deg, #3b82f6, #6366f1)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, color: "#fff", fontWeight: 700, flexShrink: 0
              }}>S</div>
              <div>
                <div style={{ color: "#fff", fontWeight: 700, fontSize: 14, letterSpacing: "-0.3px" }}>Balancekube</div>
                <div style={{ color: "#4b5563", fontSize: 10, letterSpacing: "0.08em", textTransform: "uppercase" }}>{user?.role || 'USER'}</div>
              </div>
            </div>
          )}
          {!isSidebarOpen && (
            <div style={{
              width: 30, height: 30, borderRadius: 8,
              background: "linear-gradient(135deg, #3b82f6, #6366f1)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14, color: "#fff", fontWeight: 700
            }}>S</div>
          )}
          <button
            onClick={() => setIsSidebarOpen(c => !c)}
            style={{
              background: "rgba(255,255,255,0.06)", border: "none",
              borderRadius: 6, color: "#6b7280", cursor: "pointer",
              width: 24, height: 24, display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 11, flexShrink: 0,
              transition: "background 0.15s"
            }}
          >
            {!isSidebarOpen ? "›" : "‹"}
          </button>
        </div>

        {/* Search */}
        {isSidebarOpen && (
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
          </div>
        )}

        {/* Nav Sections */}
        <div style={{
          flex: 1, overflowY: "auto", overflowX: "hidden",
          padding: !isSidebarOpen ? "8px 0" : "4px 8px 8px",
          scrollbarWidth: "none"
        }}>
          {NAV_STRUCTURE.map(section => {
            const visibleItems = section.items.filter(item => isVisible(item.id));
            if (search && visibleItems.length === 0) return null;

            return (
              <div key={section.section} style={{ marginBottom: 2 }}>
                {isSidebarOpen && (
                  <div style={{
                    color: "#374151", fontSize: 9.5, fontWeight: 700,
                    letterSpacing: "0.1em", textTransform: "uppercase",
                    padding: "12px 8px 4px",
                    opacity: search && visibleItems.length === 0 ? 0.3 : 1
                  }}>
                    {section.section}
                  </div>
                )}
                {!isSidebarOpen && <div style={{ height: 8 }} />}

                {section.items.map(item => {
                  const visible = isVisible(item.id);
                  const highlighted = isHighlighted(item.id);
                  const isActiveState = activeId === item.id || (item.sub || []).some(s => s.id === activeId);
                  const isOpen = expanded.has(item.id);
                  const hasSub = item.sub && item.sub.length > 0;

                  if (!visible && search) return null;

                  return (
                    <div key={item.id}>
                      <button
                        onClick={() => {
                          if (hasSub) {
                            toggleExpand(item.id);
                            navigate(routeMap[item.id] || "/dashboard");
                          } else {
                            navigate(routeMap[item.id] || "/dashboard");
                          }
                        }}
                        title={!isSidebarOpen ? item.label : undefined}
                        style={{
                          width: "100%", display: "flex", alignItems: "center",
                          gap: 9, padding: !isSidebarOpen ? "9px 0" : "8px 10px",
                          justifyContent: !isSidebarOpen ? "center" : "flex-start",
                          background: isActiveState
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
                          if (!isActiveState) e.currentTarget.style.background = "rgba(255,255,255,0.04)";
                        }}
                        onMouseLeave={e => {
                          if (!isActiveState) e.currentTarget.style.background = highlighted ? "rgba(99,102,241,0.1)" : "transparent";
                        }}
                      >
                        {isActiveState && (
                          <span style={{
                            position: "absolute", left: 0, top: "20%", bottom: "20%",
                            width: 3, borderRadius: "0 3px 3px 0",
                            background: "linear-gradient(180deg, #3b82f6, #6366f1)"
                          }} />
                        )}

                        <span style={{
                          fontSize: 15,
                          color: isActiveState ? "#60a5fa" : highlighted ? "#818cf8" : "#6b7280",
                          width: 18, textAlign: "center", flexShrink: 0,
                          transition: "color 0.12s"
                        }}>
                          {item.icon}
                        </span>

                        {isSidebarOpen && (
                          <>
                            <span style={{
                              color: isActiveState ? "#e5e7eb" : highlighted ? "#c7d2fe" : "#9ca3af",
                              fontSize: 13, fontWeight: isActiveState ? 600 : 400,
                              flex: 1, letterSpacing: "-0.1px",
                              transition: "color 0.12s"
                            }}>
                              {item.label}
                            </span>

                            {item.id === "clusters" && <ClusterBadge />}
                            {item.id === "approvals" && <PendingApprovalsBadge />}

                            {item.badge && item.id !== "clusters" && (
                              <span style={{
                                background: item.badgeColor || "#374151",
                                color: "#fff", fontSize: 9, fontWeight: 700,
                                padding: "1px 6px", borderRadius: 10,
                                letterSpacing: "0.04em"
                              }}>
                                {item.badge}
                              </span>
                            )}

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
                        {!isSidebarOpen && item.badge && item.id !== "clusters" && (
                          <span style={{
                            position: "absolute", top: 5, right: 8,
                            width: 6, height: 6, borderRadius: "50%",
                            background: item.badgeColor || "#f59e0b"
                          }} />
                        )}
                      </button>

                      {isSidebarOpen && hasSub && isOpen && (
                        <div style={{
                          paddingLeft: 26,
                          borderLeft: "1px solid rgba(255,255,255,0.06)",
                          marginLeft: 18,
                          marginBottom: 2,
                          marginTop: 1
                        }}>
                          {item.sub.map(sub => {
                            const isSubActive = activeId === sub.id;
                            return (
                              <button
                                key={sub.id}
                                onClick={() => navigate(routeMap[sub.id] || "/dashboard")}
                                style={{
                                  width: "100%", display: "flex", alignItems: "center",
                                  gap: 6, padding: "6px 8px",
                                  background: isSubActive ? "rgba(59,130,246,0.1)" : "transparent",
                                  border: "none", borderRadius: 6,
                                  cursor: "pointer", textAlign: "left", outline: "none",
                                  marginBottom: 1, transition: "background 0.12s"
                                }}
                                onMouseEnter={e => {
                                  if (!isSubActive) e.currentTarget.style.background = "rgba(255,255,255,0.03)";
                                }}
                                onMouseLeave={e => {
                                  if (!isSubActive) e.currentTarget.style.background = "transparent";
                                }}
                              >
                                <span style={{
                                  width: 4, height: 4, borderRadius: "50%", flexShrink: 0,
                                  background: isSubActive ? "#60a5fa" : "#374151"
                                }} />
                                <span style={{
                                  color: isSubActive ? "#93c5fd" : "#6b7280",
                                  fontSize: 12, fontWeight: isSubActive ? 500 : 400
                                }}>
                                  {sub.label}
                                </span>
                              </button>
                            );
                          })}
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
          padding: !isSidebarOpen ? "12px 0" : "12px 12px",
          flexShrink: 0
        }}>
          {isSidebarOpen ? (
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
              }}>
                {user?.email?.[0].toUpperCase() || 'U'}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: "#d1d5db", fontSize: 12, fontWeight: 500, overflow: "hidden", whiteSpace: "nowrap" }}>{user?.email || 'user@example.com'}</div>
                <div style={{ color: "#4b5563", fontSize: 10 }}>{user?.role || 'USER'}</div>
              </div>
              <button onClick={logout} style={{
                background: "none", border: "none", color: "#4b5563",
                cursor: "pointer", fontSize: 14, padding: 0
              }} title="Logout">
                <FiLogOut />
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", justifyContent: "center" }} onClick={logout} title="Logout" className="cursor-pointer">
              <div style={{
                width: 28, height: 28, borderRadius: "50%",
                background: "linear-gradient(135deg, #3b82f6, #6366f1)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12, color: "#fff", fontWeight: 700
              }}>
                {user?.email?.[0].toUpperCase() || 'U'}
              </div>
            </div>
          )}
        </div>
      </nav>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 transition-all duration-300 relative">
        {/* Glass Pill Navbar */}
        <div className={`px-6 pt-5 pb-2 z-20 sticky top-0 bg-[#f0f2f5]/80 backdrop-blur-md`}>
          <div style={{
            display: "flex", alignItems: "center",
            background: "rgba(255,255,255,0.9)",
            border: "1px solid rgba(255,255,255,0.95)",
            borderRadius: 14,
            boxShadow: "0 2px 16px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04)",
            height: 50, padding: "0 6px", gap: 2,
          }}>
            {/* Mobile menu toggle */}
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 text-gray-500 hover:text-gray-700 rounded-md hover:bg-gray-100 focus:outline-none md:hidden mr-2"
              aria-label="Toggle sidebar"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>

            {(() => {
              let currentItemLabel = 'Dashboard';
              let parentTabs = [];
              NAV_STRUCTURE.forEach(sec => {
                sec.items.forEach(item => {
                  if (item.id === activeId) {
                    currentItemLabel = item.label;
                    if (item.sub) parentTabs = item.sub;
                  }
                  if (item.sub) {
                    item.sub.forEach(si => {
                      if (si.id === activeId) {
                        currentItemLabel = item.label;
                        parentTabs = item.sub;
                      }
                    });
                  }
                });
              });

              return (
                <>
                  <div style={{ paddingLeft: 10, paddingRight: 18, borderRight: (parentTabs.length > 0 || headerStore.rightContent || headerStore.refreshAction) ? `1px solid #e8eaed` : 'none', marginRight: 4, height: 26, display: "flex", alignItems: "center", flexShrink: 0 }}>
                    <h1 style={{ fontSize: 15, fontWeight: 800, margin: 0, letterSpacing: "-0.4px" }}>{currentItemLabel}</h1>
                  </div>

                  {/* Tabs */}
                  {parentTabs.length > 0 && (
                    <div className="hidden sm:flex" style={{ alignItems: "center", gap: 4, flex: 1, paddingLeft: 8 }}>
                      {parentTabs.map(tab => (
                        <Link
                          key={tab.id}
                          to={routeMap[tab.id] || `/${tab.id}`}
                          style={{
                            padding: "6px 12px",
                            borderRadius: 8,
                            border: "none",
                            textDecoration: "none",
                            background: activeId === tab.id ? "#2563eb" : "transparent",
                            color: activeId === tab.id ? "#ffffff" : "#6b7280",
                            fontSize: 13,
                            fontWeight: activeId === tab.id ? 600 : 500,
                            cursor: "pointer",
                            transition: "all 0.2s"
                          }}
                        >
                          {tab.label}
                        </Link>
                      ))}
                    </div>
                  )}

                  {/* Placeholder for when no tabs exist so right items float to right */}
                  {parentTabs.length === 0 && <div style={{ flex: 1 }} />}
                </>
              );
            })()}

            {/* Right Content */}
            <div style={{ display: "flex", gap: 6, paddingRight: 6, alignItems: "center", marginLeft: "auto" }}>
              <button
                onClick={() => setIsNotifOpen(o => !o)}
                aria-label="Notifications"
                style={{
                  position: "relative", width: 34, height: 34, borderRadius: 8,
                  border: `1.5px solid ${isNotifOpen ? "#d1d5db" : "#e4e6ea"}`,
                  background: isNotifOpen ? "#f5f6f8" : "#ffffff",
                  cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
                  transition: "all 0.14s", outline: "none",
                  animation: bellAnim ? "bell-shake 0.65s ease" : "none",
                  marginRight: 8
                }}
              >
                <svg width={15} height={15} viewBox="0 0 24 24" fill="none"
                  stroke={isNotifOpen ? "#111318" : "#5a6272"} strokeWidth={isNotifOpen ? 2.2 : 1.75} strokeLinecap="round" strokeLinejoin="round"
                  style={{ display: "block", flexShrink: 0 }}>
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                {unreadCount > 0 && (
                  <div style={{
                    position: "absolute", top: -5, right: -5,
                    minWidth: 17, height: 17, borderRadius: 10,
                    background: "#dc2626", border: "2px solid #fff",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 8.5, fontWeight: 800, color: "#fff", padding: "0 3px",
                    animation: "badge-in 0.28s cubic-bezier(.4,0,.2,1)",
                  }}>{unreadCount > 9 ? "9+" : unreadCount}</div>
                )}
              </button>

              {/* Health Indicator Dot */}
              <div
                className={`w-2.5 h-2.5 rounded-full mr-3 ${healthStatus === 'Green' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : healthStatus === 'Yellow' ? 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)] animate-pulse' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)] animate-ping'}`}
                title={`System Health: ${healthStatus}`}
              />

              {headerStore.rightContent}
              {headerStore.refreshAction && (
                <button
                  onClick={headerStore.refreshAction.onClick}
                  disabled={headerStore.refreshAction.loading}
                  style={{
                    padding: "6px 14px", borderRadius: 9, border: "none",
                    background: "linear-gradient(135deg, #2563eb, #4f46e5)",
                    color: "#fff", fontSize: 12, fontWeight: 600,
                    cursor: headerStore.refreshAction.loading ? "not-allowed" : "pointer", fontFamily: "inherit",
                    display: "flex", alignItems: "center", gap: 6,
                    boxShadow: "0 2px 8px rgba(37,99,235,0.28)",
                    opacity: headerStore.refreshAction.loading ? 0.7 : 1
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none" className={headerStore.refreshAction.loading ? 'animate-spin' : ''}>
                    <path d="M7 1.5v3M7 1.5L5 3.5M7 1.5L9 3.5M1.5 7h11M10.5 4.5A5.5 5.5 0 1 1 3.5 4.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Refresh
                </button>
              )}
            </div>
          </div>
        </div>

        <main className="flex-1 overflow-y-auto pt-2" style={{
          transition: "filter 0.2s, opacity 0.2s"
        }}>
          <div className="p-0 sm:px-8 pb-8 h-full">
            <Outlet />
          </div>
        </main>

        <NotificationPanel
          isOpen={isNotifOpen}
          onClose={() => setIsNotifOpen(false)}
          onUnreadCount={setUnreadCount}
        />
      </div>
    </div>
  );
};

export default MainLayout;
