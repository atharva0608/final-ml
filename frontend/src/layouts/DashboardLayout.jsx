import React, { useState } from 'react';
import {
    LayoutDashboard, Server, Settings, Activity, Menu,
    Users, ChevronDown, FlaskConical, Radio, Globe, Check, X, Cloud, LogOut,
    FileText, TrendingDown
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { cn } from '../lib/utils';

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
                    "flex items-center w-full px-4 py-2.5 text-sm transition-all duration-200 group relative rounded-lg mx-2 w-[calc(100%-16px)]",
                    active
                        ? `${theme.sidebarActiveBg} ${theme.sidebarActiveText} font-bold`
                        : `${theme.sidebarText} font-medium hover:bg-opacity-50 hover:bg-slate-100`
                )}
            >
                {active && (
                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-blue-600 rounded-r-sm" />
                )}
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

const DashboardLayout = ({ children, activeView, setActiveView, role = 'admin', clientName = null }) => {
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [environmentMode, setEnvironmentMode] = useState('prod'); // 'prod' | 'lab'
    const [isScopeMenuOpen, setIsScopeMenuOpen] = useState(false);

    const { logout, user } = useAuth();
    const navigate = useNavigate();

    // Helpers
    const isLab = environmentMode === 'lab';
    const isClient = role === 'client';

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const handleSwitchToProd = () => {
        setEnvironmentMode('prod');
        setActiveView('live');
        setIsScopeMenuOpen(false);
    };

    const handleSwitchToLab = () => {
        setEnvironmentMode('lab');
        setActiveView('experiments');
        setIsScopeMenuOpen(false);
    };

    // Define Menu Items based on Role/Mode
    const getMenuItems = () => {
        if (role === 'client') {
            return [
                { id: 'dashboard', label: 'Client Dashboard', icon: LayoutDashboard },
                { id: 'savings', label: 'Available Savings', icon: TrendingDown },
                { id: 'templates', label: 'Node Templates', icon: FileText },
                { id: 'connect', label: 'Cloud Connect', icon: Cloud },
                { id: 'profile', label: 'Profile Settings', icon: Settings },
            ];
        }

        // Admin - Prod (READ-ONLY: No AWS account management in production)
        if (environmentMode === 'prod') {
            return [
                { id: 'live', label: 'Live Operations', icon: Radio },
                { id: 'fleet', label: 'Node Fleet', icon: Server },
                { id: 'savings', label: 'Available Savings', icon: TrendingDown },
                { id: 'templates', label: 'Node Templates', icon: FileText },
                { id: 'monitor', label: 'System Monitor', icon: Globe },
                { id: 'controls', label: 'Global Controls', icon: Settings },
                { id: 'clients', label: 'Client Management', icon: Users },
            ];
        }

        // Admin - Lab
        return [
            { id: 'experiments', label: 'Model Experiments', icon: FlaskConical },
            { id: 'monitor', label: 'System Monitor', icon: Activity },
            { id: 'onboarding', label: 'Connect Cloud', icon: Cloud },
            { id: 'controls', label: 'Global Controls', icon: Settings },
        ];
    };

    const menuItems = getMenuItems();

    // Theme logic for Nav Items (Lab gets purple accents)
    const navTheme = isLab ? {
        sidebarActiveBg: "bg-purple-50",
        sidebarActiveText: "text-purple-900",
        sidebarText: "text-slate-500",
        sidebarIcon: "text-slate-400",
        sidebarIconActive: "text-purple-600"
    } : undefined;

    return (
        <div className="min-h-screen bg-white text-slate-900 flex font-sans">
            {/* Sidebar */}
            <aside
                className={cn(
                    "fixed inset-y-0 left-0 z-50 bg-white border-r border-slate-200 transition-all duration-300 ease-in-out lg:relative h-screen flex flex-col",
                    isSidebarOpen ? "w-64 translate-x-0" : "-translate-x-full w-0 lg:translate-x-0 lg:w-0 overflow-hidden border-none"
                )}
            >
                <div className="flex items-center h-16 px-6 border-b border-slate-100 min-w-[16rem]">
                    <div className="flex items-center space-x-2">
                        <div className={cn("w-8 h-8 rounded flex items-center justify-center flex-shrink-0 transition-colors", isLab ? "bg-purple-600" : "bg-blue-600")}>
                            <Activity className="w-5 h-5 text-white" />
                        </div>
                        <span className="text-xl font-bold text-slate-900 tracking-tight whitespace-nowrap"> Atharva.ai 🤯</span>
                    </div>
                </div>

                <nav className="flex-1 p-2 space-y-1 min-w-[16rem] overflow-y-auto">
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4 px-4 mt-6">
                        {isClient ? 'Client Portal' : (isLab ? 'R&D Lab' : 'Platform')}
                    </div>

                    {menuItems.map(item => (
                        <NavigationItem
                            key={item.id}
                            icon={item.icon}
                            label={item.label}
                            active={activeView === item.id}
                            onClick={() => setActiveView(item.id)}
                            customTheme={navTheme}
                        />
                    ))}

                    {role === 'admin' && (
                        <div className="mt-8 pt-4 border-t border-slate-100 mx-2">
                            <NavigationItem
                                icon={Users}
                                label="Admin Profile"
                                active={activeView === 'profile'}
                                onClick={() => setActiveView('profile')}
                                customTheme={navTheme}
                            />
                        </div>
                    )}
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

                        {/* User Info & Logout */}
                        <div className="flex items-center space-x-3 border-l border-slate-200 pl-4">
                            <div className="text-right">
                                <p className="text-xs font-semibold text-slate-900">{user?.username || 'User'}</p>
                                <p className="text-[10px] text-slate-500 capitalize">{role}</p>
                            </div>
                            <button
                                onClick={handleLogout}
                                className="flex items-center space-x-2 px-3 py-1.5 bg-red-50 border border-red-200 text-red-700 hover:bg-red-100 rounded-lg transition-all group"
                                title="Logout"
                            >
                                <LogOut className="w-4 h-4" />
                                <span className="text-xs font-semibold">Logout</span>
                            </button>
                        </div>
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

export default DashboardLayout;
