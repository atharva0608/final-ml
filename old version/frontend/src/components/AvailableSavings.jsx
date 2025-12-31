import React, { useState, useEffect } from 'react';
import {
  Database,
  TrendingDown,
  Download,
  MoreVertical,
  Info,
  ChevronRight
} from 'lucide-react';
import api from '../services/api';

/**
 * Available Savings Component
 *
 * Displays cost optimization opportunities and savings potential.
 * Matches CAST AI design with large cost metrics, progress bars, and comparison tables.
 */
const AvailableSavings = () => {
  const [savingsData, setSavingsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [workloadRightsizing, setWorkloadRightsizing] = useState(false);

  useEffect(() => {
    loadSavingsData();
  }, []);

  const loadSavingsData = async () => {
    try {
      setLoading(true);

      // Mock data matching CAST AI design
      const mockData = {
        cluster: {
          name: 'mycluster-fra02-b3c4x16',
          status: 'Connected'
        },
        currentCost: {
          amount: 7143.71,
          currency: 'USD',
          period: 'mo'
        },
        progressToOptimal: 82.9,
        efficiency: {
          current: 19.98,
          waste: {
            cpu: 1.47,
            memory: 6.43
          },
          additionalSavings: 35.8
        },
        currentConfiguration: {
          nodes: [
            {
              qty: 1,
              name: 'b3c.4x16',
              specs: '4 CPU, 16 GiB mem, 0 GiB',
              cpuCost: { perHour: 2.446, total: 9.786 },
              totalMonthly: 7143.71
            }
          ],
          summary: {
            hours: 730,
            cpu: 4,
            memory: 15.09
          }
        },
        optimizedConfiguration: {
          nodes: [
            {
              qty: 1,
              name: 'b3c.4x16',
              specs: '4 CPU, 16 GiB mem, 0 GiB',
              cpuCost: { perHour: 2.446, total: 9.786 },
              totalMonthly: 5921.76
            }
          ],
          summary: {
            hours: 730,
            cpu: 6,
            memory: 12
          }
        },
        recommendedActions: [
          {
            id: 1,
            type: 'rebalance',
            title: 'Rebalance to reach optimal configuration',
            description: 'Achieve the most cost efficient state. CAST AI will replace suboptimal nodes with new ones and move your workloads automatically',
            potentialSavings: 1221.95
          }
        ]
      };

      setSavingsData(mockData);
    } catch (error) {
      console.error('Error loading savings data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  const { cluster, currentCost, progressToOptimal, efficiency, currentConfiguration, optimizedConfiguration, recommendedActions } = savingsData;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Database className="w-5 h-5 text-gray-600" />
              <h1 className="text-xl font-semibold text-gray-900">{cluster.name}</h1>
            </div>
            <span className="flex items-center gap-1.5 px-2.5 py-1 bg-green-50 text-green-700 text-xs font-medium rounded-full">
              <div className="w-2 h-2 bg-green-500 rounded-full"></div>
              {cluster.status}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">January 29, 09:32</span>
            <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
              <Download className="w-4 h-4 text-gray-600" />
            </button>
            <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
              <MoreVertical className="w-4 h-4 text-gray-600" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Cost Card */}
      <div className="bg-gradient-to-br from-green-50 to-emerald-50 border border-green-200 rounded-lg p-6 mb-6">
        <div className="grid grid-cols-2 gap-8">
          {/* Current Cost */}
          <div>
            <h3 className="text-xs font-medium text-gray-600 uppercase mb-2">
              Current Compute Cost
            </h3>
            <div className="text-4xl font-bold text-gray-900">
              ${currentCost.amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              <span className="text-lg font-normal text-gray-600"> /{currentCost.period}</span>
            </div>
          </div>

          {/* Progress to Optimal */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-medium text-gray-600 uppercase flex items-center gap-1">
                Progress to Optimal Setup
                <Info className="w-4 h-4 text-gray-400" />
              </h3>
              <span className="text-lg font-bold text-green-600">{progressToOptimal}%</span>
            </div>

            {/* Progress Bar */}
            <div className="relative h-3 bg-white rounded-full overflow-hidden border border-green-200">
              <div
                className="absolute top-0 left-0 h-full bg-gradient-to-r from-green-400 to-green-500 rounded-full transition-all duration-500"
                style={{ width: `${progressToOptimal}%` }}
              />
              {/* Optimal Marker */}
              <div className="absolute top-0 right-0 flex flex-col items-center" style={{ transform: 'translateX(50%)' }}>
                <div className="w-0 h-0 border-l-4 border-r-4 border-t-8 border-l-transparent border-r-transparent border-t-gray-700"></div>
                <div className="text-[10px] font-medium text-gray-700 mt-1">OPTIMAL</div>
              </div>
            </div>
          </div>
        </div>

        {/* Rebalance Action */}
        {recommendedActions.map((action) => (
          <div key={action.id} className="mt-6 flex items-center justify-between bg-white rounded-lg p-4 border border-green-200">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
                <Database className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-gray-900">{action.title}</h4>
                <p className="text-xs text-gray-600 mt-0.5">{action.description}</p>
              </div>
            </div>
            <button className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg transition-colors">
              Rebalance
            </button>
          </div>
        ))}
      </div>

      {/* Workload Optimization Preferences */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
        <h3 className="text-sm font-bold text-gray-900 mb-4">Workload optimization preferences</h3>

        <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h4 className="text-sm font-semibold text-gray-900">Workload rightsizing</h4>
              <button className="text-gray-400 hover:text-gray-600">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-gray-600">
              Increase your savings by applying the rightsizing recommendations in the Workloads{' '}
              <a href="#" className="text-blue-600 hover:underline">Efficiency report</a>.
            </p>
          </div>

          <div className="ml-6">
            {/* Toggle Switch */}
            <button
              onClick={() => setWorkloadRightsizing(!workloadRightsizing)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                workloadRightsizing ? 'bg-green-600' : 'bg-gray-300'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  workloadRightsizing ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
        </div>

        {/* Efficiency Metrics */}
        <div className="grid grid-cols-3 gap-6 mt-6">
          <div>
            <div className="text-xs text-gray-500 uppercase mb-1">Current Efficiency</div>
            <div className="text-2xl font-bold text-gray-900">{efficiency.current}%</div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase mb-1">$ Saved by Rightsizing</div>
            <div className="text-2xl font-bold text-green-600">$2,557.08</div>
            <div className="flex items-center gap-4 mt-1">
              <span className="text-xs text-gray-600">
                WASTE: <span className="font-medium">{efficiency.waste.cpu} CPU</span>
              </span>
              <span className="text-xs text-gray-600">
                <span className="font-medium">{efficiency.waste.memory} GiB</span>
              </span>
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500 uppercase mb-1">Additional Savings</div>
            <div className="text-2xl font-bold text-green-600">{efficiency.additionalSavings}%</div>
          </div>
        </div>
      </div>

      {/* Configuration Comparison */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="p-6 border-b border-gray-200">
          <h3 className="text-sm font-bold text-gray-900">Configuration comparison</h3>
        </div>

        <div className="grid grid-cols-2 divide-x divide-gray-200">
          {/* Current Configuration */}
          <div className="p-6">
            <h4 className="text-xs font-medium text-gray-600 uppercase mb-4">
              Current cluster configuration
            </h4>

            <table className="w-full mb-4">
              <thead>
                <tr className="text-xs text-gray-500 uppercase">
                  <th className="text-left font-medium pb-2">QTY</th>
                  <th className="text-left font-medium pb-2">Name</th>
                  <th className="text-right font-medium pb-2">CPU Cost</th>
                  <th className="text-right font-medium pb-2">Hourly</th>
                  <th className="text-right font-medium pb-2">Total Monthly</th>
                </tr>
              </thead>
              <tbody>
                {currentConfiguration.nodes.map((node, idx) => (
                  <tr key={idx} className="border-t border-gray-100">
                    <td className="py-3 text-sm text-gray-900">{node.qty} x</td>
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 bg-blue-100 rounded flex items-center justify-center">
                          <Database className="w-3 h-3 text-blue-600" />
                        </div>
                        <div>
                          <div className="text-sm font-medium text-gray-900">{node.name}</div>
                          <div className="text-xs text-gray-500">{node.specs}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-3 text-sm text-gray-900 text-right">${node.cpuCost.perHour} /h</td>
                    <td className="py-3 text-sm text-gray-900 text-right">${node.cpuCost.total} /h</td>
                    <td className="py-3 text-sm text-gray-900 text-right font-medium">
                      ${node.totalMonthly.toLocaleString('en-US', { minimumFractionDigits: 2 })} /mo
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="text-xs font-medium text-gray-600 uppercase mb-2">
                Current Cluster Compute Cost:
              </div>
              <div className="text-2xl font-bold text-gray-900">
                ${currentConfiguration.nodes.reduce((sum, n) => sum + n.totalMonthly, 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                <span className="text-sm font-normal text-gray-600"> /mo</span>
              </div>
              <div className="flex items-center gap-6 mt-2 text-xs text-gray-600">
                <span><span className="font-medium">{currentConfiguration.summary.hours}</span> HOURS</span>
                <span><span className="font-medium">{currentConfiguration.summary.cpu}</span> CPU</span>
                <span><span className="font-medium">{currentConfiguration.summary.memory}</span> GiB</span>
              </div>
            </div>
          </div>

          {/* Optimized Configuration */}
          <div className="p-6 bg-green-50/30">
            <h4 className="text-xs font-medium text-gray-600 uppercase mb-4">
              Optimized cluster configuration
            </h4>

            <table className="w-full mb-4">
              <thead>
                <tr className="text-xs text-gray-500 uppercase">
                  <th className="text-left font-medium pb-2">QTY</th>
                  <th className="text-left font-medium pb-2">Name</th>
                  <th className="text-right font-medium pb-2">CPU Cost</th>
                  <th className="text-right font-medium pb-2">Hourly</th>
                  <th className="text-right font-medium pb-2">Total Monthly</th>
                </tr>
              </thead>
              <tbody>
                {optimizedConfiguration.nodes.map((node, idx) => (
                  <tr key={idx} className="border-t border-gray-100">
                    <td className="py-3 text-sm text-gray-900">{node.qty} x</td>
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 bg-green-100 rounded flex items-center justify-center">
                          <Database className="w-3 h-3 text-green-600" />
                        </div>
                        <div>
                          <div className="text-sm font-medium text-gray-900">{node.name}</div>
                          <div className="text-xs text-gray-500">{node.specs}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-3 text-sm text-gray-900 text-right">${node.cpuCost.perHour} /h</td>
                    <td className="py-3 text-sm text-gray-900 text-right">${node.cpuCost.total} /h</td>
                    <td className="py-3 text-sm text-gray-900 text-right font-medium">
                      ${node.totalMonthly.toLocaleString('en-US', { minimumFractionDigits: 2 })} /mo
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="bg-green-100 rounded-lg p-4 border border-green-200">
              <div className="text-xs font-medium text-green-800 uppercase mb-2">
                Optimized Cluster Compute Cost:
              </div>
              <div className="text-2xl font-bold text-green-900">
                ${optimizedConfiguration.nodes.reduce((sum, n) => sum + n.totalMonthly, 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                <span className="text-sm font-normal text-green-700"> /mo</span>
              </div>
              <div className="flex items-center gap-6 mt-2 text-xs text-green-800">
                <span><span className="font-medium">{optimizedConfiguration.summary.hours}</span> HOURS</span>
                <span><span className="font-medium">{optimizedConfiguration.summary.cpu}</span> CPU</span>
                <span><span className="font-medium">{optimizedConfiguration.summary.memory}</span> GiB</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AvailableSavings;
