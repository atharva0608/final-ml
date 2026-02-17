import { create } from 'zustand';
import { atharvaaiAPI } from '../services/api';
import toast from 'react-hot-toast';

const useAtharvaStore = create((set, get) => ({
    // Pool Rankings state
    poolRankings: null,
    filteringStats: null,
    isLoading: false,
    error: null,

    // Blacklist state
    blacklist: [],

    // ─── Pool Rankings Actions ─────────────────────────────────────────────

    fetchPoolRankings: async (template = null, region = 'ap-south-1', limit = 20) => {
        try {
            set({ isLoading: true, error: null });
            // Use default template if none provided
            const requestTemplate = template || {
                architecture: ['amd64', 'arm64'],
                vcpu_min: 2,
                vcpu_max: 16,
                memory_gb_min: 4,
                memory_gb_max: 64,
                allowed_families: ['m5', 'm6i', 'c5', 'c6i', 'r5', 'r6i'],
                allowed_sizes: ['large', 'xlarge', '2xlarge', '4xlarge'],
                allowed_azs: null,
                excluded_instance_types: []
            };

            const res = await atharvaaiAPI.getRankings(requestTemplate, region, limit);
            set({ poolRankings: res.data, filteringStats: { total_pools: res.data.length } });
        } catch (err) {
            console.error("Failed to fetch pool rankings:", err);
            set({ error: err.message });
            toast.error('Failed to fetch pool rankings');
        } finally {
            set({ isLoading: false });
        }
    },

    // ─── Blacklist Actions ─────────────────────────────────────────────────

    fetchBlacklist: async () => {
        try {
            const res = await atharvaaiAPI.getBlacklist();
            set({ blacklist: res.data || [] });
        } catch (err) {
            console.error("Failed to fetch blacklist:", err);
        }
    }
}));

export default useAtharvaStore;
