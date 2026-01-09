/**
 * Cluster List Component - Redesigned
 * Matches CAST.ai style dashboard
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { clusterAPI } from '../../services/api';
import { useClusterStore } from '../../store/useStore';
import { Button, Badge, Card } from '../shared'; // Assuming Card is a simple white container
import { formatCurrency, formatClusterType } from '../../utils/formatters';
import { FiRefreshCw, FiPlus, FiMoreHorizontal, FiHardDrive, FiCpu, FiActivity, FiServer } from 'react-icons/fi'; // Icons
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'; // For Donut Charts
import toast from 'react-hot-toast';
import ClusterConnectModal from './ClusterConnectModal';
import ClusterDetails from './ClusterDetails';
import { FaAws, FaGoogle, FaMicrosoft, FaLinux } from 'react-icons/fa'; // Provider icons

const ClusterList = () => {
  const navigate = useNavigate();
  const { clusters, setClusters, setLoading, loading } = useClusterStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [selectedClusterId, setSelectedClusterId] = useState(null);

  // Mock KPI Data State
  const [kpiData, setKpiData] = useState({
    totalCost: 0,
    totalNodes: 0,
    spotNodes: 0,
    fallbackNodes: 0,
    onDemandNodes: 0,
    cpuTotal: 0,
    memTotal: 0
  });


  useEffect(() => {
    fetchClusters();
  }, []);

  const fetchClusters = async () => {
    setLoading(true);
    try {
      const response = await clusterAPI.list({});
      const fetchedClusters = response.data.clusters || [];

      // Enrich clusters with mock usage data for visualization if missing
      const enrichedClusters = fetchedClusters.map(c => ({
        ...c,
        cpu_total: c.node_count * 4, // Mock: 4 vCPU per node avg
        mem_total: c.node_count * 16, // Mock: 16 GB per node avg
        cpu_usage: Math.floor(Math.random() * (c.node_count * 4)),
        mem_usage: Math.floor(Math.random() * (c.node_count * 16)),
        provider: 'aws' // Default to AWS for now
      }));

      setClusters(enrichedClusters);
      calculateKPIs(enrichedClusters);

    } catch (error) {
      toast.error('Failed to load clusters');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const calculateKPIs = (clusterData) => {
    let cost = 0;
    let nodes = 0;
    let spot = 0;

    clusterData.forEach(c => {
      cost += c.monthly_cost || 0;
      nodes += c.node_count || 0;
      spot += c.spot_count || 0;
    });

    // Mock Fallback/OnDemand logic for now
    const onDemand = nodes - spot;

    setKpiData({
      totalCost: cost,
      totalNodes: nodes,
      spotNodes: spot,
      fallbackNodes: 0, // Not tracked yet
      onDemandNodes: onDemand,
      cpuTotal: nodes * 4, // Mock total CPU
      memTotal: nodes * 16 // Mock total Mem
    });
  };

  // --- Helper Components for KPI ---

  const CostKPI = () => (
    <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-100 flex-1 min-w-[250px]">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-semibold text-gray-500 tracking-wider uppercase">TOTAL COMPUTE COST</span>
        <FiActivity className="w-3 h-3 text-gray-400" />
      </div>
      <div className="flex items-baseline gap-2">
        <h2 className="text-3xl font-bold text-gray-900">{formatCurrency(kpiData.totalCost)}</h2>
        <span className="text-sm text-gray-500">/mo</span>
      </div>
      <div className="mt-2 flex items-center gap-1">
        <span className="bg-red-100 text-red-700 text-xs font-medium px-1.5 py-0.5 rounded flex items-center">
          ↗ 0.21%
        </span>
      </div>
    </div>
  );

  const NodesKPI = () => (
    <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-100 flex-[1.5] min-w-[300px]">
      <div className="flex justify-between items-start mb-4">
        <div>
          <span className="text-xs font-semibold text-gray-500 tracking-wider uppercase">TOTAL NODES</span>
          <h2 className="text-3xl font-bold text-gray-900 mt-1">{kpiData.totalNodes}</h2>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 border-t border-gray-50 pt-4">
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase">SPOT</p>
          <p className="text-lg font-bold text-gray-900">{kpiData.spotNodes}</p>
          <p className="text-xs text-gray-400">$---/mo</p>
        </div>
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase">FALLBACK</p>
          <p className="text-lg font-bold text-gray-900">{kpiData.fallbackNodes}</p>
          <p className="text-xs text-gray-400">$---/mo</p>
        </div>
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase">ON-DEMAND</p>
          <p className="text-lg font-bold text-gray-900">{kpiData.onDemandNodes}</p>
          <p className="text-xs text-gray-400">{formatCurrency(kpiData.totalCost)}/mo</p>
        </div>
      </div>
    </div>
  );

  const ResourceKPI = ({ label, total, unit, color }) => {
    const data = [
      { name: 'Used', value: 35, color: color }, // Fixed 35% usage mock
      { name: 'Free', value: 65, color: '#f3f4f6' },
    ];

    return (
      <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100 flex-1 min-w-[200px] flex flex-col items-center justify-center">
        <div className="w-24 h-24 relative">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                innerRadius={35}
                outerRadius={45}
                startAngle={90}
                endAngle={-270}
                dataKey="value"
                stroke="none"
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="text-xs font-bold text-gray-700">{label}</span>
          </div>
        </div>
        <div className="text-center mt-2">
          <p className="text-xs font-semibold text-gray-500 uppercase">{label} TOTAL</p>
          <p className="text-xl font-bold text-gray-900">{total}</p>
        </div>
      </div>
    );
  };

  // --- Provider Icon Helper ---
  const getProviderIcon = (provider) => {
    /* eslint-disable default-case */
    switch (String(provider).toLowerCase()) {
      case 'aws': return <FaAws className="w-5 h-5 text-[#FF9900]" />;
      case 'gcp': return <FaGoogle className="w-5 h-5 text-blue-500" />;
      case 'azure': return <FaMicrosoft className="w-5 h-5 text-blue-700" />;
      default: return <FaLinux className="w-5 h-5 text-gray-500" />;
    }
    /* eslint-enable default-case */
  };


  const filteredClusters = clusters.filter((cluster) =>
    cluster.name.toLowerCase().includes(searchTerm.toLowerCase())
  );


  if (loading && clusters.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 p-8 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8 font-sans text-gray-900">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Clusters</h1>
        <Button
          variant="primary"
          className="bg-blue-600 hover:bg-blue-700 text-white shadow-none font-semibold px-6"
          onClick={() => setShowConnectModal(true)}
        >
          Connect cluster
        </Button>
      </div>

      {/* KPI Section */}
      <div className="flex flex-wrap gap-6 mb-8">
        <CostKPI />
        <NodesKPI />
        <ResourceKPI label="CPU" total={kpiData.cpuTotal} unit="Cores" color="#3b82f6" />
        <ResourceKPI label="GIB" total={kpiData.memTotal} unit="GiB" color="#6366f1" />
      </div>

      {/* Filters / Search Bar */}
      <div className="flex justify-between items-center mb-4 bg-white p-2 rounded-lg border border-gray-200 shadow-sm">
        <div className="flex items-center flex-1 px-2">
          <FiRefreshCw className="text-gray-400 w-5 h-5 mr-3 cursor-pointer" onClick={fetchClusters} />
          <input
            type="text"
            placeholder="Enter search keywords"
            className="w-full text-sm outline-none placeholder-gray-400 text-gray-700"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2 border-l border-gray-200 pl-4">
          <select className="text-sm border-none outline-none text-gray-600 bg-transparent font-medium cursor-pointer">
            <option>Status</option>
            <option>Active</option>
            <option>Inactive</option>
          </select>
          <button className="text-sm text-gray-400 hover:text-gray-600 px-3 font-medium">Clear all</button>
        </div>
      </div>

      {/* Main Table */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead className="bg-white border-b border-gray-100">
              <tr>
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider w-10"></th> {/* Checkbox/Icon col */}
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider">Name</th>
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider">Region</th>
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider w-48">Nodes</th>
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider w-32">CPU</th>
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider w-32">Memo..</th>
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider">Cpu Cost</th>
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider">Compute Cost</th>
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider w-10"></th> {/* Menu */}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filteredClusters.map((cluster) => (
                <tr
                  key={cluster.id}
                  className="hover:bg-gray-50 transition-colors cursor-pointer group"
                  onClick={() => setSelectedClusterId(cluster.id)}
                >
                  <td className="py-4 px-6">
                    <div className="text-gray-400 group-hover:text-blue-600">
                      {/* Icon placeholder (e.g. checkbox or folder) */}
                      <FiServer />
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    <div className="flex items-center gap-2">
                      {/* Name & ID */}
                      <div>
                        <div className="text-sm font-semibold text-blue-600 hover:underline">{cluster.name}</div>
                        <div className="text-xs text-gray-400">{cluster.id.substring(0, 18)}...</div>
                      </div>
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    <div className="flex items-center gap-2">
                      {getProviderIcon(cluster.provider || 'aws')}
                      <span className="text-sm text-gray-700">{cluster.region}</span>
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    {/* Node Count & Bar */}
                    <div className="flex flex-col gap-1 w-full max-w-[120px]">
                      <span className="text-sm font-medium text-gray-900">{cluster.node_count}</span>
                      <div className="flex h-1.5 w-full bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="bg-blue-500 h-full"
                          style={{ width: `${(cluster.spot_count / cluster.node_count) * 100}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    {/* CPU Usage Bar */}
                    <div className="flex flex-col gap-1">
                      <span className="text-sm font-medium text-gray-900">{cluster.cpu_total || '-'} CPU</span>
                      <div className="h-1.5 w-24 bg-gray-200 rounded-full overflow-hidden">
                        <div className="bg-blue-500 h-full w-1/3"></div> {/* Mock 33% */}
                      </div>
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    {/* MEM Usage Bar */}
                    <div className="flex flex-col gap-1">
                      <span className="text-sm font-medium text-gray-900">{cluster.mem_total || '-'} GiB</span>
                      <div className="h-1.5 w-24 bg-gray-200 rounded-full overflow-hidden">
                        <div className="bg-indigo-500 h-full w-1/2"></div> {/* Mock 50% */}
                      </div>
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    <span className="text-sm text-gray-700">$0.0464 /h</span>
                  </td>
                  <td className="py-4 px-6">
                    <span className="text-sm font-medium text-gray-900">{formatCurrency(cluster.monthly_cost)} /mo</span>
                  </td>
                  <td className="py-4 px-6">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium ${cluster.status === 'ACTIVE'
                        ? 'bg-green-50 text-green-700'
                        : 'bg-gray-100 text-gray-700'
                      }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${cluster.status === 'ACTIVE' ? 'bg-green-500' : 'bg-gray-400'
                        }`} />
                      {cluster.status === 'ACTIVE' ? 'Connected' : cluster.status}
                    </span>
                  </td>
                  <td className="py-4 px-6 text-right">
                    <button className="text-gray-400 hover:text-gray-600">
                      <FiMoreHorizontal className="w-5 h-5" />
                    </button>
                  </td>
                </tr>
              ))}

              {filteredClusters.length === 0 && (
                <tr>
                  <td colSpan="10" className="py-12 text-center text-gray-500">
                    No clusters found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cluster Connect Modal */}
      <ClusterConnectModal
        isOpen={showConnectModal}
        onClose={() => setShowConnectModal(false)}
        onSuccess={() => {
          setShowConnectModal(false);
          fetchClusters();
        }}
      />

      {/* Cluster Details Modal - Kept for detailed view */}
      {selectedClusterId && (
        <ClusterDetails
          clusterId={selectedClusterId}
          onClose={() => setSelectedClusterId(null)}
        />
      )}
    </div>
  );
};

export default ClusterList;
