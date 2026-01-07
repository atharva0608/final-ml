/**
 * Zustand Store
 *
 * Global state management for the application
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// Auth Store
export const useAuthStore = create(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,

      setAuth: (user, accessToken, refreshToken) =>
        set({
          user,
          accessToken,
          refreshToken,
          isAuthenticated: true,
        }),

      updateUser: (user) => set({ user }),

      logout: () =>
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        }),
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
);

// Clusters Store
export const useClusterStore = create((set) => ({
  clusters: [],
  selectedCluster: null,
  loading: false,
  error: null,

  setClusters: (clusters) => set({ clusters }),
  setSelectedCluster: (cluster) => set({ selectedCluster: cluster }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  addCluster: (cluster) =>
    set((state) => ({ clusters: [...state.clusters, cluster] })),

  updateCluster: (id, updatedCluster) =>
    set((state) => ({
      clusters: state.clusters.map((c) => (c.id === id ? { ...c, ...updatedCluster } : c)),
    })),

  removeCluster: (id) =>
    set((state) => ({
      clusters: state.clusters.filter((c) => c.id !== id),
    })),
}));

// Templates Store
export const useTemplateStore = create((set) => ({
  templates: [],
  defaultTemplate: null,
  loading: false,
  error: null,

  setTemplates: (templates) => set({ templates }),
  setDefaultTemplate: (template) => set({ defaultTemplate: template }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  addTemplate: (template) =>
    set((state) => ({ templates: [...state.templates, template] })),

  updateTemplate: (id, updatedTemplate) =>
    set((state) => ({
      templates: state.templates.map((t) => (t.id === id ? { ...t, ...updatedTemplate } : t)),
    })),

  removeTemplate: (id) =>
    set((state) => ({
      templates: state.templates.filter((t) => t.id !== id),
    })),
}));

// Policies Store
export const usePolicyStore = create((set) => ({
  policies: [],
  selectedPolicy: null,
  loading: false,
  error: null,

  setPolicies: (policies) => set({ policies }),
  setSelectedPolicy: (policy) => set({ selectedPolicy: policy }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  addPolicy: (policy) =>
    set((state) => ({ policies: [...state.policies, policy] })),

  updatePolicy: (id, updatedPolicy) =>
    set((state) => ({
      policies: state.policies.map((p) => (p.id === id ? { ...p, ...updatedPolicy } : p)),
    })),

  removePolicy: (id) =>
    set((state) => ({
      policies: state.policies.filter((p) => p.id !== id),
    })),
}));

// Metrics Store
export const useMetricsStore = create((set) => ({
  dashboardKPIs: null,
  costMetrics: null,
  instanceMetrics: null,
  costTimeSeries: null,
  loading: false,
  error: null,

  setDashboardKPIs: (kpis) => set({ dashboardKPIs: kpis }),
  setCostMetrics: (metrics) => set({ costMetrics: metrics }),
  setInstanceMetrics: (metrics) => set({ instanceMetrics: metrics }),
  setCostTimeSeries: (data) => set({ costTimeSeries: data }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));

// Experiments Store
export const useExperimentStore = create((set) => ({
  experiments: [],
  selectedExperiment: null,
  experimentResults: null,
  loading: false,
  error: null,

  setExperiments: (experiments) => set({ experiments }),
  setSelectedExperiment: (experiment) => set({ selectedExperiment: experiment }),
  setExperimentResults: (results) => set({ experimentResults: results }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),

  addExperiment: (experiment) =>
    set((state) => ({ experiments: [...state.experiments, experiment] })),

  updateExperiment: (id, updatedExperiment) =>
    set((state) => ({
      experiments: state.experiments.map((e) => (e.id === id ? { ...e, ...updatedExperiment } : e)),
    })),

  removeExperiment: (id) =>
    set((state) => ({
      experiments: state.experiments.filter((e) => e.id !== id),
    })),
}));

// UI Store
export const useUIStore = create((set) => ({
  sidebarOpen: true,
  theme: 'light',
  notifications: [],

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setTheme: (theme) => set({ theme }),

  addNotification: (notification) =>
    set((state) => ({
      notifications: [...state.notifications, { id: Date.now(), ...notification }],
    })),

  removeNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    })),
}));
