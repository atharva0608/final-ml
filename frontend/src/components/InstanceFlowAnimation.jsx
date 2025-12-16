import React, { useEffect, useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Server, Zap, Layers, ChevronLeft, ChevronRight, CheckCircle, Database, AlertCircle } from 'lucide-react';
import { cn } from '../lib/utils';

// --- MOCK DATA ---
// --- MOCK DATA ---
// --- MOCK DATA ---
const STABLE_CLUSTERS = [
    {
        id: 'c1',
        cluster: 'production-us-east-1',
        region: 'us-east-1',
        type: 'stable',
        nodeCount: 45,
        nodes: Array(4).fill(null).map((_, i) => ({
            id: `n1-${i}`,
            status: 'stable',
            name: `i-0${(Math.random().toString(16) + '000000').substring(2, 9)}`,
            instanceType: 'c5.2xlarge'
        }))
    },
    {
        id: 'c2',
        cluster: 'staging-eu-west-1',
        region: 'eu-west-1',
        type: 'stable',
        nodeCount: 40,
        nodes: Array(4).fill(null).map((_, i) => ({
            id: `n2-${i}`,
            status: 'stable',
            name: `i-0${(Math.random().toString(16) + '000000').substring(2, 9)}`,
            instanceType: 'r6g.xlarge'
        }))
    },
    {
        id: 'c3',
        cluster: 'dev-ap-south-1',
        region: 'ap-south-1',
        type: 'stable',
        nodeCount: 12,
        nodes: Array(4).fill(null).map((_, i) => ({
            id: `n3-${i}`,
            status: 'stable',
            name: `i-0${(Math.random().toString(16) + '000000').substring(2, 9)}`,
            instanceType: 't3.large'
        }))
    },
];

const EVENT_SCENARIOS = [
    // 1. Single Replacement
    {
        id: 'evt-replace',
        cluster: 'US-EAST-AI-01',
        type: 'replacement',
        message: 'Spot Interruption - Auto-Replacement',
        nodes: [
            { id: 'r1', status: 'replacement', name: 'i-0d8f3a2b1c', instanceType: 'g4dn.xlarge' }
        ]
    },
    // 2. Fallback
    {
        id: 'evt-fallback',
        cluster: 'EU-Payment-Core',
        type: 'fallback',
        message: 'Capacity Loss - Fallback Activation',
        nodes: [
            { id: 'f1', status: 'fallback', name: 'i-0f9e8d7c6b', instanceType: 'OD-m5.12xl' },
            { id: 'f2', status: 'fallback', name: 'i-0e1d2c3b4a', instanceType: 'OD-m5.12xl' }
        ]
    },
    // 3. Multi-Node Impact
    {
        id: 'evt-multi',
        cluster: 'HPC-Matrix-V2',
        type: 'replacement',
        message: 'Multi-Zone Rebalancing',
        nodes: [
            { id: 'm1', status: 'replacement', name: 'i-0h1g2f3e4d', instanceType: 'c6g.metal' },
            { id: 'm2', status: 'replacement', name: 'i-0i2h3g4f5e', instanceType: 'c6g.metal' },
            { id: 'm3', status: 'replacement', name: 'i-0j3i4h5g6f', instanceType: 'c6g.metal' },
            { id: 'm4', status: 'replacement', name: 'i-0k4j5i6h7g', instanceType: 'c6g.metal' }
        ]
    }
];

// --- COMPONENTS ---

const FlowNode = ({ icon: Icon, label, status, type, className, style }) => (
    <motion.div
        layout
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.8 }}
        style={style}
        className={cn(
            "flex flex-col items-center justify-center p-3 rounded-xl border shadow-sm relative z-10 bg-white transition-all duration-300",
            // Base Sizes
            "w-24 h-24",
            // Status Styles
            status === 'active' && "border-slate-200",
            status === 'highlight' && "border-blue-400 bg-blue-50/50 shadow-md ring-2 ring-blue-100",
            status === 'draining' && "border-amber-300 bg-amber-50/80 shadow-inner",
            status === 'safe' && "border-emerald-200 bg-emerald-50/50 shadow-sm",
            status === 'fallback' && "border-red-500 bg-red-50 shadow-[0_0_15px_rgba(239,68,68,0.2)]",
            className
        )}
    >
        <div className={cn(
            "p-2.5 rounded-full mb-2 shadow-sm transition-colors duration-300",
            status === 'active' || status === 'highlight' ? "bg-white border border-slate-100 text-blue-600" : "bg-slate-50 border border-slate-200 text-slate-400",
            status === 'draining' && "bg-white border-amber-200 text-amber-500",
            status === 'optimization' && "bg-blue-600 text-white border-blue-500 shadow-lg",
            status === 'safe' && "bg-white border-emerald-100 text-emerald-600",
            status === 'fallback' && "bg-white border-red-200 text-red-600"
        )}>
            <Icon className="w-5 h-5" />
        </div>
        <div className="text-[10px] font-bold text-slate-900 text-center leading-tight truncate w-full px-1">{label}</div>
        <div className={cn(
            "text-[9px] mt-1 uppercase tracking-wider font-bold px-1.5 py-0.5 rounded-full scale-90",
            status === 'draining' ? "bg-amber-100 text-amber-700" : "text-slate-500",
            status === 'safe' && "text-emerald-600 bg-emerald-50",
            status === 'fallback' && "text-red-600 bg-red-100"
        )}>{type}</div>
    </motion.div>
);

// Connection Line Component
const ConnectionLine = ({ active, color = 'blue' }) => {
    const borderColor = color === 'green' ? 'border-l-emerald-200' : (color === 'red' ? 'border-l-red-200' : 'border-l-slate-300');

    return (
        <div className={cn("flex-1 h-[2px] relative min-w-[30px] flex items-center",
            color === 'green' && "bg-emerald-100",
            color === 'blue' && "bg-slate-200",
            color === 'red' && "bg-red-100"
        )}>
            {active && (
                <motion.div
                    initial={{ x: '-100%' }}
                    animate={{ x: '100%' }}
                    transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
                    className={cn("absolute inset-0 w-1/2",
                        color === 'green' && "bg-gradient-to-r from-transparent via-emerald-400 to-transparent",
                        color === 'blue' && "bg-gradient-to-r from-transparent via-blue-400 to-transparent",
                        color === 'red' && "bg-gradient-to-r from-transparent via-red-500 to-transparent"
                    )}
                />
            )}
            {/* Arrow Head at the End */}
            <div className={cn("absolute -right-[1px] w-0 h-0 border-l-[8px] border-y-[5px] border-y-transparent", borderColor)} />
        </div>
    );
};

// Individual Topology View (Used for both Single & Multi Modes)
// Individual Topology View (Used for both Single & Multi Modes)
const TopologyView = ({ scenario, isCompact = false }) => {
    const isFallback = scenario.type === 'fallback';
    const isStable = scenario.type === 'stable';
    const activeColor = isFallback ? 'red' : (isStable ? 'green' : 'blue');

    const [stage, setStage] = useState(0);

    useEffect(() => {
        if (scenario.nodes && scenario.nodes.some(n => n.status === 'replacement')) {
            const sequence = async () => {
                while (true) {
                    setStage(0); // Old
                    await new Promise(r => setTimeout(r, 2000));
                    setStage(1); // Swap (Active 3D move)
                    await new Promise(r => setTimeout(r, 800));
                    setStage(2); // New (Settled)
                    await new Promise(r => setTimeout(r, 2000));
                }
            };
            sequence();
        }
    }, [scenario]);

    return (
        <div className={cn("flex items-center justify-between w-full px-2", isCompact ? "gap-2" : "gap-4")}>

            {/* 1. CLUSTER */}
            <div className="flex flex-col items-center gap-3 z-10 w-32">
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest bg-slate-100/80 px-2 py-0.5 rounded-full backdrop-blur-sm border border-slate-200 whitespace-nowrap">
                    Managed Clusters
                </span>
                <FlowNode
                    icon={Layers}
                    label={
                        <div className="flex flex-col items-center mt-1">
                            <span className="font-bold text-xs">{scenario.cluster}</span>
                            <span className="text-[9px] text-slate-400 font-medium uppercase tracking-wider">{scenario.region || 'us-east-1'}</span>
                            <span className="text-[9px] text-slate-500 mt-0.5 flex items-center gap-1">
                                <span className="w-1 h-1 rounded-full bg-slate-400"></span>
                                {scenario.nodeCount || 45} Nodes
                            </span>
                        </div>
                    }
                    type={scenario.cluster}
                    status="active"
                    className={cn(isCompact ? "w-20 h-20" : "")}
                />
            </div>

            {/* Line 1 */}
            <ConnectionLine active={true} color={activeColor} />

            {/* 2. ENGINE */}
            <div className="flex flex-col items-center gap-3 z-10 w-28">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest bg-slate-100/80 px-2 py-0.5 rounded-full backdrop-blur-sm border border-slate-200">
                    Engine
                </span>
                <FlowNode
                    icon={Zap}
                    label="ATHARVA AI"
                    type="OPTIMIZER"
                    status="optimization"
                    className={cn(isCompact ? "w-20 h-20" : "")}
                />
            </div>

            {/* Line 2 */}
            <ConnectionLine active={true} color={activeColor} />

            {/* 3. NODES PILE (Stable) or IMPACT (Live) */}
            <div className="flex flex-col items-center gap-3 z-10 w-auto relative min-w-fit">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest bg-slate-100/80 px-2 py-0.5 rounded-full backdrop-blur-sm border border-slate-200">
                    Nodes
                </span>

                <div className="w-full flex justify-center min-h-[100px] items-center">
                    {scenario.nodes.some(n => n.status === 'replacement' || n.status === 'fallback') ? (
                        // --- ACTIVE EVENT (Live) ---
                        <div className="flex items-center gap-4">
                            {scenario.nodes.map(n => (
                                n.status === 'fallback' ? (
                                    <FlowNode
                                        key={n.id}
                                        icon={AlertCircle}
                                        label={n.name}
                                        type={n.instanceType}
                                        status="fallback"
                                        className={cn("animate-pulse border-red-400", isCompact ? "w-20 h-20" : "w-24 h-24")}
                                    />
                                ) : n.status === 'replacement' ? (
                                    // Replacement Animation Wrapper with Enhanced 3D
                                    <div key={n.id} className={cn("relative perspective-[600px]", isCompact ? "w-20 h-20" : "w-24 h-24")}>
                                        <AnimatePresence mode='sync'>
                                            {(stage === 0 || stage === 1) && (
                                                <motion.div
                                                    key="old"
                                                    initial={{ transformOrigin: "bottom", opacity: 1, rotateX: 0, z: 0 }}
                                                    animate={stage === 1 ? {
                                                        scale: 0.7,
                                                        opacity: 0,
                                                        z: -100,
                                                        rotateX: -60,
                                                        y: -50,
                                                        filter: 'blur(4px)'
                                                    } : { scale: 1, opacity: 1, z: 0, rotateX: 0, y: 0, filter: 'blur(0px)' }}
                                                    exit={{ opacity: 0 }}
                                                    transition={{ duration: 0.6, ease: "easeInOut" }}
                                                    className="absolute inset-0 z-0 bg-white rounded-xl"
                                                >
                                                    <FlowNode icon={Server} label={n.name} type="DRAINING" status="draining" className="w-full h-full shadow-md" />
                                                </motion.div>
                                            )}
                                            {stage >= 1 && (
                                                <motion.div
                                                    key="new"
                                                    initial={{ transformOrigin: "top", scale: 1.1, opacity: 0, y: 50, rotateX: 60, z: 50 }}
                                                    animate={{ scale: 1, opacity: 1, y: 0, rotateX: 0, z: 0 }}
                                                    transition={{ duration: 0.6, type: "spring", stiffness: 120, damping: 15 }}
                                                    className="absolute inset-0 z-20 shadow-2xl bg-white rounded-xl"
                                                >
                                                    <FlowNode
                                                        icon={Server}
                                                        label={`NEW-${n.name.split('-').pop()}`}
                                                        type={n.instanceType}
                                                        status="highlight"
                                                        className="w-full h-full ring-2 ring-emerald-400"
                                                    />
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
                                    </div>
                                ) : (
                                    <FlowNode key={n.id} icon={Server} label={n.name} type={n.instanceType} status="safe" className={cn(isCompact ? "w-20 h-20" : "w-24 h-24")} />
                                )
                            ))}
                        </div>
                    ) : (
                        // --- STABLE PILE (Cycle) ---
                        <div className="relative w-28 h-28 flex items-center justify-center">
                            {scenario.nodes.map((n, i) => (
                                <motion.div
                                    key={n.id}
                                    className="absolute"
                                    initial={{ y: 20, opacity: 0 }}
                                    animate={{
                                        y: -i * 8,
                                        scale: 1 - i * 0.08,
                                        zIndex: 10 - i,
                                        opacity: 1
                                    }}
                                    transition={{ delay: i * 0.1, type: "spring", stiffness: 100 }}
                                >
                                    <FlowNode
                                        icon={Server}
                                        label={null}
                                        type={n.instanceType || 'SPOT'}
                                        status="safe"
                                        className={cn(
                                            "w-24 h-24 shadow-lg transition-all duration-300",
                                            i === 0 ? "border-emerald-200 bg-white" : "bg-slate-50 border-slate-100"
                                        )}
                                        style={{
                                            filter: i > 0 ? `brightness(${1 - i * 0.05}) blur(${i * 0.5}px)` : 'none'
                                        }}
                                    />
                                </motion.div>
                            ))}
                            {/* Count Badge on top of pile */}
                            <div className="absolute -right-2 -top-4 z-50 bg-slate-800 text-white text-[10px] font-bold px-2 py-1 rounded-full shadow-lg border-2 border-white">
                                {scenario.nodeCount} Nodes
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

const InstanceFlowAnimation = ({ clusters = [], fallbackMode = 'none' }) => {
    const [isLiveMode, setIsLiveMode] = useState(false);
    const [cycleIndex, setCycleIndex] = useState(0);
    const [manualScenarioId, setManualScenarioId] = useState(null);

    // --- DATA MAPPING ---
    const scenarios = useMemo(() => {
        if (clusters && clusters.length > 0) {
            return clusters.map(c => ({
                id: c.id,
                cluster: c.name,
                region: c.region,
                type: 'stable',
                nodeCount: c.nodeCount,
                nodes: c.nodes ? c.nodes.map(n => ({
                    id: n.id,
                    name: n.id,
                    instanceType: n.family,
                    status: 'stable'
                })) : []
            }));
        }
        // Fallback to internal mock only if absolutely no data provided (e.g. development standalone)
        // But for consistency we prefer the prop.
        return STABLE_CLUSTERS;
    }, [clusters]);

    // --- CYCLING LOGIC ---
    useEffect(() => {
        if (!isLiveMode && scenarios.length > 0) {
            const interval = setInterval(() => {
                setCycleIndex(prev => (prev + 1) % scenarios.length);
            }, 6000);
            return () => clearInterval(interval);
        }
    }, [isLiveMode, scenarios.length]);

    const activeCycleScenario = scenarios.length > 0 ? scenarios[cycleIndex] : null;
    const nextCycle = () => setCycleIndex(p => (p + 1) % scenarios.length);
    const prevCycle = () => setCycleIndex(p => (p - 1 + scenarios.length) % scenarios.length);

    // --- LIVE LOGIC ---
    const liveEvents = useMemo(() => {
        if (!isLiveMode) return [];
        if (manualScenarioId) {
            if (manualScenarioId === 'multi-cluster') return [EVENT_SCENARIOS[0], EVENT_SCENARIOS[2]];
            return EVENT_SCENARIOS.filter(s => s.id === manualScenarioId);
        }
        if (fallbackMode !== 'none') return [EVENT_SCENARIOS[1]];
        return []; // Default Blank
    }, [isLiveMode, manualScenarioId, fallbackMode]);


    // --- BORDER / CONTAINER STYLING ---
    const containerClass = useMemo(() => {
        if (!isLiveMode) return "bg-slate-50 border-slate-200"; // Cycle

        // Live Mode Styles
        if (liveEvents.some(e => e.type === 'fallback')) {
            return "bg-red-50/30 border-red-500 shadow-[0_0_60px_rgba(239,68,68,0.2)]";
        }
        if (liveEvents.length > 0) {
            return "bg-blue-50/30 border-blue-400 shadow-[0_0_40px_rgba(59,130,246,0.1)]";
        }
        // Auto (Empty) - LIGHT THEME Requested
        return "bg-white border-slate-200 shadow-inner";
    }, [isLiveMode, liveEvents]);

    return (
        <div className="w-full mb-8 font-sans">
            {/* Header / Controls */}
            <div className="flex items-center justify-between mb-4 px-1">
                <div className="flex items-center space-x-3">
                    <div className="relative flex h-3 w-3">
                        <span className={cn("animate-ping absolute inline-flex h-full w-full rounded-full opacity-75", isLiveMode ? "bg-blue-400" : "bg-emerald-400")}></span>
                        <span className={cn("relative inline-flex rounded-full h-3 w-3", isLiveMode ? "bg-blue-500" : "bg-emerald-500")}></span>
                    </div>
                    <div>
                        <span className="text-xs font-bold uppercase tracking-widest text-slate-500 block">
                            {isLiveMode ? "Live Operations" : "Fleet Topology"}
                        </span>
                        {!isLiveMode && <span className="text-[10px] text-slate-400 font-mono">Monitoring {scenarios.length} Clusters</span>}
                    </div>

                    {/* Manual Debug Controls */}
                    {isLiveMode && (
                        <div className="flex items-center space-x-1 ml-6 bg-white p-1 rounded-lg border border-slate-200 shadow-sm">
                            <button onClick={() => setManualScenarioId(null)} className={cn("text-[10px] px-3 py-1 rounded-md transition-all font-bold", !manualScenarioId ? "bg-slate-800 text-white shadow" : "text-slate-400 hover:bg-slate-100")}>Auto</button>
                            <div className="w-px h-4 bg-slate-200 mx-1" />
                            <button onClick={() => setManualScenarioId('evt-replace')} className={cn("text-[10px] px-2 py-1 rounded transition-colors font-medium", manualScenarioId === 'evt-replace' ? "bg-blue-100 text-blue-700" : "text-slate-500 hover:text-slate-700")}>Repl</button>
                            <button onClick={() => setManualScenarioId('evt-fallback')} className={cn("text-[10px] px-2 py-1 rounded transition-colors font-medium", manualScenarioId === 'evt-fallback' ? "bg-red-100 text-red-700" : "text-slate-500 hover:text-slate-700")}>Fail</button>
                            <button onClick={() => setManualScenarioId('evt-multi')} className={cn("text-[10px] px-2 py-1 rounded transition-colors font-medium", manualScenarioId === 'evt-multi' ? "bg-purple-100 text-purple-700" : "text-slate-500 hover:text-slate-700")}>Multi</button>
                            <button onClick={() => setManualScenarioId('multi-cluster')} className={cn("text-[10px] px-2 py-1 rounded transition-colors font-medium", manualScenarioId === 'multi-cluster' ? "bg-slate-100 text-slate-700" : "text-slate-500 hover:text-slate-700")}>Split</button>
                        </div>
                    )}
                </div>

                {/* Mode Toggle */}
                <div className="flex bg-white p-1 rounded-xl border border-slate-200 shadow-sm">
                    <button onClick={() => setIsLiveMode(true)} className={cn("px-4 py-1.5 text-[10px] font-bold uppercase rounded-lg transition-all", isLiveMode ? "bg-slate-800 text-white shadow-md transform scale-105" : "text-slate-500 hover:bg-slate-50")}>Live View</button>
                    <button onClick={() => setIsLiveMode(false)} className={cn("px-4 py-1.5 text-[10px] font-bold uppercase rounded-lg transition-all", !isLiveMode ? "bg-white text-emerald-600 shadow border border-slate-100 transform scale-105" : "text-slate-500 hover:text-emerald-600")}>Cycle View</button>
                </div>
            </div>

            {/* Main Display Area */}
            <div className={cn("w-full rounded-2xl border p-8 relative flex flex-col justify-center min-h-[320px] transition-all duration-700 ease-in-out overflow-hidden group/container", containerClass)}>

                {/* Background Grid */}
                <div className="absolute inset-0 z-0 bg-[linear-gradient(to_right,#64748b_1px,transparent_1px),linear-gradient(to_bottom,#64748b_1px,transparent_1px)] bg-[size:24px_24px] opacity-[0.04] pointer-events-none" />

                <AnimatePresence mode='wait'>
                    {!isLiveMode ? (
                        // --- MODE A: CYCLE VIEW ---
                        activeCycleScenario ? (
                            <motion.div
                                key={activeCycleScenario.id}
                                initial={{ opacity: 0, x: 20 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: -20 }}
                                transition={{ duration: 0.5 }}
                                className="w-full max-w-4xl mx-auto relative group"
                            >
                                <button onClick={prevCycle} className="absolute -left-16 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center bg-white rounded-full shadow-lg border border-slate-100 text-slate-600 hover:text-blue-600 hover:border-blue-200 transition-all z-50">
                                    <ChevronLeft className="w-6 h-6" />
                                </button>
                                <button onClick={nextCycle} className="absolute -right-16 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center bg-white rounded-full shadow-lg border border-slate-100 text-slate-600 hover:text-blue-600 hover:border-blue-200 transition-all z-50">
                                    <ChevronRight className="w-6 h-6" />
                                </button>

                                <TopologyView scenario={activeCycleScenario} />

                                <div className="absolute -bottom-10 left-1/2 -translate-x-1/2 bg-emerald-50 border border-emerald-100 text-emerald-700 px-3 py-1 rounded-full text-[10px] font-bold shadow-sm flex items-center gap-1">
                                    <Database className="w-3 h-3" />
                                    {activeCycleScenario.nodeCount} Active Nodes
                                </div>
                            </motion.div>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-full text-slate-400">
                                <AlertCircle className="w-8 h-8 mb-2 opacity-50" />
                                <span className="text-xs font-bold uppercase tracking-wider">No Clusters Found</span>
                            </div>
                        )
                    ) : (
                        // --- MODE B: LIVE VIEW ---
                        liveEvents.length === 0 ? (
                            // Light Theme Auto Mode
                            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center h-full relative z-10">
                                <div className="relative mb-4">
                                    <div className="absolute inset-0 bg-blue-100 blur-xl opacity-50 animate-pulse rounded-full" />
                                    <div className="w-16 h-16 bg-white rounded-2xl flex items-center justify-center border border-slate-200 shadow-md relative z-10">
                                        <Zap className="w-8 h-8 text-blue-500" />
                                    </div>
                                    <div className="absolute -top-1 -right-1 w-3 h-3 bg-blue-500 rounded-full animate-ping" />
                                </div>
                                <div className="text-slate-400 text-sm font-bold tracking-widest uppercase">Live Monitoring</div>
                                <div className="text-slate-500 text-xs font-mono mt-2">Waiting for events...</div>
                            </motion.div>
                        ) : (
                            <motion.div
                                key="live-content"
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -20 }}
                                transition={{ duration: 0.4 }}
                                className={cn("w-full mx-auto grid gap-8", liveEvents.length > 1 ? "grid-cols-2 max-w-[95%]" : "max-w-3xl")}
                            >
                                {liveEvents.map(event => (
                                    <div key={event.id} className="relative">
                                        {liveEvents.length > 1 && (
                                            <div className="absolute -top-10 left-0 right-0 flex justify-center">
                                                <span className="text-[9px] font-bold text-slate-400 bg-white border border-slate-200 px-2 py-1 rounded-full uppercase tracking-widest shadow-sm">
                                                    {event.message}
                                                </span>
                                            </div>
                                        )}
                                        <TopologyView scenario={event} isCompact={liveEvents.length > 1} />
                                    </div>
                                ))}
                            </motion.div>
                        )
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
};

export default InstanceFlowAnimation;
// End of component
