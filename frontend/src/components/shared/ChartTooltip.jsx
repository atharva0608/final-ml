import React from 'react';

/**
 * Reusable Recharts tooltip component.
 * Extracted from ScalingActivity.jsx and RightSizing.jsx (both had identical or near-identical inline versions).
 *
 * @param {Function} valueFormatter - optional formatter for values, e.g. v => `$${v}`
 */
const ChartTooltip = ({ active, payload, label, valueFormatter }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-lg text-xs max-w-[200px]">
      <p className="font-semibold text-gray-900 mb-1 truncate">{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.fill || p.stroke }}>
          {p.name}:{' '}
          <span className="font-bold">
            {valueFormatter ? valueFormatter(p.value) : p.value}
          </span>
        </p>
      ))}
    </div>
  );
};

export default ChartTooltip;
