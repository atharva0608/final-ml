import React from 'react';

const EmptyState = ({ icon, title, description }) => (
  <div className="flex flex-col items-center justify-center py-12 text-gray-400">
    {icon}
    <p className="text-lg font-medium text-gray-600 mt-4">{title}</p>
    {description && <p className="text-sm text-gray-500 mt-1 text-center px-4">{description}</p>}
  </div>
);

export default EmptyState;
