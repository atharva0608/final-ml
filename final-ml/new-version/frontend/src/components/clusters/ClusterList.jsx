/**
 * Cluster List Component
 */
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { clusterAPI } from '../../services/api';
import { useClusterStore } from '../../store/useStore';
import { Card, Button, Badge } from '../shared';
import { formatDateTime, getStatusColor, formatClusterType } from '../../utils/formatters';
import { FiPlus, FiRefreshCw, FiExternalLink } from 'react-icons/fi';
import toast from 'react-hot-toast';
import ClusterConnectModal from './ClusterConnectModal';

import ClusterDetails from './ClusterDetails';

const ClusterList = () => {
  const navigate = useNavigate();
  const { clusters, setClusters, setLoading, loading } = useClusterStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [selectedClusterId, setSelectedClusterId] = useState(null);

  useEffect(() => {
    fetchClusters();
  }, []);

  const fetchClusters = async () => {
    setLoading(true);
    try {
      const response = await clusterAPI.list({});
      setClusters(response.data.clusters || []);
    } catch (error) {
      toast.error('Failed to load clusters');
    } finally {
      setLoading(false);
    }
  };

  const filteredClusters = clusters.filter((cluster) => {
    const matchesSearch = cluster.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = filterStatus === 'all' || cluster.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Clusters</h1>
          <p className="text-gray-600 mt-1">Manage your Kubernetes clusters</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" icon={<FiRefreshCw />} onClick={fetchClusters}>
            Refresh
          </Button>
          <Button
            variant="primary"
            icon={<FiPlus />}
            onClick={() => setShowConnectModal(true)}
          >
            Connect Cluster
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex gap-4">
          <input
            type="text"
            placeholder="Search clusters..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="all">All Status</option>
            <option value="ACTIVE">Active</option>
            <option value="DISCOVERED">Discovered</option>
            <option value="INACTIVE">Inactive</option>
            <option value="ERROR">Error</option>
          </select>
        </div>
      </Card>

      {/* Cluster List */}
      {filteredClusters.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <p className="text-gray-500 text-lg">No clusters found</p>
            <p className="text-gray-400 mt-2">Connect a cluster to get started</p>
            <Button
              variant="primary"
              className="mt-4"
              onClick={() => setShowConnectModal(true)}
            >
              Connect Your First Cluster
            </Button>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {filteredClusters.map((cluster) => (
            <Card
              key={cluster.id}
              className="hover:shadow-lg transition-shadow cursor-pointer"
              onClick={() => setSelectedClusterId(cluster.id)}
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-lg font-semibold text-gray-900">{cluster.name}</h3>
                    <Badge color={getStatusColor(cluster.status)}>{cluster.status}</Badge>
                  </div>
                  <p className="text-sm text-gray-500 mt-1">{cluster.region}</p>
                  <div className="mt-3 space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Type:</span>
                      <span className="font-medium">{formatClusterType(cluster.cluster_type)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Version:</span>
                      <span className="font-medium">{cluster.version || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Last Heartbeat:</span>
                      <span className="font-medium">
                        {cluster.last_heartbeat
                          ? formatDateTime(cluster.last_heartbeat)
                          : 'Never'}
                      </span>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-gray-100">
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-600 flex items-center gap-1">
                        📦 Provisioner:
                      </span>
                      <Badge color="green">Karpenter Active</Badge>
                    </div>
                    <div className="mt-2 text-sm flex justify-between items-center">
                      <span className="text-gray-600">Consolidation:</span>
                      <span className="font-semibold text-gray-900">88% Efficient</span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
                      <div className="bg-blue-600 h-1.5 rounded-full" style={{ width: '88%' }}></div>
                    </div>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedClusterId(cluster.id);
                  }}
                  className="p-2 text-gray-400 hover:text-blue-600 transition-colors"
                >
                  <FiExternalLink className="w-5 h-5" />
                </button>
              </div>
              <div className="mt-4 pt-4 border-t border-gray-200 flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/clusters/${cluster.id}/policy`);
                  }}
                >
                  Configure Policy
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/clusters/${cluster.id}/agent`);
                  }}
                >
                  Agent Install
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )
      }

      {/* Cluster Connect Modal */}
      <ClusterConnectModal
        isOpen={showConnectModal}
        onClose={() => setShowConnectModal(false)}
        onSuccess={() => {
          setShowConnectModal(false);
          fetchClusters();
        }}
      />

      {/* Cluster Details Modal */}
      {
        selectedClusterId && (
          <ClusterDetails
            clusterId={selectedClusterId}
            onClose={() => setSelectedClusterId(null)}
          />
        )
      }
    </div >
  );
};

export default ClusterList;
