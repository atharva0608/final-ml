import React, { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { hibernationAPI, clusterAPI, metricAPI } from "../../services/api";
import { FiArrowLeft, FiClock, FiCheck, FiAlertCircle, FiMoon, FiSun, FiSave, FiPower, FiBriefcase, FiCoffee } from "react-icons/fi";
import toast from "react-hot-toast";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const PALETTE = [
    { bg: "bg-violet-500", light: "bg-violet-50", text: "text-violet-700", border: "border-violet-300" },
    { bg: "bg-sky-500", light: "bg-sky-50", text: "text-sky-700", border: "border-sky-300" },
    { bg: "bg-rose-500", light: "bg-rose-50", text: "text-rose-700", border: "border-rose-300" },
    { bg: "bg-amber-500", light: "bg-amber-50", text: "text-amber-700", border: "border-amber-300" },
    { bg: "bg-emerald-500", light: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-300" },
];

const QUICK_TEMPLATES = [
    {
        label: "Business Hours", icon: <FiBriefcase />, description: "Nights + full weekends",
        rules: [
            { id: "t1a", label: "Nights", days: [0, 1, 2, 3, 4], sleepHour: 18, wakeHour: 9, colorIdx: 0 },
            { id: "t1b", label: "Weekend", days: [5, 6], sleepHour: 0, wakeHour: 24, colorIdx: 1 },
        ],
    },
    {
        label: "Nights Only", icon: <FiMoon />, description: "Sleep 6PM–8AM daily",
        rules: [{ id: "t2a", label: "Night", days: [0, 1, 2, 3, 4, 5, 6], sleepHour: 18, wakeHour: 8, colorIdx: 0 }],
    },
    {
        label: "Weekends Off", icon: <FiCoffee />, description: "Full weekend sleep",
        rules: [{ id: "t3a", label: "Weekend", days: [5, 6], sleepHour: 0, wakeHour: 24, colorIdx: 2 }],
    },
];

function fmt(h) {
    if (h === 0 || h === 24) return "12 AM";
    if (h === 12) return "12 PM";
    return h < 12 ? `${h} AM` : `${h - 12} PM`;
}

function rulesToMatrix(rules) {
    const m = new Array(168).fill(1);
    rules.forEach(({ days, sleepHour, wakeHour }) => {
        days.forEach((dayIdx) => {
            if (sleepHour === 0 && wakeHour === 24) {
                for (let h = 0; h < 24; h++) m[dayIdx * 24 + h] = 0;
            } else if (sleepHour < wakeHour) {
                for (let h = sleepHour; h < wakeHour; h++) m[dayIdx * 24 + h] = 0;
            } else if (sleepHour > wakeHour) {
                for (let h = sleepHour; h < 24; h++) m[dayIdx * 24 + h] = 0;
                const nextDay = (dayIdx + 1) % 7;
                for (let h = 0; h < wakeHour; h++) m[nextDay * 24 + h] = 0;
            }
        });
    });
    return m;
}

function matrixToRules(matrix) {
    const windowsByDay = DAYS.map((_, di) => {
        const row = matrix.slice(di * 24, di * 24 + 24);
        const sleepIdxs = row.map((v, i) => v === 0 ? i : null).filter(x => x !== null);
        if (sleepIdxs.length === 0) return null;
        if (sleepIdxs.length === 24) return { sleepHour: 0, wakeHour: 24 };
        return { sleepHour: sleepIdxs[0], wakeHour: sleepIdxs[sleepIdxs.length - 1] + 1 };
    });

    const rules = [];
    let colorIdx = 0;
    windowsByDay.forEach((win, di) => {
        if (!win) return;
        const existing = rules.find(r => r.sleepHour === win.sleepHour && r.wakeHour === win.wakeHour);
        if (existing) {
            existing.days.push(di);
        } else {
            rules.push({ id: `loaded_${di}`, label: "Sleep window", days: [di], ...win, colorIdx: colorIdx++ % PALETTE.length });
        }
    });
    return rules.length > 0 ? rules : [{ id: "r_new", label: "New Window", days: [], sleepHour: 21, wakeHour: 9, colorIdx: 0 }];
}

function MatrixPreview({ matrix }) {
    return (
        <div>
            {DAYS.map((day, di) => (
                <div key={day} className="flex items-center gap-1 mb-1">
                    <span className="text-[10px] text-gray-400 w-6 flex-shrink-0">{day}</span>
                    <div className="flex gap-[2px]">
                        {Array.from({ length: 24 }, (_, h) => (
                            <div key={h} title={`${day} ${fmt(h)}`}
                                className={`w-2 h-2 rounded-sm ${matrix[di * 24 + h] === 0 ? "bg-slate-800" : "bg-slate-200"}`}
                            />
                        ))}
                    </div>
                </div>
            ))}
        </div>
    );
}

function RuleCard({ rule, palette, onUpdate, onDelete, isOnly }) {
    const [expanded, setExpanded] = useState(true);
    const isFullDay = rule.sleepHour === 0 && rule.wakeHour === 24;
    const crossesMidnight = !isFullDay && rule.sleepHour > rule.wakeHour;
    const dur = isFullDay ? 24 : crossesMidnight ? 24 - rule.sleepHour + rule.wakeHour : rule.wakeHour - rule.sleepHour;

    const toggleDay = (d) => {
        const days = rule.days.includes(d)
            ? rule.days.filter(x => x !== d)
            : [...rule.days, d].sort((a, b) => a - b);
        onUpdate({ ...rule, days });
    };

    return (
        <div className={`border-2 ${palette.border} rounded-xl overflow-hidden shadow-sm mb-4 bg-white transition-all`}>
            {/* Header */}
            <div onClick={() => setExpanded(v => !v)}
                className={`${palette.light} flex items-center justify-between p-3 cursor-pointer select-none`}>
                <div className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full ${palette.bg}`} />
                    <input value={rule.label} onChange={e => onUpdate({ ...rule, label: e.target.value })} onClick={e => e.stopPropagation()}
                        className={`text-sm font-bold bg-transparent border-none outline-none ${palette.text} w-40 hover:bg-white/50 rounded px-1`} />

                    <div className="text-xs text-gray-500 font-medium">
                        {rule.days.length > 0 ? (
                            <span>
                                {isFullDay ? `Full day · ${dur}h`
                                    : crossesMidnight ? `${fmt(rule.sleepHour)} → ${fmt(rule.wakeHour)} (+1 day) · ${dur}h`
                                        : `${fmt(rule.sleepHour)} → ${fmt(rule.wakeHour)} · ${dur}h`}
                            </span>
                        ) : <span className="text-amber-500 font-bold">! Select days</span>}
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <span className="text-[10px] bg-white/70 rounded px-2 py-0.5 text-gray-500 font-medium">
                        {rule.days.map(d => DAYS[d]).join(", ") || "No days"}
                    </span>
                    <button onClick={e => { e.stopPropagation(); if (!isOnly) onDelete(rule.id); }} disabled={isOnly}
                        className={`text-gray-400 hover:text-red-500 p-1 ${isOnly ? 'opacity-30 cursor-not-allowed' : ''}`}>
                        <FiXicon />
                    </button>
                </div>
            </div>

            {/* Body */}
            {expanded && (
                <div className="p-4 flex flex-col gap-4 animate-in slide-in-from-top-2 duration-200">
                    <div>
                        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Sleep on days</p>
                        <div className="flex gap-2">
                            {DAYS.map((d, i) => (
                                <button key={d} onClick={() => toggleDay(i)}
                                    className={`w-9 h-9 rounded-full text-xs font-bold transition-all ${rule.days.includes(i)
                                        ? "bg-slate-800 text-white scale-110 shadow-md"
                                        : "bg-slate-100 text-gray-400 hover:bg-slate-200"
                                        }`}>
                                    {d}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <div className="flex items-center gap-2 mb-2">
                            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Sleep Window</p>
                            {crossesMidnight && (
                                <span className="text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-bold">Overnight (+1 day)</span>
                            )}
                        </div>

                        <label className="flex items-center gap-2 mb-3 cursor-pointer w-fit">
                            <div className={`w-9 h-5 rounded-full relative transition-colors ${isFullDay ? 'bg-slate-800' : 'bg-gray-200'}`}
                                onClick={() => onUpdate({ ...rule, sleepHour: isFullDay ? 21 : 0, wakeHour: isFullDay ? 9 : 24 })}>
                                <div className={`w-4 h-4 bg-white rounded-full absolute top-0.5 transition-all ${isFullDay ? 'left-[18px]' : 'left-0.5'}`} />
                            </div>
                            <span className="text-xs font-medium text-gray-600">Full day hibernation</span>
                        </label>

                        {!isFullDay && (
                            <div className="flex items-center gap-3">
                                <div className="flex flex-col gap-1">
                                    <span className="text-[10px] font-bold text-gray-400 uppercase">Sleep At</span>
                                    <select value={rule.sleepHour} onChange={e => onUpdate({ ...rule, sleepHour: Number(e.target.value) })}
                                        className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white hover:border-blue-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all outline-none">
                                        {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{fmt(h)}</option>)}
                                    </select>
                                </div>
                                <span className="text-gray-300 text-xl pt-4">→</span>
                                <div className="flex flex-col gap-1">
                                    <span className="text-[10px] font-bold text-gray-400 uppercase">Wake At</span>
                                    <select value={rule.wakeHour} onChange={e => onUpdate({ ...rule, wakeHour: Number(e.target.value) })}
                                        className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white hover:border-blue-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all outline-none">
                                        {Array.from({ length: 24 }, (_, h) => <option key={h + 1} value={h + 1}>{fmt(h + 1)}</option>)}
                                    </select>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

const FiXicon = () => <svg stroke="currentColor" fill="none" strokeWidth="2" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" height="1em" width="1em" xmlns="http://www.w3.org/2000/svg"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>;

export default function HibernationScheduler({ clusterId: propClusterId, embedded = false }) {
    const params = useParams();
    const navigate = useNavigate();

    const [clusters, setClusters] = useState([]);
    const [selectedClusterId, setSelectedClusterId] = useState(propClusterId || params?.clusterId || null);
    const [existingScheduleId, setExistingScheduleId] = useState(null);
    const [rules, setRules] = useState([{ id: "r1", label: "New Window", days: [], sleepHour: 21, wakeHour: 9, colorIdx: 0 }]);
    const [strategy, setStrategy] = useState("NAMESPACE_SLEEP");
    const [timezone, setTimezone] = useState("UTC");
    const [preWarmMinutes, setPreWarmMinutes] = useState(15);
    const [isScheduled, setIsScheduled] = useState(false);
    const [lastAction, setLastAction] = useState(null);
    const [lastActionAt, setLastActionAt] = useState(null);
    const [hourlyCost, setHourlyCost] = useState(0);
    const [loadingData, setLoadingData] = useState(false);
    const [saving, setSaving] = useState(false);
    const [toggling, setToggling] = useState(false);
    const [savedOk, setSavedOk] = useState(false);
    const [showMatrix, setShowMatrix] = useState(false);
    const pollRef = useRef(null);

    const validRules = useMemo(() => rules.filter(r => r.days.length > 0), [rules]);
    const matrix = useMemo(() => rulesToMatrix(validRules), [validRules]);
    const sleeping = matrix.filter(v => v === 0).length;
    const savingPct = Math.round((sleeping / 168) * 100);
    const estSaving = hourlyCost > 0 ? Math.round(sleeping * hourlyCost * 4.33) : null;
    const hasErrors = false;
    const selectedCluster = clusters.find(c => c.id === selectedClusterId);

    useEffect(() => {
        if (!existingScheduleId || !selectedClusterId) return;
        const poll = async () => {
            try {
                const res = await hibernationAPI.getByCluster(selectedClusterId);
                const sch = res.data?.schedules?.[0];
                if (sch) {
                    setIsScheduled(sch.is_active === true || sch.is_active === "Y");
                }
            } catch (_) { }
        };
        pollRef.current = setInterval(poll, 30000);
        return () => clearInterval(pollRef.current);
    }, [existingScheduleId, selectedClusterId]);

    useEffect(() => {
        clusterAPI.list({})
            .then(res => {
                const list = res.data?.clusters || res.data || [];
                setClusters(list);
                if (!selectedClusterId && list.length > 0) setSelectedClusterId(list[0].id);
            })
            .catch(() => toast.error("Failed to load clusters"));
    }, []);

    useEffect(() => {
        if (!selectedClusterId) return;
        setLoadingData(true);

        Promise.allSettled([
            hibernationAPI.getByCluster(selectedClusterId),
            metricAPI.getClusterMetrics(selectedClusterId),
        ]).then(([schedRes, metricRes]) => {
            if (metricRes.status === "fulfilled") {
                const d = metricRes.value.data;
                const monthly = d?.monthly_cost || d?.total_monthly_cost || 0;
                setHourlyCost(monthly > 0 ? monthly / 730 : 0);
            }
            if (schedRes.status === "fulfilled") {
                const schedules = schedRes.value.data?.schedules || [];
                if (schedules.length > 0) {
                    const s = schedules[0];
                    setExistingScheduleId(s.id);
                    setStrategy(s.strategy || "NAMESPACE_SLEEP");
                    setTimezone(s.timezone || "UTC");
                    setPreWarmMinutes(s.pre_warm_minutes ?? 15);
                    setIsScheduled(s.is_active === true || s.is_active === "Y");
                    const rawMatrix = Array.isArray(s.schedule_matrix)
                        ? s.schedule_matrix
                        : String(s.schedule_matrix).split("").map(Number);
                    setRules(matrixToRules(rawMatrix));
                } else {
                    setExistingScheduleId(null);
                    setIsScheduled(false);
                    setRules([{ id: "r1", label: "New Window", days: [], sleepHour: 21, wakeHour: 9, colorIdx: 0 }]);
                }
            }
        }).finally(() => setLoadingData(false));
    }, [selectedClusterId]);

    const updateRule = useCallback(u => setRules(prev => prev.map(r => r.id === u.id ? u : r)), []);
    const deleteRule = useCallback(id => setRules(prev => prev.filter(r => r.id !== id)), []);
    const addRule = () => setRules(prev => [...prev, { id: `r${Date.now()}`, label: "New Window", days: [], sleepHour: 21, wakeHour: 9, colorIdx: prev.length % PALETTE.length }]);
    const applyTemplate = tpl => setRules(tpl.rules.map((r, i) => ({ ...r, colorIdx: i % PALETTE.length })));

    const handleSave = async () => {
        if (!selectedClusterId) {
            toast.error("Please select a cluster first");
            return;
        }
        setSaving(true);
        try {
            const payload = {
                cluster_id: selectedClusterId,
                schedule_type: "WEEKLY",
                schedule_matrix: matrix,
                timezone,
                pre_warm_minutes: preWarmMinutes,
                strategy,
                is_active: isScheduled,
            };
            if (existingScheduleId) {
                await hibernationAPI.update(existingScheduleId, payload);
                toast.success("Schedule updated");
            } else {
                const res = await hibernationAPI.create(payload);
                setExistingScheduleId(res.data.id);
                setIsScheduled(res.data.is_active === true || res.data.is_active === "Y");
                toast.success("Schedule created! You can now activate it.");
            }
            setSavedOk(true);
            setTimeout(() => setSavedOk(false), 2500);
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Failed to save schedule");
        } finally {
            setSaving(false);
        }
    };

    const handleToggle = async () => {
        if (!existingScheduleId) {
            toast("Please save the schedule first.", { icon: "💾" });
            return;
        }
        setToggling(true);
        try {
            await hibernationAPI.toggle(existingScheduleId);
            const next = !isScheduled;
            setIsScheduled(next);
            toast.success(next ? "Schedule ACTIVATED" : "Schedule PAUSED");
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Failed to toggle");
        } finally {
            setToggling(false);
        }
    };

    const statusChip = () => {
        if (loadingData) return { label: "Loading…", bg: "bg-gray-100", color: "text-gray-500", dot: "bg-gray-400" };
        if (!existingScheduleId) return { label: "Not scheduled", bg: "bg-gray-100", color: "text-gray-500", dot: "bg-gray-400" };
        if (!isScheduled) return { label: "Paused", bg: "bg-amber-100", color: "text-amber-700", dot: "bg-amber-500" };
        return { label: "Active", bg: "bg-emerald-100", color: "text-emerald-700", dot: "bg-emerald-500" };
    };
    const chip = statusChip();

    return (
        <div className={`min-h-screen bg-slate-50 font-sans ${embedded ? 'p-0' : 'p-6'}`}>
            <div className="max-w-7xl mx-auto">

                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8">
                    <div>
                        {!embedded && (
                            <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-xs text-gray-400 font-bold uppercase tracking-wider mb-2 hover:text-blue-600 transition-colors">
                                <FiArrowLeft /> Back to clusters
                            </button>
                        )}
                        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Hibernation Schedule</h1>
                        <p className="text-gray-500 mt-1">Configure when your cluster should sleep to save costs.</p>
                    </div>
                    {clusters.length > 0 && (
                        <div className="flex items-center gap-3">
                            <span className="text-sm font-bold text-gray-500">Target Cluster:</span>
                            <select value={selectedClusterId || ""} onChange={e => setSelectedClusterId(e.target.value)}
                                className="text-sm font-semibold border-2 border-gray-200 rounded-lg px-4 py-2 bg-white cursor-pointer hover:border-blue-400 outline-none transition-all">
                                {clusters.map(c => <option key={c.id} value={c.id}>{c.name} ({c.region})</option>)}
                            </select>
                        </div>
                    )}
                </div>

                {/* Stats Strip */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                    <StatCard label="Sleep Hours" value={`${sleeping}h`} sub="/ 168h total" icon={<FiMoon className="text-indigo-400" />} />
                    <StatCard label="Awake Hours" value={`${168 - sleeping}h`} sub="Cluster running" icon={<FiSun className="text-amber-400" />} />
                    <StatCard label="Est. Savings" value={`${savingPct}%`} sub={estSaving ? `~$${estSaving}/mo` : "Connect metrics"} icon={<FiCheck className="text-emerald-400" />} />
                    <StatCard label="Status" value={chip.label} sub={isScheduled ? "Running normally" : "Not active"} icon={<FiAlertCircle className="text-gray-400" />} />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">

                    {/* LEFT: Rules */}
                    <div className="lg:col-span-2 space-y-6">

                        {/* Templates */}
                        <div className="bg-white rounded-xl p-5 border border-gray-100 shadow-sm">
                            <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">Quick Templates</p>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                {QUICK_TEMPLATES.map(tpl => (
                                    <button key={tpl.label} onClick={() => applyTemplate(tpl)}
                                        className="text-left border border-gray-200 rounded-lg p-3 hover:bg-blue-50 hover:border-blue-200 transition-all group">
                                        <div className="text-2xl mb-2 text-gray-400 group-hover:text-blue-500 transition-colors">{tpl.icon}</div>
                                        <div className="font-bold text-gray-700 text-sm">{tpl.label}</div>
                                        <div className="text-xs text-gray-400">{tpl.description}</div>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Rules List */}
                        <div>
                            {loadingData ? (
                                <div className="p-12 text-center text-gray-400">Loading schedule configuration...</div>
                            ) : (
                                <div className="space-y-4">
                                    {rules.map((rule, i) => (
                                        <RuleCard key={rule.id} rule={rule}
                                            palette={PALETTE[rule.colorIdx ?? (i % PALETTE.length)]}
                                            onUpdate={updateRule} onDelete={deleteRule} isOnly={rules.length === 1} />
                                    ))}
                                </div>
                            )}

                            <button onClick={addRule}
                                className="w-full border-2 border-dashed border-gray-300 rounded-xl p-4 text-gray-400 font-bold hover:border-blue-400 hover:text-blue-500 hover:bg-blue-50 transition-all mt-4 flex items-center justify-center gap-2">
                                <span className="text-xl">+</span> Add Sleep Window
                            </button>
                        </div>

                        {/* Matrix Toggle */}
                        <div className="pt-4">
                            <button onClick={() => setShowMatrix(v => !v)} className="text-xs font-bold text-gray-400 hover:text-blue-600 flex items-center gap-2">
                                {showMatrix ? "Hide" : "Show"} hourly grid preview
                            </button>
                            {showMatrix && (
                                <div className="mt-4 bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
                                    <MatrixPreview matrix={matrix} />
                                </div>
                            )}
                        </div>
                    </div>

                    {/* RIGHT: Controls */}
                    <div className="space-y-6 lg:sticky lg:top-8">

                        {/* Status Card (Updated to match screenshot) */}
                        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                            <div className="flex justify-between items-center mb-6">
                                <span className="text-xs font-bold text-gray-400 uppercase tracking-widest">Schedule Status</span>
                                <div className={`px-3 py-1 rounded-full flex items-center gap-2 text-xs font-bold ${chip.bg} ${chip.color}`}>
                                    <div className={`w-2 h-2 rounded-full ${chip.dot} ${isScheduled ? 'animate-pulse' : ''}`} />
                                    {chip.label}
                                </div>
                            </div>

                            <button
                                onClick={handleToggle}
                                disabled={!existingScheduleId || toggling}
                                className={`w-full py-4 rounded-lg font-bold text-sm mb-3 transition-all flex items-center justify-center gap-2
                            ${!existingScheduleId
                                        ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                                        : isScheduled
                                            ? "bg-red-50 text-red-600 border border-red-200 hover:bg-red-100"
                                            : "bg-emerald-50 text-emerald-600 border border-emerald-200 hover:bg-emerald-100"
                                    }
                        `}>
                                {toggling
                                    ? "Processing..."
                                    : isScheduled ? "Stop Schedule" : "Start Schedule"
                                }
                            </button>

                            <p className="text-xs text-center text-gray-400">
                                {!existingScheduleId
                                    ? "Save the schedule first to activate it."
                                    : isScheduled
                                        ? "Schedule is active and running."
                                        : "Schedule is saved but currently paused."
                                }
                            </p>
                        </div>

                        {/* Save Button */}
                        <button
                            onClick={handleSave}
                            disabled={saving || !selectedClusterId}
                            className={`w-full py-4 rounded-xl font-bold text-white text-base shadow-lg shadow-blue-200 transition-all transform active:scale-95 flex items-center justify-center gap-2
                        ${savedOk ? "bg-emerald-500" : "bg-blue-600 hover:bg-blue-700"}
                        ${(saving || !selectedClusterId) ? "opacity-50 cursor-not-allowed" : ""}
                    `}>
                            {saving ? "Saving..." : savedOk ? <><FiCheck /> Saved</> : <><FiSave /> Save Schedule</>}
                        </button>

                        {/* Config Panel */}
                        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm space-y-5">
                            <div>
                                <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Hibernation Strategy</p>
                                <select value={strategy} onChange={e => setStrategy(e.target.value)}
                                    className="w-full text-sm border-2 border-gray-100 rounded-lg p-2 bg-slate-50 font-medium outline-none focus:border-blue-400 transition-all">
                                    <option value="NAMESPACE_SLEEP">Namespace Sleep (~2 min wake, ~80% savings)</option>
                                    <option value="NUCLEAR">Nuclear (~8 min wake, ~99% savings)</option>
                                    <option value="SNAPSHOT_RESTORE">Snapshot & Restore (~12 min wake, ~90% savings)</option>
                                </select>
                                <p className="text-xs text-gray-500 mt-2">
                                    {strategy === "NAMESPACE_SLEEP" && "Scales workloads to 0 replicas. Best for stateless dev/test."}
                                    {strategy === "NUCLEAR" && "Scales all ASGs to 0. Maximum savings for non-critical environments."}
                                    {strategy === "SNAPSHOT_RESTORE" && "Snapshots volumes before shutdown. Best for stateful workloads."}
                                </p>
                            </div>
                            <div>
                                <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Timezone</p>
                                <select value={timezone} onChange={e => setTimezone(e.target.value)}
                                    className="w-full text-sm border-2 border-gray-100 rounded-lg p-2 bg-slate-50 font-medium outline-none focus:border-blue-400 transition-all">
                                    {["UTC", "America/New_York", "America/Los_Angeles", "Europe/London", "Asia/Tokyo"].map(tz => (
                                        <option key={tz} value={tz}>{tz}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Pre-warm (mins)</p>
                                <input type="number" value={preWarmMinutes} onChange={e => setPreWarmMinutes(Number(e.target.value))}
                                    className="w-full text-sm border-2 border-gray-100 rounded-lg p-2 bg-slate-50 font-medium outline-none focus:border-blue-400 transition-all" />
                            </div>
                        </div>

                    </div>
                </div>
            </div>
        </div>
    );
}

function StatCard({ label, value, sub, icon }) {
    return (
        <div className="bg-white p-5 rounded-xl border border-gray-100 shadow-sm flex items-start justify-between">
            <div>
                <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-1">{label}</p>
                <div className="text-2xl font-black text-slate-800 mb-1">{value}</div>
                <p className="text-xs text-gray-400 font-medium">{sub}</p>
            </div>
            <div className="text-xl opacity-80">{icon}</div>
        </div>
    );
}
