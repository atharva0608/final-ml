import React, { useState, useEffect } from 'react';
import { History, Download } from 'lucide-react';
import LoadingSpinner from '../../common/LoadingSpinner';
import ErrorMessage from '../../common/ErrorMessage';
import EmptyState from '../../common/EmptyState';
import Badge from '../../common/Badge';
import Button from '../../common/Button';
import api from '../../../services/api';

const ClientHistoryTab = ({ clientId }) => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadHistory = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getSwitchHistory(clientId);
        setHistory(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadHistory();
  }, [clientId]);

  if (loading) {
    return <div className="flex justify-center items-center h-64"><LoadingSpinner /></div>;
  }

  if (error) {
    return <ErrorMessage message={error} />;
  }

  return (
    <div className="bg-white p-4 md:p-6 rounded-xl shadow-sm border border-gray-200">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-6 gap-4">
        <h3 className="text-lg font-bold text-gray-900">Complete Switch History</h3>
        <div className="flex flex-wrap gap-2">
          <Button 
            variant="outline" 
            size="sm" 
            icon={<Download size={16} />}
            onClick={() => api.exportSwitchHistory(clientId)}
          >
            Export CSV
          </Button>
          <Badge variant="info">{history.length} Total</Badge>
        </div>
      </div>
      
      {history.length === 0 ? (
        <EmptyState
          icon={<History size={48} />}
          title="No Switch History"
          description="No switches have been performed yet"
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Time</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Instance</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">From → To</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Pools</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Trigger</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Price</th>
                <th className="text-left py-3 px-4 text-xs font-semibold text-gray-600 uppercase">Impact</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {history.map(sw => (
                <tr key={sw.id} className="hover:bg-gray-50">
                  <td className="py-3 px-4 text-sm text-gray-600">
                    {new Date(sw.timestamp).toLocaleString()}
                  </td>
                  <td className="py-3 px-4 text-sm font-mono text-gray-500">
                    {sw.instanceId}
                  </td>
                  <td className="py-3 px-4 text-sm">
                    <div className="flex items-center space-x-2">
                      <Badge variant={sw.fromMode === 'ondemand' ? 'danger' : 'success'}>
                        {sw.fromMode}
                      </Badge>
                      <span className="text-gray-400">→</span>
                      <Badge variant={sw.toMode === 'ondemand' ? 'danger' : 'success'}>
                        {sw.toMode}
                      </Badge>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-xs font-mono text-gray-500">
                    <div>{sw.fromPool}</div>
                    <div className="text-gray-400">→ {sw.toPool}</div>
                  </td>
                  <td className="py-3 px-4">
                    <Badge variant={sw.trigger === 'manual' ? 'warning' : 'info'}>
                      {sw.trigger}
                    </Badge>
                  </td>
                  <td className="py-3 px-4 text-sm font-semibold text-gray-900">
                    ${sw.price.toFixed(4)}
                  </td>
                  <td className="py-3 px-4 text-sm font-bold">
                    <span className={sw.savingsImpact >= 0 ? 'text-green-600' : 'text-red-600'}>
                      ${sw.savingsImpact.toFixed(4)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ClientHistoryTab;
