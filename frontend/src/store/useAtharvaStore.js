import { create } from 'zustand';
import axios from 'axios';
import toast from 'react-hot-toast';

const useAtharvaStore = create((set, get) => ({
    // Existing state
    status: null,
    rankings: null,
    recommendations: [],
    riskHistory: [],
    isLoading: false,
    error: null,
    settings: {
        autoRebalance: false,
        riskThreshold: 75,
    },

    // New state: Node Templates
    nodeTemplates: [],
    selectedTemplate: null,

    // New state: Pool Rankings
    poolRankings: null,
    filteringStats: null,

    // New state: Pool Details
    selectedPool: null,
    poolDetails: null,
    showPoolDetails: false,

    // New state: Switch Confirmation
    switchTarget: null,
    showSwitchConfirm: false,
    switchResult: null,

    // New state: Blacklist
    blacklist: [],

    // New state: Activity Feed
    activityFeed: [],

    // ─── Existing Actions ──────────────────────────────────────────────────

    fetchStatus: async () => {
        set({ isLoading: true, error: null });
        try {
            const response = await axios.get('/api/v1/atharva/status');
            set({ status: response.data, settings: { ...get().settings, autoRebalance: response.data.auto_rebalance_enabled } });
        } catch (err) {
            set({ error: err.message });
        } finally {
            set({ isLoading: false });
        }
    },

    fetchRankings: async () => {
        try {
            const response = await axios.get('/api/v1/atharva/rankings');
            set({ rankings: response.data });
        } catch (err) {
            console.error("Failed to fetch rankings:", err);
        }
    },

    fetchRecommendations: async () => {
        try {
            const response = await axios.get('/api/v1/atharva/recommendations');
            set({ recommendations: response.data });
        } catch (err) {
            console.error("Failed to fetch recommendations:", err);
        }
    },

    fetchRiskHistory: async () => {
        try {
            const response = await axios.get('/api/v1/atharva/risk-history');
            set({ riskHistory: response.data });
        } catch (err) {
            console.error("Failed to fetch risk history:", err);
        }
    },

    updateSettings: async (newSettings) => {
        try {
            const response = await axios.post('/api/v1/atharva/settings', newSettings);
            set({ settings: response.data });
            if (get().status) {
                set({ status: { ...get().status, auto_rebalance_enabled: response.data.auto_rebalance } });
            }
        } catch (err) {
            set({ error: err.message });
        }
    },

    // ─── Node Template Actions ─────────────────────────────────────────────

    fetchNodeTemplates: async () => {
        try {
            const res = await axios.get('/api/v1/atharva/node-templates');
            set({ nodeTemplates: res.data });
        } catch (err) {
            console.error("Failed to fetch templates:", err);
        }
    },

    createNodeTemplate: async (data) => {
        try {
            const res = await axios.post('/api/v1/atharva/node-templates', data);
            set({ nodeTemplates: [...get().nodeTemplates, res.data] });
            toast.success('Template created');
            return res.data;
        } catch (err) {
            toast.error('Failed to create template');
            return null;
        }
    },

    updateNodeTemplate: async (id, data) => {
        try {
            const res = await axios.put(`/api/v1/atharva/node-templates/${id}`, data);
            set({ nodeTemplates: get().nodeTemplates.map(t => t.id === id ? res.data : t) });
            toast.success('Template updated');
            return res.data;
        } catch (err) {
            toast.error('Failed to update template');
            return null;
        }
    },

    deleteNodeTemplate: async (id) => {
        try {
            await axios.delete(`/api/v1/atharva/node-templates/${id}`);
            set({ nodeTemplates: get().nodeTemplates.filter(t => t.id !== id) });
            toast.success('Template deleted');
        } catch (err) {
            toast.error('Failed to delete template');
        }
    },

    selectTemplate: (template) => set({ selectedTemplate: template }),

    // ─── Pool Rankings Actions ─────────────────────────────────────────────

    fetchPoolRankings: async (clusterId = 'cluster-prod-east', templateId = null) => {
        try {
            const params = { cluster_id: clusterId };
            if (templateId) params.template_id = templateId;
            const res = await axios.get('/api/v1/atharva/pools/rankings', { params });
            set({ poolRankings: res.data.rankings, filteringStats: res.data.filtering_stats });
        } catch (err) {
            console.error("Failed to fetch pool rankings:", err);
        }
    },

    // ─── Pool Details Actions ──────────────────────────────────────────────

    openPoolDetails: async (poolId, clusterId = 'cluster-prod-east') => {
        set({ showPoolDetails: true, selectedPool: poolId, poolDetails: null });
        try {
            const res = await axios.get(`/api/v1/atharva/pools/${poolId}/details`, { params: { cluster_id: clusterId } });
            set({ poolDetails: res.data });
        } catch (err) {
            toast.error('Failed to load pool details');
            set({ showPoolDetails: false });
        }
    },

    closePoolDetails: () => set({ showPoolDetails: false, poolDetails: null, selectedPool: null }),

    // ─── Switch Pool Actions ───────────────────────────────────────────────

    openSwitchConfirm: (pool) => set({ showSwitchConfirm: true, switchTarget: pool }),
    closeSwitchConfirm: () => set({ showSwitchConfirm: false, switchTarget: null, switchResult: null }),

    confirmSwitch: async (req) => {
        try {
            const res = await axios.post('/api/v1/atharva/pools/switch', req);
            set({ switchResult: res.data });
            toast.success('Pool switch initiated');
            // Refresh rankings
            get().fetchPoolRankings();
            return res.data;
        } catch (err) {
            toast.error('Failed to switch pool');
            return null;
        }
    },

    // ─── Blacklist Actions ─────────────────────────────────────────────────

    fetchBlacklist: async () => {
        try {
            const res = await axios.get('/api/v1/atharva/blacklist');
            set({ blacklist: res.data.blacklisted_pools || [] });
        } catch (err) {
            console.error("Failed to fetch blacklist:", err);
        }
    },

    addToBlacklist: async (data) => {
        try {
            await axios.post('/api/v1/atharva/blacklist', data);
            toast.success('Pool blacklisted');
            get().fetchBlacklist();
            get().fetchPoolRankings();
        } catch (err) {
            toast.error('Failed to blacklist pool');
        }
    },

    removeFromBlacklist: async (poolId) => {
        try {
            await axios.delete(`/api/v1/atharva/blacklist/${poolId}`);
            toast.success('Pool removed from blacklist');
            get().fetchBlacklist();
            get().fetchPoolRankings();
        } catch (err) {
            toast.error('Failed to remove from blacklist');
        }
    },

    // ─── Activity Feed Actions ─────────────────────────────────────────────

    fetchActivity: async () => {
        try {
            const res = await axios.get('/api/v1/atharva/activity');
            set({ activityFeed: res.data });
        } catch (err) {
            console.error("Failed to fetch activity:", err);
        }
    },

    // ─── Initialize ────────────────────────────────────────────────────────

    init: async () => {
        set({ isLoading: true });
        await Promise.all([
            get().fetchStatus(),
            get().fetchRankings(),
            get().fetchRecommendations(),
            get().fetchRiskHistory(),
            get().fetchNodeTemplates(),
            get().fetchPoolRankings(),
            get().fetchBlacklist(),
            get().fetchActivity()
        ]);
        set({ isLoading: false });
    }
}));

export default useAtharvaStore;
