import React from 'react';
import { FiClock, FiDollarSign, FiShield, FiZap, FiCheckCircle } from 'react-icons/fi';

/**
 * HibernationTypeCard - Displays a single hibernation strategy option
 *
 * Shows strategy details, benefits, use cases, and action button
 */
const HibernationTypeCard = ({
    type,
    name,
    description,
    wakeTime,
    savingsPercent,
    safetyLevel,
    features,
    useCases,
    isSelected,
    onSelect,
    disabled = false
}) => {
    // Get color scheme based on type
    const getColorScheme = () => {
        switch(type) {
            case 'NAMESPACE_SLEEP':
                return {
                    border: 'border-blue-200',
                    bg: 'bg-blue-50',
                    selectedBorder: 'border-blue-500',
                    selectedBg: 'bg-blue-100',
                    button: 'bg-blue-600 hover:bg-blue-700',
                    badge: 'bg-blue-100 text-blue-800',
                    icon: 'text-blue-600'
                };
            case 'NUCLEAR':
                return {
                    border: 'border-orange-200',
                    bg: 'bg-orange-50',
                    selectedBorder: 'border-orange-500',
                    selectedBg: 'bg-orange-100',
                    button: 'bg-orange-600 hover:bg-orange-700',
                    badge: 'bg-orange-100 text-orange-800',
                    icon: 'text-orange-600'
                };
            case 'SNAPSHOT_RESTORE':
                return {
                    border: 'border-green-200',
                    bg: 'bg-green-50',
                    selectedBorder: 'border-green-500',
                    selectedBg: 'bg-green-100',
                    button: 'bg-green-600 hover:bg-green-700',
                    badge: 'bg-green-100 text-green-800',
                    icon: 'text-green-600'
                };
            default:
                return {
                    border: 'border-gray-200',
                    bg: 'bg-gray-50',
                    selectedBorder: 'border-gray-500',
                    selectedBg: 'bg-gray-100',
                    button: 'bg-gray-600 hover:bg-gray-700',
                    badge: 'bg-gray-100 text-gray-800',
                    icon: 'text-gray-600'
                };
        }
    };

    const colors = getColorScheme();

    return (
        <div
            className={`
                relative rounded-lg border-2 p-6 transition-all duration-200
                ${isSelected ? `${colors.selectedBorder} ${colors.selectedBg} shadow-lg` : `${colors.border} ${colors.bg}`}
                ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:shadow-md'}
            `}
            onClick={() => !disabled && onSelect(type)}
        >
            {/* Selected Indicator */}
            {isSelected && (
                <div className="absolute top-4 right-4">
                    <FiCheckCircle className={`w-6 h-6 ${colors.icon}`} />
                </div>
            )}

            {/* Header */}
            <div className="mb-4">
                <h3 className="text-xl font-bold text-gray-900 mb-2">{name}</h3>
                <p className="text-sm text-gray-600">{description}</p>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                {/* Wake Time */}
                <div className="text-center">
                    <div className="flex items-center justify-center mb-1">
                        <FiClock className={`w-5 h-5 ${colors.icon}`} />
                    </div>
                    <div className="text-2xl font-bold text-gray-900">{wakeTime}</div>
                    <div className="text-xs text-gray-500">Wake Time</div>
                </div>

                {/* Savings */}
                <div className="text-center">
                    <div className="flex items-center justify-center mb-1">
                        <FiDollarSign className={`w-5 h-5 ${colors.icon}`} />
                    </div>
                    <div className="text-2xl font-bold text-gray-900">{savingsPercent}%</div>
                    <div className="text-xs text-gray-500">Cost Savings</div>
                </div>

                {/* Safety */}
                <div className="text-center">
                    <div className="flex items-center justify-center mb-1">
                        <FiShield className={`w-5 h-5 ${colors.icon}`} />
                    </div>
                    <div className={`text-sm font-semibold inline-block px-2 py-1 rounded ${colors.badge}`}>
                        {safetyLevel}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">Safety Level</div>
                </div>
            </div>

            {/* Features */}
            <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
                    <FiZap className="w-4 h-4" />
                    Key Features
                </h4>
                <ul className="space-y-1">
                    {features.map((feature, idx) => (
                        <li key={idx} className="text-xs text-gray-600 flex items-start gap-2">
                            <span className={`mt-0.5 ${colors.icon}`}>•</span>
                            <span>{feature}</span>
                        </li>
                    ))}
                </ul>
            </div>

            {/* Use Cases */}
            <div className="mb-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Best For</h4>
                <p className="text-xs text-gray-600 italic">{useCases}</p>
            </div>

            {/* Select Button */}
            <button
                onClick={(e) => {
                    e.stopPropagation();
                    if (!disabled) onSelect(type);
                }}
                disabled={disabled}
                className={`
                    w-full py-2 px-4 rounded-md text-white font-semibold transition-colors
                    ${isSelected
                        ? `${colors.button} ring-2 ring-offset-2 ring-${type === 'NAMESPACE_SLEEP' ? 'blue' : type === 'NUCLEAR' ? 'orange' : 'green'}-500`
                        : 'bg-gray-400 hover:bg-gray-500'
                    }
                    ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
                `}
            >
                {isSelected ? 'Selected' : 'Select Strategy'}
            </button>
        </div>
    );
};

export default HibernationTypeCard;
