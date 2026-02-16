import React, { useEffect } from 'react';
import { useHibernationStore } from '../../store/useHibernationStore';
import HibernationHeader from './HibernationHeader';
import ClusterOverview from './ClusterOverview';
import StrategySelector from './StrategySelector';
import ScheduleTemplates from './ScheduleTemplates';
import UnifiedScheduleGrid from './UnifiedScheduleGrid';
import TimeBasedRules from './TimeBasedRules';
import MultiTimezone from './MultiTimezone';
import AdvancedConfiguration from './AdvancedConfiguration';
import CostAnalytics from './CostAnalytics';
import HistoryLog from './HistoryLog';
import ValidationPanel from './ValidationPanel';
import { FiCalendar, FiList, FiGlobe, FiSettings, FiClock, FiActivity } from 'react-icons/fi';
import { Toaster } from 'react-hot-toast';

const TABS = [
  { id: 'grid', label: 'Weekly Grid', icon: FiCalendar },
  { id: 'rules', label: 'Time-Based Rules', icon: FiList },
  { id: 'timezone', label: 'Team Schedule', icon: FiGlobe },
  { id: 'settings', label: 'Advanced Settings', icon: FiSettings },
  { id: 'history', label: 'History & Audit', icon: FiClock },
];

const HibernationSchedule = () => {
  const { fetchInitialData, activeTab, setActiveTab, clusterId, loading } = useHibernationStore();

  useEffect(() => {
    console.log('HibernationSchedule - clusterId changed:', clusterId);
    if (clusterId) {
      console.log('HibernationSchedule - calling fetchInitialData');
      fetchInitialData(clusterId);
    }
  }, [clusterId, fetchInitialData]);

  return (
    <div className="min-h-screen bg-gray-50 pb-20 font-sans">
      <Toaster position="top-right" />

      <HibernationHeader />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-8">
        {/* Cluster Overview Section */}
        <section className="mb-8 animate-fade-in-up">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-gray-900">Cluster Overview</h2>
            <span className="text-sm text-gray-500">Last updated: {new Date().toLocaleTimeString()}</span>
          </div>
          <ClusterOverview />
        </section>

        {/* Tabs Navigation */}
        <div className="border-b border-gray-200 mb-6 bg-gray-50 sticky top-16 z-30 pt-2">
          <nav className="-mb-px flex space-x-8 overflow-x-auto">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                                        whitespace-nowrap pb-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2 transition-colors
                                        ${isActive
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }
                                    `}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-blue-500' : 'text-gray-400'}`} />
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Tab Content */}
        <div className="space-y-8 animate-fade-in">
          {loading ? (
            <div className="flex justify-center items-center h-64">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            </div>
          ) : (
            <>
              {activeTab === 'grid' && (
                <div className="space-y-8">
                  <StrategySelector />
                  <ScheduleTemplates />

                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    <div className="lg:col-span-2">
                      <UnifiedScheduleGrid />
                    </div>
                    <div className="lg:col-span-1 space-y-6">
                      <ValidationPanel />
                      <CostAnalytics />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'rules' && <TimeBasedRules />}
              {activeTab === 'timezone' && <MultiTimezone />}
              {activeTab === 'settings' && <AdvancedConfiguration />}
              {activeTab === 'history' && <HistoryLog />}
            </>
          )}
        </div>
      </main>
    </div>
  );
};

export default HibernationSchedule;
