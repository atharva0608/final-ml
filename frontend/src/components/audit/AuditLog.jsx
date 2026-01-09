/**
 * Audit Log Viewer Component
 * Displays immutable audit trail with filtering and diff viewer
 */
import React, { useState, useEffect } from 'react';
import { auditAPI } from '../../services/api';
import { Card, Button, Input, Badge } from '../shared';
import { FiDownload, FiEye, FiFilter, FiX, FiChevronLeft, FiChevronRight } from 'react-icons/fi';
import toast from 'react-hot-toast';
import { formatDate, formatDateTime } from '../../utils/formatters';

const EVENT_TYPES = [
  'user.signup',
  'user.login',
  'user.logout',
  'cluster.created',
  'cluster.updated',
  'cluster.deleted',
  'policy.created',
  'policy.updated',
  'policy.toggled',
  'template.created',
  'template.updated',
  'template.deleted',
  'schedule.created',
  'schedule.updated',
  'schedule.toggled',
  'optimization.started',
  'optimization.completed',
  'experiment.created',
  'experiment.started',
  'experiment.completed',
];

const AuditLog = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedLog, setSelectedLog] = useState(null);
  const [showDiffModal, setShowDiffModal] = useState(false);
  const [diffData, setDiffData] = useState(null);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const pageSize = 20;

  // Filters
  const [filters, setFilters] = useState({
    event_type: '',
    start_date: '',
    end_date: '',
    actor_id: '',
    resource_id: '',
  });
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    fetchLogs();
  }, [currentPage, filters]);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const params = {
        page: currentPage,
        page_size: pageSize,
        ...Object.fromEntries(Object.entries(filters).filter(([_, v]) => v !== '')),
      };

      const response = await auditAPI.list(params);
      setLogs(response.data.logs || []);
      setTotalPages(response.data.total_pages || 1);
      setTotalCount(response.data.total_count || 0);
    } catch (error) {
      toast.error('Failed to load audit logs');
    } finally {
      setLoading(false);
    }
  };

  const handleViewDiff = async (log) => {
    if (!log.before_state && !log.after_state) {
      toast.error('No state changes to display');
      return;
    }

    setSelectedLog(log);
    setShowDiffModal(true);

    // Calculate diff
    const before = log.before_state ? JSON.parse(JSON.stringify(log.before_state)) : {};
    const after = log.after_state ? JSON.parse(JSON.stringify(log.after_state)) : {};

    const diff = calculateDiff(before, after);
    setDiffData(diff);
  };

  const calculateDiff = (before, after) => {
    const allKeys = new Set([...Object.keys(before), ...Object.keys(after)]);
    const changes = [];

    allKeys.forEach((key) => {
      const beforeValue = before[key];
      const afterValue = after[key];

      if (JSON.stringify(beforeValue) !== JSON.stringify(afterValue)) {
        changes.push({
          key,
          before: beforeValue !== undefined ? JSON.stringify(beforeValue, null, 2) : '<not set>',
          after: afterValue !== undefined ? JSON.stringify(afterValue, null, 2) : '<removed>',
          type: beforeValue === undefined ? 'added' : afterValue === undefined ? 'removed' : 'modified',
        });
      }
    });

    return changes;
  };

  const handleExport = async () => {
    try {
      const params = {
        ...Object.fromEntries(Object.entries(filters).filter(([_, v]) => v !== '')),
      };

      const response = await auditAPI.exportLogs(params);

      // Create download link
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `audit-logs-${new Date().toISOString()}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      toast.success('Audit logs exported successfully');
    } catch (error) {
      toast.error('Failed to export audit logs');
    }
  };

  const clearFilters = () => {
    setFilters({
      event_type: '',
      start_date: '',
      end_date: '',
      actor_id: '',
      resource_id: '',
    });
    setCurrentPage(1);
  };

  const getEventBadgeColor = (eventType) => {
    if (eventType.includes('created')) return 'green';
    if (eventType.includes('updated')) return 'blue';
    if (eventType.includes('deleted')) return 'red';
    if (eventType.includes('login') || eventType.includes('signup')) return 'purple';
    if (eventType.includes('karpenter') || eventType.includes('autoscaling')) return 'indigo';
    return 'gray';
  };

  if (loading && logs.length === 0) {
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
          <h1 className="text-3xl font-bold text-gray-900">Audit Logs</h1>
          <p className="text-gray-600 mt-1">
            Immutable trail of all platform activities ({totalCount} total records)
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" icon={<FiFilter />} onClick={() => setShowFilters(!showFilters)}>
            {showFilters ? 'Hide Filters' : 'Show Filters'}
          </Button>
          <Button variant="primary" icon={<FiDownload />} onClick={handleExport}>
            Export
          </Button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <Card>
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-900">Filters</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Event Type</label>
                <select
                  value={filters.event_type}
                  onChange={(e) => {
                    setFilters({ ...filters, event_type: e.target.value });
                    setCurrentPage(1);
                  }}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">All Events</option>
                  {EVENT_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </div>

              <Input
                label="Start Date"
                type="date"
                value={filters.start_date}
                onChange={(e) => {
                  setFilters({ ...filters, start_date: e.target.value });
                  setCurrentPage(1);
                }}
              />

              <Input
                label="End Date"
                type="date"
                value={filters.end_date}
                onChange={(e) => {
                  setFilters({ ...filters, end_date: e.target.value });
                  setCurrentPage(1);
                }}
              />
            </div>

            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={clearFilters} icon={<FiX />}>
                Clear Filters
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Audit Log Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Timestamp
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Event
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actor
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Resource
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  IP Address
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-6 py-12 text-center text-gray-500">
                    No audit logs found
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {formatDateTime(log.timestamp)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <Badge color={getEventBadgeColor(log.event)}>{log.event}</Badge>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {log.actor_email || log.actor_id || 'System'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <div className="truncate max-w-xs" title={log.resource_id}>
                        {log.resource_type ? `${log.resource_type}:` : ''} {log.resource_id || '-'}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {log.ip_address || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {(log.before_state || log.after_state) && (
                        <button
                          onClick={() => handleViewDiff(log)}
                          className="text-blue-600 hover:text-blue-800 flex items-center gap-1"
                        >
                          <FiEye className="w-4 h-4" />
                          View Diff
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-6 py-4 border-t">
            <div className="text-sm text-gray-600">
              Page {currentPage} of {totalPages} ({totalCount} total records)
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                icon={<FiChevronLeft />}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
              >
                Next
                <FiChevronRight className="ml-1" />
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Diff Viewer Modal */}
      {showDiffModal && selectedLog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-2xl font-bold text-gray-900">State Changes</h2>
              <button onClick={() => setShowDiffModal(false)} className="text-gray-500 hover:text-gray-700">
                <FiX className="w-6 h-6" />
              </button>
            </div>

            <div className="mb-4 p-4 bg-gray-50 rounded-lg">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="font-medium text-gray-700">Event:</span>{' '}
                  <Badge color={getEventBadgeColor(selectedLog.event)}>{selectedLog.event}</Badge>
                </div>
                <div>
                  <span className="font-medium text-gray-700">Timestamp:</span>{' '}
                  {formatDateTime(selectedLog.timestamp)}
                </div>
                <div>
                  <span className="font-medium text-gray-700">Actor:</span>{' '}
                  {selectedLog.actor_email || selectedLog.actor_id || 'System'}
                </div>
                <div>
                  <span className="font-medium text-gray-700">Resource:</span>{' '}
                  {selectedLog.resource_id || '-'}
                </div>
              </div>
            </div>

            {diffData && diffData.length > 0 ? (
              <div className="space-y-4">
                {diffData.map((change, index) => (
                  <div key={index} className="border rounded-lg overflow-hidden">
                    <div className="bg-gray-100 px-4 py-2 font-medium text-gray-900 flex items-center gap-2">
                      {change.key}
                      <Badge
                        color={
                          change.type === 'added' ? 'green' : change.type === 'removed' ? 'red' : 'blue'
                        }
                        size="sm"
                      >
                        {change.type}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 divide-x">
                      <div className="p-4">
                        <div className="text-xs font-medium text-gray-500 mb-2">Before</div>
                        <pre className="text-xs text-gray-700 bg-red-50 p-2 rounded overflow-x-auto">
                          {change.before}
                        </pre>
                      </div>
                      <div className="p-4">
                        <div className="text-xs font-medium text-gray-500 mb-2">After</div>
                        <pre className="text-xs text-gray-700 bg-green-50 p-2 rounded overflow-x-auto">
                          {change.after}
                        </pre>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                No state changes detected
              </div>
            )}

            <div className="flex justify-end mt-6">
              <Button variant="secondary" onClick={() => setShowDiffModal(false)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AuditLog;
