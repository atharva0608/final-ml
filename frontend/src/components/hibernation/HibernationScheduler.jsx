/**
 * HibernationScheduler - Consolidated scheduling interface
 *
 * Replaces: ScheduleTemplates, UnifiedScheduleGrid, TimeBasedRules, MultiTimezone
 *
 * Contains:
 * 1. Monthly calendar for selecting hibernation days
 * 2. Start/end time + warm-up inputs
 * 3. "Schedule Hibernation" button
 * 4. List of scheduled hibernation jobs
 */
import React, { useState } from 'react';
import { useHibernationStore } from '../../store/useHibernationStore';
import { Card } from '../shared';
import { FiCalendar, FiClock, FiPlus, FiTrash2, FiZap, FiSun, FiMoon } from 'react-icons/fi';
import toast from 'react-hot-toast';

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAY_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

const HibernationScheduler = () => {
    const { hibernationJobs, addHibernationJob, removeHibernationJob } = useHibernationStore();

    // Local form state
    const [selectedDays, setSelectedDays] = useState(new Set());
    const [startTime, setStartTime] = useState('20:00');
    const [endTime, setEndTime] = useState('08:00');
    const [warmupMinutes, setWarmupMinutes] = useState(15);
    const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
    const [currentYear, setCurrentYear] = useState(new Date().getFullYear());

    // Calendar helpers
    const getDaysInMonth = (month, year) => new Date(year, month + 1, 0).getDate();
    const getFirstDayOfMonth = (month, year) => new Date(year, month, 1).getDay();

    const daysInMonth = getDaysInMonth(currentMonth, currentYear);
    const firstDay = getFirstDayOfMonth(currentMonth, currentYear);

    const toggleDay = (day) => {
        const key = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        setSelectedDays(prev => {
            const next = new Set(prev);
            if (next.has(key)) {
                next.delete(key);
            } else {
                next.add(key);
            }
            return next;
        });
    };

    const selectWeekdays = () => {
        const newSet = new Set(selectedDays);
        for (let d = 1; d <= daysInMonth; d++) {
            const dayOfWeek = new Date(currentYear, currentMonth, d).getDay();
            const key = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
            if (dayOfWeek >= 1 && dayOfWeek <= 5) {
                newSet.add(key);
            }
        }
        setSelectedDays(newSet);
    };

    const selectWeekends = () => {
        const newSet = new Set(selectedDays);
        for (let d = 1; d <= daysInMonth; d++) {
            const dayOfWeek = new Date(currentYear, currentMonth, d).getDay();
            const key = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
            if (dayOfWeek === 0 || dayOfWeek === 6) {
                newSet.add(key);
            }
        }
        setSelectedDays(newSet);
    };

    const selectAllDays = () => {
        const newSet = new Set(selectedDays);
        for (let d = 1; d <= daysInMonth; d++) {
            const key = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
            newSet.add(key);
        }
        setSelectedDays(newSet);
    };

    const clearSelection = () => {
        setSelectedDays(new Set());
    };

    const handleSchedule = () => {
        if (selectedDays.size === 0) {
            toast.error('Please select at least one day');
            return;
        }
        if (!startTime || !endTime) {
            toast.error('Please set start and end times');
            return;
        }

        const job = {
            days: Array.from(selectedDays).sort(),
            startTime,
            endTime,
            warmupMinutes: parseInt(warmupMinutes) || 0,
        };

        addHibernationJob(job);
        toast.success(`Hibernation scheduled for ${selectedDays.size} day(s)`);
        setSelectedDays(new Set());
    };

    const navigateMonth = (delta) => {
        let newMonth = currentMonth + delta;
        let newYear = currentYear;
        if (newMonth < 0) { newMonth = 11; newYear--; }
        if (newMonth > 11) { newMonth = 0; newYear++; }
        setCurrentMonth(newMonth);
        setCurrentYear(newYear);
    };

    const formatJobDays = (days) => {
        if (days.length <= 3) return days.map(d => d.split('-').slice(1).join('/')).join(', ');
        return `${days.length} days selected`;
    };

    return (
        <div className="space-y-6">
            {/* Scheduler Card */}
            <Card className="border-gray-200">
                <div className="flex items-center gap-2 mb-5">
                    <FiCalendar className="w-5 h-5 text-blue-600" />
                    <h3 className="text-lg font-semibold text-gray-900">Schedule Hibernation</h3>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* LEFT: Monthly Calendar */}
                    <div>
                        {/* Month Navigation */}
                        <div className="flex items-center justify-between mb-4">
                            <button
                                onClick={() => navigateMonth(-1)}
                                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
                            </button>
                            <h4 className="font-semibold text-gray-900">
                                {MONTH_NAMES[currentMonth]} {currentYear}
                            </h4>
                            <button
                                onClick={() => navigateMonth(1)}
                                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
                            </button>
                        </div>

                        {/* Day Labels */}
                        <div className="grid grid-cols-7 gap-1 mb-1">
                            {DAY_LABELS.map((label, i) => (
                                <div key={i} className="text-center text-xs font-medium text-gray-400 py-1">{label}</div>
                            ))}
                        </div>

                        {/* Calendar Grid */}
                        <div className="grid grid-cols-7 gap-1">
                            {/* Empty cells for offset */}
                            {Array.from({ length: firstDay }, (_, i) => (
                                <div key={`empty-${i}`} className="h-10" />
                            ))}
                            {/* Day cells */}
                            {Array.from({ length: daysInMonth }, (_, i) => {
                                const day = i + 1;
                                const key = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                                const isSelected = selectedDays.has(key);
                                const isToday = new Date().getDate() === day && new Date().getMonth() === currentMonth && new Date().getFullYear() === currentYear;

                                return (
                                    <button
                                        key={day}
                                        onClick={() => toggleDay(day)}
                                        className={`h-10 rounded-lg text-sm font-medium transition-all border ${isSelected
                                                ? 'bg-blue-600 text-white border-blue-700 shadow-sm'
                                                : isToday
                                                    ? 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100'
                                                    : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50 hover:border-gray-300'
                                            }`}
                                    >
                                        {day}
                                    </button>
                                );
                            })}
                        </div>

                        {/* Quick Select Buttons */}
                        <div className="flex gap-2 mt-3 flex-wrap">
                            <button onClick={selectWeekdays} className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors font-medium">
                                Weekdays
                            </button>
                            <button onClick={selectWeekends} className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors font-medium">
                                Weekends
                            </button>
                            <button onClick={selectAllDays} className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors font-medium">
                                All Days
                            </button>
                            <button onClick={clearSelection} className="text-xs px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg transition-colors font-medium">
                                Clear
                            </button>
                        </div>

                        {selectedDays.size > 0 && (
                            <p className="text-xs text-gray-500 mt-2">
                                <span className="font-semibold text-gray-700">{selectedDays.size}</span> day(s) selected
                            </p>
                        )}
                    </div>

                    {/* RIGHT: Time Configuration + Schedule Button */}
                    <div className="space-y-5">
                        {/* Hibernation Window */}
                        <div>
                            <label className="text-xs font-bold text-gray-500 uppercase tracking-wider block mb-3">Hibernation Window</label>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1.5">
                                        <FiMoon className="w-3.5 h-3.5 text-indigo-500" /> Start Time
                                    </label>
                                    <input
                                        type="time"
                                        value={startTime}
                                        onChange={(e) => setStartTime(e.target.value)}
                                        className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm bg-white"
                                    />
                                    <p className="text-[10px] text-gray-400 mt-1">Cluster enters sleep</p>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1.5 flex items-center gap-1.5">
                                        <FiSun className="w-3.5 h-3.5 text-yellow-500" /> End Time
                                    </label>
                                    <input
                                        type="time"
                                        value={endTime}
                                        onChange={(e) => setEndTime(e.target.value)}
                                        className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm bg-white"
                                    />
                                    <p className="text-[10px] text-gray-400 mt-1">Cluster wakes up</p>
                                </div>
                            </div>
                        </div>

                        {/* Warm-up Period */}
                        <div>
                            <label className="text-xs font-bold text-gray-500 uppercase tracking-wider block mb-3">Warm-Up Period</label>
                            <div className="flex items-center gap-3">
                                <input
                                    type="number"
                                    value={warmupMinutes}
                                    onChange={(e) => setWarmupMinutes(e.target.value)}
                                    min="0"
                                    max="60"
                                    className="w-24 px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm bg-white"
                                />
                                <span className="text-sm text-gray-600">minutes before end time</span>
                            </div>
                            <p className="text-[10px] text-gray-400 mt-1.5">Pre-warm the cluster before the scheduled wake-up to minimize boot time.</p>
                        </div>

                        {/* Duration Preview */}
                        {startTime && endTime && (
                            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                                <div className="flex items-center gap-2 text-blue-800 text-sm">
                                    <FiClock className="w-4 h-4" />
                                    <span className="font-medium">
                                        Sleep: {startTime} → Wake: {endTime}
                                        {warmupMinutes > 0 && ` (warm-up at ${(() => {
                                            const [h, m] = endTime.split(':').map(Number);
                                            const totalMin = h * 60 + m - parseInt(warmupMinutes);
                                            const wh = Math.floor(((totalMin % 1440) + 1440) % 1440 / 60);
                                            const wm = ((totalMin % 1440) + 1440) % 1440 % 60;
                                            return `${String(wh).padStart(2, '0')}:${String(wm).padStart(2, '0')}`;
                                        })()})`}
                                    </span>
                                </div>
                            </div>
                        )}

                        {/* Schedule Button */}
                        <button
                            onClick={handleSchedule}
                            disabled={selectedDays.size === 0}
                            className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-semibold text-sm transition-all ${selectedDays.size > 0
                                    ? 'bg-blue-600 hover:bg-blue-700 text-white shadow-sm'
                                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                }`}
                        >
                            <FiPlus className="w-4 h-4" />
                            Schedule Hibernation
                        </button>
                    </div>
                </div>
            </Card>

            {/* Scheduled Jobs List */}
            <Card className="border-gray-200">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <FiZap className="w-5 h-5 text-purple-600" />
                        <h3 className="text-lg font-semibold text-gray-900">Scheduled Jobs</h3>
                    </div>
                    <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full font-medium">
                        {hibernationJobs.length} job{hibernationJobs.length !== 1 ? 's' : ''}
                    </span>
                </div>

                {hibernationJobs.length === 0 ? (
                    <div className="text-center py-8 border-2 border-dashed border-gray-200 rounded-xl">
                        <FiCalendar className="w-8 h-8 text-gray-300 mx-auto mb-3" />
                        <p className="text-gray-500 text-sm font-medium">No hibernation jobs scheduled</p>
                        <p className="text-gray-400 text-xs mt-1">Select days and times above to create a schedule</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {hibernationJobs.map((job) => (
                            <div
                                key={job.id}
                                className="flex items-center justify-between p-4 bg-gray-50 rounded-xl border border-gray-200 hover:shadow-sm transition-all group"
                            >
                                <div className="flex items-center gap-4">
                                    <div className="p-2.5 bg-white rounded-lg border border-gray-200 shadow-sm">
                                        <FiMoon className="w-5 h-5 text-indigo-500" />
                                    </div>
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <p className="font-semibold text-gray-900 text-sm">
                                                {job.startTime} → {job.endTime}
                                            </p>
                                            {job.warmupMinutes > 0 && (
                                                <span className="text-[10px] bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded border border-yellow-200 font-medium">
                                                    {job.warmupMinutes}min warm-up
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-xs text-gray-500 mt-0.5">
                                            {formatJobDays(job.days)}
                                        </p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => {
                                        removeHibernationJob(job.id);
                                        toast.success('Job removed');
                                    }}
                                    className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                                    title="Remove job"
                                >
                                    <FiTrash2 className="w-4 h-4" />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </Card>
        </div>
    );
};

export default HibernationScheduler;
