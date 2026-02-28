import React, { useState, useEffect } from 'react';
import { decisionEngineAPI } from '../../services/api';
import { FiZap, FiShield, FiDollarSign, FiAlertCircle, FiClock } from 'react-icons/fi';

const OPTIMIZATION_MODES = {
    COST_FIRST: {
        label: 'Cost First',
        icon: FiDollarSign,
        color: 'green',
        description: '25% risk ceiling, 3% delta threshold - Aggressive savings',
        riskCeiling: '25%',
        deltaThreshold: '3%',
    },
    BALANCED: {
        label: 'Balanced',
        icon: FiZap,
        color: 'indigo',
        description: '20% risk ceiling, 5% delta threshold - Default profile',
        riskCeiling: '20%',
        deltaThreshold: '5%',
    },
    NO_DOWNTIME_FIRST: {
        label: 'No Downtime First',
        icon: FiShield,
        color: 'orange',
        description: '10% risk ceiling, 8% delta threshold - Maximum safety',
        riskCeiling: '10%',
        deltaThreshold: '8%',
    }
};

const OptimizationModeSelector = ({ clusterId, currentMode, onModeChange }) => {
    const [selectedMode, setSelectedMode] = useState(currentMode || 'BALANCED');
    const [cooldownActive, setCooldownActive] = useState(false);
    const [cooldownRemaining, setCooldownRemaining] = useState(0);
    const [isChanging, setIsChanging] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        setSelectedMode(currentMode || 'BALANCED');
    }, [currentMode]);

    useEffect(() => {
        // Check cooldown status
        const checkCooldown = async () => {
            try {
                const response = await decisionEngineAPI.getCooldownStatusV3(clusterId);
                if (response.data) {
                    setCooldownActive(response.data.cooldown_active || false);
                    setCooldownRemaining(response.data.remaining_seconds || 0);
                }
            } catch (err) {
                console.error('Failed to check cooldown:', err);
            }
        };

        checkCooldown();
        const interval = setInterval(checkCooldown, 10000);
        return () => clearInterval(interval);
    }, [clusterId]);

    const handleModeChange = async (mode) => {
        if (cooldownActive) {
            setError(`Mode switch cooldown active. Retry in ${Math.ceil(cooldownRemaining / 60)} minutes.`);
            return;
        }

        setIsChanging(true);
        setError(null);

        try {
            await decisionEngineAPI.setOptimizationMode(clusterId, mode);
            setSelectedMode(mode);
            setCooldownActive(true);
            setCooldownRemaining(1800); // 30 minutes
            if (onModeChange) onModeChange(mode);
        } catch (err) {
            const errorMsg = err.response?.data?.detail || 'Failed to update optimization mode';
            setError(errorMsg);
            console.error('Mode change error:', err);
        } finally {
            setIsChanging(false);
        }
    };

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">Optimization Profile</h3>
                {cooldownActive && (
                    <div className="flex items-center text-sm text-orange-600 bg-orange-50 px-3 py-1.5 rounded-lg">
                        <FiClock className="mr-1.5" />
                        Cooldown: {Math.ceil(cooldownRemaining / 60)}m
                    </div>
                )}
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start">
                    <FiAlertCircle className="text-red-600 mt-0.5 mr-2 flex-shrink-0" />
                    <p className="text-sm text-red-800">{error}</p>
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {Object.entries(OPTIMIZATION_MODES).map(([key, mode]) => {
                    const Icon = mode.icon;
                    const isSelected = selectedMode === key;
                    const isDisabled = cooldownActive && !isSelected;

                    return (
                        <button
                            key={key}
                            onClick={() => !isDisabled && handleModeChange(key)}
                            disabled={isDisabled || isChanging}
                            className={`
                                relative p-4 rounded-lg border-2 transition-all text-left
                                ${isSelected
                                    ? `border-${mode.color}-500 bg-${mode.color}-50 shadow-md`
                                    : `border-gray-200 bg-white hover:border-${mode.color}-300 hover:bg-${mode.color}-50`
                                }
                                ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                            `}
                        >
                            <div className="flex items-center mb-2">
                                <Icon className={`mr-2 text-${mode.color}-600`} size={20} />
                                <span className={`font-semibold ${isSelected ? `text-${mode.color}-900` : 'text-gray-900'}`}>
                                    {mode.label}
                                </span>
                                {isSelected && (
                                    <span className={`ml-auto text-xs font-medium text-${mode.color}-700 bg-${mode.color}-100 px-2 py-0.5 rounded`}>
                                        Active
                                    </span>
                                )}
                            </div>

                            <p className="text-xs text-gray-600 mb-3">{mode.description}</p>

                            <div className="flex gap-3 text-xs">
                                <div>
                                    <span className="text-gray-500">Risk:</span>
                                    <span className="ml-1 font-semibold text-gray-900">{mode.riskCeiling}</span>
                                </div>
                                <div>
                                    <span className="text-gray-500">Delta:</span>
                                    <span className="ml-1 font-semibold text-gray-900">{mode.deltaThreshold}</span>
                                </div>
                            </div>
                        </button>
                    );
                })}
            </div>

            <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-xs text-blue-800">
                    <strong>Note:</strong> Mode changes trigger a 30-minute cooldown to prevent configuration thrashing.
                    The new profile applies to all future decision evaluations.
                </p>
            </div>
        </div>
    );
};

export default OptimizationModeSelector;
