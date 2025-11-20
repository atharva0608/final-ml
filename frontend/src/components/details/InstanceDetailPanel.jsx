import React, { useState, useEffect } from 'react';
import {
  CartesianGrid, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line
} from 'recharts';
import { X, Clock, BarChart3 } from 'lucide-react';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';
import Button from '../common/Button';
import Badge from '../common/Badge';
import EmptyState from '../common/EmptyState';
import api from '../../services/api';

const InstanceDetailPanel = ({ instanceId, clientId, onClose }) => {
  const [pricing, setPricing] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);
  const [availableOptions, setAvailableOptions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(null);
  const [error, setError] = useState(null);
  const [showFallback, setShowFallback] = useState(false);
  const [selectedPool, setSelectedPool] = useState('');
  const [selectedInstanceType, setSelectedInstanceType] = useState('');

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [pricingData, metricsData, optionsData] = await Promise.all([
          api.getInstancePricing(instanceId),
          api.getInstanceMetrics(instanceId),
          api.getInstanceAvailableOptions(instanceId)
        ]);
        setPricing(pricingData);
        setMetrics(metricsData);
        setAvailableOptions(optionsData);

        // Set initial dropdown values
        if (optionsData?.pools?.length > 0) {
          setSelectedPool(optionsData.pools[0].id);
        }
        if (optionsData?.instanceTypes?.length > 0) {
          setSelectedInstanceType(optionsData.instanceTypes[0]);
        }

        try {
          const historyData = await api.getPriceHistory(instanceId, 7, 'hour');
          setPriceHistory(historyData);
        } catch (histError) {
          console.warn('Price history not available:', histError);
          setPriceHistory([]);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [instanceId]);

  const handleForceSwitch = async (body) => {
    const target = body.target === 'ondemand' ? 'On-Demand' : `Pool ${body.pool_id}`;

    if (!window.confirm(`Force switch to ${target}?\n\nThis will queue a command for the agent to execute on its next check cycle.`)) {
      return;
    }

    setSwitching(body.target === 'ondemand' ? 'ondemand' : body.pool_id);
    try {
      await api.forceSwitch(instanceId, body);
      alert(`✓ Switch command queued successfully!\n\nTarget: ${target}\n\nThe agent will execute this switch within ~1 minute.`);
      if (onClose) onClose();
    } catch (err) {
      alert(`✗ Failed to queue switch: ${err.message}\n\nPlease ensure the agent is online and try again.`);
    } finally {
      setSwitching(null);
    }
  };

  if (loading) {
    return (
      <tr className="bg-gray-50">
        <td colSpan="10" className="p-8">
          <div className="flex justify-center"><LoadingSpinner /></div>
        </td>
      </tr>
    );
  }

  if (error) {
    return (
      <tr className="bg-red-50">
        <td colSpan="10" className="p-6">
          <ErrorMessage message={error} />
        </td>
      </tr>
    );
  }

  return (
    <tr className="bg-gray-50">
      <td colSpan="10" className="p-4 md:p-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
          {/* Metrics Column */}
          <div className="space-y-4">
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-md font-bold text-gray-900">Instance Metrics</h4>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                <X size={18} />
              </button>
            </div>
            {metrics && (
              <div className="space-y-3">
                <div className="bg-white p-4 rounded-lg border border-gray-200">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-xs text-gray-500">Uptime</p>
                    <Clock size={14} className="text-gray-400" />
                  </div>
                  <p className="text-2xl font-bold text-gray-900">{metrics.uptimeHours}h</p>
                </div>

                <div className="bg-white p-4 rounded-lg border border-gray-200">
                  <p className="text-xs text-gray-500 mb-1">Total Switches</p>
                  <p className="text-2xl font-bold text-gray-900">{metrics.totalSwitches}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {metrics.switchesLast7Days} in last 7 days
                  </p>
                </div>

                <div className="bg-white p-4 rounded-lg border-2 border-green-200 bg-green-50">
                  <p className="text-xs text-green-600 font-semibold mb-1">Total Savings</p>
                  <p className="text-2xl font-bold text-green-700">
                    ${metrics.totalSavings.toFixed(2)}
                  </p>
                  <p className="text-xs text-green-600 mt-1">
                    ${(metrics.savingsLast30Days || 0).toFixed(2)} last 30 days
                  </p>
                </div>

                <div className="bg-white p-4 rounded-lg border border-gray-200">
                  <p className="text-xs text-gray-500 mb-1">Current Prices</p>
                  <div className="space-y-2 mt-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Spot:</span>
                      <span className="font-bold text-gray-900">${metrics.spotPrice.toFixed(4)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">On-Demand:</span>
                      <span className="font-bold text-gray-900">${metrics.onDemandPrice.toFixed(4)}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Available Options Column */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-md font-bold text-gray-900">Available Options</h4>
              <button
                onClick={() => setShowFallback(!showFallback)}
                className="text-xs text-blue-600 hover:text-blue-800 font-medium"
              >
                {showFallback ? 'Hide' : 'Show'} Fallback
              </button>
            </div>

            {/* Advanced Switching - Pool and Type Selection */}
            {availableOptions && (
              <div className="bg-blue-50 p-4 rounded-lg border-2 border-blue-200">
                <h5 className="text-sm font-bold text-blue-900 mb-3">Advanced Switching</h5>

                {/* Pool Selection */}
                <div className="mb-3">
                  <label className="block text-xs font-semibold text-gray-700 mb-2">
                    Select Pool
                  </label>
                  <select
                    value={selectedPool}
                    onChange={(e) => setSelectedPool(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    {availableOptions.pools?.map((pool) => (
                      <option key={pool.id} value={pool.id}>
                        {pool.id} - ${pool.price.toFixed(4)}/hr ({pool.savings.toFixed(1)}% savings)
                      </option>
                    ))}
                  </select>
                </div>

                {/* Instance Type Selection */}
                {availableOptions.instanceTypes && availableOptions.instanceTypes.length > 0 && (
                  <div className="mb-3">
                    <label className="block text-xs font-semibold text-gray-700 mb-2">
                      Change Instance Type
                    </label>
                    <select
                      value={selectedInstanceType}
                      onChange={(e) => setSelectedInstanceType(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    >
                      {availableOptions.instanceTypes.map((type) => (
                        <option key={type} value={type}>
                          {type}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Switch Button */}
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    const body = {
                      target: 'pool',
                      pool_id: selectedPool
                    };
                    if (selectedInstanceType && selectedInstanceType !== availableOptions.currentInstanceType) {
                      body.instance_type = selectedInstanceType;
                    }
                    handleForceSwitch(body);
                  }}
                  loading={switching}
                  className="w-full"
                >
                  Apply Switch
                </Button>
              </div>
            )}
            {pricing && (
              <>
                {showFallback && (
                  <div className="bg-white p-4 rounded-lg border-2 border-red-200 shadow-sm">
                    <div className="flex justify-between items-center mb-3">
                      <div>
                        <p className="text-sm font-semibold text-red-700">On-Demand (Fallback)</p>
                        <p className="text-2xl font-bold text-gray-900 mt-1">
                          ${pricing.onDemand.price.toFixed(4)}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">Guaranteed availability</p>
                      </div>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => handleForceSwitch({ target: 'ondemand' })}
                        loading={switching === 'ondemand'}
                      >
                        Switch
                      </Button>
                    </div>
                  </div>
                )}

                <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                  <p className="text-xs font-semibold text-gray-600 uppercase mb-2">
                    Spot Pools ({pricing.pools.length})
                  </p>
                  {pricing.pools.map((pool, idx) => (
                    <div
                      key={pool.id}
                      className={`bg-white p-4 rounded-lg border-2 transition-all ${idx === 0
                          ? 'border-blue-300 shadow-md'
                          : 'border-gray-200 hover:border-blue-200'
                        }`}
                    >
                      <div className="flex justify-between items-center">
                        <div className="flex-1 min-w-0">
                          {idx === 0 && (
                            <Badge variant="success" className="mb-2">Best Price</Badge>
                          )}
                          <p className="text-xs font-mono text-blue-600 mb-1 truncate">
                            {pool.id}
                          </p>
                          <p className="text-xl font-bold text-gray-900">
                            ${pool.price.toFixed(4)}
                          </p>
                          <div className="flex items-center space-x-2 mt-1">
                            <p className="text-xs font-semibold text-green-600">
                              {pool.savings.toFixed(1)}% savings
                            </p>
                            <p className="text-xs text-gray-500">
                              ${(pricing.onDemand.price - pool.price).toFixed(4)}/hr
                            </p>
                          </div>
                        </div>
                        <Button
                          variant={idx === 0 ? 'success' : 'primary'}
                          size="sm"
                          onClick={() => handleForceSwitch({ target: 'pool', pool_id: pool.id })}
                          loading={switching === pool.id}
                        >
                          Switch
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Price History Chart Column */}
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <h4 className="text-md font-bold text-gray-900 mb-4">
              Price History (7 Days)
            </h4>
            {priceHistory.length > 0 ? (
              <ResponsiveContainer width="100%" height={350}>
                <LineChart data={priceHistory}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="time"
                    tick={{ fontSize: 10 }}
                    angle={-45}
                    textAnchor="end"
                    height={80}
                  />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="avgPrice"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    name="Avg Price"
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="minPrice"
                    stroke="#10b981"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                    name="Min Price"
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="maxPrice"
                    stroke="#ef4444"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                    name="Max Price"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState
                icon={<BarChart3 size={48} />}
                title="No Price History"
                description="Price history data is not available for this instance"
              />
            )}
          </div>
        </div>
      </td>
    </tr>
  );
};

export default InstanceDetailPanel;
