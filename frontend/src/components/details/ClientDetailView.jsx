import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Server, Zap, BarChart3, History, ChevronLeft, Brain, Copy } from 'lucide-react';
import Button from '../common/Button';
import Badge from '../common/Badge';
import api from '../../services/api';
import ClientOverviewTab from './tabs/ClientOverviewTab';
import ClientAgentsTab from './tabs/ClientAgentsTab';
import ClientInstancesTab from './tabs/ClientInstancesTab';
import ClientSavingsTab from './tabs/ClientSavingsTab';
import ClientHistoryTab from './tabs/ClientHistoryTab';
import ClientModelsTab from './tabs/ClientModelsTab';
import ClientReplicasTab from './tabs/ClientReplicasTab';

const ClientDetailView = ({ clientId, onBack }) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [client, setClient] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadClient = async () => {
      setLoading(true);
      try {
        const data = await api.getClientDetails(clientId);
        setClient(data);
      } catch (error) {
        console.error('Failed to load client:', error);
      } finally {
        setLoading(false);
      }
    };
    loadClient();
  }, [clientId]);

  const tabs = [
    { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={16} /> },
    { id: 'agents', label: 'Agents', icon: <Server size={16} /> },
    { id: 'instances', label: 'Instances', icon: <Zap size={16} /> },
    { id: 'replicas', label: 'Replicas', icon: <Copy size={16} /> },
    { id: 'savings', label: 'Savings', icon: <BarChart3 size={16} /> },
    { id: 'models', label: 'Models', icon: <Brain size={16} /> },
    { id: 'history', label: 'History', icon: <History size={16} /> },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-4">
            <Button variant="outline" size="sm" onClick={onBack} icon={<ChevronLeft size={16} />}>
              Back
            </Button>
            <div>
              <h2 className="text-xl md:text-2xl font-bold text-gray-900">
                {loading ? 'Loading...' : client?.name}
              </h2>
              <p className="text-sm text-gray-500 mt-1 font-mono break-all">{clientId}</p>
            </div>
          </div>
          {client && (
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <p className="text-sm text-gray-500">Total Savings</p>
                <p className="text-xl md:text-2xl font-bold text-green-600">
                  ${(client.totalSavings / 1000).toFixed(1)}k
                </p>
              </div>
              <Badge variant={client.status === 'active' ? 'success' : 'danger'}>
                {client.status}
              </Badge>
            </div>
          )}
        </div>
        
        {/* Tabs */}
        <div className="flex space-x-2 mt-6 border-b border-gray-200 overflow-x-auto">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center space-x-2 px-4 py-3 text-sm font-medium transition-all border-b-2 whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>
      
      {/* Tab Content */}
      <div>
        {activeTab === 'overview' && <ClientOverviewTab clientId={clientId} />}
        {activeTab === 'agents' && <ClientAgentsTab clientId={clientId} />}
        {activeTab === 'instances' && <ClientInstancesTab clientId={clientId} />}
        {activeTab === 'replicas' && <ClientReplicasTab clientId={clientId} />}
        {activeTab === 'savings' && <ClientSavingsTab clientId={clientId} />}
        {activeTab === 'models' && <ClientModelsTab clientId={clientId} />}
        {activeTab === 'history' && <ClientHistoryTab clientId={clientId} />}
      </div>
    </div>
  );
};

export default ClientDetailView;
