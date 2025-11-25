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

const InstanceDetailPanel = ({ instanceId, clientId, isPrimary = true, instanceStatus = 'running_primary', onClose, onSwitchComplete }) => {
  const [pricing, setPricing] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);
  const [priceHistoryPools, setPriceHistoryPools] = useState([]);
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
        // Load all data in parallel - backend now checks instances table for immediate availability
        const [pricingData, metricsData, optionsData] = await Promise.all([
          api.getInstancePricing(instanceId),
          api.getInstanceMetrics(instanceId),
          // Backend fallback ensures this works immediately after switch
          api.getInstanceAvailableOptions(instanceId).catch(err => {
            console.warn('Available options loading delayed:', err);
            return null; // Non-blocking - will retry in background
          })
        ]);

        setPricing(pricingData);
        setMetrics(metricsData);

        // Set available options if loaded
        if (optionsData) {
          setAvailableOptions(optionsData);
          if (optionsData?.pools?.length > 0) {
            setSelectedPool(optionsData.pools[0].id);
          }
          if (optionsData?.instanceTypes?.length > 0) {
            setSelectedInstanceType(optionsData.instanceTypes[0]);
          }
        }

        // Load price history (non-critical, can fail gracefully)
        try {
          const historyData = await api.getPriceHistory(instanceId, 7, 'hour');
          if (historyData && historyData.data) {
            setPriceHistory(historyData.data);
            setPriceHistoryPools(historyData.pools || []);
          } else {
            setPriceHistory(Array.isArray(historyData) ? historyData : []);
            setPriceHistoryPools([]);
          }
        } catch (histError) {
          console.warn('Price history not available:', histError);
          setPriceHistory([]);
          setPriceHistoryPools([]);
        }

        // Background retry for options if initial load failed
        if (!optionsData) {
          setTimeout(async () => {
            try {
              const retryOptions = await api.getInstanceAvailableOptions(instanceId);
              setAvailableOptions(retryOptions);
              if (retryOptions?.pools?.length > 0 && !selectedPool) {
                setSelectedPool(retryOptions.pools[0].id);
              }
              if (retryOptions?.instanceTypes?.length > 0 && !selectedInstanceType) {
                setSelectedInstanceType(retryOptions.instanceTypes[0]);
              }
            } catch (retryErr) {
              console.warn('Background retry for options failed:', retryErr);
            }
          }, 2000);
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

      // Refresh the instances list after successful switch
      if (onSwitchComplete) {
        onSwitchComplete();
      }

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
        {/* Warning for non-primary instances */}
        {!isPrimary && (
          <div className="mb-4 p-4 bg-yellow-50 border-l-4 border-yellow-400 rounded-r-lg">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-yellow-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-yellow-700">
                  <span className="font-semibold">Replica/Non-Primary Instance: </span>
                  Switching options are only available for primary instances. This instance is a {instanceStatus === 'running_replica' ? 'replica' : 'non-primary'} instance.
                </p>
              </div>
            </div>
          </div>
        )}

        <div className={`grid grid-cols-1 ${isPrimary ? 'lg:grid-cols-3' : 'lg:grid-cols-2'} gap-4 md:gap-6`}>
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

          {/* Available Options Column - Only show for primary instances */}
          {isPrimary && (
            <div className="space-y-4">
              <h4 className="text-md font-bold text-gray-900">Switch to Pool</h4>

              {pricing && (
              <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                {/* On-Demand - Always at top with red button */}
                <div className={`p-4 rounded-lg border-2 transition-all ${
                  pricing.currentMode === 'ondemand'
                    ? 'bg-gray-100 border-gray-300 opacity-60 cursor-not-allowed'
                    : 'bg-white border-red-200 shadow-sm hover:border-red-300'
                }`}>
                  <div className="flex justify-between items-center">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-2">
                        <p className="text-sm font-semibold text-red-700">On-Demand</p>
                        {pricing.currentMode === 'ondemand' && (
                          <Badge variant="secondary">Current</Badge>
                        )}
                      </div>
                      <p className="text-2xl font-bold text-gray-900">
                        ${pricing.onDemand.price.toFixed(4)}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">Guaranteed availability</p>
                    </div>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => handleForceSwitch({ target: 'ondemand' })}
                      loading={switching === 'ondemand'}
                      disabled={pricing.currentMode === 'ondemand'}
                    >
                      {pricing.currentMode === 'ondemand' ? 'Current' : 'Switch'}
                    </Button>
                  </div>
                </div>

                {/* Spot Pools - Sorted by price */}
                <p className="text-xs font-semibold text-gray-600 uppercase mt-4 mb-2">
                  Spot Pools ({pricing.pools.length})
                </p>
                {pricing.pools.map((pool, idx) => {
                  const isCurrentPool = pricing.currentMode === 'spot' && pricing.currentPool?.id === pool.id;
                  const isCheapest = idx === 0;

                  return (
                    <div
                      key={pool.id}
                      className={`p-4 rounded-lg border-2 transition-all ${
                        isCurrentPool
                          ? 'bg-gray-100 border-gray-300 opacity-60 cursor-not-allowed'
                          : isCheapest
                          ? 'bg-white border-green-300 shadow-md hover:border-green-400'
                          : 'bg-white border-gray-200 hover:border-blue-200'
                      }`}
                    >
                      <div className="flex justify-between items-center">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center space-x-2 mb-2">
                            {isCheapest && !isCurrentPool && (
                              <Badge variant="success">Cheapest</Badge>
                            )}
                            {isCurrentPool && (
                              <Badge variant="secondary">Current Pool</Badge>
                            )}
                          </div>
                          <p className="text-xs font-mono text-blue-600 mb-1 truncate">
                            Pool: {pool.id}
                          </p>
                          <p className="text-xl font-bold text-gray-900">
                            ${pool.price.toFixed(4)}
                          </p>
                          <div className="flex items-center space-x-2 mt-1">
                            <p className="text-xs font-semibold text-green-600">
                              {pool.savings.toFixed(1)}% savings
                            </p>
                            <p className="text-xs text-gray-500">
                              ${(pricing.onDemand.price - pool.price).toFixed(4)}/hr saved
                            </p>
                          </div>
                        </div>
                        <Button
                          variant={isCheapest && !isCurrentPool ? 'success' : 'primary'}
                          size="sm"
                          onClick={() => handleForceSwitch({ target: 'pool', pool_id: pool.id })}
                          loading={switching === pool.id}
                          disabled={isCurrentPool}
                        >
                          {isCurrentPool ? 'Current' : 'Switch'}
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            </div>
          )}

          {/* Price History Chart Column */}
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <h4 className="text-md font-bold text-gray-900 mb-4">
              Price History (7 Days) - All Pools
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
                  <YAxis
                    tick={{ fontSize: 10 }}
                    label={{ value: 'Price ($/hr)', angle: -90, position: 'insideLeft', fontSize: 11 }}
                  />
                  <Tooltip
                    contentStyle={{ fontSize: 12 }}
                    formatter={(value) => value ? `$${value.toFixed(4)}` : 'N/A'}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />

                  {/* On-Demand Price Line (Red, Dashed) */}
                  <Line
                    type="monotone"
                    dataKey="onDemand"
                    stroke="#dc2626"
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    name="On-Demand"
                    dot={false}
                  />

                  {/* Dynamic Pool Lines */}
                  {priceHistoryPools.map((pool, idx) => {
                    // Color palette for different pools
                    const colors = [
                      '#10b981', // green
                      '#3b82f6', // blue
                      '#8b5cf6', // purple
                      '#f59e0b', // amber
                      '#06b6d4', // cyan
                      '#ec4899', // pink
                      '#14b8a6', // teal
                      '#f97316'  // orange
                    ];
                    const color = colors[idx % colors.length];

                    return (
                      <Line
                        key={pool.id}
                        type="monotone"
                        dataKey={pool.key}
                        stroke={color}
                        strokeWidth={2}
                        name={`${pool.name} (${pool.az})`}
                        dot={false}
                        connectNulls
                      />
                    );
                  })}
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
