import React, { useState, useEffect } from 'react';
import { cleanupAPI, accountAPI } from '../../services/api';
import { Card, Button, Badge, StatsCard } from '../shared';
import {
  FiTrash2,
  FiCheckCircle,
  FiXCircle,
  FiAlertTriangle,
  FiDollarSign,
  FiHardDrive,
  FiDatabase,
  FiGlobe
} from 'react-icons/fi';

const CleanupDashboard = () => {
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [activeTab, setActiveTab] = useState('instances');
  const [cleanupData, setCleanupData] = useState(null);
  const [selectedItems, setSelectedItems] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [executing, setExecuting] = useState(false);

  useEffect(() => {
    loadAccounts();
  }, []);

  useEffect(() => {
    if (selectedAccount) {
      scanAccount();
    }
  }, [selectedAccount]);

  const loadAccounts = async () => {
    try {
      const response = await accountAPI.list();
      setAccounts(response.data || []);
      if (response.data && response.data.length > 0) {
        setSelectedAccount(response.data[0].id);
      }
      setLoading(false);
    } catch (error) {
      console.error('Failed to load accounts:', error);
      setLoading(false);
    }
  };

  const scanAccount = async () => {
    if (!selectedAccount) return;

    setScanning(true);
    try {
      const response = await cleanupAPI.scan(selectedAccount);
      setCleanupData(response.data);
      setSelectedItems([]);
    } catch (error) {
      console.error('Failed to scan account:', error);
      alert('Failed to scan account: ' + (error.response?.data?.detail || error.message));
    } finally {
      setScanning(false);
    }
  };

  const handleSelectItem = (itemId) => {
    setSelectedItems(prev =>
      prev.includes(itemId)
        ? prev.filter(id => id !== itemId)
        : [...prev, itemId]
    );
  };

  const handleSelectAll = () => {
    const currentTabData = getCurrentTabData();
    if (selectedItems.length === currentTabData.length) {
      setSelectedItems([]);
    } else {
      setSelectedItems(currentTabData.map(item => item.id));
    }
  };

  const handleExecuteAction = async (actionType) => {
    if (selectedItems.length === 0) {
      alert('Please select at least one item');
      return;
    }

    const resourceTypeMap = {
      'instances': 'instance',
      'volumes': 'volume',
      'snapshots': 'snapshot',
      'elastic_ips': 'elastic_ip'
    };

    const actionPayload = {
      resource_ids: selectedItems,
      action_type: actionType,
      resource_type: resourceTypeMap[activeTab]
    };

    setExecuting(true);
    try {
      const response = await cleanupAPI.execute(selectedAccount, actionPayload);

      if (response.data.success) {
        alert(`Successfully ${actionType}d ${response.data.affected_resources.length} resource(s)`);
        scanAccount(); // Refresh data
        setSelectedItems([]);
      } else {
        alert(`Action partially completed. Errors: ${response.data.errors.join(', ')}`);
      }
    } catch (error) {
      console.error('Failed to execute cleanup action:', error);
      alert('Failed to execute action: ' + (error.response?.data?.detail || error.message));
    } finally {
      setExecuting(false);
    }
  };

  const getCurrentTabData = () => {
    if (!cleanupData) return [];

    switch (activeTab) {
      case 'instances':
        return cleanupData.instances || [];
      case 'volumes':
        return cleanupData.volumes || [];
      case 'snapshots':
        return cleanupData.snapshots || [];
      case 'elastic_ips':
        return cleanupData.elastic_ips || [];
      default:
        return [];
    }
  };

  // FIX: Helper function to get count for specific tab instead of active tab
  const getTabDataCount = (tabId) => {
    if (!cleanupData) return 0;

    switch (tabId) {
      case 'instances':
        return (cleanupData.instances || []).length;
      case 'volumes':
        return (cleanupData.volumes || []).length;
      case 'snapshots':
        return (cleanupData.snapshots || []).length;
      case 'elastic_ips':
        return (cleanupData.elastic_ips || []).length;
      default:
        return 0;
    }
  };

  const getStatusBadgeColor = (status) => {
    const colors = {
      'active': 'green',
      'orphaned': 'red',
      'terminating': 'yellow',
      'deleted': 'gray',
      'stopped': 'orange',
      'available': 'yellow',
      'unattached': 'red'
    };
    return colors[status] || 'gray';
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value);
  };

  const tabs = [
    { id: 'instances', label: 'Instances', icon: FiHardDrive },
    { id: 'volumes', label: 'Volumes', icon: FiDatabase },
    { id: 'snapshots', label: 'Snapshots', icon: FiDatabase },
    { id: 'elastic_ips', label: 'Elastic IPs', icon: FiGlobe }
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading accounts...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Resource Hygiene</h1>
            <p className="text-gray-600 mt-1">
              Scan and cleanup orphaned AWS resources across all regions
            </p>
          </div>
          <div className="flex gap-3">
            <select
              value={selectedAccount || ''}
              onChange={(e) => setSelectedAccount(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              disabled={scanning}
            >
              {accounts.map(account => (
                <option key={account.id} value={account.id}>
                  {account.name || account.aws_account_id}
                </option>
              ))}
            </select>
            <Button
              onClick={scanAccount}
              disabled={scanning || !selectedAccount}
              className="bg-indigo-600 hover:bg-indigo-700"
            >
              {scanning ? 'Scanning...' : 'Rescan'}
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        {cleanupData && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <StatsCard
              title="Potential Savings"
              value={formatCurrency(cleanupData.total_savings_potential)}
              icon={FiDollarSign}
              trend="up"
              trendValue="Monthly"
              iconColor="green"
            />
            <StatsCard
              title="Unauthorized Instances"
              value={cleanupData.unauthorized_instances_count}
              icon={FiHardDrive}
              iconColor="red"
            />
            <StatsCard
              title="Orphaned Volumes"
              value={cleanupData.orphaned_volumes_count}
              icon={FiDatabase}
              iconColor="yellow"
            />
            <StatsCard
              title="Unused IPs"
              value={cleanupData.unused_ips_count}
              icon={FiGlobe}
              iconColor="orange"
            />
          </div>
        )}

        {/* Scanned Regions Info */}
        {cleanupData && cleanupData.scanned_regions && cleanupData.scanned_regions.length > 0 && (
          <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-800">
              <strong>Multi-Region Scan:</strong> Scanned {cleanupData.scanned_regions.length} regions: {' '}
              {cleanupData.scanned_regions.slice(0, 5).join(', ')}
              {cleanupData.scanned_regions.length > 5 && ` and ${cleanupData.scanned_regions.length - 5} more`}
            </p>
          </div>
        )}
      </div>

      {scanning ? (
        <Card>
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
              <p className="mt-4 text-gray-600">Scanning AWS account across all regions...</p>
              <p className="text-sm text-gray-500 mt-2">This may take a few minutes</p>
            </div>
          </div>
        </Card>
      ) : cleanupData ? (
        <Card>
          {/* Tabs */}
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => {
                    setActiveTab(tab.id);
                    setSelectedItems([]);
                  }}
                  className={`
                    flex items-center gap-2 px-6 py-3 border-b-2 font-medium text-sm
                    ${activeTab === tab.id
                      ? 'border-indigo-500 text-indigo-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                    }
                  `}
                >
                  <tab.icon className="w-4 h-4" />
                  {tab.label}
                  <Badge color={activeTab === tab.id ? 'blue' : 'gray'}>
                    {getTabDataCount(tab.id)}
                  </Badge>
                </button>
              ))}
            </nav>
          </div>

          {/* Action Bar */}
          {getCurrentTabData().length > 0 && (
            <div className="flex items-center justify-between p-4 bg-gray-50 border-b">
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={selectedItems.length === getCurrentTabData().length && getCurrentTabData().length > 0}
                  onChange={handleSelectAll}
                  className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                />
                <span className="text-sm text-gray-700">
                  {selectedItems.length} selected
                </span>
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={() => handleExecuteAction('authorize')}
                  disabled={selectedItems.length === 0 || executing}
                  variant="secondary"
                  size="sm"
                >
                  <FiCheckCircle className="w-4 h-4 mr-1" />
                  Authorize
                </Button>
                <Button
                  onClick={() => {
                    if (window.confirm(`Are you sure you want to delete ${selectedItems.length} resource(s)? This action cannot be undone.`)) {
                      const actionType = activeTab === 'elastic_ips' ? 'release' :
                                        activeTab === 'instances' ? 'terminate' : 'delete';
                      handleExecuteAction(actionType);
                    }
                  }}
                  disabled={selectedItems.length === 0 || executing}
                  variant="danger"
                  size="sm"
                >
                  <FiTrash2 className="w-4 h-4 mr-1" />
                  {executing ? 'Processing...' :
                   activeTab === 'elastic_ips' ? 'Release' :
                   activeTab === 'instances' ? 'Terminate' : 'Delete'}
                </Button>
              </div>
            </div>
          )}

          {/* Data Table */}
          <div className="overflow-x-auto">
            {getCurrentTabData().length === 0 ? (
              <div className="text-center py-12">
                <FiCheckCircle className="w-12 h-12 text-green-500 mx-auto mb-3" />
                <p className="text-gray-600">No orphaned {activeTab} found</p>
                <p className="text-sm text-gray-500 mt-1">Your resources are clean!</p>
              </div>
            ) : (
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th scope="col" className="w-12 px-6 py-3">
                      <input
                        type="checkbox"
                        checked={selectedItems.length === getCurrentTabData().length}
                        onChange={handleSelectAll}
                        className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                      />
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Resource ID
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Name
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Region
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Monthly Cost
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Details
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {getCurrentTabData().map((item) => (
                    <tr
                      key={item.id}
                      className={`hover:bg-gray-50 ${selectedItems.includes(item.id) ? 'bg-indigo-50' : ''}`}
                    >
                      <td className="px-6 py-4 whitespace-nowrap">
                        <input
                          type="checkbox"
                          checked={selectedItems.includes(item.id)}
                          onChange={() => handleSelectItem(item.id)}
                          className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900">
                        {item.id}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {item.name}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                        {item.region}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Badge color={getStatusBadgeColor(item.status)}>
                          {item.status}
                        </Badge>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {formatCurrency(item.cost_per_month)}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500">
                        {activeTab === 'instances' && (
                          <span>Type: {item.metadata?.instance_type || 'N/A'}, State: {item.metadata?.state || 'N/A'}</span>
                        )}
                        {activeTab === 'volumes' && (
                          <span>Size: {item.metadata?.size_gb || 'N/A'} GB, Type: {item.metadata?.volume_type || 'N/A'}</span>
                        )}
                        {activeTab === 'snapshots' && (
                          <span>Size: {item.metadata?.size_gb || 'N/A'} GB, State: {item.metadata?.state || 'N/A'}</span>
                        )}
                        {activeTab === 'elastic_ips' && (
                          <span>IP: {item.metadata?.public_ip || 'N/A'}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      ) : (
        <Card>
          <div className="text-center py-12">
            <FiAlertTriangle className="w-12 h-12 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-600">No scan data available</p>
            <p className="text-sm text-gray-500 mt-1">Select an account and click "Rescan" to begin</p>
          </div>
        </Card>
      )}
    </div>
  );
};

export default CleanupDashboard;
