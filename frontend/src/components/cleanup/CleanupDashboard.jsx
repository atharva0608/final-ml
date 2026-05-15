import React, { useState } from 'react';
import {
  FiChevronDown, FiChevronRight, FiFilter, FiSearch,
  FiTrash2, FiPlay, FiSquare, FiAlertCircle, FiCheckCircle, FiClock
} from 'react-icons/fi';

const MOCK_HYGIENE = [
  { id: '1', resource: 'i-0abcdef1234567890', type: 'EC2 Instance', age: '14 days', rule: 'Untagged Resource', state: 'Running', action: 'Stop', cost: 120.00, status: 'VIOLATION' },
  { id: '2', resource: 'sg-0987654321fedcba', type: 'Security Group', age: '60 days', rule: 'Unused Security Group', state: 'Unattached', action: 'Delete', cost: 0.00, status: 'VIOLATION' },
  { id: '3', resource: 'vol-0xyz987654321abc', type: 'EBS Volume', age: '30 days', rule: 'Unattached Volume', state: 'Available', action: 'Snapshot & Delete', cost: 15.00, status: 'VIOLATION' },
  { id: '4', resource: 'eipalloc-0a1b2c3d4e5f6g7', type: 'Elastic IP', age: '45 days', rule: 'Unassociated IP', state: 'Available', action: 'Release', cost: 3.60, status: 'VIOLATION' }
];

const CleanupDashboard = () => {
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [filter, setFilter] = useState('All');
  const [search, setSearch] = useState('');

  const toggleRow = (id) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(id)) newExpanded.delete(id);
    else newExpanded.add(id);
    setExpandedRows(newExpanded);
  };

  const filteredData = MOCK_HYGIENE.filter(item => {
    if (filter !== 'All' && item.type !== filter) return false;
    if (search && !item.resource.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);

  return (
    <div className="p-6 min-h-screen bg-[#0a0a0a] text-gray-300 font-sans">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="flex bg-[#1a1a1a] rounded-md p-1 border border-gray-800">
            {['All', 'EC2 Instance', 'EBS Volume', 'Elastic IP', 'Security Group'].map(opt => (
              <button
                key={opt}
                onClick={() => setFilter(opt)}
                className={`px-4 py-1.5 text-sm rounded-sm transition-colors ${filter === opt ? 'bg-[#2a2a2a] text-white font-medium shadow-sm' : 'text-gray-400 hover:text-gray-200'}`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
        <div className="relative">
          <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search resources..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 pr-4 py-1.5 bg-[#1a1a1a] border border-gray-800 rounded-md text-sm focus:outline-none focus:border-blue-500/50 text-gray-200 w-64 placeholder-gray-600"
          />
        </div>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xs font-bold tracking-wider text-gray-500 uppercase">RESOURCE HYGIENE (Dense Table View)</h2>
        <div className="flex gap-6 text-xs font-mono">
          <span className="text-gray-400">Total Violations: <span className="text-gray-200">{MOCK_HYGIENE.length}</span></span>
          <span className="text-red-400">Potential Savings: <span className="font-bold">{formatCurrency(MOCK_HYGIENE.reduce((a, b) => a + b.cost, 0))}/mo</span></span>
        </div>
      </div>

      <div className="bg-[#111111] border border-gray-800 rounded-lg overflow-hidden">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-[#1a1a1a] border-b border-gray-800 text-gray-400 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 font-medium w-8"></th>
              <th className="px-4 py-3 font-medium">Resource ID</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Policy Violation</th>
              <th className="px-4 py-3 font-medium">State</th>
              <th className="px-4 py-3 font-medium text-right">Cost/mo</th>
              <th className="px-4 py-3 font-medium text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {filteredData.length === 0 ? (
              <tr>
                <td colSpan="7" className="px-4 py-8 text-center text-gray-500">No hygiene violations found.</td>
              </tr>
            ) : (
              filteredData.map(row => (
                <React.Fragment key={row.id}>
                  <tr 
                    onClick={() => toggleRow(row.id)}
                    className="hover:bg-[#1a1a1a] transition-colors cursor-pointer group"
                  >
                    <td className="px-4 py-3 text-gray-500 group-hover:text-gray-300">
                      {expandedRows.has(row.id) ? <FiChevronDown /> : <FiChevronRight />}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium font-mono text-gray-200">{row.resource}</div>
                    </td>
                    <td className="px-4 py-3 text-gray-400">{row.type}</td>
                    <td className="px-4 py-3 text-gray-300">{row.rule}</td>
                    <td className="px-4 py-3 text-gray-400">{row.state}</td>
                    <td className="px-4 py-3 text-right font-mono text-gray-400">{formatCurrency(row.cost)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border bg-red-500/10 text-red-400 border-red-500/20">
                        <FiAlertCircle /> {row.status}
                      </span>
                    </td>
                  </tr>
                  
                  {expandedRows.has(row.id) && (
                    <tr className="bg-[#151515] border-l-2 border-l-purple-500/50">
                      <td colSpan="7" className="px-8 py-6">
                        <div className="grid grid-cols-3 gap-8">
                          <div>
                            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Context</h4>
                            <div className="text-sm text-gray-300 space-y-2">
                              <p><strong>Age:</strong> {row.age}</p>
                              <p><strong>Detected:</strong> {new Date().toLocaleDateString()}</p>
                            </div>
                          </div>
                          <div>
                            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recommended Action</h4>
                            <div className="text-sm text-gray-300 border border-gray-800 bg-[#1a1a1a] p-3 rounded">
                              <div className="font-medium text-purple-400 mb-1">{row.action}</div>
                              <div className="text-xs text-gray-400">
                                Enforce resource hygiene policy. Proceed with action to remediate the violation.
                              </div>
                            </div>
                          </div>
                          <div className="flex flex-col justify-end gap-2">
                            <button className="w-full flex items-center justify-center gap-2 py-2 bg-purple-600/90 hover:bg-purple-600 text-white text-sm font-medium rounded transition-colors shadow-sm">
                              {row.action.includes('Delete') ? <FiTrash2 /> : row.action.includes('Stop') ? <FiSquare /> : <FiPlay />} Execute {row.action}
                            </button>
                            <button className="w-full py-1.5 bg-transparent hover:bg-gray-800 text-gray-400 text-sm font-medium rounded transition-colors border border-gray-700">
                              View in AWS Console
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default CleanupDashboard;