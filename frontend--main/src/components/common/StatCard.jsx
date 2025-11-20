import React from 'react';

const StatCard = ({ title, value, icon, change, changeType, subtitle, className = '' }) => (
  <div className={`bg-white p-4 md:p-5 rounded-xl shadow-sm border border-gray-200 hover:shadow-md transition-all duration-200 ${className}`}>
    <div className="flex items-center justify-between">
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide truncate">{title}</p>
        <p className="text-2xl md:text-3xl font-bold text-gray-900 mt-2 truncate">{value}</p>
        {subtitle && <p className="text-xs text-gray-500 mt-1 truncate">{subtitle}</p>}
        {change && (
          <p className={`text-sm font-medium mt-2 ${changeType === 'positive' ? 'text-green-600' : 'text-red-600'}`}>
            {change}
          </p>
        )}
      </div>
      <div className="bg-gradient-to-br from-blue-500 to-blue-600 text-white p-3 md:p-4 rounded-xl shadow-lg flex-shrink-0 ml-2">
        {icon}
      </div>
    </div>
  </div>
);

export default StatCard;
