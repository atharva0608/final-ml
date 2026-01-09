import React from 'react';
import { FiInbox } from 'react-icons/fi';

const EmptyState = ({ title, message, action }) => (
    <div className="flex flex-col items-center justify-center py-12 px-4 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
        <div className="p-4 bg-white rounded-full shadow-sm mb-4">
            <FiInbox className="w-8 h-8 text-gray-400" />
        </div>
        <h3 className="text-lg font-medium text-gray-900">{title}</h3>
        <p className="text-gray-500 text-center max-w-sm mt-1 mb-6">{message}</p>
        {action}
    </div>
);

export default EmptyState;
