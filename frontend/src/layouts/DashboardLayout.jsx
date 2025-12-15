import React, { useState } from 'react';
import { LayoutDashboard, Server, Settings, Activity, Menu, X, Users, ChevronDown } from 'lucide-react';
import { cn } from '../lib/utils';

const NavigationItem = ({ icon: Icon, label, active, onClick, hasSubmenu, isOpen, onToggle }) => (
    <div className="w-full">
        <button
            onClick={onClick}
            className={cn(
                "flex items-center w-full px-4 py-2.5 text-sm transition-all duration-200 group relative",
                active
                    ? "text-slate-900 font-bold bg-slate-50"
                    : "text-slate-500 font-medium hover:text-slate-900 hover:bg-slate-50"
            )}
        >
            {active && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-blue-600 rounded-r-sm" />
            )}
            <Icon className={cn("w-4 h-4 mr-3 transition-colors", active ? "text-blue-600" : "text-slate-400 group-hover:text-slate-600")} />
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

const DashboardLayout = ({ children, activeView, setActiveView, onSelectClient, selectedClientId }) => {
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);

    return (
        <div className="min-h-screen bg-white text-slate-900 flex font-sans">
            {/* Sidebar */}
            <aside
                className={cn(
                    "fixed inset-y-0 left-0 z-50 bg-white border-r border-slate-200 transition-all duration-300 ease-in-out lg:relative h-screen",
                    isSidebarOpen ? "w-64 translate-x-0" : "-translate-x-full w-0 lg:translate-x-0 lg:w-0 overflow-hidden border-none"
                )}
            >
                <div className="flex items-center h-16 px-6 border-b border-slate-100 min-w-[16rem]"> {/* min-w to prevent text wrap during transition */}
                    <div className="flex items-center space-x-2">
                        <div className="w-8 h-8 bg-blue-600 rounded flex items-center justify-center flex-shrink-0">
                            <Activity className="w-5 h-5 text-white" />
                        </div>
                        <span className="text-xl font-bold text-slate-900 tracking-tight whitespace-nowrap"> Atharva.ai 🤯</span>
                    </div>
                </div>

                <nav className="p-4 space-y-1 min-w-[16rem]">
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4 px-4 mt-4">
                        Platform
                    </div>

                    <NavigationItem
                        icon={Activity}
                        label="Live Operations"
                        active={activeView === 'live'}
                        onClick={() => setActiveView('live')}
                    />

                    {/* Clients Section */}
                    <div>
                        <NavigationItem
                            icon={Users}
                            label="Clients"
                            active={activeView === 'fleet'}
                            onClick={() => {
                                setActiveView('fleet');
                                onSelectClient(null);
                            }}
                        />
                    </div>

                    <NavigationItem
                        icon={Settings}
                        label="Controls"
                        active={activeView === 'controls'}
                        onClick={() => setActiveView('controls')}
                    />
                </nav>
            </aside>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-h-screen overflow-hidden bg-white">
                {/* Header */}
                <header className="h-16 bg-white border-b border-slate-100 flex items-center justify-between px-8">
                    <div className="flex items-center">
                        <button
                            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                            className="mr-4 text-slate-500 hover:bg-slate-50 p-1 rounded transition-colors"
                        >
                            <Menu className="w-5 h-5" />
                        </button>
                        <h2 className="text-sm font-semibold text-slate-500">
                            Organization / <span className="text-slate-900">Spot Optimization</span>
                        </h2>
                    </div>

                    <div className="flex items-center space-x-4">
                        <div className="flex items-center space-x-2 px-3 py-1.5 bg-slate-50 rounded border border-slate-200">
                            <div className="w-2 h-2 bg-emerald-500 rounded-full"></div>
                            <span className="text-xs font-semibold text-slate-700">Production Environment</span>
                        </div>
                    </div>
                </header>

                {/* Content Area */}
                <main className="flex-1 overflow-auto p-8">
                    <div className="max-w-[1600px] mx-auto">
                        {children}
                    </div>
                </main>
            </div>
        </div>
    );
};

export default DashboardLayout;
