import React, { useState } from 'react';
import { FiGrid, FiCheckCircle, FiXCircle, FiRefreshCw, FiSettings, FiExternalLink, FiPlus, FiAlertCircle, FiMonitor, FiCpu, FiCloud, FiActivity, FiShield, FiLock, FiDatabase } from 'react-icons/fi';
import { useHeaderStore } from '../../store/useStore';

const C = {
  bg: "#f5f6f8",
  surface: "#ffffff",
  surfaceHover: "#fafafa",
  border: "#e4e6ea",
  text: "#111318",
  muted: "#5a6272",
  subtle: "#98a1b0",
  accent: "#2563eb",
  accentLight: "#eff6ff",
  green: "#16a34a", greenBg: "#f0fdf4",
  amber: "#b45309", amberBg: "#fffbeb",
  red: "#dc2626", redBg: "#fef2f2",
};

const integrations = [
  {
    id: 'karpenter',
    name: 'Karpenter',
    description: 'Just-in-time node provisioning for Kubernetes clusters.',
    category: 'Provisioning',
    status: 'connected',
    version: 'v0.32.1',
    lastSync: '2 mins ago',
    icon: <FiCpu className="w-6 h-6 text-indigo-600" />,
    color: 'indigo'
  },
  {
    id: 'keda',
    name: 'KEDA',
    description: 'Event-driven autoscaling for Kubernetes workloads.',
    category: 'Scaling',
    status: 'connected',
    version: 'v2.12.0',
    lastSync: '5 mins ago',
    icon: <FiActivity className="w-6 h-6 text-blue-600" />,
    color: 'blue'
  },
  {
    id: 'aws_billing',
    name: 'AWS Cost Explorer',
    description: 'Cost and usage data ingestion for accurate financial tracking.',
    category: 'Billing',
    status: 'warning',
    version: 'v2',
    lastSync: '4 hours ago',
    icon: <FiCloud className="w-6 h-6 text-orange-500" />,
    color: 'orange',
    alertMessage: 'Credentials expiring in 3 days'
  },
  {
    id: 'datadog',
    name: 'Datadog',
    description: 'Enhanced metrics and application profiling integration.',
    category: 'Observability',
    status: 'disconnected',
    icon: <FiMonitor className="w-6 h-6 text-purple-600" />,
    color: 'purple'
  },
  {
    id: 'vault',
    name: 'HashiCorp Vault',
    description: 'Secret management for agent authentication.',
    category: 'Security',
    status: 'connected',
    version: 'v1.14.0',
    lastSync: '1 min ago',
    icon: <FiLock className="w-6 h-6 text-slate-700" />,
    color: 'slate'
  },
  {
    id: 'prometheus',
    name: 'Prometheus',
    description: 'Scrapes custom metrics for HPA and VPA scaling decisions.',
    category: 'Observability',
    status: 'connected',
    version: 'v2.45.0',
    lastSync: 'Just now',
    icon: <FiDatabase className="w-6 h-6 text-red-500" />,
    color: 'red'
  }
];

const IntegrationCard = ({ integration }) => {
  const isConnected = integration.status === 'connected';
  const isWarning = integration.status === 'warning';
  const isDisconnected = integration.status === 'disconnected';

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden hover:shadow-md transition-shadow duration-200 flex flex-col">
      <div className="p-5 border-b border-gray-100">
        <div className="flex justify-between items-start mb-4">
          <div className={`p-3 rounded-lg bg-${integration.color}-50 inline-block`}>
            {integration.icon}
          </div>
          <div>
            {isConnected && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-green-50 text-green-700 text-xs font-medium border border-green-200">
                <FiCheckCircle className="w-3.5 h-3.5" /> Active
              </span>
            )}
            {isWarning && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-50 text-amber-700 text-xs font-medium border border-amber-200">
                <FiAlertCircle className="w-3.5 h-3.5" /> Warning
              </span>
            )}
            {isDisconnected && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-gray-100 text-gray-600 text-xs font-medium border border-gray-200">
                <FiXCircle className="w-3.5 h-3.5" /> Disconnected
              </span>
            )}
          </div>
        </div>
        
        <h3 className="text-lg font-bold text-gray-900 mb-1">{integration.name}</h3>
        <p className="text-sm text-gray-500 line-clamp-2 min-h-[40px]">{integration.description}</p>
        
        {isWarning && integration.alertMessage && (
          <div className="mt-3 p-2 bg-amber-50 rounded text-xs text-amber-800 flex items-start gap-1.5 border border-amber-100">
            <FiAlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{integration.alertMessage}</span>
          </div>
        )}
      </div>
      
      <div className="p-4 bg-gray-50 flex-grow flex flex-col justify-end">
        {!isDisconnected ? (
          <div className="flex justify-between items-center text-xs text-gray-500 mb-3">
            <div className="flex items-center gap-1">
              <FiRefreshCw className="w-3.5 h-3.5" />
              <span>Synced {integration.lastSync}</span>
            </div>
            <div className="font-medium bg-white px-2 py-0.5 rounded border border-gray-200 shadow-sm">
              {integration.version}
            </div>
          </div>
        ) : (
          <div className="text-xs text-gray-500 mb-3 italic">
            Not configured
          </div>
        )}
        
        <div className="flex gap-2 mt-auto">
          {!isDisconnected ? (
            <>
              <button className="flex-1 px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors shadow-sm flex items-center justify-center gap-2">
                <FiSettings className="w-4 h-4 text-gray-500" />
                Configure
              </button>
              <button className="px-3 py-2 bg-white border border-gray-300 rounded-lg text-gray-500 hover:text-indigo-600 hover:border-indigo-200 transition-colors shadow-sm" title="View Documentation">
                <FiExternalLink className="w-4 h-4" />
              </button>
            </>
          ) : (
            <button className="w-full px-3 py-2 bg-indigo-50 text-indigo-700 border border-indigo-100 rounded-lg text-sm font-medium hover:bg-indigo-100 transition-colors shadow-sm flex items-center justify-center gap-2">
              <FiPlus className="w-4 h-4" />
              Connect
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default function Integrations() {
  const headerStore = useHeaderStore();
  const [filter, setFilter] = useState('all');

  React.useEffect(() => {
    headerStore.setRightContent(
      <button className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors flex items-center gap-2 shadow-sm">
        <FiPlus className="w-4 h-4" />
        Add Integration
      </button>
    );
    return () => headerStore.clearHeader();
  }, []);

  const filteredIntegrations = integrations.filter(i => {
    if (filter === 'all') return true;
    if (filter === 'connected') return i.status === 'connected' || i.status === 'warning';
    if (filter === 'disconnected') return i.status === 'disconnected';
    return true;
  });

  return (
    <div className="min-h-full bg-gray-50 p-6 md:p-8">
      <div className="max-w-screen-xl mx-auto space-y-8">
        
        {/* Header Section */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2.5 bg-white border border-gray-200 rounded-xl shadow-sm">
              <FiGrid className="w-6 h-6 text-indigo-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Integrations</h1>
              <p className="text-sm text-gray-500 mt-1">
                Manage connections to cloud providers, infrastructure operators, and observability tools.
              </p>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 border-b border-gray-200 pb-4">
          <button 
            onClick={() => setFilter('all')}
            className={`px-4 py-2 text-sm font-medium rounded-full transition-colors ${filter === 'all' ? 'bg-gray-900 text-white' : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50'}`}
          >
            All Integrations
          </button>
          <button 
            onClick={() => setFilter('connected')}
            className={`px-4 py-2 text-sm font-medium rounded-full transition-colors ${filter === 'connected' ? 'bg-gray-900 text-white' : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50'}`}
          >
            Connected
          </button>
          <button 
            onClick={() => setFilter('disconnected')}
            className={`px-4 py-2 text-sm font-medium rounded-full transition-colors ${filter === 'disconnected' ? 'bg-gray-900 text-white' : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50'}`}
          >
            Available
          </button>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {filteredIntegrations.map(integration => (
            <IntegrationCard key={integration.id} integration={integration} />
          ))}
        </div>

      </div>
    </div>
  );
}
