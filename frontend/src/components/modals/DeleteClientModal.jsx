import React, { useState } from 'react';
import { Trash2, X } from 'lucide-react';
import Button from '../common/Button';
import api from '../../services/api';

const DeleteClientModal = ({ client, onClose, onSuccess }) => {
  const [confirmName, setConfirmName] = useState('');
  const [loading, setLoading] = useState(false);

  const handleDelete = async () => {
    if (confirmName !== client.name) {
      alert('Client name does not match. Please type the exact client name to confirm deletion.');
      return;
    }

    setLoading(true);
    try {
      await api.deleteClient(client.id);
      alert(`✓ Client "${client.name}" has been deleted successfully.`);
      onSuccess();
      onClose();
    } catch (err) {
      alert('Failed to delete client: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            <div className="bg-red-100 p-2 rounded-lg">
              <Trash2 size={24} className="text-red-600" />
            </div>
            <div>
              <h3 className="text-xl font-bold text-gray-900">Delete Client</h3>
              <p className="text-sm text-gray-500 mt-1">This action cannot be undone</p>
            </div>
          </div>
        </div>

        <div className="p-6 space-y-4">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-sm text-red-800">
              <strong>Warning:</strong> Deleting this client will permanently remove:
            </p>
            <ul className="list-disc list-inside text-sm text-red-700 mt-2 space-y-1">
              <li>All agents and their configurations</li>
              <li>All instances and their history</li>
              <li>All switch events and savings data</li>
              <li>All notifications and system events</li>
            </ul>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Type <strong>"{client.name}"</strong> to confirm deletion:
            </label>
            <input
              type="text"
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
              placeholder="Enter client name"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent text-sm"
            />
          </div>
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-end space-x-3">
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={handleDelete}
            loading={loading}
            disabled={confirmName !== client.name}
            icon={<Trash2 size={16} />}
          >
            Delete Client
          </Button>
        </div>
      </div>
    </div>
  );
};

export default DeleteClientModal;
