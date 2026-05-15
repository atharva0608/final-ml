import React from 'react';

const colorMap = {
  green:  'bg-green-50  text-green-700  border-green-200',
  blue:   'bg-blue-50   text-blue-700   border-blue-200',
  yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  red:    'bg-red-50    text-red-700    border-red-200',
  gray:   'bg-gray-100  text-gray-700   border-gray-200',
};

/**
 * Pill-shaped stat indicator used in the ScalingActivity status bar.
 * Extracted from ScalingActivity.jsx to be reusable across live-ops pages.
 */
const StatPill = ({ label, value, color = 'gray' }) => (
  <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-semibold ${colorMap[color] || colorMap.gray}`}>
    <span className="font-bold text-sm">{value}</span>
    <span className="opacity-75">{label}</span>
  </div>
);

export default StatPill;
