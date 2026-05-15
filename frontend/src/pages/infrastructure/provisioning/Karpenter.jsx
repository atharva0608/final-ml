import React from 'react';
import { FiZap } from 'react-icons/fi';

const Karpenter = () => {
  return (
    <div className="min-h-full bg-gray-50 p-6">
      <div className="max-w-screen-xl mx-auto">
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-1">
            <div className="p-2 bg-indigo-50 rounded-lg">
              <FiZap className="w-5 h-5 text-indigo-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Karpenter</h1>
              <p className="text-sm text-gray-500 mt-0.5">Karpenter configuration, deployment mode, and dry-run recommendations</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Karpenter;
