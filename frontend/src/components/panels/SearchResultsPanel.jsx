import React, { useState, useEffect } from 'react';
import { X, Search } from 'lucide-react';
import LoadingSpinner from '../common/LoadingSpinner';
import EmptyState from '../common/EmptyState';
import Badge from '../common/Badge';
import api from '../../services/api';

const SearchResultsPanel = ({ isOpen, onClose, query, onSelectResult }) => {
  const [results, setResults] = useState({ clients: [], instances: [], agents: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && query && query.length >= 2) {
      performSearch();
    } else {
      setResults({ clients: [], instances: [], agents: [] });
    }
  }, [isOpen, query]);

  const performSearch = async () => {
    setLoading(true);
    try {
      const data = await api.globalSearch(query);
      setResults(data);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const totalResults = results.clients.length + results.instances.length + results.agents.length;

  return (
    <>
      <div className="fixed inset-0 bg-black bg-opacity-50 z-40" onClick={onClose}></div>
      <div className="fixed top-20 left-1/2 transform -translate-x-1/2 w-full max-w-2xl bg-white rounded-lg shadow-2xl z-50 max-h-96 overflow-hidden">
        <div className="p-4 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold text-gray-900">
              Search Results {query && `for "${query}"`}
            </h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X size={20} />
            </button>
          </div>
          {totalResults > 0 && (
            <p className="text-sm text-gray-500 mt-1">{totalResults} results found</p>
          )}
        </div>

        <div className="overflow-y-auto max-h-80">
          {loading ? (
            <div className="flex justify-center items-center h-40">
              <LoadingSpinner />
            </div>
          ) : totalResults === 0 ? (
            <div className="p-8">
              <EmptyState
                icon={<Search size={48} />}
                title="No results found"
                description={query ? `No matches for "${query}"` : 'Enter a search query'}
              />
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {results.clients.length > 0 && (
                <div className="p-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">Clients</h4>
                  {results.clients.map(item => (
                    <div
                      key={item.id}
                      onClick={() => {
                        onSelectResult('client', item.id);
                        onClose();
                      }}
                      className="p-3 hover:bg-gray-50 rounded-lg cursor-pointer mb-2"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-gray-900">{item.name}</p>
                          <p className="text-xs text-gray-500">{item.id}</p>
                        </div>
                        <Badge variant={item.status === 'active' ? 'success' : 'danger'}>
                          {item.status}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {results.instances.length > 0 && (
                <div className="p-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">Instances</h4>
                  {results.instances.map(item => (
                    <div
                      key={item.id}
                      onClick={() => {
                        onSelectResult('instance', item.id);
                        onClose();
                      }}
                      className="p-3 hover:bg-gray-50 rounded-lg cursor-pointer mb-2"
                    >
                      <p className="text-sm font-medium text-gray-900">{item.name}</p>
                      <p className="text-xs text-gray-500">{item.client}</p>
                    </div>
                  ))}
                </div>
              )}

              {results.agents.length > 0 && (
                <div className="p-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">Agents</h4>
                  {results.agents.map(item => (
                    <div
                      key={item.id}
                      onClick={() => {
                        onSelectResult('agent', item.id);
                        onClose();
                      }}
                      className="p-3 hover:bg-gray-50 rounded-lg cursor-pointer mb-2"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-gray-900">{item.name}</p>
                          <p className="text-xs text-gray-500">{item.client}</p>
                        </div>
                        <Badge variant={item.status === 'online' ? 'success' : 'danger'}>
                          {item.status}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default SearchResultsPanel;
