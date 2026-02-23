import { useState, useRef, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";

// ── Tailwind color tokens matching your app ──────────────────────────────────
// Primary green: #059669 / emerald-600
// Red policy: #dc2626 / red-600
// Sidebar bg: white, border-gray-200
// Text: gray-900 / gray-600 / gray-400
// Card: white, shadow-sm, border-gray-200

// ── Lucide-style inline SVG icons ───────────────────────────────────────────
const Ico = ({ d, size = 16, className = "", strokeWidth = 1.75 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className={className}>
    {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
  </svg>
);

const I = {
  Shield: () => <Ico d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />,
  ShieldCheck: () => <Ico d={["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", "M9 12l2 2 4-4"]} />,
  Tag: () => <Ico d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" />,
  Tags: () => <Ico d={["M9 5H2v7l6.29 6.29c.94.94 2.48.94 3.42 0l3.58-3.58c.94-.94.94-2.48 0-3.42L9 5z", "M6 9.01V9"]} />,
  Layers: () => <Ico d={["M12 2L2 7l10 5 10-5-10-5z", "M2 17l10 5 10-5", "M2 12l10 5 10-5"]} />,
  Zap: () => <Ico d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />,
  Eye: () => <Ico d={["M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z", "M12 9a3 3 0 100 6 3 3 0 000-6z"]} />,
  Plus: () => <Ico d="M12 5v14M5 12h14" />,
  X: () => <Ico d="M18 6L6 18M6 6l12 12" />,
  Check: () => <Ico d="M20 6L9 17l-5-5" />,
  ChevronDown: () => <Ico d="M6 9l6 6 6-6" />,
  ChevronRight: () => <Ico d="M9 18l6-6-6-6" />,
  Trash2: () => <Ico d={["M3 6h18", "M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6", "M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"]} />,
  Edit2: () => <Ico d="M17 3a2.828 2.828 0 114 4L7.5 20.5 2 22l1.5-5.5L17 3z" />,
  Info: () => <Ico d={["M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z", "M12 8h.01", "M12 12v4"]} />,
  AlertTriangle: () => <Ico d={["M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z", "M12 9v4", "M12 17h.01"]} />,
  Clock: () => <Ico d={["M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z", "M12 6v6l4 2"]} />,
  Settings: () => <Ico d={["M12 15a3 3 0 100-6 3 3 0 000 6z", "M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"]} />,
  BarChart2: () => <Ico d={["M18 20V10", "M12 20V4", "M6 20v-6"]} />,
  Activity: () => <Ico d="M22 12h-4l-3 9L9 3l-3 9H2" />,
  Target: () => <Ico d={["M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z", "M12 18a6 6 0 100-12 6 6 0 000 12z", "M12 14a2 2 0 100-4 2 2 0 000 4z"]} />,
  ArrowRight: () => <Ico d={["M5 12h14", "M12 5l7 7-7 7"]} />,
  Copy: () => <Ico d={["M8 4H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-2", "M8 4a2 2 0 012-2h4a2 2 0 012 2v0a2 2 0 01-2 2h-4a2 2 0 01-2-2v0z"]} />,
  Package: () => <Ico d={["M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z", "M3.27 6.96L12 12.01l8.73-5.05", "M12 22.08V12"]} />,
  Filter: () => <Ico d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" />,
  Download: () => <Ico d={["M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4", "M7 10l5 5 5-5", "M12 15V3"]} />,
  Minus: () => <Ico d="M5 12h14" />,
  Circle: () => <Ico d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" />,
  TrendingUp: () => <Ico d={["M23 6l-9.5 9.5-5-5L1 18", "M17 6h6v6"]} />,
  Bell: () => <Ico d={["M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9", "M13.73 21a2 2 0 01-3.46 0"]} />,
  Lock: () => <Ico d={["M19 11H5a2 2 0 00-2 2v7a2 2 0 002 2h14a2 2 0 002-2v-7a2 2 0 00-2-2z", "M7 11V7a5 5 0 0110 0v4"]} />,
  Unlock: () => <Ico d={["M19 11H5a2 2 0 00-2 2v7a2 2 0 002 2h14a2 2 0 002-2v-7a2 2 0 00-2-2z", "M7 11V7a5 5 0 019.9-1"]} />,
  RefreshCw: () => <Ico d={["M23 4v6h-6", "M1 20v-6h6", "M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"]} />,
  ExternalLink: () => <Ico d={["M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6", "M15 3h6v6", "M10 14L21 3"]} />,
  Cpu: () => <Ico d={["M18 4H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2z", "M9 9h6v6H9z"]} />,
};

// ── Shared primitives ────────────────────────────────────────────────────────
const Badge = ({ children, variant = "gray", size = "sm" }) => {
  const variants = {
    gray: "bg-gray-100 text-gray-600 border-gray-200",
    green: "bg-emerald-50 text-emerald-700 border-emerald-200",
    red: "bg-red-50 text-red-700 border-red-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    blue: "bg-blue-50 text-blue-700 border-blue-200",
    violet: "bg-violet-50 text-violet-700 border-violet-200",
    teal: "bg-teal-50 text-teal-700 border-teal-200",
  };
  const sizes = { xs: "text-xs px-1.5 py-0.5", sm: "text-xs px-2 py-0.5", md: "text-sm px-2.5 py-1" };
  return <span className={`inline-flex items-center gap-1 font-medium rounded-md border ${variants[variant]} ${sizes[size]}`}>{children}</span>;
};

const Toggle = ({ checked, onChange, disabled }) => (
  <button disabled={disabled} onClick={() => onChange(!checked)}
    className={`relative inline-flex w-9 h-5 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-1 ${checked ? "bg-emerald-600" : "bg-gray-200"} ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}>
    <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
  </button>
);

const Btn = ({ children, variant = "primary", size = "md", onClick, disabled, className = "", type = "button" }) => {
  const variants = {
    primary: "bg-emerald-600 hover:bg-emerald-700 text-white border-emerald-600",
    danger: "bg-red-600 hover:bg-red-700 text-white border-red-600",
    secondary: "bg-white hover:bg-gray-50 text-gray-700 border-gray-300",
    ghost: "bg-transparent hover:bg-gray-100 text-gray-600 border-transparent",
    outline: "bg-white hover:bg-emerald-50 text-emerald-700 border-emerald-300",
  };
  const sizes = { sm: "px-3 py-1.5 text-sm gap-1.5", md: "px-4 py-2 text-sm gap-2", lg: "px-5 py-2.5 text-base gap-2" };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`inline-flex items-center justify-center font-medium rounded-lg border transition-all focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${className}`}>
      {children}
    </button>
  );
};

const Input = ({ label, required, value, onChange, placeholder, type = "text", hint, error, className = "" }) => (
  <div className={className}>
    {label && <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}{required && <span className="text-red-500 ml-0.5">*</span>}</label>}
    <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      className={`w-full px-3 py-2 text-sm border rounded-lg bg-white text-gray-900 placeholder-gray-400 transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 ${error ? "border-red-400 focus:ring-red-400 focus:border-red-400" : "border-gray-300"}`} />
    {hint && <p className="mt-1.5 text-xs text-gray-500">{hint}</p>}
    {error && <p className="mt-1.5 text-xs text-red-600">{error}</p>}
  </div>
);

const Select = ({ label, required, value, onChange, children, hint, className = "" }) => (
  <div className={className}>
    {label && <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}{required && <span className="text-red-500 ml-0.5">*</span>}</label>}
    <div className="relative">
      <select value={value} onChange={e => onChange(e.target.value)}
        className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white text-gray-900 appearance-none focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 pr-9">
        {children}
      </select>
      <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-400"><I.ChevronDown /></div>
    </div>
    {hint && <p className="mt-1.5 text-xs text-gray-500">{hint}</p>}
  </div>
);

const Card = ({ children, className = "" }) => (
  <div className={`bg-white border border-gray-200 rounded-xl shadow-sm ${className}`}>{children}</div>
);

const InfoBanner = ({ children, variant = "blue" }) => {
  const v = { blue: "bg-blue-50 border-blue-200 text-blue-800", green: "bg-emerald-50 border-emerald-200 text-emerald-800", amber: "bg-amber-50 border-amber-200 text-amber-800", red: "bg-red-50 border-red-200 text-red-800" };
  const icons = { blue: <I.Info />, green: <I.ShieldCheck />, amber: <I.AlertTriangle />, red: <I.AlertTriangle /> };
  return (
    <div className={`flex gap-3 p-3.5 rounded-lg border text-sm ${v[variant]}`}>
      <div className="flex-shrink-0 mt-0.5">{icons[variant]}</div>
      <div className="flex-1">{children}</div>
    </div>
  );
};

const Modal = ({ open, onClose, title, subtitle, icon, iconColor = "text-emerald-600", children, footer, size = "md" }) => {
  if (!open) return null;
  const sizes = { sm: "max-w-md", md: "max-w-2xl", lg: "max-w-3xl", xl: "max-w-5xl" };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.4)" }}>
      <div className={`bg-white rounded-2xl shadow-2xl w-full ${sizes[size]} max-h-[90vh] flex flex-col`}>
        <div className="flex items-start justify-between px-6 py-5 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className={iconColor}>{icon}</div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
              {subtitle && <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>}
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"><I.X /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-end gap-3 bg-gray-50 rounded-b-2xl">{footer}</div>}
      </div>
    </div>
  );
};

// ── Score Donut ──────────────────────────────────────────────────────────────
const ScoreDonut = ({ score, size = 64, strokeWidth = 6 }) => {
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const color = score >= 80 ? "#059669" : score >= 60 ? "#d97706" : "#dc2626";
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f3f4f6" strokeWidth={strokeWidth} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
          strokeDasharray={`${dash} ${circ - dash}`} strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.6s ease" }} />
      </svg>
      <div className="absolute text-center">
        <div className="text-sm font-bold" style={{ color, lineHeight: 1 }}>{score}</div>
      </div>
    </div>
  );
};

// ── Mini compliance bar ──────────────────────────────────────────────────────
const ComplianceBar = ({ value, showLabel = true }) => {
  const color = value >= 80 ? "bg-emerald-500" : value >= 60 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${value}%` }} />
      </div>
      {showLabel && <span className="text-xs font-medium text-gray-600 w-8 text-right">{value}%</span>}
    </div>
  );
};

// ── Heatmap cell for tag coverage ───────────────────────────────────────────
const TagHeatmapCell = ({ value, label }) => {
  const bg = value >= 90 ? "bg-emerald-500" : value >= 70 ? "bg-emerald-300" : value >= 50 ? "bg-amber-300" : value >= 30 ? "bg-orange-400" : "bg-red-500";
  const text = value >= 70 ? "text-white" : "text-gray-800";
  return (
    <div title={`${label}: ${value}%`} className={`${bg} ${text} rounded flex flex-col items-center justify-center p-2 cursor-pointer hover:opacity-90 transition-opacity`} style={{ minHeight: 56 }}>
      <div className="text-xs font-semibold">{value}%</div>
      <div className="text-xs opacity-75 mt-0.5 truncate w-full text-center">{label}</div>
    </div>
  );
};

// ── Step Wizard ──────────────────────────────────────────────────────────────
const StepWizard = ({ steps, currentStep }) => (
  <div className="flex items-center gap-0">
    {steps.map((step, i) => (
      <div key={i} className="flex items-center">
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${i + 1 === currentStep ? "bg-emerald-50 text-emerald-700" : i + 1 < currentStep ? "text-emerald-600" : "text-gray-400"}`}>
          <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${i + 1 === currentStep ? "bg-emerald-600 text-white" : i + 1 < currentStep ? "bg-emerald-100 text-emerald-600" : "bg-gray-100 text-gray-400"}`}>
            {i + 1 < currentStep ? <I.Check /> : i + 1}
          </div>
          <span className="hidden sm:inline">{step}</span>
        </div>
        {i < steps.length - 1 && <div className={`w-8 h-px mx-1 ${i + 1 < currentStep ? "bg-emerald-300" : "bg-gray-200"}`} />}
      </div>
    ))}
  </div>
);

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════════════════════════
export default function TagGovernancePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryParams = new URLSearchParams(location.search);
  const tabFromUrl = queryParams.get("tab") || "policies";

  const [activeTab, setActiveTab] = useState(tabFromUrl);

  useEffect(() => {
    if (tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
  }, [tabFromUrl]);

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    navigate(`?tab=${tabId}`);
  };

  return (
    <div className="min-h-screen bg-gray-50" style={{ fontFamily: "'DM Sans', 'Nunito', system-ui, sans-serif" }}>
      <div className="p-6 max-w-7xl mx-auto">
        {activeTab === "policies" && <PoliciesTab />}
        {activeTab === "templates" && <TemplatesTab />}
        {activeTab === "scoring" && <ScoringTab />}
        {activeTab === "automation" && <AutomationTab />}
        {activeTab === "monitor" && <MonitorTab />}
      </div>
    </div>
  );
}

const TabBtn = ({ id, active, onClick, icon, label, accent }) => {
  const activeStyle = accent === "red"
    ? "border-red-600 text-red-600"
    : "border-emerald-600 text-emerald-600";
  return (
    <button onClick={() => onClick(id)}
      className={`flex items-center gap-2 px-4 py-3.5 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${active ? activeStyle : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"}`}>
      <span className={active ? (accent === "red" ? "text-red-600" : "text-emerald-600") : "text-gray-400"}>{icon}</span>
      {label}
    </button>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 1: GOVERNANCE POLICIES
// ═══════════════════════════════════════════════════════════════════════════════
function PoliciesTab() {
  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [policies, setPolicies] = useState([
    { id: 1, key: "owner", enforcement: "required", valueMode: "free", pattern: "^[a-z]+@company\\.com$", description: "Team email address responsible for this resource", enabled: true, resources: 847 },
    { id: 2, key: "environment", enforcement: "strict", valueMode: "allowed", allowedValues: ["production", "staging", "development", "sandbox"], description: "Deployment environment classification", enabled: true, resources: 1203 },
    { id: 3, key: "cost-center", enforcement: "required", valueMode: "pattern", pattern: "^CC-[0-9]{4}$", description: "Finance department cost tracking code", enabled: true, resources: 612 },
    { id: 4, key: "data-classification", enforcement: "advisory", valueMode: "allowed", allowedValues: ["public", "internal", "confidential", "restricted"], description: "Data sensitivity level for compliance", enabled: false, resources: 0 },
  ]);

  const grouped = {
    strict: policies.filter(p => p.enforcement === "strict"),
    required: policies.filter(p => p.enforcement === "required"),
    advisory: policies.filter(p => p.enforcement === "advisory"),
  };

  const enforcementMeta = {
    strict: { label: "Strict", color: "red", desc: "Blocks ALL operations including authorization on non-compliant resources", icon: <I.Lock /> },
    required: { label: "Required", color: "amber", desc: "Blocks cleanup/delete actions on non-compliant resources", icon: <I.Shield /> },
    advisory: { label: "Advisory", color: "blue", desc: "Shows warnings but does not block any actions", icon: <I.Info /> },
  };

  const handleSave = (policy) => {
    if (editItem) {
      setPolicies(policies.map(p => p.id === editItem.id ? { ...p, ...policy } : p));
      setEditItem(null);
    } else {
      setPolicies([...policies, { ...policy, id: Date.now(), enabled: true, resources: 0 }]);
      setShowCreate(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="text-red-600"><I.Shield /></div>
            <h1 className="text-2xl font-bold text-gray-900">Tag Policies</h1>
          </div>
          <p className="text-gray-500 text-sm">Define enforcement rules for resource tags. Required policies block operations on non-compliant resources.</p>
        </div>
        <Btn variant="danger" onClick={() => setShowCreate(true)}><I.Plus /> Create Policy</Btn>
      </div>

      <InfoBanner variant="blue">
        <div className="font-medium mb-1">Tag Policies are governance rules that enforce tagging compliance.</div>
        <ul className="space-y-0.5 text-sm mt-2">
          <li><strong>Advisory:</strong> Shows warnings but does not block actions</li>
          <li><strong>Required:</strong> Blocks cleanup/delete actions on non-compliant resources</li>
          <li><strong>Strict:</strong> Blocks ALL operations including authorization</li>
        </ul>
      </InfoBanner>

      {/* Policy groups */}
      {Object.entries(grouped).map(([level, items]) => (
        <div key={level}>
          <div className="flex items-center gap-2 mb-3">
            <div className={`text-${enforcementMeta[level].color}-600`}>{enforcementMeta[level].icon}</div>
            <h2 className="text-base font-semibold text-gray-800">{enforcementMeta[level].label} Policies ({items.length})</h2>
            <span className="text-xs text-gray-400 ml-1">— {enforcementMeta[level].desc}</span>
          </div>
          {items.length === 0 ? (
            <Card className="p-10 text-center">
              <div className="text-gray-300 flex justify-center mb-3"><I.Shield /></div>
              <p className="text-gray-400 text-sm">No {level} policies defined yet.</p>
              <button onClick={() => setShowCreate(true)} className="mt-2 text-sm text-red-600 hover:underline font-medium">Create your first policy</button>
            </Card>
          ) : (
            <div className="space-y-2">
              {items.map(p => (
                <PolicyRow key={p.id} policy={p} meta={enforcementMeta[level]}
                  onEdit={() => setEditItem(p)}
                  onDelete={() => setPolicies(policies.filter(x => x.id !== p.id))}
                  onToggle={() => setPolicies(policies.map(x => x.id === p.id ? { ...x, enabled: !x.enabled } : x))} />
              ))}
            </div>
          )}
        </div>
      ))}

      <PolicyModal open={showCreate || !!editItem} initial={editItem} onClose={() => { setShowCreate(false); setEditItem(null); }} onSave={handleSave} />
    </div>
  );
}

function PolicyRow({ policy, meta, onEdit, onDelete, onToggle }) {
  const [expanded, setExpanded] = useState(false);
  const enforcementColors = { strict: "red", required: "amber", advisory: "blue" };
  const color = enforcementColors[policy.enforcement];

  return (
    <Card className={`overflow-hidden transition-all ${!policy.enabled ? "opacity-60" : ""}`}>
      <div className="px-5 py-4 flex items-center gap-4">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className={`w-2 h-2 rounded-full flex-shrink-0 ${policy.enabled ? `bg-${color}-500` : "bg-gray-300"}`} />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <code className="text-sm font-mono font-semibold text-gray-900 bg-gray-100 px-2 py-0.5 rounded">{policy.key}</code>
              <Badge variant={color === "amber" ? "amber" : color === "red" ? "red" : "blue"}>{meta.label}</Badge>
              <Badge variant="gray">{policy.valueMode === "allowed" ? `${policy.allowedValues?.length || 0} allowed values` : policy.valueMode === "pattern" ? "Pattern" : "Free text"}</Badge>
            </div>
            {policy.description && <p className="text-xs text-gray-400 mt-1 truncate">{policy.description}</p>}
          </div>
        </div>
        <div className="flex items-center gap-5 flex-shrink-0">
          <div className="text-right hidden md:block">
            <div className="text-xs text-gray-400">Resources</div>
            <div className="text-sm font-semibold text-gray-700">{policy.resources.toLocaleString()}</div>
          </div>
          <Toggle checked={policy.enabled} onChange={onToggle} />
          <div className="flex gap-1">
            <button onClick={onEdit} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"><I.Edit2 /></button>
            <button onClick={onDelete} className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors"><I.Trash2 /></button>
          </div>
          <button onClick={() => setExpanded(!expanded)} className={`text-gray-400 transition-transform ${expanded ? "rotate-90" : ""}`}><I.ChevronRight /></button>
        </div>
      </div>
      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50 px-5 py-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div><span className="text-gray-400 text-xs block mb-0.5">Tag Key</span><code className="text-gray-800 font-mono">{policy.key}</code></div>
            <div><span className="text-gray-400 text-xs block mb-0.5">Enforcement</span><span className="text-gray-800 capitalize">{policy.enforcement}</span></div>
            <div><span className="text-gray-400 text-xs block mb-0.5">Value Mode</span><span className="text-gray-800 capitalize">{policy.valueMode}</span></div>
            <div><span className="text-gray-400 text-xs block mb-0.5">Status</span><span className={`font-medium ${policy.enabled ? "text-emerald-600" : "text-gray-400"}`}>{policy.enabled ? "Active" : "Disabled"}</span></div>
            {policy.pattern && <div className="col-span-2"><span className="text-gray-400 text-xs block mb-0.5">Validation Regex</span><code className="text-gray-700 text-xs bg-gray-100 px-2 py-1 rounded">{policy.pattern}</code></div>}
            {policy.allowedValues?.length > 0 && (
              <div className="col-span-4"><span className="text-gray-400 text-xs block mb-1.5">Allowed Values</span>
                <div className="flex flex-wrap gap-1.5">{policy.allowedValues.map(v => <Badge key={v} variant="gray">{v}</Badge>)}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

function PolicyModal({ open, initial, onClose, onSave }) {
  const [key, setKey] = useState(initial?.key || "");
  const [desc, setDesc] = useState(initial?.description || "");
  const [enforcement, setEnforcement] = useState(initial?.enforcement || "advisory");
  const [valueMode, setValueMode] = useState(initial?.valueMode || "free");
  const [pattern, setPattern] = useState(initial?.pattern || "");
  const [allowedValues, setAllowedValues] = useState(initial?.allowedValues || []);
  const [newVal, setNewVal] = useState("");

  useEffect(() => {
    if (initial) { setKey(initial.key || ""); setDesc(initial.description || ""); setEnforcement(initial.enforcement || "advisory"); setValueMode(initial.valueMode || "free"); setPattern(initial.pattern || ""); setAllowedValues(initial.allowedValues || []); }
    else { setKey(""); setDesc(""); setEnforcement("advisory"); setValueMode("free"); setPattern(""); setAllowedValues([]); setNewVal(""); }
  }, [initial, open]);

  const handle = () => { onSave({ key, description: desc, enforcement, valueMode, pattern, allowedValues }); };

  return (
    <Modal open={open} onClose={onClose} size="md"
      title={initial ? "Edit Tag Policy" : "Create Tag Policy"}
      icon={<I.Shield size={20} />} iconColor="text-red-600"
      footer={<><Btn variant="secondary" onClick={onClose}>Cancel</Btn><Btn variant="danger" onClick={handle} disabled={!key}>Create Policy</Btn></>}>
      <div className="space-y-5">
        <Input label="Tag Key" required value={key} onChange={setKey} placeholder="e.g., Owner, Environment, CostCenter" hint="Use the exact key name that will appear on AWS resources" />
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">Description</label>
          <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2} placeholder="Help text for users (e.g., 'Enter your team email address')"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 resize-none" />
        </div>

        <Select label="Enforcement Level" required value={enforcement} onChange={setEnforcement}>
          <option value="advisory">Advisory — Warning only, no blocking</option>
          <option value="required">Required — Blocks cleanup/delete on non-compliant</option>
          <option value="strict">Strict — Blocks ALL operations including authorization</option>
        </Select>

        {(enforcement === "required" || enforcement === "strict") && (
          <InfoBanner variant="amber">
            <strong>{enforcement === "strict" ? "Strict" : "Required"} policies</strong> will {enforcement === "strict" ? "block all operations (including marking as authorized)" : "block delete and cleanup operations"} on resources missing this tag.
          </InfoBanner>
        )}

        <Select label="Value Mode" value={valueMode} onChange={setValueMode}>
          <option value="free">Free Text — Any value allowed</option>
          <option value="allowed">Allowed Values — Restrict to a predefined list</option>
          <option value="pattern">Pattern — Validate against a regex</option>
          <option value="email">Email — Must be a valid email address</option>
          <option value="arn">AWS ARN — Must match ARN format</option>
        </Select>

        {valueMode === "allowed" && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Allowed Values</label>
            <div className="flex gap-2 mb-2">
              <input value={newVal} onChange={e => setNewVal(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && newVal.trim()) { setAllowedValues([...allowedValues, newVal.trim()]); setNewVal(""); } }}
                placeholder="Type a value and press Enter"
                className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500" />
              <Btn variant="outline" onClick={() => { if (newVal.trim()) { setAllowedValues([...allowedValues, newVal.trim()]); setNewVal(""); } }}><I.Plus /></Btn>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {allowedValues.map((v, i) => (
                <button key={i} onClick={() => setAllowedValues(allowedValues.filter((_, j) => j !== i))}
                  className="inline-flex items-center gap-1 px-2.5 py-1 bg-gray-100 hover:bg-red-50 text-gray-700 hover:text-red-700 border border-gray-200 hover:border-red-200 rounded-md text-xs font-medium transition-colors">
                  {v} <I.X />
                </button>
              ))}
              {allowedValues.length === 0 && <p className="text-xs text-gray-400">No values added yet</p>}
            </div>
          </div>
        )}

        {(valueMode === "pattern") && (
          <Input label="Validation Regex" value={pattern} onChange={setPattern}
            placeholder="e.g., ^CC-\d{4}$ for CostCenter format"
            hint="Regular expression to validate tag values (e.g., ^[a-z]+@company\.com$ for emails)" />
        )}
      </div>
    </Modal>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 2: TAG TEMPLATES
// ═══════════════════════════════════════════════════════════════════════════════
function TemplatesTab() {
  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState(null);
  const [templates, setTemplates] = useState([
    {
      id: 1, name: "EC2 Workload Standard", description: "Standard tagging for production compute resources", scope: ["EC2", "EBS"], isDefault: true,
      tags: [
        { key: "environment", required: true, type: "enum", values: ["production", "staging", "development"], weight: 20, description: "Deployment environment" },
        { key: "owner", required: true, type: "email", values: [], weight: 20, description: "Responsible team email" },
        { key: "team", required: true, type: "enum", values: ["platform", "data", "backend", "frontend", "security"], weight: 15, description: "Owning team" },
        { key: "cost-center", required: true, type: "pattern", values: [], pattern: "CC-[0-9]{4}", weight: 20, description: "Finance cost center" },
        { key: "project", required: false, type: "free", values: [], weight: 10, description: "Project name" },
        { key: "data-classification", required: false, type: "enum", values: ["public", "internal", "confidential", "restricted"], weight: 15, description: "Data sensitivity" },
      ],
      resources: 847, compliance: 91
    },
    {
      id: 2, name: "Database Resources", description: "For RDS, DynamoDB, and caching layers", scope: ["RDS", "DynamoDB", "ElastiCache"],
      tags: [
        { key: "environment", required: true, type: "enum", values: ["production", "staging", "development"], weight: 15, description: "" },
        { key: "owner", required: true, type: "email", values: [], weight: 20, description: "" },
        { key: "cost-center", required: true, type: "pattern", values: [], weight: 20, description: "" },
        { key: "backup-policy", required: true, type: "enum", values: ["daily", "weekly", "monthly", "none"], weight: 20, description: "Backup frequency requirement" },
        { key: "data-classification", required: true, type: "enum", values: ["public", "internal", "confidential", "restricted"], weight: 25, description: "" },
      ],
      resources: 142, compliance: 78
    },
  ]);

  const handleSave = (template) => {
    if (editItem) { setTemplates(templates.map(t => t.id === editItem.id ? { ...t, ...template } : t)); setEditItem(null); }
    else { setTemplates([...templates, { ...template, id: Date.now(), resources: 0, compliance: 0 }]); setShowCreate(false); }
  };

  if (showCreate || editItem) {
    return <TemplateBuilder initial={editItem} onClose={() => { setShowCreate(false); setEditItem(null); }} onSave={handleSave} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="text-emerald-600"><I.Layers /></div>
            <h1 className="text-2xl font-bold text-gray-900">Tag Templates</h1>
          </div>
          <p className="text-gray-500 text-sm">Create reusable tag presets with scoring weights for quick bulk tagging operations</p>
        </div>
        <Btn onClick={() => setShowCreate(true)}><I.Plus /> Create Template</Btn>
      </div>

      <InfoBanner variant="green">
        <div className="font-medium mb-1">Tag Templates are reusable tag schemas with compliance scoring weights.</div>
        <ul className="space-y-0.5 text-sm mt-2">
          <li>Use <strong>dynamic variables</strong> like <code className="bg-emerald-100 px-1 rounded">{"{CURRENT_USER_EMAIL}"}</code> for auto-filled values</li>
          <li>Templates follow your organization's <strong>Tag Policies</strong> for validation</li>
          <li>Each tag has a <strong>weight</strong> that contributes to the resource's compliance score (0–100)</li>
          <li>Apply templates via the <strong>Bulk Tag Wizard</strong> in Resource Hygiene</li>
        </ul>
      </InfoBanner>

      {/* Tag coverage heatmap */}
      {templates.length > 0 && (
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-800">Tag Coverage Heatmap</h3>
              <p className="text-xs text-gray-400 mt-0.5">Compliance rate per tag key across all templates</p>
            </div>
            <Badge variant="gray">Live data</Badge>
          </div>
          <div className="grid gap-1.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(80px, 1fr))" }}>
            {[
              { label: "environment", value: 94 }, { label: "owner", value: 72 }, { label: "team", value: 68 },
              { label: "cost-center", value: 61 }, { label: "project", value: 44 }, { label: "backup-policy", value: 78 },
              { label: "data-class", value: 29 }, { label: "managed-by", value: 88 },
            ].map((cell, i) => <TagHeatmapCell key={i} {...cell} />)}
          </div>
          <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
            <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded bg-emerald-500" />&gt;90% Excellent</div>
            <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded bg-amber-300" />50–70% Moderate</div>
            <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded bg-red-500" />&lt;30% Critical</div>
          </div>
        </Card>
      )}

      {templates.length === 0 ? (
        <Card className="p-16 text-center">
          <div className="text-gray-200 flex justify-center mb-4"><I.Layers size={48} /></div>
          <p className="text-gray-500 font-medium">No templates defined yet.</p>
          <button onClick={() => setShowCreate(true)} className="mt-2 text-sm text-emerald-600 hover:underline font-medium">Create your first template</button>
        </Card>
      ) : (
        <div className="space-y-3">
          {templates.map(t => <TemplateCard key={t.id} template={t} onEdit={() => setEditItem(t)} onDelete={() => setTemplates(templates.filter(x => x.id !== t.id))} />)}
        </div>
      )}
    </div>
  );
}

function TemplateCard({ template, onEdit, onDelete }) {
  const [expanded, setExpanded] = useState(false);
  const required = template.tags.filter(t => t.required).length;

  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-4 flex items-center gap-4 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="w-10 h-10 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-center flex-shrink-0 text-emerald-600">
          <I.Package />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-gray-900">{template.name}</span>
            {template.isDefault && <Badge variant="green">Default</Badge>}
            <div className="flex gap-1">{template.scope.map(s => <Badge key={s} variant="gray" size="xs">{s}</Badge>)}</div>
          </div>
          {template.description && <p className="text-xs text-gray-400 mt-0.5 truncate">{template.description}</p>}
        </div>
        <div className="flex items-center gap-6 flex-shrink-0">
          <div className="hidden lg:block text-right">
            <div className="text-xs text-gray-400 mb-1">Compliance</div>
            <div className="w-28"><ComplianceBar value={template.compliance} /></div>
          </div>
          <div className="text-right hidden md:block">
            <div className="text-xs text-gray-400">Tags</div>
            <div className="text-sm font-medium text-gray-700"><span className="text-red-600">{required}R</span> + <span className="text-gray-500">{template.tags.length - required}O</span></div>
          </div>
          <div className="text-right hidden md:block">
            <div className="text-xs text-gray-400">Resources</div>
            <div className="text-sm font-semibold text-gray-700">{template.resources.toLocaleString()}</div>
          </div>
          <div className="flex gap-1">
            <button onClick={e => { e.stopPropagation(); onEdit(); }} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"><I.Edit2 /></button>
            <button onClick={e => { e.stopPropagation(); onDelete(); }} className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors"><I.Trash2 /></button>
          </div>
          <div className={`text-gray-400 transition-transform ${expanded ? "rotate-90" : ""}`}><I.ChevronRight /></div>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-100">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-gray-100 bg-gray-50">
                {["Tag Key", "Required", "Value Type", "Weight", "Description"].map(h => (
                  <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr></thead>
              <tbody className="divide-y divide-gray-50">
                {template.tags.map((tag, i) => {
                  const totalWeight = template.tags.reduce((s, t) => s + t.weight, 0);
                  const pct = Math.round((tag.weight / totalWeight) * 100);
                  return (
                    <tr key={i} className="hover:bg-gray-50/50 transition-colors">
                      <td className="px-4 py-2.5"><code className="text-xs font-mono font-medium text-gray-800 bg-gray-100 px-1.5 py-0.5 rounded">{tag.key}</code></td>
                      <td className="px-4 py-2.5"><Badge variant={tag.required ? "red" : "gray"}>{tag.required ? "Required" : "Optional"}</Badge></td>
                      <td className="px-4 py-2.5">
                        <Badge variant="teal">{tag.type}</Badge>
                        {tag.values?.length > 0 && <span className="text-xs text-gray-400 ml-1">{tag.values.length} values</span>}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div className="h-full bg-emerald-400 rounded-full" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs text-gray-500">{pct}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-500">{tag.description || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Template Builder (full-page wizard) ──────────────────────────────────────
function TemplateBuilder({ initial, onClose, onSave }) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState(initial?.name || "");
  const [desc, setDesc] = useState(initial?.description || "");
  const [scope, setScope] = useState(initial?.scope || []);
  const [isDefault, setIsDefault] = useState(initial?.isDefault || false);
  const [tags, setTags] = useState(initial?.tags || []);
  const [newTag, setNewTag] = useState({ key: "", required: true, type: "free", values: [], pattern: "", description: "", weight: 10 });
  const [newVal, setNewVal] = useState("");

  const resourceTypes = ["EC2", "EBS", "RDS", "DynamoDB", "S3", "ELB", "VPC", "Lambda", "EKS", "ElastiCache", "NAT Gateway", "Elastic IP", "Security Group", "CloudFront", "SNS", "SQS"];
  const tagTypes = [
    { id: "free", label: "Free Text" }, { id: "enum", label: "Allowed Values" },
    { id: "email", label: "Email Address" }, { id: "pattern", label: "Regex Pattern" },
    { id: "number", label: "Numeric" }, { id: "boolean", label: "Boolean (true/false)" },
    { id: "arn", label: "AWS ARN" }, { id: "date", label: "ISO Date (YYYY-MM-DD)" },
  ];
  const dynamicVars = ["{CURRENT_USER_EMAIL}", "{CURRENT_USER_NAME}", "{CURRENT_DATE}", "{CURRENT_ORG}", "{PROJECT_ID}", "{TEAM_NAME}"];
  const wizardSteps = ["Basic Info", "Resource Scope", "Tag Schema", "Weights & Review"];

  const addTag = () => {
    if (!newTag.key.trim()) return;
    setTags([...tags, { ...newTag, values: [...newTag.values] }]);
    setNewTag({ key: "", required: true, type: "free", values: [], pattern: "", description: "", weight: 10 });
    setNewVal("");
  };

  const totalWeight = tags.reduce((s, t) => s + t.weight, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="text-emerald-600"><I.Layers /></div>
            <h1 className="text-2xl font-bold text-gray-900">{initial ? "Edit Template" : "Create Tag Template"}</h1>
          </div>
          <p className="text-gray-500 text-sm">Define the compliance contract for a resource group</p>
        </div>
        <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
      </div>

      <Card className="p-4">
        <StepWizard steps={wizardSteps} currentStep={step} />
      </Card>

      {/* Step 1 */}
      {step === 1 && (
        <Card className="p-6 space-y-5">
          <h2 className="text-base font-semibold text-gray-800 border-b border-gray-100 pb-3">Template Identity</h2>
          <Input label="Template Name" required value={name} onChange={setName} placeholder="e.g., Production Standard, Dev Team Alpha" />
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Description</label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3}
              placeholder="Brief description of when to use this template"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-none" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Dynamic Variables</label>
            <p className="text-xs text-gray-400 mb-2">Click to copy a variable to use as a tag value in your schema:</p>
            <div className="flex flex-wrap gap-2">
              {dynamicVars.map(v => (
                <button key={v} onClick={() => navigator.clipboard?.writeText(v)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-mono bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 rounded-lg transition-colors">
                  <I.Copy /> {v}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between p-4 border border-gray-200 rounded-xl bg-gray-50">
            <div>
              <div className="text-sm font-medium text-gray-800">Set as Default Template</div>
              <div className="text-xs text-gray-500 mt-0.5">Applied to resource types with no specific template assigned</div>
            </div>
            <Toggle checked={isDefault} onChange={setIsDefault} />
          </div>
        </Card>
      )}

      {/* Step 2 */}
      {step === 2 && (
        <Card className="p-6 space-y-5">
          <h2 className="text-base font-semibold text-gray-800 border-b border-gray-100 pb-3">Resource Scope</h2>
          <InfoBanner variant="blue">Select which AWS resource types this template applies to. A resource inherits the most specific matching template.</InfoBanner>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-3">Resource Types</label>
            <div className="grid grid-cols-4 gap-2">
              {resourceTypes.map(rt => {
                const sel = scope.includes(rt);
                return (
                  <button key={rt} onClick={() => setScope(sel ? scope.filter(s => s !== rt) : [...scope, rt])}
                    className={`px-3 py-2.5 text-sm rounded-lg border transition-all flex items-center gap-2 ${sel ? "bg-emerald-50 border-emerald-300 text-emerald-800 font-medium" : "bg-white border-gray-200 text-gray-600 hover:border-emerald-200 hover:bg-emerald-50/50"}`}>
                    <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${sel ? "bg-emerald-600 border-emerald-600 text-white" : "border-gray-300"}`}>
                      {sel && <I.Check />}
                    </div>
                    <span className="truncate">{rt}</span>
                  </button>
                );
              })}
            </div>
          </div>
          {scope.length > 0 && (
            <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
              <div className="text-emerald-600 flex-shrink-0"><I.Check /></div>
              <p className="text-sm text-emerald-800 font-medium">Template will apply to: {scope.join(", ")}</p>
            </div>
          )}
        </Card>
      )}

      {/* Step 3 */}
      {step === 3 && (
        <div className="space-y-4">
          <Card className="overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-800">Tag Schema</h2>
              <div className="flex gap-3 text-xs text-gray-500">
                <span><strong className="text-red-600">{tags.filter(t => t.required).length}</strong> required</span>
                <span><strong className="text-gray-700">{tags.filter(t => !t.required).length}</strong> optional</span>
              </div>
            </div>
            {tags.length === 0 ? (
              <div className="p-10 text-center text-gray-400 text-sm">No tags defined yet. Add your first tag below.</div>
            ) : (
              <table className="w-full text-sm">
                <thead><tr className="border-b border-gray-100 bg-gray-50">
                  {["Tag Key", "Required", "Type", "Weight", "Description", ""].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">{h}</th>
                  ))}
                </tr></thead>
                <tbody className="divide-y divide-gray-50">
                  {tags.map((tag, i) => (
                    <tr key={i} className="hover:bg-gray-50/50">
                      <td className="px-4 py-2.5"><code className="text-xs font-mono bg-gray-100 px-1.5 py-0.5 rounded">{tag.key}</code></td>
                      <td className="px-4 py-2.5"><Badge variant={tag.required ? "red" : "gray"}>{tag.required ? "Required" : "Optional"}</Badge></td>
                      <td className="px-4 py-2.5"><Badge variant="teal">{tag.type}</Badge></td>
                      <td className="px-4 py-2.5 text-xs text-gray-600 font-mono">{tag.weight}</td>
                      <td className="px-4 py-2.5 text-xs text-gray-400">{tag.description || "—"}</td>
                      <td className="px-4 py-2.5 text-right">
                        <button onClick={() => setTags(tags.filter((_, j) => j !== i))} className="p-1 hover:bg-red-50 hover:text-red-600 text-gray-400 rounded transition-colors"><I.Trash2 /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card className="p-5 space-y-4">
            <h3 className="text-sm font-semibold text-gray-700">Add Tag to Schema</h3>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Tag Key" required value={newTag.key} onChange={v => setNewTag({ ...newTag, key: v })} placeholder="e.g. environment" />
              <Select label="Value Type" value={newTag.type} onChange={v => setNewTag({ ...newTag, type: v })}>
                {tagTypes.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
              </Select>
            </div>

            {newTag.type === "enum" && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Allowed Values</label>
                <div className="flex gap-2 mb-2">
                  <input value={newVal} onChange={e => setNewVal(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter" && newVal.trim()) { setNewTag({ ...newTag, values: [...newTag.values, newVal.trim()] }); setNewVal(""); } }}
                    placeholder="Type a value and press Enter"
                    className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500" />
                  <Btn variant="outline" size="sm" onClick={() => { if (newVal.trim()) { setNewTag({ ...newTag, values: [...newTag.values, newVal.trim()] }); setNewVal(""); } }}><I.Plus /></Btn>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {newTag.values.map((v, i) => (
                    <button key={i} onClick={() => setNewTag({ ...newTag, values: newTag.values.filter((_, j) => j !== i) })}
                      className="inline-flex items-center gap-1 px-2 py-0.5 bg-violet-50 hover:bg-red-50 text-violet-700 hover:text-red-700 border border-violet-200 hover:border-red-200 rounded text-xs font-medium transition-colors">
                      {v} <I.X />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {newTag.type === "pattern" && (
              <Input label="Regex Pattern" value={newTag.pattern} onChange={v => setNewTag({ ...newTag, pattern: v })} placeholder="e.g. CC-[0-9]{4}" hint="Regular expression the tag value must match" />
            )}

            <div className="grid grid-cols-3 gap-3">
              <div className="flex items-center justify-between p-3 border border-gray-200 rounded-lg bg-gray-50">
                <div className="text-sm text-gray-700">Required</div>
                <Toggle checked={newTag.required} onChange={v => setNewTag({ ...newTag, required: v })} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Score Weight (1–20)</label>
                <div className="flex items-center gap-2">
                  <input type="range" min="1" max="20" value={newTag.weight} onChange={e => setNewTag({ ...newTag, weight: parseInt(e.target.value) })}
                    className="flex-1 accent-emerald-600" />
                  <span className="text-sm font-mono font-semibold text-gray-700 w-6 text-right">{newTag.weight}</span>
                </div>
              </div>
              <Input label="Description" value={newTag.description} onChange={v => setNewTag({ ...newTag, description: v })} placeholder="What is this tag for?" />
            </div>
            <Btn variant="outline" onClick={addTag} disabled={!newTag.key.trim()}><I.Plus /> Add Tag to Schema</Btn>
          </Card>
        </div>
      )}

      {/* Step 4: Weights & Review */}
      {step === 4 && (
        <div className="grid grid-cols-5 gap-6">
          <div className="col-span-3 space-y-4">
            <Card className="p-5">
              <h3 className="text-sm font-semibold text-gray-800 mb-1">Weight Distribution</h3>
              <p className="text-xs text-gray-400 mb-4">Adjust how much each tag contributes to the compliance score. Total normalizes to 100%.</p>
              {tags.length === 0 ? (
                <p className="text-gray-400 text-sm text-center py-4">No tags defined. Go back to Step 3.</p>
              ) : (
                <div className="space-y-4">
                  {tags.map((tag, i) => {
                    const pct = totalWeight > 0 ? Math.round((tag.weight / totalWeight) * 100) : 0;
                    const color = tag.required ? "bg-emerald-500" : "bg-gray-300";
                    return (
                      <div key={i}>
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${tag.required ? "bg-red-500" : "bg-gray-400"}`} />
                            <code className="text-xs font-mono text-gray-800">{tag.key}</code>
                            <Badge variant={tag.required ? "red" : "gray"} size="xs">{tag.required ? "req" : "opt"}</Badge>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-400 w-8 text-right">{pct}%</span>
                            <input type="number" min="1" max="20" value={tag.weight}
                              onChange={e => { const updated = [...tags]; updated[i] = { ...updated[i], weight: parseInt(e.target.value) || 1 }; setTags(updated); }}
                              className="w-14 px-2 py-1 text-xs border border-gray-300 rounded text-center font-mono focus:outline-none focus:ring-1 focus:ring-emerald-500" />
                          </div>
                        </div>
                        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div className={`h-full ${color} rounded-full transition-all duration-300`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          </div>
          <div className="col-span-2 space-y-4">
            <Card className="p-5">
              <h3 className="text-sm font-semibold text-gray-800 mb-4">Summary</h3>
              <dl className="space-y-3 text-sm">
                {[["Name", name || "—"], ["Description", desc || "—"], ["Resource Types", scope.join(", ") || "—"], ["Default Template", isDefault ? "Yes" : "No"], ["Required Tags", `${tags.filter(t => t.required).length}`], ["Optional Tags", `${tags.filter(t => !t.required).length}`]].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4 py-2 border-b border-gray-50 last:border-0">
                    <dt className="text-gray-500">{k}</dt>
                    <dd className="font-medium text-gray-800 text-right truncate">{v}</dd>
                  </div>
                ))}
              </dl>
            </Card>
            {tags.length > 0 && (
              <Card className="p-5 text-center">
                <div className="text-xs text-gray-400 mb-2">Preview Score for Fully-Tagged Resource</div>
                <ScoreDonut score={100} size={72} />
                <div className="text-xs text-gray-400 mt-2">All tags present = 100%</div>
              </Card>
            )}
          </div>
        </div>
      )}

      <div className="flex justify-between pt-2">
        <Btn variant="secondary" onClick={step > 1 ? () => setStep(step - 1) : onClose}>{step > 1 ? "Back" : "Cancel"}</Btn>
        <Btn onClick={step < 4 ? () => setStep(step + 1) : () => onSave({ name, description: desc, scope, isDefault, tags })}>
          {step < 4 ? <>Next <I.ChevronRight /></> : "Save Template"}
        </Btn>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 3: SCORING ENGINE
// ═══════════════════════════════════════════════════════════════════════════════
function ScoringTab() {
  const [mode, setMode] = useState("weighted");
  const [threshold, setThreshold] = useState(60);

  const modes = [
    { id: "all", title: "Require All Tags", desc: "All required tags must be present. Any missing required tag = score 0. Zero tolerance." },
    { id: "weighted", title: "Weighted Score", desc: "Each tag contributes a weighted percentage. Set a minimum passing threshold (recommended: 60)." },
    { id: "custom", title: "Custom Key Set", desc: "Specify exactly which tag keys must exist. Values are informational unless a policy also applies." },
  ];

  const bands = [
    { range: `0–${threshold - 1}`, label: "Non-compliant", variant: "red", action: "Enters automation pipeline" },
    { range: `${threshold}–69`, label: "Below Standard", variant: "amber", action: "Flagged for owner review" },
    { range: "70–89", label: "Acceptable", variant: "blue", action: "Informational only" },
    { range: "90–100", label: "Exemplary", variant: "green", action: "Compliant — no action" },
  ];

  const preview = [
    { name: "web-prod-01", id: "i-0abc123", tags: { environment: "production", owner: "alice@corp.com", "cost-center": "CC-1042", team: "platform" }, score: 91 },
    { name: "worker-stg-03", id: "i-0def456", tags: { environment: "staging" }, score: 23 },
    { name: "postgres-prod", id: "rds-prod", tags: { environment: "production", owner: "dba@corp.com", "cost-center": "CC-2017", "backup-policy": "daily", "data-classification": "confidential" }, score: 100 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <div className="text-emerald-600"><I.Target /></div>
          <h1 className="text-2xl font-bold text-gray-900">Scoring Engine</h1>
        </div>
        <p className="text-gray-500 text-sm">Configure how tag compliance is measured. This score determines which resources enter the automation pipeline.</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {modes.map(m => (
          <button key={m.id} onClick={() => setMode(m.id)}
            className={`p-4 text-left border-2 rounded-xl transition-all ${mode === m.id ? "border-emerald-500 bg-emerald-50" : "border-gray-200 bg-white hover:border-emerald-200"}`}>
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="text-sm font-semibold text-gray-900">{m.title}</div>
              <div className={`w-4 h-4 rounded-full border-2 flex-shrink-0 mt-0.5 flex items-center justify-center ${mode === m.id ? "border-emerald-500 bg-emerald-500" : "border-gray-300"}`}>
                {mode === m.id && <div className="w-2 h-2 bg-white rounded-full" />}
              </div>
            </div>
            <p className="text-xs text-gray-500">{m.desc}</p>
          </button>
        ))}
      </div>

      {mode === "weighted" && (
        <Card className="p-6 space-y-6">
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700">Minimum Passing Score</label>
              <div className="flex items-center gap-2">
                <input type="number" min={0} max={100} value={threshold} onChange={e => setThreshold(parseInt(e.target.value) || 0)}
                  className="w-16 px-2 py-1 text-sm border border-gray-300 rounded-lg text-center font-mono font-semibold text-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500" />
                <span className="text-sm text-gray-500">/ 100</span>
              </div>
            </div>
            <div className="relative">
              <input type="range" min={0} max={100} value={threshold} onChange={e => setThreshold(parseInt(e.target.value))}
                className="w-full accent-emerald-600 h-2" />
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>0 — No requirement</span><span>60 — Recommended</span><span>100 — All tags required</span>
              </div>
            </div>
          </div>

          <div>
            <div className="text-sm font-medium text-gray-700 mb-3">Score Bands</div>
            <div className="grid grid-cols-4 gap-3">
              {bands.map(b => (
                <div key={b.range} className="p-3 border border-gray-200 rounded-xl bg-gray-50">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-mono font-bold text-gray-800">{b.range}</span>
                    <Badge variant={b.variant} size="xs">{b.label}</Badge>
                  </div>
                  <p className="text-xs text-gray-500">{b.action}</p>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {mode === "all" && (
        <Card className="p-6">
          <InfoBanner variant="amber">
            <strong>All-or-Nothing mode:</strong> A resource scores 100 only if ALL required template tags are present with valid values. Any missing required tag results in score 0 and immediate entry into the automation pipeline.
          </InfoBanner>
          <div className="mt-4 grid grid-cols-3 gap-3">
            {[["Missing 1+ required tags", "Score: 0 — Flagged"], ["All required tags present", "Score: 100 — Compliant"], ["Optional tags also present", "+5 bonus per optional (max 100)"]].map(([c, r], i) => (
              <div key={i} className="p-3 bg-gray-50 border border-gray-200 rounded-xl text-xs">
                <div className="text-gray-500 mb-1.5">{c}</div>
                <div className="font-medium text-gray-800">{r}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Live preview */}
      <Card className="overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-800">Score Preview</h3>
          <p className="text-xs text-gray-400 mt-0.5">Example resources scored under your current configuration</p>
        </div>
        <div className="divide-y divide-gray-50">
          {preview.map((r, i) => (
            <div key={i} className="px-5 py-4 flex items-center gap-4">
              <ScoreDonut score={r.score} size={48} strokeWidth={5} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-sm font-medium text-gray-900">{r.name}</span>
                  <code className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded font-mono">{r.id}</code>
                </div>
                <div className="flex flex-wrap gap-1">
                  {Object.entries(r.tags).map(([k, v]) => (
                    <span key={k} className="text-xs bg-gray-100 border border-gray-200 px-1.5 py-0.5 rounded font-mono text-gray-600">
                      {k}=<span className="text-emerald-700">{v}</span>
                    </span>
                  ))}
                </div>
              </div>
              <Badge variant={r.score >= 90 ? "green" : r.score >= threshold ? "blue" : "red"}>
                {r.score >= 90 ? "Compliant" : r.score >= threshold ? "Passing" : "Non-compliant"}
              </Badge>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 4: AUTOMATION RULES
// ═══════════════════════════════════════════════════════════════════════════════
function AutomationTab() {
  const [showCreate, setShowCreate] = useState(false);
  const [rules, setRules] = useState([
    { id: 1, name: "Delete Untagged EC2 after 30 Days", trigger: "score < 20", resourceTypes: ["EC2"], graceDays: 30, action: "delete", notifs: ["email", "slack"], enabled: true, conditions: ["not_system_managed", "older_than_30d"] },
    { id: 2, name: "Flag RDS Below Score Threshold", trigger: "score < 60", resourceTypes: ["RDS", "DynamoDB"], graceDays: 7, action: "flag", notifs: ["email"], enabled: true, conditions: [] },
    { id: 3, name: "Auto-Tag from IAM Instance Profile", trigger: "missing:owner", resourceTypes: ["EC2"], graceDays: 0, action: "auto_tag", notifs: [], enabled: false, conditions: ["has_iam_profile"] },
  ]);

  const actionMeta = {
    delete: { label: "Delete Resource", variant: "red" },
    flag: { label: "Flag for Review", variant: "amber" },
    auto_tag: { label: "Auto-Tag", variant: "blue" },
    notify: { label: "Notify Only", variant: "teal" },
    stop: { label: "Stop Instance", variant: "violet" },
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="text-emerald-600"><I.Zap /></div>
            <h1 className="text-2xl font-bold text-gray-900">Automation Rules</h1>
          </div>
          <p className="text-gray-500 text-sm">Define what happens to non-compliant resources. Runs on a configurable rolling window cycle.</p>
        </div>
        <Btn onClick={() => setShowCreate(true)}><I.Plus /> New Rule</Btn>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Next Cycle", value: "Mar 22, 2026 02:00 UTC", sub: "30-day cycle", icon: <I.Clock />, color: "blue" },
          { label: "In Grace Period", value: "234 resources", sub: "Awaiting remediation", icon: <I.AlertTriangle />, color: "amber" },
          { label: "Pending Deletion", value: "18 resources", sub: "$1,240/mo savings", icon: <I.Trash2 />, color: "red" },
        ].map(({ label, value, sub, icon, color }) => (
          <Card key={label} className="p-4">
            <div className={`text-${color}-600 mb-3`}>{icon}</div>
            <div className="text-xs text-gray-400 mb-0.5">{label}</div>
            <div className="text-sm font-semibold text-gray-900">{value}</div>
            <div className="text-xs text-gray-400">{sub}</div>
          </Card>
        ))}
      </div>

      {/* Execution timeline */}
      <Card className="p-5">
        <h3 className="text-sm font-semibold text-gray-800 mb-4">Automation Lifecycle</h3>
        <div className="flex items-start gap-0 overflow-x-auto pb-2">
          {[
            { day: "Day 0", label: "Scan", desc: "Scores computed", color: "bg-gray-400" },
            { day: "Day 1", label: "Notify", desc: "Owner email sent", color: "bg-blue-400" },
            { day: "Day 7", label: "Escalate", desc: "Manager + Jira", color: "bg-amber-400" },
            { day: "Day 14", label: "Reminder", desc: "2nd escalation", color: "bg-orange-400" },
            { day: "Day 28", label: "Final Warning", desc: "48h countdown", color: "bg-red-400" },
            { day: "Day 30", label: "Execute", desc: "Rule action runs", color: "bg-red-600" },
            { day: "Day 30+", label: "Audit Log", desc: "SHA-256 recorded", color: "bg-emerald-500" },
          ].map((t, i, arr) => (
            <div key={i} className="flex items-start flex-shrink-0">
              <div className="flex flex-col items-center">
                <div className={`w-8 h-8 rounded-full ${t.color} flex items-center justify-center text-white text-xs font-bold flex-shrink-0`}>{i + 1}</div>
                <div className="text-center mt-2 w-20">
                  <div className="text-xs font-semibold text-gray-700">{t.label}</div>
                  <div className="text-xs text-gray-400">{t.day}</div>
                  <div className="text-xs text-gray-400 mt-0.5">{t.desc}</div>
                </div>
              </div>
              {i < arr.length - 1 && <div className="w-10 h-px bg-gray-200 mt-4 flex-shrink-0" />}
            </div>
          ))}
        </div>
      </Card>

      <div className="space-y-3">
        {rules.map(rule => (
          <Card key={rule.id} className={!rule.enabled ? "opacity-60" : ""}>
            <div className="px-5 py-4 flex items-start gap-4">
              <div className="pt-0.5"><Toggle checked={rule.enabled} onChange={v => setRules(rules.map(r => r.id === rule.id ? { ...r, enabled: v } : r))} /></div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1.5">
                  <span className="text-sm font-semibold text-gray-900">{rule.name}</span>
                  <Badge variant={actionMeta[rule.action].variant}>{actionMeta[rule.action].label}</Badge>
                  {rule.action === "delete" && <Badge variant="red">Irreversible</Badge>}
                </div>
                <div className="flex flex-wrap gap-3 text-xs text-gray-500">
                  <span>Trigger: <code className="bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded border border-amber-200">{rule.trigger}</code></span>
                  <span>Scope: {rule.resourceTypes.map(t => <Badge key={t} variant="gray" size="xs" className="ml-1">{t}</Badge>)}</span>
                  {rule.graceDays > 0 && <span>Grace: <strong className="text-gray-700">{rule.graceDays} days</strong></span>}
                  {rule.notifs.length > 0 && <span>Notify: {rule.notifs.map(n => <Badge key={n} variant="teal" size="xs" className="ml-1">{n}</Badge>)}</span>}
                </div>
                {rule.conditions.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    <span className="text-xs text-gray-400 mr-1">Only if:</span>
                    {rule.conditions.map(c => <Badge key={c} variant="gray" size="xs">{c.replace(/_/g, " ")}</Badge>)}
                  </div>
                )}
              </div>
              <div className="flex gap-1 flex-shrink-0">
                <button className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"><I.Edit2 /></button>
                <button onClick={() => setRules(rules.filter(r => r.id !== rule.id))} className="p-1.5 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors"><I.Trash2 /></button>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {showCreate && <NewAutomationRule onClose={() => setShowCreate(false)} onSave={rule => { setRules([...rules, { ...rule, id: Date.now() }]); setShowCreate(false); }} />}
    </div>
  );
}

function NewAutomationRule({ onClose, onSave }) {
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("score < 60");
  const [resourceTypes, setResourceTypes] = useState([]);
  const [graceDays, setGraceDays] = useState(30);
  const [action, setAction] = useState("flag");
  const [notifs, setNotifs] = useState([]);
  const [conditions, setConditions] = useState([]);
  const toggle = (arr, set, val) => set(arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val]);
  const resourceOpts = ["EC2", "EBS", "RDS", "S3", "ELB", "Lambda", "DynamoDB", "ElastiCache"];
  const notifOpts = ["email", "slack", "pagerduty", "webhook", "jira"];
  const condOpts = [
    { id: "not_system_managed", label: "Not system-managed" },
    { id: "older_than_30d", label: "Resource older than 30 days" },
    { id: "has_cost", label: "Has monthly cost > $0" },
    { id: "not_prod", label: "Not in production environment" },
    { id: "has_iam_profile", label: "Has IAM instance profile" },
    { id: "no_recent_activity", label: "No activity in last 14 days" },
  ];

  return (
    <Card className="p-6 border-emerald-200 border-2">
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-base font-semibold text-gray-900">New Automation Rule</h3>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"><I.X /></button>
      </div>
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <Input label="Rule Name" required value={name} onChange={setName} placeholder="e.g. Delete untagged EC2 after 30 days" />
          <Select label="Trigger Condition" required value={trigger} onChange={setTrigger}>
            <option value="score < 20">Score below 20 — Severely non-compliant</option>
            <option value="score < 40">Score below 40 — Mostly untagged</option>
            <option value="score < 60">Score below 60 — Below threshold</option>
            <option value="score == 0">Score is zero — No tags at all</option>
            <option value="missing:owner">Missing owner tag</option>
            <option value="missing:cost-center">Missing cost-center tag</option>
            <option value="missing:environment">Missing environment tag</option>
            <option value="unauthorized">Not in authorized resources list</option>
          </Select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Resource Types <span className="text-red-500">*</span></label>
          <div className="flex flex-wrap gap-2">
            {resourceOpts.map(r => (
              <button key={r} onClick={() => toggle(resourceTypes, setResourceTypes, r)}
                className={`px-3 py-1.5 text-sm rounded-lg border transition-all ${resourceTypes.includes(r) ? "bg-emerald-50 border-emerald-300 text-emerald-800 font-medium" : "bg-white border-gray-200 text-gray-600 hover:border-emerald-200"}`}>
                {resourceTypes.includes(r) && <span className="mr-1 text-emerald-600">✓</span>}{r}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Select label="Action" value={action} onChange={setAction}>
            <option value="notify">Notify Only — No automated action taken</option>
            <option value="flag">Flag for Review — Marks in hygiene report</option>
            <option value="stop">Stop Instance — Halts compute, preserves data</option>
            <option value="auto_tag">Auto-Tag — Attempt to infer missing tags</option>
            <option value="delete">Delete Resource — Irreversible</option>
          </Select>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Grace Period: <strong className="text-emerald-700">{graceDays} days</strong></label>
            <input type="range" min={0} max={90} step={1} value={graceDays} onChange={e => setGraceDays(parseInt(e.target.value))}
              className="w-full accent-emerald-600 mt-2" />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5"><span>0 — Immediate</span><span>90 days max</span></div>
          </div>
        </div>

        {action === "delete" && (
          <InfoBanner variant="red">
            <strong>Delete is irreversible.</strong> An approval gate will be required before any deletion runs. Resources will receive a final notification 48 hours before action.
          </InfoBanner>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Notification Channels</label>
          <div className="flex flex-wrap gap-2">
            {notifOpts.map(n => (
              <button key={n} onClick={() => toggle(notifs, setNotifs, n)}
                className={`px-3 py-1.5 text-sm rounded-lg border transition-all capitalize ${notifs.includes(n) ? "bg-teal-50 border-teal-300 text-teal-800 font-medium" : "bg-white border-gray-200 text-gray-600 hover:border-teal-200"}`}>
                {notifs.includes(n) && <span className="mr-1 text-teal-600">✓</span>}{n}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">Safety Conditions</label>
          <p className="text-xs text-gray-400 mb-2">Resource must match ALL selected conditions in addition to the trigger:</p>
          <div className="grid grid-cols-2 gap-2">
            {condOpts.map(c => (
              <button key={c.id} onClick={() => toggle(conditions, setConditions, c.id)}
                className={`px-3 py-2 text-sm text-left rounded-lg border transition-all ${conditions.includes(c.id) ? "bg-gray-100 border-gray-400 text-gray-900 font-medium" : "bg-white border-gray-200 text-gray-600 hover:border-gray-300"}`}>
                <span className={`mr-2 ${conditions.includes(c.id) ? "text-emerald-600" : "text-gray-300"}`}>
                  {conditions.includes(c.id) ? <I.Check /> : <I.Circle />}
                </span>
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-2 border-t border-gray-100">
          <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
          <Btn disabled={!name || resourceTypes.length === 0} onClick={() => onSave({ name, trigger, resourceTypes, graceDays, action, notifs, conditions, enabled: true })}>
            Save Rule
          </Btn>
        </div>
      </div>
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TAB 5: COMPLIANCE MONITOR
// ═══════════════════════════════════════════════════════════════════════════════
function MonitorTab() {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const resources = [
    { id: "i-0abc123", name: "web-prod-01", type: "EC2", score: 92, status: "compliant", cost: 184, tags: 6, daysLeft: null, team: "platform", env: "production" },
    { id: "i-0def456", name: "worker-stg-03", type: "EC2", score: 58, status: "review", cost: 47, tags: 3, daysLeft: 23, team: "backend", env: "staging" },
    { id: "vol-0xyz789", name: "data-volume-01", type: "EBS", score: 8, status: "critical", cost: 12, tags: 0, daysLeft: 7, team: "—", env: "—" },
    { id: "rds-prod-db", name: "postgres-prod", type: "RDS", score: 100, status: "compliant", cost: 420, tags: 7, daysLeft: null, team: "data", env: "production" },
    { id: "i-0ghi012", name: "old-batch-worker", type: "EC2", score: 0, status: "deletion", cost: 88, tags: 0, daysLeft: 3, team: "—", env: "—" },
    { id: "elb-frontend", name: "prod-alb-01", type: "ELB", score: 75, status: "passing", cost: 23, tags: 4, daysLeft: null, team: "platform", env: "production" },
    { id: "lambda-proc", name: "event-processor", type: "Lambda", score: 44, status: "review", cost: 8, tags: 2, daysLeft: 16, team: "backend", env: "staging" },
  ];

  const statusMeta = {
    compliant: { label: "Compliant", variant: "green" },
    passing: { label: "Passing", variant: "blue" },
    review: { label: "Needs Review", variant: "amber" },
    critical: { label: "Critical", variant: "red" },
    deletion: { label: "Pending Deletion", variant: "red" },
  };

  const filtered = resources.filter(r => {
    if (filter !== "all" && r.status !== filter) return false;
    if (search && !r.name.includes(search) && !r.id.includes(search) && !r.team.includes(search)) return false;
    return true;
  });

  const kpis = [
    { label: "Total Analyzed", value: resources.length, sub: "Resources", icon: <I.Package />, color: "gray" },
    { label: "Compliant", value: resources.filter(r => r.status === "compliant" || r.status === "passing").length, sub: "Above threshold", icon: <I.ShieldCheck />, color: "green" },
    { label: "Needs Remediation", value: resources.filter(r => r.status === "review" || r.status === "critical").length, sub: "Below threshold", icon: <I.AlertTriangle />, color: "amber" },
    { label: "Monthly Cost at Risk", value: `$${resources.filter(r => ["review", "critical", "deletion"].includes(r.status)).reduce((s, r) => s + r.cost, 0).toLocaleString()}`, sub: "Non-compliant spend", icon: <I.TrendingUp />, color: "red" },
  ];

  const colorMap = { gray: "text-gray-500 bg-gray-50 border-gray-200", green: "text-emerald-600 bg-emerald-50 border-emerald-200", amber: "text-amber-600 bg-amber-50 border-amber-200", red: "text-red-600 bg-red-50 border-red-200" };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="text-emerald-600"><I.Activity /></div>
            <h1 className="text-2xl font-bold text-gray-900">Compliance Monitor</h1>
          </div>
          <p className="text-gray-500 text-sm">Live compliance view across your AWS fleet. Scores refresh every 30 minutes.</p>
        </div>
        <div className="flex gap-2">
          <Btn variant="secondary" size="sm"><I.RefreshCw /> Refresh</Btn>
          <Btn variant="secondary" size="sm"><I.Download /> Export CSV</Btn>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {kpis.map(({ label, value, sub, icon, color }) => (
          <Card key={label} className={`p-4 border ${colorMap[color]}`}>
            <div className={`mb-3 ${colorMap[color].split(" ")[0]}`}>{icon}</div>
            <div className="text-xs text-gray-400 mb-0.5">{label}</div>
            <div className="text-2xl font-bold text-gray-900">{value}</div>
            <div className="text-xs text-gray-400">{sub}</div>
          </Card>
        ))}
      </div>

      {/* Fleet health visual */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-800">Fleet Compliance Distribution</h3>
          <Badge variant="gray">Last scan: 2 min ago</Badge>
        </div>
        <div className="flex gap-1 h-8 rounded-lg overflow-hidden">
          {[
            { pct: 28, color: "bg-emerald-500", label: "Compliant" },
            { pct: 15, color: "bg-blue-400", label: "Passing" },
            { pct: 36, color: "bg-amber-400", label: "Review" },
            { pct: 14, color: "bg-red-400", label: "Critical" },
            { pct: 7, color: "bg-red-600", label: "Deletion" },
          ].map((s, i) => (
            <div key={i} title={`${s.label}: ${s.pct}%`} className={`${s.color} relative group cursor-default transition-all hover:opacity-90`} style={{ width: `${s.pct}%` }}>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-white text-xs font-semibold opacity-0 group-hover:opacity-100 transition-opacity">{s.pct}%</span>
              </div>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-4 mt-3 text-xs text-gray-500">
          {[["bg-emerald-500", "Compliant", "28%"], ["bg-blue-400", "Passing", "15%"], ["bg-amber-400", "Needs Review", "36%"], ["bg-red-400", "Critical", "14%"], ["bg-red-600", "Pending Deletion", "7%"]].map(([c, l, p]) => (
            <div key={l} className="flex items-center gap-1.5"><div className={`w-3 h-3 rounded ${c}`} />{l} {p}</div>
          ))}
        </div>
      </Card>

      {/* Filters + table */}
      <div className="flex items-center gap-3 flex-wrap">
        {["all", "compliant", "review", "critical", "deletion"].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 text-sm rounded-lg border transition-all capitalize ${filter === f ? "bg-emerald-50 border-emerald-300 text-emerald-800 font-medium" : "bg-white border-gray-200 text-gray-600 hover:border-emerald-200"}`}>
            {f === "all" ? "All Resources" : statusMeta[f]?.label || f}
          </button>
        ))}
        <div className="flex-1" />
        <div className="relative">
          <I.Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 w-3.5 h-3.5" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search resources..."
            className="pl-8 pr-3 py-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 w-56" />
        </div>
      </div>

      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50">
              {["Resource", "Type", "Score", "Status", "Monthly Cost", "Tags", "Days Left", "Actions"].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {filtered.map(r => (
              <tr key={r.id} className="hover:bg-gray-50/50 transition-colors">
                <td className="px-4 py-3.5">
                  <div className="font-medium text-gray-900">{r.name}</div>
                  <code className="text-xs text-gray-400 font-mono">{r.id}</code>
                </td>
                <td className="px-4 py-3.5"><Badge variant="gray">{r.type}</Badge></td>
                <td className="px-4 py-3.5"><ScoreDonut score={r.score} size={40} strokeWidth={4} /></td>
                <td className="px-4 py-3.5"><Badge variant={statusMeta[r.status].variant}>{statusMeta[r.status].label}</Badge></td>
                <td className="px-4 py-3.5 font-mono text-sm text-gray-700">${r.cost}/mo</td>
                <td className="px-4 py-3.5 text-gray-600">{r.tags} tag{r.tags !== 1 ? "s" : ""}</td>
                <td className="px-4 py-3.5">
                  {r.daysLeft !== null ? <span className={`text-xs font-mono font-semibold ${r.daysLeft <= 7 ? "text-red-600" : "text-amber-600"}`}>{r.daysLeft}d</span> : <span className="text-gray-300 text-xs">—</span>}
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex gap-1.5">
                    <Btn size="sm" variant="ghost" className="text-xs">Remediate</Btn>
                    <Btn size="sm" variant="ghost" className="text-xs"><I.Eye /></Btn>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Recent automation audit */}
      <Card className="overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-800">Recent Automation Actions</h3>
          <p className="text-xs text-gray-400 mt-0.5">Tamper-evident audit log with SHA-256 checksums</p>
        </div>
        <div className="divide-y divide-gray-50">
          {[
            { time: "Feb 22, 2026 14:32", action: "DELETED", resource: "vol-0abc123 (EBS)", reason: "Score 0 — 30+ day grace period expired", savings: "$8.40/mo recovered", outcome: "success" },
            { time: "Feb 22, 2026 09:15", action: "FLAGGED", resource: "i-0xyz789 (EC2)", reason: "Score 18 — below threshold of 60", savings: "$47/mo at risk", outcome: "success" },
            { time: "Feb 21, 2026 02:00", action: "NOTIFIED", resource: "rds-staging (RDS)", reason: "Missing: cost-center, data-classification", savings: "$120/mo", outcome: "success" },
            { time: "Feb 20, 2026 18:44", action: "AUTO-TAGGED", resource: "i-0prod456 (EC2)", reason: "Owner inferred from IAM instance profile", savings: "—", outcome: "success" },
          ].map((log, i) => (
            <div key={i} className="px-5 py-3.5 flex items-center gap-4 hover:bg-gray-50/50 transition-colors">
              <div className="text-xs text-gray-400 w-36 flex-shrink-0">{log.time}</div>
              <Badge variant={log.action === "DELETED" ? "red" : log.action === "FLAGGED" ? "amber" : log.action === "NOTIFIED" ? "blue" : "teal"}>{log.action}</Badge>
              <div className="flex-1 min-w-0">
                <div className="text-sm text-gray-800 font-medium">{log.resource}</div>
                <div className="text-xs text-gray-400">{log.reason}</div>
              </div>
              <div className="text-xs font-medium text-emerald-600 text-right w-36">{log.savings}</div>
              <Badge variant="green">Success</Badge>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}