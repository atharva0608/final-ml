import React from 'react';
import { FiActivity } from 'react-icons/fi';

const KarpenterStatus = () => {
  return (
    <div className="min-h-full bg-gray-50 p-6">
      <div className="max-w-screen-xl mx-auto">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-1">
            <div className="p-2 bg-indigo-50 rounded-lg">
              <FiActivity className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Karpenter Status</h1>
              <p className="text-sm text-gray-500 mt-0.5">Karpenter installation health, operator status, and version information</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default KarpenterStatus;
