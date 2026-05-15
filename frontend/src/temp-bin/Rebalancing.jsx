import React from 'react';
import { FiRefreshCw } from 'react-icons/fi';

// TODO: Replace with final implementation — canonical page for Optimization > Rebalancing.
// Canonical rebalancing UI lives at /live/event-timeline (EventTimeline component).
const Rebalancing = () => (
  <div className="min-h-full bg-gray-50 p-6">
    <div className="max-w-screen-xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-indigo-50 rounded-lg">
          <FiRefreshCw className="w-5 h-5 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Rebalancing</h1>
          <p className="text-sm text-gray-500 mt-0.5">Parallel node eviction and pod scheduling optimization</p>
        </div>
      </div>
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm flex flex-col items-center justify-center py-24 gap-4">
        <FiRefreshCw className="w-12 h-12 text-gray-200" />
        <p className="text-gray-400 text-sm font-medium">This page is under restructuring</p>
        <p className="text-gray-300 text-xs">TODO: Replace with final implementation</p>
      </div>
    </div>
  </div>
);

export default Rebalancing;
