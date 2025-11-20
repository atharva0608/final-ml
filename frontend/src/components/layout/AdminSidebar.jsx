import React from 'react';
import {
  LayoutDashboard, Users, Server, Zap, History, Activity, X, Brain
} from 'lucide-react';
import LoadingSpinner from '../common/LoadingSpinner';
import Badge from '../common/Badge';

const AdminSidebar = ({ clients, onSelectClient, activeClientId, onSelectPage, activePage, isOpen, onClose, systemHealth }) => {
  const menuItems = [
    { id: 'overview', label: 'Overview', icon: <LayoutDashboard size={18} /> },
    { id: 'clients', label: 'Clients', icon: <Users size={18} /> },
    { id: 'agents', label: 'All Agents', icon: <Server size={18} /> },
    { id: 'instances', label: 'All Instances', icon: <Zap size={18} /> },
    { id: 'activity', label: 'Activity Log', icon: <History size={18} /> },
    { id: 'health', label: 'System Health', icon: <Activity size={18} /> },
  ];

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      <div className={`fixed top-0 left-0 h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white shadow-2xl overflow-y-auto z-50 transition-transform duration-300 ease-in-out ${isOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0 w-72`}>
        <div className="p-6 border-b border-gray-700 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-blue-600 p-2 rounded-lg">
                <Zap size={24} />
              </div>
              <div>
                <h1 className="text-xl font-bold">SmartDevops</h1>
                <p className="text-xs text-gray-400">Admin Dashboard</p>
              </div>
            </div>
            <button onClick={onClose} className="lg:hidden text-gray-400 hover:text-white">
              <X size={24} />
            </button>
          </div>
        </div>

        {/* System Status Card */}
        {systemHealth && (
          <div className="mx-3 mt-6 mb-3 bg-gray-800 rounded-lg p-3 border border-gray-700">
            <div className="flex items-center space-x-2 mb-3">
              <Brain size={16} className="text-blue-400" />
              <span className="text-xs font-semibold text-gray-200">System Status</span>
            </div>

            <div className="space-y-3 text-xs">
              {/* Decision Engine */}
              <div>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-gray-400">Decision Engine:</span>
                  <span className={`font-medium ${
                    systemHealth.decisionEngineStatus?.loaded
                      ? 'text-green-400'
                      : 'text-red-400'
                  }`}>
                    {systemHealth.decisionEngineStatus?.loaded ? 'Loaded' : 'Not Loaded'}
                  </span>
                </div>
                {systemHealth.decisionEngineStatus?.loaded && (
                  <div className="ml-2 space-y-1">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Type:</span>
                      <span className="text-gray-300">{systemHealth.decisionEngineStatus.type || 'ML-Based'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Version:</span>
                      <span className="text-gray-300">{systemHealth.decisionEngineStatus.version || 'v1.0.0'}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* ML Models */}
              <div className="border-t border-gray-700 pt-2">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-gray-400">ML Models:</span>
                  <span className={`font-medium ${
                    systemHealth.modelStatus?.loaded
                      ? 'text-green-400'
                      : 'text-gray-400'
                  }`}>
                    {systemHealth.modelStatus?.loaded ? 'Loaded' : 'Not Loaded'}
                  </span>
                </div>
                {systemHealth.modelStatus?.loaded && (
                  <div className="ml-2 space-y-1">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Files:</span>
                      <span className="text-gray-300">{systemHealth.modelStatus.filesUploaded || 0}</span>
                    </div>
                    {systemHealth.modelStatus.activeModels && systemHealth.modelStatus.activeModels.length > 0 && (
                      <div className="mt-1">
                        <span className="text-gray-500 block mb-1">Active:</span>
                        {systemHealth.modelStatus.activeModels.map((model, idx) => (
                          <div key={idx} className="flex items-center space-x-1 ml-2">
                            <div className="w-1 h-1 bg-green-400 rounded-full"></div>
                            <span className="text-gray-300">{model.name} v{model.version}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        <nav className="p-3 flex-shrink-0">
          <ul className="space-y-1">
            {menuItems.map(item => {
              const isActive = activePage === item.id;
              return (
                <li key={item.id}>
                  <button
                    onClick={() => {
                      onSelectPage(item.id);
                      if (window.innerWidth < 1024) onClose();
                    }}
                    className={`flex items-center w-full px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${isActive
                      ? 'bg-blue-600 text-white shadow-lg'
                      : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                      }`}
                  >
                    {item.icon}
                    <span className="ml-3">{item.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="p-3 mt-2 border-t border-gray-700 flex-1 overflow-y-auto">
          <h2 className="px-4 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Active Clients ({clients.length})
          </h2>
          <ul className="mt-2 space-y-1">
            {clients.length === 0 ? (
              <div className="flex justify-center p-4">
                <LoadingSpinner size="sm" />
              </div>
            ) : (
              clients.map(client => (
                <li key={client.id}>
                  <button
                    onClick={() => {
                      onSelectClient(client.id);
                      if (window.innerWidth < 1024) onClose();
                    }}
                    className={`flex items-center justify-between w-full px-4 py-3 rounded-lg text-sm transition-all duration-200 ${activeClientId === client.id
                      ? 'bg-blue-600 text-white shadow-lg'
                      : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                      }`}
                  >
                    <div className="flex items-center space-x-3 flex-1 min-w-0">
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${client.status === 'active' ? 'bg-green-400' : 'bg-red-400'}`}></div>
                      <span className="truncate">{client.name}</span>
                    </div>
                    <Badge variant={client.status === 'active' ? 'success' : 'danger'}>
                      {client.instances}
                    </Badge>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>

        <div className="p-4 border-t border-gray-700 flex-shrink-0">
          <div className="text-xs text-gray-400 text-center">
            <p>© 2025 SmartDevops</p>
          </div>
        </div>
      </div>
    </>
  );
};

export default AdminSidebar;
