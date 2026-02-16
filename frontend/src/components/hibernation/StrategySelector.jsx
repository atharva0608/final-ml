import React, { useState } from 'react';
import { useHibernationStore } from '../../store/useHibernationStore';
import { FiMoon, FiZap, FiShield, FiChevronDown, FiChevronUp, FiCheck } from 'react-icons/fi';
import { Card, Badge } from '../shared';

const STRATEGY_UI_CONFIG = {
    NAMESPACE_SLEEP: {
        icon: FiMoon,
        color: 'blue',
        bgColor: 'bg-blue-50',
        borderColor: 'border-blue-500',
        textColor: 'text-blue-700',
        tagline: '~2 min wake | ~80% savings',
        description: 'Scales workloads to 0 replicas. Cluster Autoscaler drains idle nodes.',
        bestFor: 'Stateless dev/test workloads'
    },
    NUCLEAR: {
        icon: FiZap,
        color: 'red',
        bgColor: 'bg-red-50',
        borderColor: 'border-red-500',
        textColor: 'text-red-700',
        tagline: '~8 min wake | ~99% savings',
        description: 'Scales all ASGs to 0. Maximum cost reduction but slower recovery.',
        bestFor: 'Non-critical environments'
    },
    SNAPSHOT_RESTORE: {
        icon: FiShield,
        color: 'green',
        bgColor: 'bg-green-50',
        borderColor: 'border-green-500',
        textColor: 'text-green-700',
        tagline: '~12 min wake | ~90% savings',
        description: 'Snapshots EBS volumes before shutdown. Preserves data with AZ affinity.',
        bestFor: 'Stateful workloads, databases'
    }
};

const StrategySelector = () => {
    const { schedule, updateScheduleLocal, strategies } = useHibernationStore();
    const [showComparison, setShowComparison] = useState(false);

    // Merge API data with UI config
    const availableStrategies = strategies.length > 0 ? strategies : Object.keys(STRATEGY_UI_CONFIG).map(k => ({ name: k }));

    return (
        <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900">Hibernation Strategy</h3>
                <button
                    onClick={() => setShowComparison(!showComparison)}
                    className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
                >
                    {showComparison ? 'Hide Comparison' : 'Compare Strategies'}
                    {showComparison ? <FiChevronUp /> : <FiChevronDown />}
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {availableStrategies.map((strategy) => {
                    const config = STRATEGY_UI_CONFIG[strategy.name] || STRATEGY_UI_CONFIG.NAMESPACE_SLEEP;
                    const Icon = config.icon;
                    const isSelected = schedule?.strategy === strategy.name;

                    return (
                        <div
                            key={strategy.name}
                            onClick={() => updateScheduleLocal({ strategy: strategy.name })}
                            className={`relative cursor-pointer rounded-xl border-2 p-5 transition-all duration-200 ${isSelected
                                    ? `${config.borderColor} ${config.bgColor} shadow-lg scale-[1.02]`
                                    : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-md'
                                }`}
                        >
                            {isSelected && (
                                <div className={`absolute top-3 right-3 w-6 h-6 rounded-full ${config.borderColor.replace('border', 'bg')} flex items-center justify-center`}>
                                    <FiCheck className="w-4 h-4 text-white" />
                                </div>
                            )}

                            <div className="flex items-center gap-4 mb-3">
                                <div className={`p-3 rounded-lg ${isSelected ? 'bg-white' : config.bgColor}`}>
                                    <Icon className={`w-6 h-6 ${config.textColor}`} />
                                </div>
                                <div>
                                    <h4 className={`font-bold ${isSelected ? config.textColor : 'text-gray-900'}`}>
                                        {strategy.display_name || strategy.name.replace('_', ' ')}
                                    </h4>
                                    <p className="text-xs text-gray-500 font-medium">{config.tagline}</p>
                                </div>
                            </div>

                            <p className="text-sm text-gray-600 mb-4 min-h-[40px] leading-relaxed">
                                {config.description}
                            </p>

                            <div className={`px-3 py-2 rounded-lg text-xs font-semibold ${isSelected ? 'bg-white/50' : 'bg-gray-50'} ${config.textColor}`}>
                                Best for: {config.bestFor}
                            </div>
                        </div>
                    );
                })}
            </div>

            {showComparison && (
                <Card className="mt-6 border-t-0 rounded-t-none bg-gray-50 animate-fade-in-down">
                    <table className="min-w-full text-sm">
                        <thead>
                            <tr className="text-left text-gray-500 border-b border-gray-200">
                                <th className="pb-2 font-medium">Metric</th>
                                {availableStrategies.map(s => (
                                    <th key={s.name} className="pb-2 font-medium px-4">{s.display_name || s.name}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                            <tr>
                                <td className="py-2 text-gray-600 font-medium">Wake Time</td>
                                {availableStrategies.map(s => (
                                    <td key={s.name} className="py-2 px-4 text-gray-900">
                                        {s.wake_time || STRATEGY_UI_CONFIG[s.name]?.tagline.split('|')[0].trim()}
                                    </td>
                                ))}
                            </tr>
                            <tr>
                                <td className="py-2 text-gray-600 font-medium">Cost Savings</td>
                                {availableStrategies.map(s => (
                                    <td key={s.name} className="py-2 px-4 text-gray-900 font-bold text-green-600">
                                        {s.savings_pct ? `~${s.savings_pct}%` : STRATEGY_UI_CONFIG[s.name]?.tagline.split('|')[1].trim()}
                                    </td>
                                ))}
                            </tr>
                            <tr>
                                <td className="py-2 text-gray-600 font-medium">Safety</td>
                                {availableStrategies.map(s => (
                                    <td key={s.name} className="py-2 px-4">
                                        <Badge variant={s.safety === 'HIGH' || !s.safety ? 'success' : 'warning'}>
                                            {s.safety || 'HIGH'}
                                        </Badge>
                                    </td>
                                ))}
                            </tr>
                        </tbody>
                    </table>
                </Card>
            )}
        </div>
    );
};

export default StrategySelector;
