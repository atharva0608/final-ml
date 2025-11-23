import React, { useState, useEffect, useCallback } from 'react';
import { Users, Search, Plus, Key, Eye, Trash2 } from 'lucide-react';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import Badge from '../components/common/Badge';
import Button from '../components/common/Button';
import AddClientModal from '../components/modals/AddClientModal';
import ViewTokenModal from '../components/modals/ViewTokenModal';
import DeleteClientModal from '../components/modals/DeleteClientModal';
import api from '../services/api';

const AllClientsPage = ({ onSelectClient }) => {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [selectedClient, setSelectedClient] = useState(null);

  const loadClients = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getAllClients();
      setClients(data);
    } catch (error) {
      console.error('Failed to load clients:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  const filteredClients = clients.filter(c => 
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.id.toLowerCase().includes(search.toLowerCase())
  );

  const handleViewToken = (client, e) => {
    e.stopPropagation();
    setSelectedClient(client);
    setShowTokenModal(true);
  };

  const handleDeleteClient = (client, e) => {
    e.stopPropagation();
    setSelectedClient(client);
    setShowDeleteModal(true);
  };

  return (
    <>
      <div className="space-y-6">
        <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
            <div>
              <h3 className="text-lg font-bold text-gray-900">All Clients</h3>
              <p className="text-sm text-gray-500 mt-1">Manage client accounts and tokens</p>
            </div>
            <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
              <div className="relative flex-1 sm:w-64">
                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search clients..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                />
              </div>
              <Button
                variant="primary"
                size="md"
                icon={<Plus size={18} />}
                onClick={() => setShowAddModal(true)}
              >
                Add Client
              </Button>
            </div>
          </div>

          {loading ? (
            <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>
          ) : filteredClients.length === 0 ? (
            <EmptyState
              icon={<Users size={48} />}
              title="No Clients Found"
              description={search ? `No clients match "${search}"` : 'Click "Add Client" to create your first client'}
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredClients.map(client => (
                <div 
                  key={client.id}
                  className="border border-gray-200 rounded-lg p-5 hover:shadow-lg transition-all cursor-pointer bg-gradient-to-br from-white to-gray-50 relative group"
                >
                  {/* Card Header with Actions */}
                  <div className="flex items-start justify-between mb-4">
                    <div 
                      className="flex-1 min-w-0 cursor-pointer"
                      onClick={() => onSelectClient(client.id)}
                    >
                      <h4 className="text-lg font-bold text-gray-900 truncate">{client.name}</h4>
                      <p className="text-xs text-gray-500 font-mono mt-1 break-all">{client.id}</p>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Badge variant={client.status === 'active' ? 'success' : 'danger'}>
                        {client.status}
                      </Badge>
                    </div>
                  </div>

                  {/* Client Stats */}
                  <div 
                    className="grid grid-cols-2 gap-4 mb-4 cursor-pointer"
                    onClick={() => onSelectClient(client.id)}
                  >
                    <div>
                      <p className="text-xs text-gray-500">Instances</p>
                      <p className="text-xl font-bold text-gray-900">{client.instances}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Agents</p>
                      <p className="text-xl font-bold text-gray-900">
                        <span className="text-green-600">{client.agentsOnline}</span>
                        <span className="text-gray-400">/{client.agentsTotal}</span>
                      </p>
                    </div>
                  </div>

                  {/* Savings */}
                  <div 
                    className="pt-4 border-t border-gray-200 cursor-pointer"
                    onClick={() => onSelectClient(client.id)}
                  >
                    <p className="text-xs text-gray-500">Total Savings</p>
                    <p className="text-2xl font-bold text-green-600">${(client.totalSavings / 1000).toFixed(1)}k</p>
                  </div>

                  {/* Action Buttons - Always visible */}
                  <div className="mt-4 pt-4 border-t border-gray-200 flex space-x-2">
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<Key size={14} />}
                      onClick={(e) => handleViewToken(client, e)}
                      className="flex-1"
                    >
                      Token
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<Eye size={14} />}
                      onClick={() => onSelectClient(client.id)}
                      className="flex-1"
                    >
                      View
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      icon={<Trash2 size={14} />}
                      onClick={(e) => handleDeleteClient(client, e)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {showAddModal && (
        <AddClientModal
          onClose={() => setShowAddModal(false)}
          onSuccess={loadClients}
        />
      )}

      {showTokenModal && selectedClient && (
        <ViewTokenModal
          client={selectedClient}
          onClose={() => {
            setShowTokenModal(false);
            setSelectedClient(null);
          }}
          onRegenerate={loadClients}
        />
      )}

      {showDeleteModal && selectedClient && (
        <DeleteClientModal
          client={selectedClient}
          onClose={() => {
            setShowDeleteModal(false);
            setSelectedClient(null);
          }}
          onSuccess={loadClients}
        />
      )}
    </>
  );
};

export default AllClientsPage;
