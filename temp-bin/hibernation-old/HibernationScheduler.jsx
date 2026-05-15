import React, { useState, useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { hibernationAPI, clusterAPI } from "../../services/api";
import { FiArrowLeft, FiCheck, FiAlertCircle, FiSave, FiEdit2, FiTrash2, FiPlay, FiPause, FiX, FiPlus } from "react-icons/fi";
import toast from "react-hot-toast";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const PALETTE = [
    { bg: "bg-violet-500", light: "bg-violet-50", text: "text-violet-700", border: "border-violet-300" },
    { bg: "bg-sky-500", light: "bg-sky-50", text: "text-sky-700", border: "border-sky-300" },
    { bg: "bg-rose-500", light: "bg-rose-50", text: "text-rose-700", border: "border-rose-300" },
    { bg: "bg-amber-500", light: "bg-amber-50", text: "text-amber-700", border: "border-amber-300" },
    { bg: "bg-emerald-500", light: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-300" },
];

const STRATEGIES = [
    { value: "NAMESPACE_SLEEP", label: "Namespace Sleep", wake: "~2 min", savings: "~80%", color: "blue" },
    { value: "NUCLEAR", label: "Nuclear", wake: "~8 min", savings: "~99%", color: "red" },
    { value: "SNAPSHOT_RESTORE", label: "Snapshot & Restore", wake: "~12 min", savings: "~90%", color: "purple" }
];

function fmt(h) {
    if (h === 0 || h === 24) return "12 AM";
    if (h === 12) return "12 PM";
    return h < 12 ? `${h} AM` : `${h - 12} PM`;
}

function windowToMatrix(window) {
    const m = new Array(168).fill(1);
    window.days.forEach((dayIdx) => {
        if (window.sleepHour === 0 && window.wakeHour === 24) {
            for (let h = 0; h < 24; h++) m[dayIdx * 24 + h] = 0;
        } else if (window.sleepHour < window.wakeHour) {
            for (let h = window.sleepHour; h < window.wakeHour; h++) m[dayIdx * 24 + h] = 0;
        } else if (window.sleepHour > window.wakeHour) {
            for (let h = window.sleepHour; h < 24; h++) m[dayIdx * 24 + h] = 0;
            const nextDay = (dayIdx + 1) % 7;
            for (let h = 0; h < window.wakeHour; h++) m[nextDay * 24 + h] = 0;
        }
    });
    return m;
}

// Window Card Component
function WindowCard({ window, palette, clusters, onUpdate, onDelete, isOnly }) {
    const [expanded, setExpanded] = useState(true);
    const isFullDay = window.sleepHour === 0 && window.wakeHour === 24;
    const crossesMidnight = !isFullDay && window.sleepHour > window.wakeHour;
    const dur = isFullDay ? 24 : crossesMidnight ? 24 - window.sleepHour + window.wakeHour : window.wakeHour - window.sleepHour;

    const toggleDay = (d) => {
        const days = window.days.includes(d)
            ? window.days.filter(x => x !== d)
            : [...window.days, d].sort((a, b) => a - b);
        onUpdate({ ...window, days });
    };

    return (
        <div className={`border-2 ${palette.border} rounded-xl overflow-hidden shadow-sm mb-4 bg-white transition-all`}>
            {/* Header */}
            <div onClick={() => setExpanded(v => !v)}
                className={`${palette.light} flex items-center justify-between p-3 cursor-pointer select-none`}>
                <div className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full ${palette.bg}`} />
                    <input value={window.label} onChange={e => onUpdate({ ...window, label: e.target.value })} onClick={e => e.stopPropagation()}
                        className={`text-sm font-bold bg-transparent border-none outline-none ${palette.text} w-40 hover:bg-white/50 rounded px-1`} />

                    <div className="text-xs text-gray-500 font-medium">
                        {window.days.length > 0 ? (
                            <span>
                                {isFullDay ? `Full day · ${dur}h`
                                    : crossesMidnight ? `${fmt(window.sleepHour)} → ${fmt(window.wakeHour)} (+1 day) · ${dur}h`
                                        : `${fmt(window.sleepHour)} → ${fmt(window.wakeHour)} · ${dur}h`}
                            </span>
                        ) : <span className="text-amber-500 font-bold">! Select days and cluster</span>}
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <span className="text-[10px] bg-white/70 rounded px-2 py-0.5 text-gray-500 font-medium">
                        {window.days.map(d => DAYS[d]).join(", ") || "No days"}
                    </span>
                    <button onClick={e => { e.stopPropagation(); if (!isOnly) onDelete(window.id); }} disabled={isOnly}
                        className={`text-gray-400 hover:text-red-500 p-1 ${isOnly ? 'opacity-30 cursor-not-allowed' : ''}`}>
                        <FiX />
                    </button>
                </div>
            </div>

            {/* Body */}
            {expanded && (
                <div className="p-4 flex flex-col gap-4 animate-in slide-in-from-top-2 duration-200">
                    {/* Cluster Selection */}
                    <div>
                        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Target Cluster</p>
                        <select value={window.clusterId || ""} onChange={e => onUpdate({ ...window, clusterId: e.target.value })}
                            className="w-full text-sm border-2 border-gray-200 rounded-lg px-3 py-2 bg-white hover:border-blue-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all outline-none">
                            <option value="">Select a cluster...</option>
                            {clusters.map(c => (
                                <option key={c.id} value={c.id}>{c.name} ({c.region})</option>
                            ))}
                        </select>
                    </div>

                    {/* Hibernation Strategy */}
                    <div>
                        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Hibernation Strategy</p>
                        <select value={window.strategy} onChange={e => onUpdate({ ...window, strategy: e.target.value })}
                            className="w-full text-sm border-2 border-gray-200 rounded-lg px-3 py-2 bg-white hover:border-blue-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all outline-none">
                            {STRATEGIES.map(s => (
                                <option key={s.value} value={s.value}>{s.label} ({s.wake}, {s.savings})</option>
                            ))}
                        </select>
                    </div>

                    {/* Days */}
                    <div>
                        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-2">Sleep on days</p>
                        <div className="flex gap-2 mb-2">
                            {DAYS.map((d, i) => (
                                <button key={d} onClick={() => toggleDay(i)}
                                    className={`w-9 h-9 rounded-full text-xs font-bold transition-all ${window.days.includes(i)
                                        ? "bg-slate-800 text-white scale-110 shadow-md"
                                        : "bg-slate-100 text-gray-400 hover:bg-slate-200"
                                        }`}>
                                    {d}
                                </button>
                            ))}
                        </div>
                        <div className="flex gap-2">
                            <button onClick={() => onUpdate({ ...window, days: [0, 1, 2, 3, 4] })} className="text-[10px] px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-600 font-medium">
                                Weekdays
                            </button>
                            <button onClick={() => onUpdate({ ...window, days: [5, 6] })} className="text-[10px] px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-600 font-medium">
                                Weekends
                            </button>
                            <button onClick={() => onUpdate({ ...window, days: [0, 1, 2, 3, 4, 5, 6] })} className="text-[10px] px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-600 font-medium">
                                All Days
                            </button>
                        </div>
                    </div>

                    {/* Time Configuration */}
                    <div>
                        <div className="flex items-center gap-2 mb-2">
                            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Sleep Window</p>
                            {crossesMidnight && (
                                <span className="text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded font-bold">Overnight (+1 day)</span>
                            )}
                        </div>

                        <label className="flex items-center gap-2 mb-3 cursor-pointer w-fit">
                            <div className={`w-9 h-5 rounded-full relative transition-colors ${isFullDay ? 'bg-slate-800' : 'bg-gray-200'}`}
                                onClick={() => onUpdate({ ...window, sleepHour: isFullDay ? 21 : 0, wakeHour: isFullDay ? 9 : 24 })}>
                                <div className={`w-4 h-4 bg-white rounded-full absolute top-0.5 transition-all ${isFullDay ? 'left-[18px]' : 'left-0.5'}`} />
                            </div>
                            <span className="text-xs font-medium text-gray-600">Full day hibernation</span>
                        </label>

                        {!isFullDay && (
                            <div className="flex items-center gap-3">
                                <div className="flex flex-col gap-1">
                                    <span className="text-[10px] font-bold text-gray-400 uppercase">Sleep At</span>
                                    <select value={window.sleepHour} onChange={e => onUpdate({ ...window, sleepHour: Number(e.target.value) })}
                                        className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white hover:border-blue-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all outline-none">
                                        {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{fmt(h)}</option>)}
                                    </select>
                                </div>
                                <span className="text-gray-300 text-xl pt-4">→</span>
                                <div className="flex flex-col gap-1">
                                    <span className="text-[10px] font-bold text-gray-400 uppercase">Wake At</span>
                                    <select value={window.wakeHour} onChange={e => onUpdate({ ...window, wakeHour: Number(e.target.value) })}
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

export default function HibernationScheduler({ embedded = false }) {
    const navigate = useNavigate();

    // Clusters
    const [clusters, setClusters] = useState([]);

    // Saved schedules list
    const [savedSchedules, setSavedSchedules] = useState([]);
    const [loadingSchedules, setLoadingSchedules] = useState(false);

    // Window creation/editing
    const [windows, setWindows] = useState([
        {
            id: "w1",
            label: "New Window",
            clusterId: null,
            strategy: "NAMESPACE_SLEEP",
            days: [],
            sleepHour: 21,
            wakeHour: 9,
            colorIdx: 0
        }
    ]);

    // Global settings
    const [timezone, setTimezone] = useState("UTC");
    const [preWarmMinutes, setPreWarmMinutes] = useState(15);

    // UI state
    const [saving, setSaving] = useState(false);
    const [editingScheduleId, setEditingScheduleId] = useState(null);
    const [selectedScheduleIds, setSelectedScheduleIds] = useState([]);

    const pollRef = useRef(null);

    // Load clusters on mount
    useEffect(() => {
        fetchClusters();
        fetchSavedSchedules();

        // Poll for schedule status updates
        pollRef.current = setInterval(fetchSavedSchedules, 10000);
        return () => clearInterval(pollRef.current);
    }, []);

    const fetchClusters = async () => {
        try {
            const res = await clusterAPI.list({});
            const list = res.data?.clusters || res.data || [];
            setClusters(list);
        } catch (err) {
            toast.error("Failed to load clusters");
        }
    };

    const fetchSavedSchedules = async () => {
        setLoadingSchedules(true);
        try {
            const res = await hibernationAPI.list({});
            const schedules = res.data?.schedules || [];
            setSavedSchedules(schedules);
        } catch (err) {
            console.error("Failed to load schedules:", err);
        } finally {
            setLoadingSchedules(false);
        }
    };

    const updateWindow = useCallback((id, updates) => {
        setWindows(prev => prev.map(w => w.id === id ? { ...w, ...updates } : w));
    }, []);

    const deleteWindow = useCallback(id => {
        setWindows(prev => prev.filter(w => w.id !== id));
    }, []);

    const addWindow = () => {
        setWindows(prev => [
            ...prev,
            {
                id: `w${Date.now()}`,
                label: "New Window",
                clusterId: null,
                strategy: "NAMESPACE_SLEEP",
                days: [],
                sleepHour: 21,
                wakeHour: 9,
                colorIdx: prev.length % PALETTE.length
            }
        ]);
    };

    const handleSaveSchedule = async () => {
        // Validate windows
        const validWindows = windows.filter(w => w.clusterId && w.days.length > 0);

        if (validWindows.length === 0) {
            toast.error("Please add at least one valid window with a cluster and days selected");
            return;
        }

        setSaving(true);
        try {
            // Save each window as a separate schedule
            for (const window of validWindows) {
                const matrix = windowToMatrix(window);
                const payload = {
                    cluster_id: window.clusterId,
                    schedule_type: "WEEKLY",
                    schedule_matrix: matrix,
                    timezone,
                    pre_warm_minutes: preWarmMinutes,
                    strategy: window.strategy,
                    is_active: false, // Start as planned (yellow)
                };

                if (editingScheduleId) {
                    await hibernationAPI.update(editingScheduleId, payload);
                } else {
                    await hibernationAPI.create(payload);
                }
            }

            // Clear windows and refresh list
            setWindows([{
                id: "w1",
                label: "New Window",
                clusterId: null,
                strategy: "NAMESPACE_SLEEP",
                days: [],
                sleepHour: 21,
                wakeHour: 9,
                colorIdx: 0
            }]);
            setEditingScheduleId(null);

            await fetchSavedSchedules();
            toast.success(editingScheduleId ? "Schedule updated!" : `${validWindows.length} schedule(s) created!`);
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Failed to save schedules");
        } finally {
            setSaving(false);
        }
    };

    const handleStartSelectedSchedules = async () => {
        if (selectedScheduleIds.length === 0) {
            toast.error("Please select at least one schedule");
            return;
        }

        try {
            for (const schedId of selectedScheduleIds) {
                const schedule = savedSchedules.find(s => s.id === schedId);
                if (schedule && !schedule.is_active) {
                    await hibernationAPI.toggle(schedId);
                }
            }
            await fetchSavedSchedules();
            setSelectedScheduleIds([]);
            toast.success(`${selectedScheduleIds.length} schedule(s) started!`);
        } catch (err) {
            toast.error("Failed to start schedules");
        }
    };

    const handleEditSchedule = async (schedule) => {
        // For now, just allow editing the first window
        setEditingScheduleId(schedule.id);

        const matrix = Array.isArray(schedule.schedule_matrix)
            ? schedule.schedule_matrix
            : String(schedule.schedule_matrix).split("").map(Number);

        // Find sleep hours from matrix
        const firstDay = matrix.slice(0, 24);
        const sleepStart = firstDay.findIndex(v => v === 0);
        const sleepEnd = firstDay.lastIndexOf(0) + 1;
        const days = [];
        for (let d = 0; d < 7; d++) {
            if (matrix.slice(d * 24, (d + 1) * 24).some(v => v === 0)) {
                days.push(d);
            }
        }

        setWindows([{
            id: "w1",
            label: "Editing Schedule",
            clusterId: schedule.cluster_id,
            strategy: schedule.strategy,
            days,
            sleepHour: sleepStart >= 0 ? sleepStart : 21,
            wakeHour: sleepEnd > sleepStart ? sleepEnd : 9,
            colorIdx: 0
        }]);

        setTimezone(schedule.timezone || "UTC");
        setPreWarmMinutes(schedule.pre_warm_minutes ?? 15);

        toast.info("Editing schedule - modify and save again");
    };

    const handleDeleteSchedule = async (scheduleId) => {
        if (!window.confirm("Are you sure you want to delete this schedule?")) return;

        try {
            await hibernationAPI.delete(scheduleId);
            await fetchSavedSchedules();
            toast.success("Schedule deleted");
        } catch (err) {
            toast.error("Failed to delete schedule");
        }
    };

    const handleToggleSchedule = async (scheduleId) => {
        try {
            await hibernationAPI.toggle(scheduleId);
            await fetchSavedSchedules();
        } catch (err) {
            toast.error("Failed to toggle schedule");
        }
    };

    const getScheduleStatus = (schedule) => {
        if (schedule.is_active) {
            return { label: "Started", dot: "bg-green-500", text: "text-green-700" };
        }
        return { label: "Planned", dot: "bg-yellow-500", text: "text-yellow-700" };
    };

    const toggleScheduleSelection = (scheduleId) => {
        setSelectedScheduleIds(prev =>
            prev.includes(scheduleId)
                ? prev.filter(id => id !== scheduleId)
                : [...prev, scheduleId]
        );
    };

    return (
        <div className={`min-h-screen bg-slate-50 font-sans ${embedded ? 'p-0' : 'p-6'}`}>
            <div className="max-w-7xl mx-auto">

                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                    <div>
                        {!embedded && (
                            <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-xs text-gray-400 font-bold uppercase tracking-wider mb-2 hover:text-blue-600 transition-colors">
                                <FiArrowLeft /> Back
                            </button>
                        )}
                        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Hibernation Schedules</h1>
                        <p className="text-gray-500 mt-1">Configure when your clusters should sleep to save costs</p>
                    </div>
                </div>

                {/* SAVED SCHEDULES LIST - AT TOP */}
                <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-8">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <h2 className="text-lg font-bold text-gray-900">Saved Schedules</h2>
                            {savedSchedules.length > 0 && (
                                <span className="text-sm bg-blue-100 text-blue-700 px-3 py-1 rounded-full font-bold">
                                    {savedSchedules.length} {savedSchedules.length === 1 ? 'schedule' : 'schedules'} planned
                                </span>
                            )}
                        </div>

                        {selectedScheduleIds.length > 0 && (
                            <button onClick={handleStartSelectedSchedules}
                                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-bold text-sm transition-all">
                                <FiPlay /> Start Selected ({selectedScheduleIds.length})
                            </button>
                        )}
                    </div>

                    {loadingSchedules ? (
                        <div className="p-12 text-center text-gray-400">Loading schedules...</div>
                    ) : savedSchedules.length === 0 ? (
                        <div className="p-12 text-center text-gray-400">
                            <p className="mb-2 font-medium">No schedules created yet</p>
                            <p className="text-xs">Create your first schedule below</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {savedSchedules.map((schedule) => {
                                const status = getScheduleStatus(schedule);
                                const cluster = clusters.find(c => c.id === schedule.cluster_id);
                                const strategy = STRATEGIES.find(s => s.value === schedule.strategy);

                                return (
                                    <div key={schedule.id}
                                        className="flex items-center gap-4 p-4 border border-gray-200 rounded-lg hover:border-gray-300 transition-all">
                                        <input type="checkbox"
                                            checked={selectedScheduleIds.includes(schedule.id)}
                                            onChange={() => toggleScheduleSelection(schedule.id)}
                                            className="w-4 h-4 rounded border-gray-300" />

                                        <div className={`w-2 h-2 rounded-full ${status.dot}`} />

                                        <div className="flex-1">
                                            <div className="flex items-center gap-3 mb-1">
                                                <span className="font-bold text-sm text-gray-900">
                                                    {cluster?.name || 'Unknown Cluster'}
                                                </span>
                                                <span className="text-xs text-gray-500">
                                                    {strategy?.label} ({strategy?.savings})
                                                </span>
                                                <span className={`text-xs font-bold px-2 py-0.5 rounded ${status.text} bg-${status.dot.replace('bg-', '')}-100`}>
                                                    {status.label}
                                                </span>
                                            </div>
                                            <div className="text-xs text-gray-500">
                                                Timezone: {schedule.timezone} • Pre-warm: {schedule.pre_warm_minutes}min
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-2">
                                            <button onClick={() => handleToggleSchedule(schedule.id)}
                                                className="p-2 hover:bg-gray-100 rounded-lg transition-colors" title={schedule.is_active ? "Pause" : "Resume"}>
                                                {schedule.is_active ? <FiPause className="text-amber-600" /> : <FiPlay className="text-green-600" />}
                                            </button>
                                            <button onClick={() => handleEditSchedule(schedule)}
                                                className="p-2 hover:bg-gray-100 rounded-lg transition-colors" title="Edit">
                                                <FiEdit2 className="text-blue-600" />
                                            </button>
                                            <button onClick={() => handleDeleteSchedule(schedule.id)}
                                                className="p-2 hover:bg-gray-100 rounded-lg transition-colors" title="Delete">
                                                <FiTrash2 className="text-red-600" />
                                            </button>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* WINDOW CREATION - BELOW */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    {/* LEFT: Windows */}
                    <div className="lg:col-span-2 space-y-4">
                        <h2 className="text-lg font-bold text-gray-900">
                            {editingScheduleId ? 'Edit Schedule' : 'Create New Schedule'}
                        </h2>

                        {/* Windows List */}
                        <div className="space-y-4">
                            {windows.map((window, i) => (
                                <WindowCard
                                    key={window.id}
                                    window={window}
                                    palette={PALETTE[window.colorIdx ?? (i % PALETTE.length)]}
                                    clusters={clusters}
                                    onUpdate={(updated) => updateWindow(window.id, updated)}
                                    onDelete={deleteWindow}
                                    isOnly={windows.length === 1}
                                />
                            ))}
                        </div>

                        <button onClick={addWindow}
                            className="w-full border-2 border-dashed border-gray-300 rounded-xl p-4 text-gray-400 font-bold hover:border-blue-400 hover:text-blue-500 hover:bg-blue-50 transition-all flex items-center justify-center gap-2">
                            <FiPlus /> Add Another Window
                        </button>
                    </div>

                    {/* RIGHT: Global Settings & Save */}
                    <div className="space-y-6">
                        {/* Global Settings */}
                        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                            <p className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">Global Settings</p>

                            <div className="space-y-4">
                                <div>
                                    <p className="text-xs font-bold text-gray-500 mb-2">Timezone</p>
                                    <select value={timezone} onChange={e => setTimezone(e.target.value)}
                                        className="w-full text-sm border-2 border-gray-200 rounded-lg p-2 bg-white outline-none focus:border-blue-400 transition-all">
                                        <option value="UTC">UTC</option>
                                        <option value="America/New_York">America/New_York</option>
                                        <option value="America/Los_Angeles">America/Los_Angeles</option>
                                        <option value="Europe/London">Europe/London</option>
                                        <option value="Asia/Tokyo">Asia/Tokyo</option>
                                    </select>
                                </div>

                                <div>
                                    <p className="text-xs font-bold text-gray-500 mb-2">Pre-warm (minutes)</p>
                                    <input type="number" value={preWarmMinutes} onChange={e => setPreWarmMinutes(Number(e.target.value))}
                                        min="0" max="60"
                                        className="w-full text-sm border-2 border-gray-200 rounded-lg p-2 bg-white outline-none focus:border-blue-400 transition-all" />
                                    <p className="text-xs text-gray-400 mt-1">Applies to all clusters (0-60)</p>
                                </div>
                            </div>
                        </div>

                        {/* Save Button */}
                        <button onClick={handleSaveSchedule} disabled={saving}
                            className={`w-full py-4 rounded-xl font-bold text-white text-base shadow-lg transition-all flex items-center justify-center gap-2
                                ${saving ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-blue-200'}
                            `}>
                            {saving ? (
                                <>
                                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                    Saving...
                                </>
                            ) : (
                                <>
                                    <FiSave /> {editingScheduleId ? 'Update Schedule' : 'Save Schedule'}
                                </>
                            )}
                        </button>

                        {editingScheduleId && (
                            <button onClick={() => {
                                setEditingScheduleId(null);
                                setWindows([{
                                    id: "w1",
                                    label: "New Window",
                                    clusterId: null,
                                    strategy: "NAMESPACE_SLEEP",
                                    days: [],
                                    sleepHour: 21,
                                    wakeHour: 9,
                                    colorIdx: 0
                                }]);
                            }}
                                className="w-full py-3 rounded-lg border-2 border-gray-300 text-gray-600 font-bold hover:bg-gray-50 transition-all">
                                Cancel Editing
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
