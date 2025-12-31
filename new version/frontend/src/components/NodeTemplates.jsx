import React, { useState, useEffect } from 'react';
import {
  Server,
  MoreVertical,
  Star,
  ChevronDown,
  Search,
  Sparkles
} from 'lucide-react';
import api from '../services/api';

/**
 * Node Templates Component
 *
 * Manages instance templates for autoscaling and optimization.
 * Matches CAST AI design with table layout, toggles, and template creation.
 */
const NodeTemplates = () => {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [showCreateMenu, setShowCreateMenu] = useState(false);

  // Mock data for demonstration - replace with API call
  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      setLoading(true);

      // Mock data matching CAST AI design
      const mockTemplates = [
        {
          id: '1',
          name: 'Default',
          isDefault: true,
          isFavorite: true,
          enabled: true,
          nodeConfiguration: 'default configuration',
          resourceOffering: 'All',
          nodeCount: 5,
          cpu: { value: 8, utilization: 89 },
          memory: { value: 5.72, unit: 'TiB', utilization: 89 }
        },
        {
          id: '2',
          name: 'gpu_heavy',
          isDefault: false,
          isFavorite: true,
          enabled: true,
          nodeConfiguration: 'default configuration',
          resourceOffering: 'All',
          nodeCount: 5,
          cpu: { value: 8, utilization: 89 },
          memory: { value: 5.72, unit: 'TiB', utilization: 89 }
        },
        {
          id: '3',
          name: 'Default',
          isDefault: true,
          isFavorite: false,
          enabled: true,
          nodeConfiguration: 'default configuration',
          resourceOffering: 'All',
          nodeCount: 5,
          cpu: { value: 8, utilization: 89 },
          memory: { value: 5.72, unit: 'TiB', utilization: 89 }
        },
        {
          id: '4',
          name: 'cpu_heavy',
          isDefault: false,
          isFavorite: false,
          enabled: true,
          nodeConfiguration: 'default configuration',
          resourceOffering: 'All',
          nodeCount: 5,
          cpu: { value: 8, utilization: 89 },
          memory: { value: 5.72, unit: 'TiB', utilization: 89 }
        }
      ];

      setTemplates(mockTemplates);
    } catch (error) {
      console.error('Error loading templates:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleTemplate = async (templateId) => {
    setTemplates(templates.map(t =>
      t.id === templateId ? { ...t, enabled: !t.enabled } : t
    ));
  };

  const toggleFavorite = async (templateId) => {
    setTemplates(templates.map(t =>
      t.id === templateId ? { ...t, isFavorite: !t.isFavorite } : t
    ));
  };

  const filteredTemplates = templates.filter(t =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-semibold text-gray-900">Node templates</h1>

          <div className="flex items-center gap-3">
            <span className="px-3 py-1 bg-gray-100 text-gray-600 text-xs font-medium rounded-full">
              EFFICIENCY
            </span>

            {/* Create Template Dropdown */}
            <div className="relative">
              <button
                onClick={() => setShowCreateMenu(!showCreateMenu)}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Create template
                <ChevronDown className="w-4 h-4" />
              </button>

              {showCreateMenu && (
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-10">
                  <button
                    onClick={() => {
                      setShowCreateMenu(false);
                      // Handle custom template creation
                    }}
                    className="w-full text-left px-4 py-2 hover:bg-gray-50 text-sm text-gray-700"
                  >
                    Custom template
                  </button>
                  <button
                    onClick={() => {
                      setShowCreateMenu(false);
                      // Handle generate templates
                    }}
                    className="w-full text-left px-4 py-2 hover:bg-gray-50 text-sm text-gray-700 flex items-center justify-between"
                  >
                    <span>Generate templates</span>
                    <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-medium rounded">
                      NEW
                    </span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Enter search keywords"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        <p className="text-sm text-gray-500 mt-4">
          {filteredTemplates.length} template{filteredTemplates.length !== 1 ? 's' : ''}
        </p>
      </div>

      {/* Templates Table */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <div className="flex items-center gap-2">
                  Template Name
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                  </svg>
                </div>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <div className="flex items-center gap-2">
                  Node Configuration
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <div className="flex items-center gap-2">
                  Res. Offering
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                  </svg>
                </div>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <div className="flex items-center gap-2">
                  Nodes
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                  </svg>
                </div>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <div className="flex items-center gap-2">
                  CPU
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <div className="flex items-center gap-2">
                  Memory
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
              </th>
              <th className="px-6 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {filteredTemplates.map((template) => (
              <tr key={template.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center gap-3">
                    {/* Toggle Switch */}
                    <button
                      onClick={() => toggleTemplate(template.id)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        template.enabled ? 'bg-blue-600' : 'bg-gray-300'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          template.enabled ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>

                    {/* Favorite Star */}
                    <button
                      onClick={() => toggleFavorite(template.id)}
                      className={`${
                        template.isFavorite ? 'text-blue-600' : 'text-gray-300 hover:text-gray-400'
                      }`}
                    >
                      <Star className="w-5 h-5" fill={template.isFavorite ? 'currentColor' : 'none'} />
                    </button>

                    {/* Template Name */}
                    <span className="text-sm font-medium text-blue-600">
                      {template.name}
                    </span>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center gap-2 text-sm text-gray-600">
                    <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    {template.nodeConfiguration}
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                  {template.resourceOffering}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                  {template.nodeCount}
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="flex-1">
                      <div className="flex items-baseline gap-1 mb-1">
                        <span className="text-sm font-medium text-gray-900">
                          {template.cpu.value} CPU
                        </span>
                        <span className="text-xs text-gray-500">
                          {template.cpu.utilization}%
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full"
                          style={{ width: `${template.cpu.utilization}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="flex-1">
                      <div className="flex items-baseline gap-1 mb-1">
                        <span className="text-sm font-medium text-gray-900">
                          {template.memory.value} {template.memory.unit}
                        </span>
                        <span className="text-xs text-gray-500">
                          {template.memory.utilization}%
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full"
                          style={{ width: `${template.memory.utilization}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right">
                  <button className="text-gray-400 hover:text-gray-600">
                    <MoreVertical className="w-5 h-5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default NodeTemplates;
