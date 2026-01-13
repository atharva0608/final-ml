import React, { useEffect, useState } from 'react';

/**
 * Semi-circular gauge chart component inspired by CAST AI design
 * Used to display resource metrics visually
 */
const GaugeChart = ({ value, maxValue, label, unit, color = 'blue' }) => {
    const [displayValue, setDisplayValue] = useState(0);

    useEffect(() => {
        // Validation to prevent NaN or negative values
        if (typeof value !== 'number' || isNaN(value)) return;

        // Small delay to ensure CSS transition triggers after mount
        const timer = setTimeout(() => {
            setDisplayValue(value);
        }, 100);

        return () => clearTimeout(timer);
    }, [value]);

    const percentage = Math.min((displayValue / Math.max(maxValue, 1)) * 100, 100);
    // stroke-dasharray for semi-circle: circum * (percentage / 100). 
    // Radius ~45 units. Circumference (half) = PI * 45 ≈ 141.37
    const dashArray = (percentage / 100) * 141.37;

    const colorClasses = {
        blue: { track: 'text-blue-100', fill: 'text-blue-400', accent: 'text-blue-600' },
        green: { track: 'text-green-100', fill: 'text-green-400', accent: 'text-green-600' },
        yellow: { track: 'text-yellow-100', fill: 'text-yellow-400', accent: 'text-yellow-600' },
        red: { track: 'text-red-100', fill: 'text-red-400', accent: 'text-red-600' },
        indigo: { track: 'text-indigo-100', fill: 'text-indigo-400', accent: 'text-indigo-600' },
        gray: { track: 'text-gray-100', fill: 'text-gray-400', accent: 'text-gray-600' },
    };

    const colors = colorClasses[color] || colorClasses.blue;

    return (
        <div className="flex flex-col items-center">
            <div className="relative w-32 h-16 overflow-hidden">
                {/* Background track */}
                <svg className="absolute inset-0" viewBox="0 0 100 50">
                    <path
                        d="M 5 50 A 45 45 0 0 1 95 50"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="8"
                        strokeLinecap="round"
                        className={colors.track}
                    />
                    {/* Filled portion */}
                    <path
                        d="M 5 50 A 45 45 0 0 1 95 50"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="8"
                        strokeLinecap="round"
                        strokeDasharray={`${dashArray} 141.37`}
                        className={`${colors.fill} transition-all duration-1000 ease-out`}
                    />
                </svg>
                {/* Center value */}
                <div className="absolute inset-0 flex items-end justify-center pb-1">
                    <span className={`text-2xl font-bold ${colors.accent}`}>{value}</span>
                </div>
            </div>
            <div className="text-center mt-1">
                <span className="text-xs text-gray-500 uppercase tracking-wide">{unit}</span>
            </div>
            <div className="text-sm font-medium text-gray-700 mt-1">{label}</div>
        </div>
    );
};

export default GaugeChart;
