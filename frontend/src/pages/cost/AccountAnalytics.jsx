import React, { useState, useEffect } from 'react';
import {
  FiFilter,
  FiSearch,
  FiChevronDown,
  FiChevronRight,
  FiAlertCircle,
  FiCheckCircle,
  FiTrendingUp,
  FiTrendingDown
} from 'react-icons/fi';
import { metricsAPI } from '../../services/api';

const MOCK_DATA = [
  { id: '1', resource: 'eks-cluster-prod', type: 'Compute', service: 'EKS', account: 'prod-acct (112233)', mtd: 12450.50, proj: 15100.00, trend: 4.2, status: 'WARNING', children: [
    { id: '1a', resource: 'ng-spot-large', type: 'NodeGroup', service: 'EC2', mtd: 8400.00, proj: 10200.00, trend: 5.1 },
    { id: '1b', resource: 'ng-ondemand', type: 'NodeGroup', service: 'EC2', mtd: 4050.50, proj: 4900.00, trend: 2.1 }
  ]},
  { id: '2', resource: 'rds-main-db', type: 'Database', service: 'RDS', account: 'prod-acct (112233)', mtd: 3200.00, proj: 3800.00, trend: -1.5, status: 'OPTIMIZED', children: [] },
  { id: '3', resource: 's3-data-lake', type: 'Storage', service: 'S3', account: 'data-acct (445566)', mtd: 4100.25, proj: 4900.00, trend: 12.4, status: 'CRITICAL', children: [
    { id: '3a', resource: 'raw-events-bucket', type: 'Bucket', service: 'S3', mtd: 3800.00, proj: 4500.00, trend: 15.2 }
  ]},
  { id: '4', resource: 'eks-cluster-dev', type: 'Compute', service: 'EKS', account: 'dev-acct (778899)', mtd: 850.00, proj: 950.00, trend: 0.5, status: 'OPTIMIZED', children: [] }
];

const CostOverview = () => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [filter, setFilter] = useState('All');
  const [search, setSearch] = useState('');

  useEffect(() => {
    // Simulate API fetch
    setTimeout(() => {
      setData(MOCK_DATA);
      setLoading(false);
    }, 600);
  }, []);

  const toggleRow = (id) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(id)) newExpanded.delete(id);
    else newExpanded.add(id);
    setExpandedRows(newExpanded);
  };

  const filteredData = data.filter(item => {
    if (filter !== 'All' && item.service !== filter) return false;
    if (search && !item.resource.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const formatCurrency = (val) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);

  const renderStatus = (status) => {
    switch(status) {
      case 'OPTIMIZED': return <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20"><FiCheckCircle /> Optimized</span>;
      case 'WARNING': return <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-500/10 text-yellow-400 border border-yellow-500/20"><FiAlertCircle /> Review Needed</span>;
      case 'CRITICAL': return <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20"><FiAlertCircle /> High Waste</span>;
      default: return <span className="text-gray-500">-</span>;
    }
  };

  return (
    <div className="p-6 min-h-screen bg-[#0a0a0a] text-gray-300 font-sans">
      {/* Header Controls */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <div className="flex bg-[#1a1a1a] rounded-md p-1 border border-gray-800">
            {['All', 'EKS', 'EC2', 'RDS', 'S3'].map(opt => (
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

      <div className="mb-4">
        <h2 className="text-xs font-bold tracking-wider text-gray-500 uppercase">COST OVERVIEW (Dense Table View)</h2>
      </div>

      {/* Dense Table */}
      <div className="bg-[#111111] border border-gray-800 rounded-lg overflow-hidden">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-[#1a1a1a] border-b border-gray-800 text-gray-400 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 font-medium w-8"></th>
              <th className="px-4 py-3 font-medium">Resource</th>
              <th className="px-4 py-3 font-medium">Service</th>
              <th className="px-4 py-3 font-medium">Account</th>
              <th className="px-4 py-3 font-medium text-right">MTD Cost</th>
              <th className="px-4 py-3 font-medium text-right">Proj Cost</th>
              <th className="px-4 py-3 font-medium text-right">MoM Trend</th>
              <th className="px-4 py-3 font-medium text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {loading ? (
              <tr>
                <td colSpan="8" className="px-4 py-8 text-center text-gray-500">Loading cost telemetry...</td>
              </tr>
            ) : filteredData.length === 0 ? (
              <tr>
                <td colSpan="8" className="px-4 py-8 text-center text-gray-500">No resources found matching criteria.</td>
              </tr>
            ) : (
              filteredData.map(row => (
                <React.Fragment key={row.id}>
                  <tr 
                    onClick={() => toggleRow(row.id)}
                    className="hover:bg-[#1a1a1a] transition-colors cursor-pointer group"
                  >
                    <td className="px-4 py-3 text-gray-500 group-hover:text-gray-300">
                      {row.children?.length > 0 && (
                        expandedRows.has(row.id) ? <FiChevronDown /> : <FiChevronRight />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-200">{row.resource}</div>
                      <div className="text-xs text-gray-500">{row.type}</div>
                    </td>
                    <td className="px-4 py-3 text-gray-400">{row.service}</td>
                    <td className="px-4 py-3 text-gray-400">{row.account}</td>
                    <td className="px-4 py-3 text-right font-mono text-gray-300">{formatCurrency(row.mtd)}</td>
                    <td className="px-4 py-3 text-right font-mono text-gray-300">{formatCurrency(row.proj)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className={`inline-flex items-center gap-1 ${row.trend > 0 ? 'text-red-400' : 'text-green-400'}`}>
                        {row.trend > 0 ? <FiTrendingUp className="w-3 h-3" /> : <FiTrendingDown className="w-3 h-3" />}
                        {Math.abs(row.trend)}%
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {renderStatus(row.status)}
                    </td>
                  </tr>
                  
                  {/* Expanded Row */}
                  {expandedRows.has(row.id) && row.children?.map(child => (
                    <tr key={child.id} className="bg-[#0f0f0f] border-l-2 border-l-blue-500/30">
                      <td className="px-4 py-2"></td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <div className="w-4 border-t border-gray-700"></div>
                          <div>
                            <div className="text-sm text-gray-300">{child.resource}</div>
                            <div className="text-xs text-gray-600">{child.type}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2 text-gray-500 text-sm">{child.service}</td>
                      <td className="px-4 py-2 text-gray-500">↳</td>
                      <td className="px-4 py-2 text-right font-mono text-gray-400 text-sm">{formatCurrency(child.mtd)}</td>
                      <td className="px-4 py-2 text-right font-mono text-gray-400 text-sm">{formatCurrency(child.proj)}</td>
                      <td className="px-4 py-2 text-right text-sm">
                        <div className={`inline-flex items-center gap-1 ${child.trend > 0 ? 'text-red-400/70' : 'text-green-400/70'}`}>
                          {child.trend > 0 ? <FiTrendingUp className="w-3 h-3" /> : <FiTrendingDown className="w-3 h-3" />}
                          {Math.abs(child.trend)}%
                        </div>
                      </td>
                      <td className="px-4 py-2"></td>
                    </tr>
                  ))}
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default CostOverview;
