import React from 'react';
import { FiAlertCircle, FiSettings, FiCheck } from 'react-icons/fi';

const PolicyGapAlert = ({ gapCount, onFix }) => {
    // If no gaps, return null or a happy state
    if (!gapCount || gapCount === 0) return (
        <div className="flex items-center gap-1.5 px-2 py-1 bg-green-50 text-green-700 rounded text-xs border border-green-100" title="Policies fully aligned">
            <FiCheck className="w-3 h-3" /> Aligned
        </div>
    );

    return (
        <div className="flex items-center gap-2 px-2 py-1 bg-orange-50 text-orange-800 rounded text-xs border border-orange-200">
            <FiAlertCircle className="w-3 h-3 flex-shrink-0" />
            <span className="font-medium whitespace-nowrap">{gapCount} Policy Gaps</span>
            {onFix && (
                <button
                    onClick={(e) => { e.stopPropagation(); onFix(); }}
                    className="ml-1 px-1.5 py-0.5 bg-white border border-orange-200 rounded hover:bg-orange-100 flex items-center gap-1 text-[10px]"
                >
                    <FiSettings className="w-2.5 h-2.5" /> Fix
                </button>
            )}
        </div>
    );
};

export default PolicyGapAlert;
