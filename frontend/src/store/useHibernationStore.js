import { create } from 'zustand';
import { hibernationAPI, metricAPI } from '../services/api';
import toast from 'react-hot-toast';

/**
 * Hibernation Store
 * 
 * Manages global state for the Hibernation UI module including:
 * - Current schedule and configuration
 * - Cluster hibernation status and history
 * - Cost savings metrics
 * - UI state (tabs, validation warnings, active operations)
 */
export const useHibernationStore = create((set, get) => ({
    // Data State
    clusterId: null,
    schedule: null,
    strategies: [],
    history: [],
    metrics: {
        hourlyCost: 0,
        monthlySavings: 0,
        savingsPct: 0,
        status: 'unknown' // active, hibernating, waking, error
    },

    // UI State
    loading: false,
    saving: false,
    error: null,
    activeTab: 'grid', // grid, rules, timezone, settings
    validationWarnings: [],
    validationErrors: [],

    // Hibernation Jobs (new scheduler)
    hibernationJobs: [],

    // Actions
    setClusterId: (id) => set({ clusterId: id }),

    setActiveTab: (tab) => set({ activeTab: tab }),

    addHibernationJob: (job) => {
        const { hibernationJobs } = get();
        const newJob = {
            id: `job_${Date.now()}`,
            ...job,
            createdAt: new Date().toISOString()
        };
        set({ hibernationJobs: [...hibernationJobs, newJob] });
        return newJob;
    },

    removeHibernationJob: (jobId) => {
        const { hibernationJobs } = get();
        set({ hibernationJobs: hibernationJobs.filter(j => j.id !== jobId) });
    },

    fetchInitialData: async (clusterId) => {
        set({ loading: true, clusterId, error: null });
        try {
            // Parallel fetch for efficiency
            const [scheduleRes, strategiesRes, metricsRes, historyRes] = await Promise.allSettled([
                hibernationAPI.getByCluster(clusterId),
                hibernationAPI.getStrategies(),
                metricAPI.getClusterMetrics(clusterId),
                hibernationAPI.list({ cluster_id: clusterId, limit: 5 }) // Get recent history
            ]);

            // Process Schedule
            let schedule = null;
            if (scheduleRes.status === 'fulfilled' && scheduleRes.value.data?.schedules?.length > 0) {
                schedule = scheduleRes.value.data.schedules[0];
                console.log('Loaded existing schedule:', schedule);

                // Ensure schedule_type is set (for backwards compatibility)
                if (!schedule.schedule_type) {
                    schedule.schedule_type = 'WEEKLY';
                }
                // Ensure date_overrides is set
                if (!schedule.date_overrides) {
                    schedule.date_overrides = {};
                }
            } else {
                // Default empty schedule
                schedule = {
                    cluster_id: clusterId,
                    schedule_type: 'WEEKLY',
                    schedule_matrix: Array(168).fill(1), // All awake by default
                    date_overrides: {},
                    timezone: 'UTC',
                    strategy: 'NAMESPACE_SLEEP',
                    pre_warm_minutes: 15,
                    is_active: true
                };
                console.log('Created default schedule:', schedule);
            }

            // Process Strategies
            const strategies = strategiesRes.status === 'fulfilled' ? strategiesRes.value.data.strategies : [];

            // Process Metrics (Mock calculation for now if API doesn't return everything)
            const clusterMetrics = metricsRes.status === 'fulfilled' ? metricsRes.value.data : {};
            const hourlyCost = (clusterMetrics.total_instances || 0) * 0.12; // Fallback estimation

            set({
                schedule,
                strategies,
                metrics: {
                    ...get().metrics,
                    hourlyCost,
                    // Calculate initial savings based on schedule
                    ...calculateSavings(schedule, strategies, hourlyCost)
                },
                loading: false
            });

        } catch (err) {
            console.error('Failed to load hibernation data', err);
            set({ error: err.message, loading: false });
            toast.error('Failed to load hibernation data');
        }
    },

    updateScheduleLocal: (updates) => {
        const { schedule, strategies, metrics } = get();
        const newSchedule = { ...schedule, ...updates };

        // Recalculate savings when schedule changes
        const savings = calculateSavings(newSchedule, strategies, metrics.hourlyCost);

        set({
            schedule: newSchedule,
            metrics: { ...metrics, ...savings }
        });

        // Validation is handled by ValidationPanel component
    },

    saveSchedule: async () => {
        const { schedule, clusterId } = get();
        set({ saving: true });

        try {
            if (schedule.id) {
                await hibernationAPI.update(schedule.id, schedule);
                toast.success('Schedule updated successfully');
            } else {
                const res = await hibernationAPI.create({ ...schedule, cluster_id: clusterId });
                set({ schedule: { ...schedule, id: res.data.id } });
                toast.success('Schedule created successfully');
            }
            set({ saving: false });
            return true;
        } catch (err) {
            console.error('Failed to save schedule', err);
            toast.error(err.response?.data?.message || 'Failed to save schedule');
            set({ saving: false, error: err.message });
            return false;
        }
    },

    toggleScheduleActive: async () => {
        const { schedule } = get();
        if (!schedule.id) return;

        try {
            await hibernationAPI.toggle(schedule.id);
            set({
                schedule: { ...schedule, is_active: !schedule.is_active }
            });
            toast.success(schedule.is_active ? 'Schedule deactivated' : 'Schedule activated');
        } catch (err) {
            toast.error('Failed to toggle schedule');
        }
    },

    overrideSchedule: async (action) => {
        const { schedule } = get();
        if (!schedule?.id) return;

        try {
            await hibernationAPI.override(schedule.id, { action });
            toast.success(`Cluster ${action === 'SLEEP' ? 'hibernation' : 'wake-up'} initiated`);
        } catch (err) {
            toast.error(`Failed to trigger ${action}`);
        }
    },

    validateSchedule: () => {
        const { schedule } = get();
        const warnings = [];
        const errors = [];

        // Check if schedule exists
        if (!schedule) {
            set({ validationWarnings: warnings, validationErrors: errors });
            return true;
        }

        // Example validation logic (to be expanded)
        if (schedule.pre_warm_minutes > 60) {
            errors.push("Pre-warm time cannot exceed 60 minutes");
        }

        // Check for "Nuclear" strategy safety
        if (schedule.strategy === 'NUCLEAR') {
            warnings.push("Nuclear strategy selected: Verify stateful workloads have backups");
        }

        set({ validationWarnings: warnings, validationErrors: errors });
        return errors.length === 0;
    }

}));

// Helper to calculate savings
function calculateSavings(schedule, strategies, hourlyCost) {
    if (!schedule || !schedule.schedule_matrix) return { monthlySavings: 0, savingsPct: 0 };

    const sleepHours = schedule.schedule_matrix.filter(h => h === 0).length;
    const strategy = strategies.find(s => s.name === schedule.strategy) || { savings_pct: 0 };

    // Monthly hours approx 730
    const totalPotentialCost = hourlyCost * 730;
    const savingsMultiplier = (strategy.savings_pct || 0) / 100;

    // Savings = (Sleep Hours / 168) * Total Monthly Cost * Strategy Efficiency
    const sleepRatio = sleepHours / 168;
    const monthlySavings = totalPotentialCost * sleepRatio * savingsMultiplier;
    const savingsPct = Math.round(sleepRatio * savingsMultiplier * 100);

    return {
        monthlySavings,
        savingsPct
    };
}
