import React, { useState, useEffect } from 'react';
import {
  Menu, Search, RefreshCw, Bell, Users, Server, Database, DollarSign, Activity
} from 'lucide-react';
import Button from '../common/Button';
import SearchResultsPanel from '../panels/SearchResultsPanel';
import NotificationPanel from '../panels/NotificationPanel';
import api from '../../services/api';

const AdminHeader = ({ stats, onRefresh, lastRefresh, onMenuToggle }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    loadUnreadCount();
    const interval = setInterval(loadUnreadCount, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadUnreadCount = async () => {
    try {
      const notifications = await api.getNotifications(null, 50);
      setUnreadCount(notifications.filter(n => !n.isRead).length);
    } catch (error) {
      console.error('Failed to load unread count:', error);
    }
  };

  const handleSearchResultSelect = (type, id) => {
    console.log('Selected:', type, id);
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setTimeout(() => setIsRefreshing(false), 500);
    }
  };

  return (
    <>
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="p-4 md:p-6">
          <div className="flex items-center justify-between mb-4 md:mb-6">
            <div className="flex items-center space-x-3">
              <button
                onClick={onMenuToggle}
                className="lg:hidden text-gray-600 hover:text-gray-900"
              >
                <Menu size={24} />
              </button>
              <div>
                <h2 className="text-xl md:text-2xl font-bold text-gray-900">Dashboard Overview</h2>
                <p className="text-xs md:text-sm text-gray-500 mt-1 hidden sm:block">Real-time monitoring and management</p>
              </div>
            </div>
            <div className="flex items-center space-x-2 md:space-x-4">
              <div className="relative hidden md:block">
                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onFocus={() => setShowSearch(true)}
                  className="pl-10 pr-4 py-2.5 w-64 xl:w-80 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                icon={<RefreshCw size={16} className={isRefreshing ? 'animate-spin' : ''} />}
                onClick={handleRefresh}
                loading={isRefreshing}
                disabled={isRefreshing}
                className="hidden sm:flex"
              >
                Refresh
              </Button>
              <button
                className="relative p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                onClick={() => setShowNotifications(true)}
              >
                <Bell size={20} />
                {unreadCount > 0 && (
                  <span className="absolute top-1 right-1 w-5 h-5 bg-red-500 rounded-full text-white text-xs flex items-center justify-center">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
            </div>
          </div>

          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 md:gap-4">
              {[
                { label: 'Accounts', value: stats.totalAccounts, color: 'blue', icon: <Users size={20} /> },
                { label: 'Agents', value: `${stats.agentsOnline}/${stats.agentsTotal}`, color: 'green', icon: <Server size={20} /> },
                { label: 'Pools', value: stats.poolsCovered, color: 'purple', icon: <Database size={20} /> },
                { label: 'Savings', value: `${(stats.totalSavings / 1000).toFixed(1)}k`, color: 'emerald', icon: <DollarSign size={20} /> },
                { label: 'Switches', value: stats.totalSwitches, color: 'orange', icon: <RefreshCw size={20} /> },
                { label: 'Auto/Manual', value: `${stats.modelSwitches}/${stats.manualSwitches}`, color: 'cyan', icon: <Activity size={20} /> },
              ].map((stat, idx) => (
                <div key={idx} className={`bg-gradient-to-br from-${stat.color}-50 to-${stat.color}-100 p-3 md:p-4 rounded-xl border border-${stat.color}-200`}>
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <p className={`text-xs text-${stat.color}-600 font-semibold uppercase truncate`}>{stat.label}</p>
                      <p className={`text-lg md:text-2xl font-bold text-${stat.color}-900 mt-1 truncate`}>{stat.value}</p>
                    </div>
                    <div className={`text-${stat.color}-600 flex-shrink-0 ml-2`}>{stat.icon}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {lastRefresh && (
            <p className="text-xs text-gray-400 mt-4">Last updated: {new Date(lastRefresh).toLocaleTimeString()}</p>
          )}
        </div>
      </header>

      <SearchResultsPanel
        isOpen={showSearch}
        onClose={() => setShowSearch(false)}
        query={searchQuery}
        onSelectResult={handleSearchResultSelect}
      />

      <NotificationPanel
        isOpen={showNotifications}
        onClose={() => {
          setShowNotifications(false);
          loadUnreadCount();
        }}
      />
    </>
  );
};

export default AdminHeader;
