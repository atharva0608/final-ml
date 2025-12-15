import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { FlaskConical, ChevronDown, Check, Activity, Menu, Settings, Server, User, Lock, LogOut, KeyRound, ScrollText } from 'lucide-react';
import { cn } from '../lib/utils';

const DashboardLayout = ({ children, activeView, setActiveView, onSelectClient, selectedClientId, role = 'admin', clientName = '' }) => {
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const { accountScope, switchScope } = useAuth();
    const [isScopeMenuOpen, setIsScopeMenuOpen] = useState(false);
    const navigate = useNavigate();

    const isLab = accountScope === 'lab';
    const isClient = role === 'client';

    // Theme Config
    const theme = isLab ? {
        sidebarBg: "bg-slate-50",
        sidebarBorder: "border-purple-100",
        sidebarText: "text-slate-600 font-medium",
        sidebarActiveBg: "bg-purple-50",
        sidebarActiveText: "text-purple-700 font-bold",
        sidebarIcon: "text-slate-400",
        sidebarIconActive: "text-purple-600",
        logoBg: "bg-purple-600",
        logoText: "text-white",
        headerEnvBadge: "bg-purple-50 border-purple-200 text-purple-700"
    } : {
        // User's Requested "Old" Design for Prod
        sidebarBg: "bg-white",
        sidebarBorder: "border-slate-200", // border-r
        sidebarText: "text-slate-500 font-medium",
        sidebarActiveBg: "bg-slate-50",
        sidebarActiveText: "text-slate-900 font-bold",
        sidebarIcon: "text-slate-400 group-hover:text-slate-600",
        sidebarIconActive: "text-blue-600",
        logoBg: "bg-blue-600",
        logoText: "text-slate-900 tracking-tight",
        headerEnvBadge: "bg-slate-50 border-slate-200 text-slate-700"
    };

    // Navigation Items Configuration
    const navItems = isClient ? [
        { id: 'live', label: 'Dashboard', icon: Activity },
    ] : [
        // Admin Navigation
        // Hide Live Ops in Lab Mode
        ...(accountScope !== 'lab' ? [{ id: 'live', label: 'Live Operations', icon: Activity }] : []),
        // Show Fleet ONLY in Production
        ...(accountScope !== 'lab' ? [{ id: 'fleet', label: 'Node Fleet', icon: Server }] : []),
        // Hide Controls in Lab Mode
        ...(accountScope !== 'lab' ? [{ id: 'controls', label: 'System Controls', icon: Settings }] : []),
        // Show Experiments ONLY in Lab Mode
        ...(accountScope === 'lab' ? [{ id: 'experiments', label: 'Model Experiments', icon: FlaskConical }] : [])
    ];

    // Sidebar Theme (Dynamic)
    const sidebarTheme = isLab
        ? "bg-slate-900 border-r border-purple-900/50"
        : "bg-white border-r border-slate-200";

    const handleSwitchToProd = () => {
        switchScope('production');
        setIsScopeMenuOpen(false);
        setActiveView('live');
    };

    const handleSwitchToLab = () => {
        switchScope('lab');
        setIsScopeMenuOpen(false);
        setActiveView('experiments');
    };

    return (
        <div className={cn("min-h-screen flex transition-colors duration-500", isLab ? "bg-slate-950" : "bg-slate-50")}>
            {/* Sidebar */}
            {/* Sidebar Overlay for Mobile */}
            {isSidebarOpen && (
                <div
                    className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm lg:hidden"
                    onClick={() => setIsSidebarOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside className={cn(
                "fixed inset-y-0 left-0 z-50 transition-all duration-300 ease-in-out lg:relative lg:translate-x-0",
                sidebarTheme,
                isSidebarOpen ? "w-64 translate-x-0" : "w-0 -translate-x-full lg:w-0 lg:translate-x-0 border-none overflow-hidden"
            )}>
                <div className={cn("flex items-center h-16 px-6 min-w-[16rem] relative z-20 shadow-sm", isLab ? "bg-slate-900" : "bg-white")}>
                    <div className="flex items-center space-x-2">
                        <div className={cn("w-8 h-8 rounded flex items-center justify-center flex-shrink-0 shadow-sm", theme.logoBg)}>
                            <Activity className="w-5 h-5 text-white" />
                        </div>
                        <span className={cn("text-xl font-bold tracking-tight whitespace-nowrap", isLab ? "text-white" : "text-slate-900")}> Atharva.ai 🤯</span>
                    </div>
                </div>

                <nav className="p-4 space-y-1 min-w-[16rem]">
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4 px-4 mt-4">
                        Platform
                    </div>

                    {navItems.map((item) => (
                        <NavigationItem
                            key={item.id}
                            icon={item.icon}
                            label={item.label}
                            active={activeView === item.id}
                            onClick={() => {
                                setActiveView(item.id);
                                if (item.id === 'fleet') onSelectClient(null);
                                // On mobile, close sidebar after click
                                if (window.innerWidth < 1024) setIsSidebarOpen(false);
                            }}
                            customTheme={theme}
                        />
                    ))}

                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 px-4 mt-8">
                        Account
                    </div>

                    {/* Unified Profile for Everyone */}
                    <NavigationItem
                        icon={User}
                        label={isClient ? "My Profile" : "Admin Profile"}
                        active={activeView === 'profile'}
                        onClick={() => setActiveView('profile')}
                        customTheme={theme}
                    />

                    <NavigationItem
                        icon={LogOut}
                        label="Sign Out"
                        onClick={() => {
                            // Mock Sign Out
                            window.location.href = '/login';
                        }}
                        customTheme={theme}
                    />
                </nav>
            </aside>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-h-screen overflow-hidden bg-white">
                {/* Header */}
                <header className="h-16 bg-white border-b border-slate-100 flex items-center justify-between px-8 relative z-20">
                    <div className="flex items-center">
                        <div className="border-r border-slate-200 pr-4 mr-4">
                            <button
                                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                                className="text-slate-500 hover:bg-slate-100 p-2 rounded-lg transition-colors"
                            >
                                <Menu className="w-5 h-5" />
                            </button>
                        </div>
                        <h2 className="text-sm font-semibold text-slate-500 flex items-center gap-2">
                            {!isSidebarOpen && <span className="font-bold text-slate-900 border-r border-slate-300 pr-3 mr-1">Atharva.ai</span>}
                            Organization / <span className="text-slate-900">
                                {isClient ? clientName : (isLab ? "Internal Lab" : "Spot Optimization")}
                            </span>
                        </h2>
                    </div>

                    <div className="flex items-center space-x-4">
                        {/* Scope Switcher - Admin Only */}
                        {!isClient && (
                            <div className="relative">
                                <button
                                    onClick={() => setIsScopeMenuOpen(!isScopeMenuOpen)}
                                    className={cn(
                                        "flex items-center space-x-2 px-3 py-1.5 rounded border transition-all",
                                        isLab
                                            ? "bg-purple-50 border-purple-200 text-purple-700 hover:bg-purple-100"
                                            : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
                                    )}
                                >
                                    <div className={cn("w-2 h-2 rounded-full", isLab ? "bg-purple-500" : "bg-emerald-500")}></div>
                                    <span className="text-xs font-semibold">
                                        {isLab ? "Internal Lab (R&D)" : "Production Environment"}
                                    </span>
                                    <ChevronDown className="w-3 h-3 ml-2 opacity-50" />
                                </button>

                                {/* Dropdown Menu */}
                                {isScopeMenuOpen && (
                                    <>
                                        <div
                                            className="fixed inset-0 z-10"
                                            onClick={() => setIsScopeMenuOpen(false)}
                                        />
                                        <div className="absolute right-0 top-full mt-2 w-64 bg-white border border-slate-200 rounded-lg shadow-xl z-20 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                                            <div className="px-4 py-3 bg-slate-50 border-b border-slate-100">
                                                <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Account Scope</p>
                                            </div>
                                            <div className="p-2 space-y-1">
                                                <button
                                                    onClick={handleSwitchToProd}
                                                    className="w-full text-left px-3 py-2 text-sm rounded-md hover:bg-slate-50 flex items-center justify-between group"
                                                >
                                                    <div className="flex items-center space-x-3">
                                                        <div className="w-2 h-2 rounded-full bg-emerald-500" />
                                                        <span className="text-slate-700 font-medium group-hover:text-slate-900">Production</span>
                                                    </div>
                                                    {!isLab && <Check className="w-4 h-4 text-emerald-600" />}
                                                </button>

                                                <button
                                                    onClick={handleSwitchToLab}
                                                    className="w-full text-left px-3 py-2 text-sm rounded-md hover:bg-purple-50 flex items-center justify-between group"
                                                >
                                                    <div className="flex items-center space-x-3">
                                                        <div className="w-2 h-2 rounded-full bg-purple-500" />
                                                        <div>
                                                            <span className="text-slate-700 font-medium group-hover:text-purple-700 block">Internal Lab</span>
                                                            <span className="text-[10px] text-slate-400">Dev Account (Sandbox)</span>
                                                        </div>
                                                    </div>
                                                    {isLab && <Check className="w-4 h-4 text-purple-600" />}
                                                </button>
                                            </div>
                                        </div>
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                </header>

                {/* Content Area */}
                <main className={cn("flex-1 overflow-auto p-8", isLab ? "bg-slate-50" : "bg-white")}>
                    <div className="max-w-[1600px] mx-auto">
                        {children}
                    </div>
                </main>
            </div>
        </div>
    );
};

const NavigationItem = ({ icon: Icon, label, active, onClick, hasSubmenu, isOpen, onToggle, customTheme }) => {
    // Default theme fallback
    const theme = customTheme || {
        sidebarActiveBg: "bg-slate-50",
        sidebarActiveText: "text-slate-900",
        sidebarText: "text-slate-500",
        sidebarIcon: "text-slate-400",
        sidebarIconActive: "text-blue-600"
    };

    return (
        <div className="w-full">
            <button
                onClick={onClick}
                className={cn(
                    "flex items-center w-full px-4 py-2.5 text-sm transition-all duration-200 group relative rounded-lg mx-2 w-[calc(100%-16px)]", // Added rounded and margin
                    active
                        ? `${theme.sidebarActiveBg} ${theme.sidebarActiveText} font-bold`
                        : `${theme.sidebarText} font-medium hover:bg-opacity-50 hover:bg-slate-100` // Simplified hover
                )}
            >
                <Icon className={cn("w-4 h-4 mr-3 transition-colors", active ? theme.sidebarIconActive : theme.sidebarIcon)} />
                <span className="flex-1 text-left">{label}</span>
                {hasSubmenu && (
                    <div
                        role="button"
                        onClick={(e) => {
                            e.stopPropagation();
                            onToggle();
                        }}
                        className="p-1 hover:bg-slate-200 rounded"
                    >
                        <ChevronDown className={cn("w-3 h-3 transition-transform", isOpen && "rotate-180")} />
                    </div>
                )}
            </button>
        </div>
    );
};

export default DashboardLayout;
