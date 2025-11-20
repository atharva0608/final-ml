import React, { useState } from 'react';
import { UserPlus, X, AlertCircle, CheckCircle, Copy, AlertTriangle, Plus } from 'lucide-react';
import Button from '../common/Button';
import api from '../../services/api';

const AddClientModal = ({ onClose, onSuccess }) => {
  const [clientName, setClientName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [createdClient, setCreatedClient] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleCreate = async () => {
    if (!clientName.trim()) {
      setError('Client name is required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await api.createClient(clientName.trim());
      setCreatedClient(result.client);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyToken = () => {
    if (createdClient?.token) {
      navigator.clipboard.writeText(createdClient.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleClose = () => {
    if (createdClient) {
      onSuccess();
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Modal Header */}
        <div className="p-6 border-b border-gray-200 sticky top-0 bg-white">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-blue-100 p-2 rounded-lg">
                <UserPlus size={24} className="text-blue-600" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">
                  {createdClient ? 'Client Created!' : 'Add New Client'}
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  {createdClient
                    ? 'Save the token below - it won\'t be shown again'
                    : 'Create a new client account with auto-generated token'}
                </p>
              </div>
            </div>
            <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 transition-colors">
              <X size={24} />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6">
          {!createdClient ? (
            // Creation Form
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Client Name *
                </label>
                <input
                  type="text"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                  placeholder="e.g., Acme Corporation"
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                  onKeyPress={(e) => e.key === 'Enter' && handleCreate()}
                  autoFocus
                />
                <p className="text-xs text-gray-500 mt-2">
                  A unique client ID and secure token will be auto-generated
                </p>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <div className="flex items-center space-x-2">
                    <AlertCircle size={16} className="text-red-600" />
                    <p className="text-sm text-red-600">{error}</p>
                  </div>
                </div>
              )}
            </div>
          ) : (
            // Success View with Token Display
            <div className="space-y-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <div className="flex items-center space-x-2 mb-2">
                  <CheckCircle size={20} className="text-green-600" />
                  <p className="text-sm font-semibold text-green-800">Client Created Successfully!</p>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                    Client ID
                  </label>
                  <div className="bg-gray-50 px-4 py-3 rounded-lg border border-gray-200">
                    <code className="text-sm font-mono text-gray-800">{createdClient.id}</code>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                    Client Name
                  </label>
                  <div className="bg-gray-50 px-4 py-3 rounded-lg border border-gray-200">
                    <span className="text-sm text-gray-800">{createdClient.name}</span>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                    Client Token (API Key)
                  </label>
                  <div className="relative">
                    <div className="bg-yellow-50 px-4 py-3 rounded-lg border-2 border-yellow-300 pr-24">
                      <code className="text-sm font-mono text-gray-800 break-all">
                        {createdClient.token}
                      </code>
                    </div>
                    <button
                      onClick={handleCopyToken}
                      className="absolute right-2 top-1/2 -translate-y-1/2 bg-white px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 transition-colors flex items-center space-x-1"
                    >
                      {copied ? (
                        <>
                          <CheckCircle size={14} className="text-green-600" />
                          <span className="text-xs font-medium text-green-600">Copied!</span>
                        </>
                      ) : (
                        <>
                          <Copy size={14} className="text-gray-600" />
                          <span className="text-xs font-medium text-gray-600">Copy</span>
                        </>
                      )}
                    </button>
                  </div>
                  <div className="mt-2 bg-yellow-50 border border-yellow-200 rounded p-3">
                    <div className="flex items-start space-x-2">
                      <AlertTriangle size={16} className="text-yellow-600 flex-shrink-0 mt-0.5" />
                      <p className="text-xs text-yellow-800">
                        <strong>Important:</strong> Save this token securely! It will be used by the agent to authenticate with the server. You can regenerate it later, but all existing agents will need to be updated.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-6 border-t border-gray-200 flex justify-end space-x-3 sticky bottom-0 bg-white">
          {!createdClient ? (
            <>
              <Button variant="outline" onClick={onClose} disabled={loading}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleCreate}
                loading={loading}
                icon={<Plus size={16} />}
              >
                Create Client
              </Button>
            </>
          ) : (
            <Button variant="success" onClick={handleClose} icon={<CheckCircle size={16} />}>
              Done
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default AddClientModal;
