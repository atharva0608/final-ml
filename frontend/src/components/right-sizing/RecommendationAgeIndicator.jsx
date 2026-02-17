import React from 'react';
import { FiClock } from 'react-icons/fi';

const RecommendationAgeIndicator = ({ days }) => {
    // Determine urgency/staleness
    // < 3 days: New (Green)
    // 3-7 days: Pending (Yellow)
    // > 7 days: Stale (Orange/Red)

    let color = 'bg-green-100 text-green-700 border-green-200';
    let label = 'New';

    if (days >= 7) {
        color = 'bg-orange-100 text-orange-800 border-orange-200';
        label = 'Stale';
    } else if (days >= 3) {
        color = 'bg-yellow-100 text-yellow-800 border-yellow-200';
        label = 'Pending';
    }

    return (
        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border ${color}`} title={`${days} days since recommendation generated`}>
            <FiClock className="w-3 h-3" />
            {days}d ({label})
        </span>
    );
};

export default RecommendationAgeIndicator;
