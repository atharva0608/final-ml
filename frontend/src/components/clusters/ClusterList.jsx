/**
 * Cluster List Component - Redesigned
 * Matches CAST.ai style dashboard
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { clusterAPI } from '../../services/api';
import { useClusterStore } from '../../store/useStore';
import { useAuth } from '../../hooks/useAuth';
import { Button, Badge, Card } from '../shared'; // Assuming Card is a simple white container
import { formatCurrency, formatClusterType } from '../../utils/formatters';
import { FiRefreshCw, FiMoreHorizontal, FiHardDrive, FiCpu, FiActivity, FiServer, FiTrash2, FiLink, FiLink2, FiDownloadCloud } from 'react-icons/fi'; // Icons
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'; // For Donut Charts
import toast from 'react-hot-toast';
import ClusterDetails from './ClusterDetails';
import ClusterDisconnectModal from './ClusterDisconnectModal';
import { FaAws, FaGoogle, FaMicrosoft, FaLinux } from 'react-icons/fa'; // Provider icons

const ClusterList = () => {
  const navigate = useNavigate();
  const { user } = useAuth(); // Get authenticated user
  const { clusters, setClusters, setLoading, loading } = useClusterStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedClusterId, setSelectedClusterId] = useState(null);
  const [openMenuId, setOpenMenuId] = useState(null); // For dropdown menu
  const [disconnectCluster, setDisconnectCluster] = useState(null); // For disconnect modal
  const [refreshing, setRefreshing] = useState(false); // For refresh button loading
  const [injectingClusterId, setInjectingClusterId] = useState(null); // For inject agent loading

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


  const [isDiscovering, setIsDiscovering] = useState(false);

  useEffect(() => {
    fetchData();
    // Poll for discovery if we are in discovering state
    let interval;
    if (isDiscovering) {
      interval = setInterval(fetchData, 5000);
    }
    return () => clearInterval(interval);
  }, [isDiscovering]);

  const fetchData = async () => {
    setLoading(true); // Initial load only? No, maybe silent refresh
    try {
      const [clusterRes, accountRes] = await Promise.all([
        clusterAPI.list({}),
        import('../../services/api').then(mod => mod.accountAPI.list({})).catch(() => ({ data: [] }))
      ]);

      const fetchedClusters = clusterRes.data.clusters || [];
      const accounts = accountRes.data || [];

      setClusters(fetchedClusters);
      calculateKPIs(fetchedClusters);

      // Check if any account is scanning
      // Check if any account is scanning
      const scanning = accounts.some(a => (a.status || '').toUpperCase() === 'SCANNING');

      // If scanning, we are discovering. 
      // Also keep discovering state if we have no clusters but just finished (heuristic) 
      // or simply rely on scanning status.
      setIsDiscovering(scanning);

    } catch (error) {
      toast.error('Failed to load data');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const fetchClusters = fetchData;

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

  // Trigger discovery refresh
  const handleRefreshDiscovery = async () => {
    setRefreshing(true);
    toast.loading('Refreshing cluster discovery...', { id: 'discovery' });
    try {
      await fetchClusters();
      toast.success('Discovery refreshed!', { id: 'discovery' });
    } catch (error) {
      toast.error('Failed to refresh', { id: 'discovery' });
    } finally {
      setRefreshing(false);
    }
  };

  // Inject agent into discovered cluster
  const handleInjectAgent = async (clusterId, clusterName, e) => {
    e?.stopPropagation();
    setInjectingClusterId(clusterId);
    try {
      toast.loading(`Injecting agent into ${clusterName}...`, { id: 'inject' });
      await clusterAPI.autoInstallAgent(clusterId);
      toast.success(`Agent injected into ${clusterName}!`, { id: 'inject' });
      fetchClusters();
    } catch (error) {
      toast.error('Failed to inject agent: ' + (error.response?.data?.detail || error.message), { id: 'inject' });
    } finally {
      setInjectingClusterId(null);
    }
  };

  const handleDisconnectCluster = async (clusterId, deleteNodes) => {
    try {
      // Update cluster status to DISCONNECTED instead of deleting
      await clusterAPI.updateCluster(clusterId, {
        status: 'DISCONNECTED',
        deleteNodes: deleteNodes
      });
      toast.success('Cluster disconnected successfully');
      fetchClusters();
    } catch (error) {
      toast.error('Failed to disconnect cluster');
      console.error(error);
    }
  };

  const handleReconnectCluster = async (clusterId, e) => {
    e.stopPropagation();
    setOpenMenuId(null);
    try {
      await clusterAPI.updateCluster(clusterId, { status: 'ACTIVE' });
      toast.success('Cluster reconnected successfully');
      fetchClusters();
    } catch (error) {
      toast.error('Failed to reconnect cluster');
      console.error(error);
    }
  };

  const handleRemoveCluster = async (clusterId, e) => {
    e.stopPropagation();
    setOpenMenuId(null);
    if (!window.confirm('Are you sure you want to permanently remove this cluster? This cannot be undone.')) return;
    try {
      await clusterAPI.deleteCluster(clusterId);
      toast.success('Cluster removed successfully');
      fetchClusters();
    } catch (error) {
      toast.error('Failed to remove cluster');
      console.error(error);
    }
  };

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
          className={`bg-blue-600 hover:bg-blue-700 text-white shadow-none font-semibold px-6 flex items-center gap-2`}
          onClick={handleRefreshDiscovery}
          disabled={refreshing}
        >
          <FiRefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh Discovery
        </Button>
      </div>

      {/* KPI Section */}
      <div className="flex flex-wrap gap-6 mb-8">
        <CostKPI />
        <NodesKPI />
        <ResourceKPI label="CPU" total={kpiData.cpuTotal} unit="Cores" color="#3b82f6" />
        <ResourceKPI label="GIB" total={kpiData.memTotal} unit="GiB" color="#6366f1" />
      </div>

      {/* Discovery Animation Banner */}
      {isDiscovering && (
        <div className="mb-6 bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 rounded-xl p-6 shadow-lg relative overflow-hidden">
          {/* Animated background elements */}
          <div className="absolute inset-0 overflow-hidden">
            {/* Radar sweep animation */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64">
              <div className="absolute inset-0 border-2 border-white/20 rounded-full animate-ping" style={{ animationDuration: '2s' }}></div>
              <div className="absolute inset-4 border-2 border-white/15 rounded-full animate-ping" style={{ animationDuration: '2.5s', animationDelay: '0.5s' }}></div>
              <div className="absolute inset-8 border-2 border-white/10 rounded-full animate-ping" style={{ animationDuration: '3s', animationDelay: '1s' }}></div>
            </div>
            {/* Floating particles */}
            <div className="absolute w-2 h-2 bg-white/30 rounded-full animate-pulse top-4 left-[20%]" style={{ animationDuration: '1.5s' }}></div>
            <div className="absolute w-1.5 h-1.5 bg-white/20 rounded-full animate-pulse top-8 right-[30%]" style={{ animationDuration: '2s', animationDelay: '0.3s' }}></div>
            <div className="absolute w-2.5 h-2.5 bg-white/25 rounded-full animate-pulse bottom-6 left-[40%]" style={{ animationDuration: '1.8s', animationDelay: '0.6s' }}></div>
            <div className="absolute w-1 h-1 bg-white/20 rounded-full animate-pulse bottom-4 right-[15%]" style={{ animationDuration: '2.2s', animationDelay: '0.9s' }}></div>
          </div>

          {/* Content */}
          <div className="relative z-10 flex items-center gap-6">
            {/* Animated Icon */}
            <div className="relative">
              <div className="w-16 h-16 bg-white/10 backdrop-blur-sm rounded-xl flex items-center justify-center">
                <FiActivity className="w-8 h-8 text-white animate-pulse" />
              </div>
              <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-400 rounded-full animate-ping"></div>
              <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-400 rounded-full"></div>
            </div>

            {/* Text Content */}
            <div className="flex-1">
              <h3 className="text-xl font-bold text-white flex items-center gap-3">
                <span className="inline-block animate-pulse">🔍</span>
                Discovering Your Cloud Infrastructure
              </h3>
              <p className="text-white/80 mt-1 text-sm">
                Scanning AWS regions • Analyzing EKS clusters • Calculating potential savings
              </p>

              {/* Progress Steps */}
              <div className="flex items-center gap-4 mt-3">
                <div className="flex items-center gap-2 text-xs text-white/70">
                  <div className="w-5 h-5 bg-green-500/80 rounded-full flex items-center justify-center">
                    <span className="text-white text-[10px]">✓</span>
                  </div>
                  <span>Authenticating</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-white">
                  <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center animate-spin">
                    <FiRefreshCw className="w-3 h-3 text-white" />
                  </div>
                  <span>Scanning Clusters</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-white/50">
                  <div className="w-5 h-5 bg-white/10 rounded-full flex items-center justify-center">
                    <span className="text-white/50 text-[10px]">3</span>
                  </div>
                  <span>Analyzing Costs</span>
                </div>
              </div>
            </div>

            {/* Animated Counter */}
            <div className="text-right">
              <div className="text-3xl font-bold text-white tabular-nums">
                <span className="animate-pulse">...</span>
              </div>
              <p className="text-white/70 text-xs mt-1">clusters found</p>
            </div>
          </div>
        </div>
      )}

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
                <th className="py-4 px-6 text-xs font-bold text-gray-500 uppercase tracking-wider">Potential Savings</th>
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
                    {cluster.status === 'DISCOVERED' ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                        Agent Required
                      </span>
                    ) : (
                      <div className="flex flex-col gap-1">
                        <span className="text-sm font-medium text-gray-900">{cluster.cpu_total || '-'} CPU</span>
                        <div className="h-1.5 w-24 bg-gray-200 rounded-full overflow-hidden">
                          <div className="bg-blue-500 h-full w-1/3"></div> {/* Mock 33% */}
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="py-4 px-6">
                    {/* MEM Usage Bar */}
                    {cluster.status === 'DISCOVERED' ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                        Agent Required
                      </span>
                    ) : (
                      <div className="flex flex-col gap-1">
                        <span className="text-sm font-medium text-gray-900">{cluster.mem_total || '-'} GiB</span>
                        <div className="h-1.5 w-24 bg-gray-200 rounded-full overflow-hidden">
                          <div className="bg-indigo-500 h-full w-1/2"></div> {/* Mock 50% */}
                        </div>
                      </div>
                    )}
                  </td>
                  <td className="py-4 px-6">
                    <div className="flex flex-col">
                      <span className="text-sm font-bold text-green-600">
                        {formatCurrency(cluster.potential_savings_monthly || cluster.estimated_savings || 0)}
                      </span>
                      {cluster.status === 'DISCOVERED' && (cluster.potential_savings_monthly > 0) && (
                        <span className="text-[10px] text-gray-500">potential savings</span>
                      )}
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    <span className="text-sm font-medium text-gray-900">{formatCurrency(cluster.monthly_cost)} /mo</span>
                  </td>
                  <td className="py-4 px-6">
                    {(() => {
                      // Real-time status check based on last_heartbeat
                      const isReallyConnected = () => {
                        if (cluster.status !== 'ACTIVE') return false;
                        if (!cluster.last_heartbeat) return false;
                        const lastHB = new Date(cluster.last_heartbeat);
                        const twoMinAgo = new Date(Date.now() - 2 * 60 * 1000);
                        return lastHB > twoMinAgo;
                      };
                      const connected = isReallyConnected();

                      // Show prominent Inject Agent button for DISCOVERED clusters
                      if (cluster.status === 'DISCOVERED') {
                        return (
                          <button
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-green-500 to-emerald-600 text-white hover:from-green-600 hover:to-emerald-700 shadow-sm transition-all"
                            onClick={async (e) => {
                              e.stopPropagation();
                              try {
                                toast.loading('Injecting agent into cluster...', { id: 'inject-' + cluster.id });
                                await clusterAPI.autoInstallAgent(cluster.id);
                                toast.success('Agent injected successfully! Cluster is now active.', { id: 'inject-' + cluster.id });
                                fetchClusters();
                              } catch (error) {
                                toast.error('Failed to inject agent: ' + (error.response?.data?.detail || error.message), { id: 'inject-' + cluster.id });
                              }
                            }}
                          >
                            <FiDownloadCloud className="w-3.5 h-3.5" />
                            Activate Optimization
                          </button>
                        );
                      }

                      const statusText = connected ? 'Connected' :
                        cluster.status === 'DISCONNECTED' ? 'Disconnected' :
                          cluster.status === 'PENDING' ? 'Pending' : 'Offline';
                      const bgColor = connected ? 'bg-green-50 text-green-700' :
                        cluster.status === 'PENDING' ? 'bg-yellow-50 text-yellow-700' :
                          'bg-orange-50 text-orange-700';
                      const dotColor = connected ? 'bg-green-500' :
                        cluster.status === 'PENDING' ? 'bg-yellow-500' :
                          'bg-orange-500';
                      return (
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium ${bgColor}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
                          {statusText}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="py-4 px-6 text-right relative">
                    <button
                      className="text-gray-400 hover:text-gray-600"
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenMenuId(openMenuId === cluster.id ? null : cluster.id);
                      }}
                    >
                      <FiMoreHorizontal className="w-5 h-5" />
                    </button>
                    {openMenuId === cluster.id && (
                      <div className="absolute right-6 top-10 bg-white border border-gray-200 rounded-lg shadow-lg z-20 py-1 min-w-[160px]">
                        {cluster.status === 'DISCOVERED' && (
                          <button
                            className="w-full px-4 py-2 text-left text-sm text-green-600 hover:bg-green-50 flex items-center gap-2"
                            onClick={async (e) => {
                              e.stopPropagation();
                              setOpenMenuId(null);
                              try {
                                toast.loading('Activating cluster...', { id: 'activate' });
                                await clusterAPI.autoInstallAgent(cluster.id);
                                toast.success('Agent installation started!', { id: 'activate' });
                                fetchClusters();
                              } catch (error) {
                                toast.error('Failed to activate cluster: ' + (error.response?.data?.detail || error.message), { id: 'activate' });
                              }
                            }}
                          >
                            <FiDownloadCloud className="w-4 h-4" />
                            Inject Agent
                          </button>
                        )}
                        {cluster.status === 'DISCONNECTED' && (
                          <button
                            className="w-full px-4 py-2 text-left text-sm text-blue-600 hover:bg-blue-50 flex items-center gap-2"
                            onClick={(e) => handleReconnectCluster(cluster.id, e)}
                          >
                            <FiLink className="w-4 h-4" />
                            Reconnect
                          </button>
                        )}
                        {(cluster.status === 'ACTIVE' || cluster.status === 'PENDING') && (
                          <button
                            className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                            onClick={(e) => {
                              e.stopPropagation();
                              setOpenMenuId(null);
                              setDisconnectCluster(cluster);
                            }}
                          >
                            <FiLink2 className="w-4 h-4" />
                            Disconnect
                          </button>
                        )}
                        <button
                          className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
                          onClick={(e) => handleRemoveCluster(cluster.id, e)}
                        >
                          <FiTrash2 className="w-4 h-4" />
                          Remove cluster
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}

              {filteredClusters.length === 0 && (
                <tr>
                  <td colSpan="10" className="py-12 text-center text-gray-500">
                    {isDiscovering ? (
                      <div className="flex flex-col items-center justify-center gap-2">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                        <p className="font-medium text-gray-700">Discovering clusters from your AWS account...</p>
                        <p className="text-sm text-gray-400">This usually takes about 1-2 minutes.</p>
                      </div>
                    ) : (
                      "No clusters found."
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cluster Details Modal - Kept for detailed view */}
      {selectedClusterId && (
        <ClusterDetails
          clusterId={selectedClusterId}
          onClose={() => setSelectedClusterId(null)}
        />
      )}

      {/* Disconnect Modal */}
      <ClusterDisconnectModal
        isOpen={!!disconnectCluster}
        onClose={() => setDisconnectCluster(null)}
        cluster={disconnectCluster}
        onConfirm={handleDisconnectCluster}
      />
    </div>
  );
};

export default ClusterList;
