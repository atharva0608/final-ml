import React, { useState } from 'react';
import {
  FiChevronDown, FiChevronRight, FiHardDrive, FiActivity,
  FiAlertCircle, FiCheckCircle, FiSearch, FiTrash2
} from 'react-icons/fi';

const MOCK_STORAGE = [
  { id: '1', resource: 'vol-0abcd1234efgh5678', type: 'EBS Volume', subtype: 'gp3', state: 'Unattached', age: '45 days', size: '500 GB', monthlyCost: 40.00, status: 'WASTE', account: 'prod-acct (112233)' },
  { id: '2', resource: 'snap-0xyz98765dcba4321', type: 'Snapshot', subtype: 'Automated', state: 'Orphaned', age: '120 days', size: '2 TB', monthlyCost: 100.00, status: 'WASTE', account: 'prod-acct (112233)' },
  { id: '3', resource: 'Cross-AZ Traffic (ap-south-1)', type: 'Data Transfer', subtype: 'Inter-AZ', state: 'Active', age: '-', size: '1.2 TB', monthlyCost: 12.00, status: 'WARNING', account: 'prod-acct (112233)' },
  { id: '4', resource: 'eipalloc-0123456789abcdef0', type: 'Elastic IP', subtype: 'Public', state: 'Unassociated', age: '15 days', size: '-', monthlyCost: 3.60, status: 'WASTE', account: 'dev-acct (778899)' }
];

const StorageTransfer = () => {
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [filter, setFilter] = useState('All');
  const [search, setSearch] = useState('');

  const toggleRow = (id) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(id)) newExpanded.delete(id);
    else newExpanded.add(id);
    setExpandedRows(newExpanded);
  };

  const filteredData = MOCK_STORAGE.filter(item => {
    if (filter !== 'All' && item.type !== filter && filter !== 'Waste' && filter !== 'Transfer') return false;
    if (filter === 'Waste' && item.status !== 'WASTE') return false;
    if (filter === 'Transfer' && item.type !== 'Data Transfer') return false;
    if (search && !item.resource.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);

  return (
    <div className="p-6 min-h-screen bg-[#0a0a0a] text-gray-300 font-sans">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="flex bg-[#1a1a1a] rounded-md p-1 border border-gray-800">
            {['All', 'Waste', 'EBS Volume', 'Snapshot', 'Transfer'].map(opt => (
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
            placeholder="Search volumes, IPs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 pr-4 py-1.5 bg-[#1a1a1a] border border-gray-800 rounded-md text-sm focus:outline-none focus:border-blue-500/50 text-gray-200 w-64 placeholder-gray-600"
          />
        </div>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xs font-bold tracking-wider text-gray-500 uppercase">STORAGE & TRANSFER WASTE (Dense Table View)</h2>
        <div className="text-xs font-mono text-red-400 font-bold">
          Total Waste Identified: {formatCurrency(MOCK_STORAGE.filter(i => i.status === 'WASTE').reduce((a, b) => a + b.monthlyCost, 0))}/mo
        </div>
      </div>

      <div className="bg-[#111111] border border-gray-800 rounded-lg overflow-hidden">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-[#1a1a1a] border-b border-gray-800 text-gray-400 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 font-medium w-8"></th>
              <th className="px-4 py-3 font-medium">Resource ID</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">State</th>
              <th className="px-4 py-3 font-medium">Age / Usage</th>
              <th className="px-4 py-3 font-medium text-right">Size</th>
              <th className="px-4 py-3 font-medium text-right text-red-500">Cost/mo</th>
              <th className="px-4 py-3 font-medium text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {filteredData.length === 0 ? (
              <tr>
                <td colSpan="8" className="px-4 py-8 text-center text-gray-500">No storage or transfer waste found.</td>
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
                      <div className="flex items-center gap-2">
                        {row.type.includes('Data') ? <FiActivity className="text-blue-400" /> : <FiHardDrive className="text-orange-400" />}
                        <div className="font-medium font-mono text-gray-200">{row.resource}</div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-gray-300">{row.type}</div>
                      <div className="text-xs text-gray-500">{row.subtype}</div>
                    </td>
                    <td className="px-4 py-3 text-gray-400">{row.state}</td>
                    <td className="px-4 py-3 text-gray-400">{row.age}</td>
                    <td className="px-4 py-3 text-right font-mono text-gray-400">{row.size}</td>
                    <td className="px-4 py-3 text-right font-mono text-gray-300">{formatCurrency(row.monthlyCost)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${row.status === 'WASTE' ? 'bg-red-500/10 text-red-400 border-red-500/20' : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'}`}>
                        {row.status === 'WASTE' ? <FiAlertCircle /> : <FiAlertCircle />} {row.status}
                      </span>
                    </td>
                  </tr>
                  
                  {expandedRows.has(row.id) && (
                    <tr className="bg-[#151515] border-l-2 border-l-red-500">
                      <td colSpan="8" className="px-8 py-6">
                        <div className="grid grid-cols-3 gap-8">
                          <div>
                            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Context</h4>
                            <div className="text-sm text-gray-300 space-y-2">
                              <p><strong>Account:</strong> {row.account}</p>
                              <p><strong>Detected:</strong> {new Date().toLocaleDateString()}</p>
                            </div>
                          </div>
                          <div>
                            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recommendation</h4>
                            <div className="text-sm text-gray-300 border border-gray-800 bg-[#1a1a1a] p-3 rounded">
                              <div className="font-medium text-red-400 mb-1">{row.type === 'Data Transfer' ? 'Enable Topology Aware Routing' : `Delete Unused ${row.type}`}</div>
                              <div className="text-xs text-gray-400">
                                {row.type === 'Data Transfer' 
                                  ? 'Cross-AZ traffic is high. Configure topology-aware routing on your EKS cluster to keep traffic within the same AZ.'
                                  : `This resource has been ${row.state.toLowerCase()} for ${row.age}. It is safe to delete.`}
                              </div>
                            </div>
                          </div>
                          <div className="flex flex-col justify-end gap-2">
                            {row.type !== 'Data Transfer' && (
                              <button className="w-full flex items-center justify-center gap-2 py-2 bg-red-600/90 hover:bg-red-600 text-white text-sm font-medium rounded transition-colors shadow-sm">
                                <FiTrash2 /> Terminate Resource
                              </button>
                            )}
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

export default StorageTransfer;
