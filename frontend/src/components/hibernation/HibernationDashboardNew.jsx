import React, { useState, useEffect } from 'react';
import {
  FiMoon, FiSun, FiZap, FiShield, FiAlertCircle, FiPlay, FiPause,
  FiEdit, FiTrash, FiPlus, FiClock, FiCheck, FiChevronDown, FiServer,
  FiTrendingUp, FiDownload, FiMail, FiBarChart2, FiX, FiList
} from 'react-icons/fi';
import { hibernationApi } from '../../services/hibernationApi';
import api from '../../services/api';
import ScheduleMatrix from './ScheduleMatrix';
import AuditHistory from './AuditHistory';

// ==================== CONSTANTS ====================

const STRATEGIES = [
  {
    id: 'NAMESPACE_SLEEP',
    label: 'Namespace Sleep',
    icon: FiMoon,
    color: '#6366f1',
    bg: 'rgba(99,102,241,0.08)',
    border: 'rgba(99,102,241,0.25)',
    wakeTime: '~2 min',
    savings: '80%',
    risk: 'LOW',
    desc: 'Scales workloads to 0 replicas. Best for stateless apps.'
  },
  {
    id: 'NUCLEAR',
    label: 'Nuclear',
    icon: FiZap,
    color: '#ef4444',
    bg: 'rgba(239,68,68,0.08)',
    border: 'rgba(239,68,68,0.25)',
    wakeTime: '~8 min',
    savings: '99%',
    risk: 'MEDIUM',
    desc: 'Scales ASGs to 0 directly. Maximum cost reduction.'
  },
  {
    id: 'SNAPSHOT_RESTORE',
    label: 'Snapshot & Restore',
    icon: FiShield,
    color: '#22c55e',
    bg: 'rgba(34,197,94,0.08)',
    border: 'rgba(34,197,94,0.25)',
    wakeTime: '~12 min',
    savings: '90%',
    risk: 'LOWEST',
    desc: 'Creates EBS snapshots before sleep. For stateful workloads.'
  },
];

const TIMEZONES = [
  'UTC', 'America/New_York', 'America/Chicago', 'America/Denver',
  'America/Los_Angeles', 'Europe/London', 'Europe/Paris', 'Asia/Tokyo', 'Asia/Kolkata'
];

// ==================== HELPER FUNCTIONS ====================

const getStrategyMeta = (id) => STRATEGIES.find(s => s.id === id) || STRATEGIES[0];

const calculateStats = (schedules) => {
  let totalSleepHours = 0;
  const activeSchedules = schedules.filter(s => s.is_active === 'Y');

  activeSchedules.forEach(s => {
    const sleepHours = (s.schedule_matrix?.match(/1/g) || []).length;
    totalSleepHours += sleepHours;
  });

  // Clamp to max 168 hours
  totalSleepHours = Math.min(totalSleepHours, 168);

  return {
    sleepHours: totalSleepHours,
    awakeHours: 168 - totalSleepHours,
    savings: Math.round((totalSleepHours / 168) * 100),
    activeCount: activeSchedules.length,
    pausedCount: schedules.length - activeSchedules.length,
    monthlySaved: activeSchedules.length * 1500 // Estimate
  };
};

// ==================== SUB-COMPONENTS ====================

// Live Progress Banner
const LiveProgressBanner = ({ onDismiss }) => {
  const [progress, setProgress] = useState(65);
  const [elapsed, setElapsed] = useState(134);
  const [step, setStep] = useState(18);
  const total = 23;

  useEffect(() => {
    const interval = setInterval(() => {
      setProgress(p => Math.min(p + 0.35, 99));
      setElapsed(e => e + 1);
      setStep(s => Math.min(s + 0.04, total - 0.01));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  const remaining = Math.max(0, Math.round(((100 - progress) / progress) * elapsed));
  const pct = Math.round(progress);

  return (
    <div className="bg-gradient-to-r from-indigo-900 to-purple-900 border-b border-indigo-700 px-8 py-3 flex items-center gap-4">
      <div className="flex items-center gap-2 flex-shrink-0">
        <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></div>
        <span className="text-xs font-bold text-indigo-200 uppercase tracking-wide">
          Hibernation In Progress
        </span>
      </div>
      <div className="w-px h-4 bg-indigo-600"></div>
      <div className="text-sm text-indigo-200">
        <span className="font-bold text-white">Weekend Shutdown</span>
        {' · '}Scaling deployments to 0 replicas ({Math.floor(step)}/{total})
      </div>
      <div className="flex-1 bg-indigo-800/40 rounded-full h-1.5 min-w-[100px]">
        <div
          className="h-full bg-gradient-to-r from-indigo-400 to-cyan-400 rounded-full transition-all duration-1000"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-sm font-bold text-white flex-shrink-0">{pct}%</span>
      <span className="text-xs text-indigo-300 flex-shrink-0">
        {formatTime(elapsed)} · ~{formatTime(remaining)} left
      </span>
      <button className="px-3 py-1 bg-indigo-700/50 hover:bg-indigo-700 border border-indigo-600 rounded-md text-xs font-medium text-indigo-200 transition-colors">
        View Logs
      </button>
      <button
        onClick={onDismiss}
        className="px-3 py-1 bg-red-900/50 hover:bg-red-900 border border-red-700 rounded-md text-xs font-medium text-red-200 transition-colors"
      >
        <FiX size={12} className="inline mr-1" />
        Cancel
      </button>
    </div>
  );
};

// Savings Report
const SavingsReport = ({ schedules }) => {
  const activeSchedules = schedules.filter(s => s.is_active === 'Y');
  const totalSaved = activeSchedules.length * 1500; // Estimate per schedule
  const projectedAnnual = totalSaved * 12;

  // Mock trend data (last 6 months)
  const trendData = [
    { month: 'Sep', value: 2100 },
    { month: 'Oct', value: 2800 },
    { month: 'Nov', value: 3200 },
    { month: 'Dec', value: 3900 },
    { month: 'Jan', value: 4400 },
    { month: 'Feb', value: totalSaved }
  ];

  const maxValue = Math.max(...trendData.map(d => d.value));

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-200 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <FiTrendingUp size={18} className="text-gray-900" />
          <span className="text-sm font-bold uppercase tracking-wide text-gray-900">
            SAVINGS REPORT
          </span>
        </div>
        <span className="text-sm font-semibold text-green-600">
          Feb 2026
        </span>
      </div>

      {/* Top KPIs */}
      <div className="grid grid-cols-2 border-b border-gray-200">
        <div className="p-4 border-r border-gray-200">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Saved This Month
          </div>
          <div className="text-2xl font-extrabold text-green-600 tracking-tight">
            ${totalSaved.toLocaleString()}
          </div>
          <div className="text-xs text-gray-500 mt-1">42% less than baseline</div>
        </div>
        <div className="p-4">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
            Projected Annual
          </div>
          <div className="text-2xl font-extrabold text-indigo-600 tracking-tight">
            ~${Math.round(projectedAnnual / 1000)}K
          </div>
          <div className="text-xs text-gray-500 mt-1">at current rate</div>
        </div>
      </div>

      {/* Trend Chart - Line Chart with filled area */}
      <div className="p-5">
        <div className="text-sm font-semibold text-gray-700 mb-4">
          Savings Trend — Last 6 Months
        </div>
        <div className="relative h-32">
          {/* Chart area */}
          <svg className="w-full h-full" viewBox="0 0 600 120" preserveAspectRatio="none">
            {/* Filled area gradient */}
            <defs>
              <linearGradient id="savingsGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style={{ stopColor: '#22c55e', stopOpacity: 0.3 }} />
                <stop offset="100%" style={{ stopColor: '#22c55e', stopOpacity: 0.05 }} />
              </linearGradient>
            </defs>

            {/* Generate path for filled area */}
            <path
              d={`M 0,${120 - (trendData[0].value / maxValue) * 110} ${trendData.map((d, i) => {
                const x = (i / (trendData.length - 1)) * 600;
                const y = 120 - (d.value / maxValue) * 110;
                return `L ${x},${y}`;
              }).join(' ')} L 600,120 L 0,120 Z`}
              fill="url(#savingsGradient)"
            />

            {/* Green line */}
            <polyline
              points={trendData.map((d, i) => {
                const x = (i / (trendData.length - 1)) * 600;
                const y = 120 - (d.value / maxValue) * 110;
                return `${x},${y}`;
              }).join(' ')}
              fill="none"
              stroke="#22c55e"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Data points (dots) */}
            {trendData.map((d, i) => {
              const x = (i / (trendData.length - 1)) * 600;
              const y = 120 - (d.value / maxValue) * 110;
              return (
                <circle
                  key={i}
                  cx={x}
                  cy={y}
                  r="5"
                  fill="#22c55e"
                  stroke="white"
                  strokeWidth="2"
                />
              );
            })}
          </svg>

          {/* Month labels */}
          <div className="absolute -bottom-6 left-0 right-0 flex justify-between px-1">
            {trendData.map((d, i) => (
              <span key={i} className="text-xs text-gray-500">
                {d.month}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Per-schedule Breakdown */}
      <div className="px-4 pb-4">
        <div className="text-xs font-semibold text-gray-600 mb-3">
          Breakdown by Schedule
        </div>
        <div className="space-y-3">
          {activeSchedules.length === 0 ? (
            <div className="text-sm text-gray-400 text-center py-2">
              No active schedules
            </div>
          ) : (
            activeSchedules.map((s, idx) => {
              const st = getStrategyMeta(s.strategy);
              const savings = 1500; // Per schedule estimate
              const pct = totalSaved > 0 ? Math.round((savings / totalSaved) * 100) : 0;
              return (
                <div key={s.id}>
                  <div className="flex justify-between items-center mb-1">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2 h-2 rounded-sm"
                        style={{ background: st.color }}
                      />
                      <span className="text-sm font-medium text-gray-700">
                        {s.name}
                      </span>
                    </div>
                    <span className="text-sm font-bold text-gray-900">
                      ${savings.toLocaleString()}
                      <span className="text-xs font-normal text-gray-500 ml-1">
                        /mo ({pct}%)
                      </span>
                    </span>
                  </div>
                  <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ background: st.color, width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Footer Actions */}
      <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 flex gap-3">
        {[
          { icon: <FiDownload size={14} />, label: 'Export' },
          { icon: <FiMail size={14} />, label: 'Email Team' },
          { icon: <FiBarChart2 size={14} />, label: 'Detailed View' }
        ].map((action, idx) => (
          <button
            key={idx}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all"
          >
            {action.icon}
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
};

// KPI Card
const KPICard = ({ label, value, sub, color = '#0f172a', accent }) => (
  <div className="bg-white border border-gray-200 rounded-xl p-5" style={{ borderTop: `3px solid ${accent || '#e2e8f0'}` }}>
    <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">{label}</div>
    <div className="text-3xl font-extrabold tracking-tight" style={{ color }}>{value}</div>
    <div className="text-xs text-gray-500 mt-1">{sub}</div>
  </div>
);

// Strategy Selector
const StrategySelector = ({ value, onChange }) => (
  <div className="space-y-2">
    {STRATEGIES.map(st => {
      const Icon = st.icon;
      const isSelected = value === st.id;
      return (
        <button
          key={st.id}
          onClick={() => onChange(st.id)}
          className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-all text-left ${
            isSelected
              ? 'border-indigo-500 bg-indigo-50'
              : 'border-gray-200 bg-gray-50 hover:bg-gray-100'
          }`}
        >
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 border"
            style={{
              background: st.bg,
              color: st.color,
              borderColor: st.border
            }}
          >
            <Icon size={16} />
          </div>
          <div className="flex-1">
            <div className="flex justify-between items-center mb-1">
              <span className="text-sm font-semibold text-gray-900">{st.label}</span>
              <span className="text-xs font-bold" style={{ color: st.color }}>{st.savings}</span>
            </div>
            <div className="text-xs text-gray-600">Wake: {st.wakeTime} · Risk: {st.risk}</div>
          </div>
          {isSelected && <FiCheck size={16} className="text-indigo-600" />}
        </button>
      );
    })}
  </div>
);

// Schedule Form
const ScheduleForm = ({ initial, clusters, onSave, onCancel }) => {
  const blank = {
    name: '',
    description: '',
    strategy: 'NAMESPACE_SLEEP',
    cluster_ids: [],
    schedule_matrix: '0'.repeat(168),
    timezone: 'UTC',
    pre_warm_minutes: 15
  };

  const [form, setForm] = useState(initial || blank);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const toggleCluster = (id) => {
    set('cluster_ids', form.cluster_ids.includes(id)
      ? form.cluster_ids.filter(x => x !== id)
      : [...form.cluster_ids, id]
    );
  };

  const valid = form.name.trim() && form.cluster_ids.length > 0;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden mb-4">
      <div className="px-5 py-4 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-indigo-600"></div>
          <span className="text-xs font-bold uppercase tracking-wide text-gray-900">
            {initial ? 'Edit Schedule' : 'New Schedule'}
          </span>
        </div>
        <button
          onClick={onCancel}
          className="px-3 py-1 text-xs font-medium text-gray-600 hover:text-gray-800 bg-white border border-gray-300 rounded-md transition-colors"
        >
          Cancel
        </button>
      </div>

      <div className="p-5 space-y-4">
        {/* Name */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Schedule Name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="e.g. Business Hours Off"
            value={form.name}
            onChange={e => set('name', e.target.value)}
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">Description</label>
          <textarea
            className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Optional description..."
            rows={2}
            value={form.description || ''}
            onChange={e => set('description', e.target.value)}
          />
        </div>

        {/* Strategy */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">Hibernation Strategy</label>
          <StrategySelector value={form.strategy} onChange={v => set('strategy', v)} />
        </div>

        {/* Clusters */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Target Clusters <span className="text-red-500">*</span>
            {form.cluster_ids.length > 0 && (
              <span className="ml-2 text-indigo-600 font-normal">
                {form.cluster_ids.length} selected
              </span>
            )}
          </label>
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            {clusters.length === 0 ? (
              <div className="p-4 text-center text-sm text-gray-500">
                No clusters available
              </div>
            ) : (
              clusters.map((cluster, idx) => {
                const selected = form.cluster_ids.includes(cluster.id);
                return (
                  <label
                    key={cluster.id}
                    className={`flex items-center gap-3 p-3 cursor-pointer border-b last:border-b-0 transition-colors ${
                      selected ? 'bg-indigo-50' : 'bg-white hover:bg-gray-50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleCluster(cluster.id)}
                      className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-gray-900">{cluster.name}</span>
                        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                          cluster.status === 'ACTIVE'
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}>
                          {cluster.status === 'ACTIVE' ? 'Active' : cluster.status}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 mt-0.5">{cluster.region || 'N/A'}</div>
                    </div>
                    {selected && <FiCheck size={14} className="text-indigo-600" />}
                  </label>
                );
              })
            )}
          </div>
        </div>

        {/* Schedule Matrix */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Sleep Schedule (168-hour grid)
          </label>
          <ScheduleMatrix
            value={form.schedule_matrix}
            onChange={v => set('schedule_matrix', v)}
          />
        </div>

        {/* Timezone & Pre-warm */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Timezone</label>
            <div className="relative">
              <select
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg appearance-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={form.timezone}
                onChange={e => set('timezone', e.target.value)}
              >
                {TIMEZONES.map(tz => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
              <FiChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" size={14} />
            </div>
          </div>
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Pre-warm (minutes)</label>
            <input
              type="number"
              min={0}
              max={60}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={form.pre_warm_minutes}
              onChange={e => set('pre_warm_minutes', parseInt(e.target.value) || 0)}
            />
          </div>
        </div>

        {/* Save Button */}
        <button
          onClick={() => valid && onSave(form)}
          disabled={!valid}
          className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg text-sm font-semibold transition-all ${
            valid
              ? 'bg-indigo-600 text-white hover:bg-indigo-700'
              : 'bg-gray-200 text-gray-500 cursor-not-allowed'
          }`}
        >
          <FiCheck size={16} />
          {initial ? 'Update Schedule' : 'Create Schedule'}
        </button>
      </div>
    </div>
  );
};

// Schedule Item
const ScheduleItem = ({ schedule, clusters, onToggle, onEdit, onDelete }) => {
  const st = getStrategyMeta(schedule.strategy);
  const Icon = st.icon;
  const isActive = schedule.is_active === 'Y';

  const clusterNames = schedule.cluster_ids
    ?.map(id => clusters.find(c => c.id === id)?.name || id)
    .join(', ') || 'No clusters';

  const sleepHours = (schedule.schedule_matrix?.match(/1/g) || []).length;

  return (
    <div
      className="flex items-start gap-3 p-4 rounded-lg border mb-2 bg-white"
      style={{ borderLeft: `3px solid ${isActive ? st.color : '#cbd5e1'}` }}
    >
      <div className="flex-shrink-0 mt-0.5" style={{ color: st.color }}>
        <Icon size={16} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm font-bold text-gray-900">{schedule.name}</span>
          <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${
            isActive
              ? 'bg-green-100 text-green-700'
              : 'bg-gray-100 text-gray-600'
          }`}>
            {isActive ? 'Active' : 'Paused'}
          </span>
        </div>

        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-600 mb-2">
          <span className="flex items-center gap-1">
            <FiServer size={10} />
            {clusterNames}
          </span>
          <span className="flex items-center gap-1">
            <FiClock size={10} />
            {sleepHours}h/week sleep
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div
            className="px-2 py-1 text-xs font-semibold rounded border"
            style={{
              background: st.bg,
              color: st.color,
              borderColor: st.border
            }}
          >
            {st.label}
          </div>
          <span className="text-xs text-gray-400">·</span>
          <span className="text-xs font-semibold text-green-600">
            {st.savings} savings
          </span>
          {schedule.pre_warm_minutes > 0 && (
            <>
              <span className="text-xs text-gray-400">·</span>
              <span className="text-xs text-amber-600">
                {schedule.pre_warm_minutes}m pre-warm
              </span>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          onClick={() => onToggle(schedule.id)}
          className={`p-2 rounded-lg border transition-colors ${
            isActive
              ? 'bg-amber-50 text-amber-600 border-amber-200 hover:bg-amber-100'
              : 'bg-green-50 text-green-600 border-green-200 hover:bg-green-100'
          }`}
          title={isActive ? 'Pause' : 'Resume'}
        >
          {isActive ? <FiPause size={14} /> : <FiPlay size={14} />}
        </button>
        <button
          onClick={() => onEdit(schedule)}
          className="p-2 bg-gray-50 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
          title="Edit"
        >
          <FiEdit size={14} />
        </button>
        <button
          onClick={() => onDelete(schedule.id)}
          className="p-2 bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors"
          title="Delete"
        >
          <FiTrash size={14} />
        </button>
      </div>
    </div>
  );
};

// Emergency Controls
const EmergencyControls = ({ clusters }) => {
  const [selections, setSelections] = useState({});
  const [tempHours, setTempHours] = useState(4);

  const controls = [
    {
      key: 'shutdown',
      label: 'SHUTDOWN',
      sub: 'Immediate hibernate',
      icon: FiAlertCircle,
      color: '#ef4444',
      btnLabel: 'Shutdown Now'
    },
    {
      key: 'temp',
      label: 'TEMPORARY',
      sub: 'Duration-based sleep',
      icon: FiClock,
      color: '#f59e0b',
      btnLabel: 'Hibernate',
      hasHours: true
    },
    {
      key: 'wake',
      label: 'WAKE',
      sub: 'Immediate wake',
      icon: FiSun,
      color: '#22c55e',
      btnLabel: 'Wake Now'
    },
  ];

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-5 py-3 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <FiAlertCircle size={14} />
          <span className="text-xs font-bold uppercase tracking-wide text-gray-900">
            Emergency Controls
          </span>
        </div>
        <span className="px-2 py-1 bg-amber-100 text-amber-700 text-xs font-semibold rounded-full">
          Immediate
        </span>
      </div>

      <div className="p-3 space-y-2">
        {controls.map(c => {
          const Icon = c.icon;
          return (
            <div
              key={c.key}
              className="p-3 rounded-lg border"
              style={{
                borderColor: `${c.color}28`,
                background: `${c.color}07`
              }}
            >
              <div className="flex items-center gap-2 mb-2">
                <Icon size={14} style={{ color: c.color }} />
                <div>
                  <div className="text-xs font-bold tracking-wide" style={{ color: c.color }}>
                    {c.label}
                  </div>
                  <div className="text-xs text-gray-600">{c.sub}</div>
                </div>
              </div>

              {c.hasHours && (
                <div className="flex items-center gap-2 mb-2">
                  <input
                    type="number"
                    min={1}
                    max={24}
                    value={tempHours}
                    onChange={e => setTempHours(parseInt(e.target.value) || 1)}
                    className="w-16 px-2 py-1 text-sm text-center border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                  <span className="text-sm text-gray-600">hours</span>
                </div>
              )}

              <select
                value={selections[c.key] || ''}
                onChange={e => setSelections({ ...selections, [c.key]: e.target.value })}
                className="w-full px-3 py-2 mb-2 text-sm border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select Clusters ▾</option>
                <option value="all">All Clusters</option>
                {clusters.map(cl => (
                  <option key={cl.id} value={cl.id}>{cl.name}</option>
                ))}
              </select>

              <button
                className="w-full px-3 py-2 text-xs font-bold uppercase tracking-wide text-white rounded-lg hover:opacity-90 transition-opacity"
                style={{ background: c.color }}
              >
                {c.btnLabel}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// Strategy Reference
const StrategyReference = () => (
  <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
    <div className="px-5 py-3 bg-gray-50 border-b border-gray-200">
      <span className="text-xs font-bold uppercase tracking-wide text-gray-900">
        Strategy Reference
      </span>
    </div>
    <div className="p-3 space-y-2">
      {STRATEGIES.map(st => {
        const Icon = st.icon;
        return (
          <div
            key={st.id}
            className="p-3 rounded-lg border"
            style={{ borderColor: st.border, background: st.bg }}
          >
            <div className="flex items-center gap-2 mb-1">
              <Icon size={14} style={{ color: st.color }} />
              <span className="text-sm font-bold" style={{ color: st.color }}>
                {st.label}
              </span>
              <span className="ml-auto text-xs font-bold" style={{ color: st.color }}>
                {st.savings}
              </span>
            </div>
            <div className="text-xs text-gray-600 mb-2">{st.desc}</div>
            <div className="flex gap-3 text-xs text-gray-500">
              <span>Wake: {st.wakeTime}</span>
              <span>Risk: {st.risk}</span>
            </div>
          </div>
        );
      })}
    </div>
  </div>
);

// ==================== MAIN COMPONENT ====================

const HibernationDashboardNew = () => {
  const [schedules, setSchedules] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState(null);
  const [toast, setToast] = useState(null);
  const [showProgress, setShowProgress] = useState(true);

  // Load data
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [schedulesRes, clustersRes] = await Promise.all([
        hibernationApi.listSchedules(),
        api.get('/api/v1/clusters')
      ]);

      setSchedules(schedulesRes.data.schedules || []);
      setClusters(clustersRes.data.clusters || []);
    } catch (error) {
      console.error('Failed to load data:', error);
      showToast('Failed to load data', 'error');
    } finally {
      setLoading(false);
    }
  };

  const stats = calculateStats(schedules);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleSave = async (schedule) => {
    try {
      if (editingSchedule) {
        await hibernationApi.updateSchedule(editingSchedule.id, schedule);
        showToast('Schedule updated');
      } else {
        await hibernationApi.createSchedule(schedule);
        showToast('Schedule created');
      }
      setShowForm(false);
      setEditingSchedule(null);
      loadData();
    } catch (error) {
      console.error('Failed to save schedule:', error);
      showToast('Failed to save schedule', 'error');
    }
  };

  const handleToggle = async (id) => {
    try {
      const schedule = schedules.find(s => s.id === id);
      await hibernationApi.toggleSchedule(id, schedule.is_active !== 'Y');
      showToast(`Schedule ${schedule.is_active === 'Y' ? 'paused' : 'resumed'}`);
      loadData();
    } catch (error) {
      console.error('Failed to toggle schedule:', error);
      showToast('Failed to toggle schedule', 'error');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this schedule?')) return;

    try {
      await hibernationApi.deleteSchedule(id);
      showToast('Schedule deleted', 'warning');
      loadData();
    } catch (error) {
      console.error('Failed to delete schedule:', error);
      showToast('Failed to delete schedule', 'error');
    }
  };

  const handleEdit = (schedule) => {
    setEditingSchedule(schedule);
    setShowForm(true);
  };

  const handleNew = () => {
    setEditingSchedule(null);
    setShowForm(true);
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditingSchedule(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-5 right-5 z-50 px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 animate-slide-in-right ${
          toast.type === 'error' ? 'bg-red-50 border border-red-200 text-red-800' :
          toast.type === 'warning' ? 'bg-amber-50 border border-amber-200 text-amber-800' :
          'bg-green-50 border border-green-200 text-green-800'
        }`}>
          {toast.type === 'success' ? <FiCheck size={16} /> : <FiAlertCircle size={16} />}
          <span className="text-sm font-semibold">{toast.msg}</span>
        </div>
      )}

      {/* Top Bar */}
      <div className="bg-white border-b border-gray-200 px-8 py-5 sticky top-0 z-30">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-indigo-600 to-purple-600 rounded-lg flex items-center justify-center text-white">
              <FiMoon size={20} />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 tracking-tight">
                Hibernation Management
              </h1>
              <p className="text-sm text-gray-500">
                Automated cluster sleep schedules and cost optimization
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 border border-red-200 rounded-lg text-sm font-semibold hover:bg-red-100 transition-colors">
              <FiSun size={16} />
              Emergency Wake All
            </button>
            <button
              onClick={handleNew}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition-colors"
            >
              <FiPlus size={16} />
              New Schedule
            </button>
          </div>
        </div>
      </div>

      {/* Live Progress Banner */}
      {showProgress && <LiveProgressBanner onDismiss={() => setShowProgress(false)} />}

      {/* Content */}
      <div className="px-8 py-6 max-w-[1600px] mx-auto">
        {/* KPI Cards */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <KPICard
            label="Saved This Month"
            value={`$${stats.monthlySaved.toLocaleString()}`}
            sub="vs. always-on baseline"
            color="#16a34a"
            accent="#22c55e"
          />
          <KPICard
            label="Sleep Hours / Week"
            value={`${stats.sleepHours}h`}
            sub="of 168h total"
            color="#6366f1"
            accent="#6366f1"
          />
          <KPICard
            label="Est. Savings"
            value={`${stats.savings}%`}
            sub="per week vs always-on"
            color={stats.savings > 30 ? '#22c55e' : '#f59e0b'}
            accent={stats.savings > 30 ? '#22c55e' : '#f59e0b'}
          />
          <KPICard
            label="Schedules"
            value={stats.activeCount}
            sub={`${stats.pausedCount} paused`}
            color="#0f172a"
            accent="#e2e8f0"
          />
        </div>

        {/* Two-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Column 1: Form + Schedules */}
          <div>
            {showForm && (
              <ScheduleForm
                initial={editingSchedule}
                clusters={clusters}
                onSave={handleSave}
                onCancel={handleCancel}
              />
            )}

            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
              <div className="px-5 py-4 bg-gray-50 border-b border-gray-200 flex justify-between items-center">
                <span className="text-xs font-bold uppercase tracking-wide text-gray-900">
                  Active Schedules ({schedules.length})
                </span>
                {!showForm && (
                  <button
                    onClick={handleNew}
                    className="flex items-center gap-1 px-3 py-1 text-xs font-medium text-gray-600 hover:text-gray-800 bg-white border border-gray-300 rounded-md transition-colors"
                  >
                    <FiPlus size={14} />
                    New
                  </button>
                )}
              </div>

              {schedules.length === 0 ? (
                <div className="p-10 text-center">
                  <FiMoon size={48} className="mx-auto text-gray-300 mb-4" />
                  <div className="text-base font-bold text-gray-900 mb-2">
                    No Hibernation Schedules
                  </div>
                  <div className="text-sm text-gray-500 mb-4">
                    Create your first schedule to start saving costs
                  </div>
                  <button
                    onClick={handleNew}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition-colors"
                  >
                    <FiPlus size={16} />
                    Create Schedule
                  </button>
                </div>
              ) : (
                <div className="p-3">
                  {schedules.map(s => (
                    <ScheduleItem
                      key={s.id}
                      schedule={s}
                      clusters={clusters}
                      onToggle={handleToggle}
                      onEdit={handleEdit}
                      onDelete={handleDelete}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Column 2: Savings Report + Audit History + Emergency Controls */}
          <div className="space-y-6">
            <SavingsReport schedules={schedules} />
            <AuditHistory />
            <EmergencyControls clusters={clusters} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default HibernationDashboardNew;
