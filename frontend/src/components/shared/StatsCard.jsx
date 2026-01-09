/**
 * StatsCard Component
 *
 * Displays a statistic with an icon, label, value, and change indicator
 */
import React from 'react';
import Card from './Card';

const StatsCard = ({ label, value, change, icon: Icon, color = 'blue' }) => {
    const colorClasses = {
        blue: 'bg-blue-100 text-blue-600',
        purple: 'bg-purple-100 text-purple-600',
        green: 'bg-green-100 text-green-600',
        red: 'bg-red-100 text-red-600',
        yellow: 'bg-yellow-100 text-yellow-600',
        indigo: 'bg-indigo-100 text-indigo-600',
    };

    const selectedColorClass = colorClasses[color] || colorClasses.blue;

    return (
        <Card className="hover:shadow-lg transition-shadow">
            <div className="flex items-start justify-between">
                <div>
                    <p className="text-sm font-medium text-gray-600">{label}</p>
                    <h3 className="text-2xl font-bold text-gray-900 mt-1">{value}</h3>
                    {change && (
                        <p className="text-xs font-medium text-gray-500 mt-1">
                            {change}
                        </p>
                    )}
                </div>
                {Icon && (
                    <div className={`p-3 rounded-lg ${selectedColorClass}`}>
                        <Icon className="w-6 h-6" />
                    </div>
                )}
            </div>
        </Card>
    );
};

export default StatsCard;
