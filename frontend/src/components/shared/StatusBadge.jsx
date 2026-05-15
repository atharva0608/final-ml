import React from 'react';

const statusMap = {
  completed:    'bg-green-100  text-green-700',
  success:      'bg-green-100  text-green-700',
  in_progress:  'bg-blue-100   text-blue-700',
  scaling_up:   'bg-indigo-100 text-indigo-700',
  scale_up:     'bg-indigo-100 text-indigo-700',
  scaling_down: 'bg-yellow-100 text-yellow-700',
  scale_down:   'bg-yellow-100 text-yellow-700',
  failed:       'bg-red-100    text-red-700',
  pending:      'bg-gray-100   text-gray-600',
};

/**
 * Pill badge showing a normalized execution status.
 * Extracted from ScalingActivity.jsx to be reusable across execution-related pages.
 */
const StatusBadge = ({ status }) => {
  const label = (status || 'unknown').replace(/_/g, ' ');
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${statusMap[status] || statusMap.pending}`}>
      {label}
    </span>
  );
};

export default StatusBadge;
