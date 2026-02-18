import React, { useState, useEffect } from 'react';
import { hibernationApi } from '../../services/hibernationApi';

const StrategySelector = ({ selected, onSelect }) => {
  const [strategies, setStrategies] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStrategies();
  }, []);

  const loadStrategies = async () => {
    try {
      const response = await hibernationApi.compareStrategies();
      setStrategies(response.data || []);
    } catch (error) {
      console.error('Failed to load strategies:', error);
      // Fallback to hardcoded strategies
      setStrategies([
        {
          strategy: 'NAMESPACE_SLEEP',
          name: 'Namespace Sleep',
          description: 'Scales all workload replicas to 0',
          savings_percentage: 80,
          wake_time_minutes: 2,
          risk_level: 'low'
        },
        {
          strategy: 'NUCLEAR',
          name: 'Node Scale-Down',
          description: 'Terminates worker nodes',
          savings_percentage: 70,
          wake_time_minutes: 5,
          risk_level: 'medium'
        },
        {
          strategy: 'SNAPSHOT_RESTORE',
          name: 'Full Hibernation',
          description: 'Stops entire cluster',
          savings_percentage: 95,
          wake_time_minutes: 15,
          risk_level: 'high'
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const getStrategyIcon = (strategy) => {
    const icons = {
      NAMESPACE_SLEEP: '🌙',
      NUCLEAR: '🖥️',
      SNAPSHOT_RESTORE: '💥'
    };
    return icons[strategy] || '🌙';
  };

  const getRiskBadge = (risk) => {
    const badges = {
      low: { color: 'bg-green-100 text-green-800', label: 'Low Risk' },
      medium: { color: 'bg-yellow-100 text-yellow-800', label: 'Medium Risk' },
      high: { color: 'bg-red-100 text-red-800', label: 'High Risk' }
    };
    return badges[risk] || badges.low;
  };

  if (loading) {
    return <div className="text-center py-8">Loading strategies...</div>;
  }

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-bold">SELECT HIBERNATION STRATEGY</h3>
      
      {strategies.map(strategy => {
        const icon = getStrategyIcon(strategy.strategy);
        const riskBadge = getRiskBadge(strategy.risk_level);
        const isSelected = selected === strategy.strategy;
        const isRecommended = strategy.strategy === 'NAMESPACE_SLEEP';

        return (
          <div
            key={strategy.strategy}
            onClick={() => onSelect(strategy.strategy)}
            className={`
              border-2 rounded-lg p-6 cursor-pointer transition-all
              ${isSelected 
                ? 'border-blue-500 bg-blue-50' 
                : 'border-gray-200 hover:border-blue-300'
              }
            `}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center space-x-3">
                <span className="text-3xl">{icon}</span>
                <div>
                  <h4 className="font-bold text-lg">{strategy.name}</h4>
                  {isRecommended && (
                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                      Recommended
                    </span>
                  )}
                </div>
              </div>
              {isSelected && (
                <svg className="w-6 h-6 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              )}
            </div>

            <p className="text-gray-700 mb-4">{strategy.description}</p>

            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <div className="font-medium text-gray-600">Savings</div>
                <div className="text-2xl font-bold text-green-600">
                  ~{strategy.savings_percentage}%
                </div>
              </div>
              <div>
                <div className="font-medium text-gray-600">Wake Time</div>
                <div className="text-2xl font-bold text-blue-600">
                  {strategy.wake_time_minutes}min
                </div>
              </div>
              <div>
                <div className="font-medium text-gray-600">Risk</div>
                <div className="mt-1">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${riskBadge.color}`}>
                    {riskBadge.label}
                  </span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default StrategySelector;
