import React from 'react';
import { FiShield } from 'react-icons/fi';

// TODO: Replace with final implementation — wraps or replaces PolicyConfig component.
const Policies = () => (
  <div className="min-h-full bg-gray-50 p-6">
    <div className="max-w-screen-xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-indigo-50 rounded-lg">
          <FiShield className="w-5 h-5 text-indigo-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Policies</h1>
          <p className="text-sm text-gray-500 mt-0.5">Automation policies, scaling rules, and governance controls</p>
        </div>
      </div>
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm flex flex-col items-center justify-center py-24 gap-4">
        <FiShield className="w-12 h-12 text-gray-200" />
        <p className="text-gray-400 text-sm font-medium">This page is under restructuring</p>
        <p className="text-gray-300 text-xs">TODO: Replace with final implementation</p>
      </div>
    </div>
  </div>
);

export default Policies;
