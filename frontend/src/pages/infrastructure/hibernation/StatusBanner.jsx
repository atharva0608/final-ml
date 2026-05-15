import React, { useState, useEffect } from 'react';

/**
 * Real-Time Status Banner - Shows live hibernation status using SSE
 * Displays current state of all active schedules
 */
const StatusBanner = () => {
  const [liveStatuses, setLiveStatuses] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    // Connect to SSE endpoint for real-time updates
    const eventSource = new EventSource('http://localhost:8000/api/v1/sse/hibernation');

    eventSource.onopen = () => {
      console.log('SSE connection established');
      setIsConnected(true);
    };

    eventSource.addEventListener('hibernation_status', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('Received hibernation status:', data);

        setLiveStatuses(prev => {
          // Update or add new status
          const existingIndex = prev.findIndex(s => s.schedule_id === data.schedule_id);
          if (existingIndex >= 0) {
            const updated = [...prev];
            updated[existingIndex] = { ...data, timestamp: new Date() };
            return updated;
          }
          return [...prev, { ...data, timestamp: new Date() }];
        });

        setLastUpdate(new Date());
      } catch (error) {
        console.error('Error parsing SSE data:', error);
      }
    });

    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      setIsConnected(false);
      eventSource.close();

      // Attempt reconnection after 5 seconds
      setTimeout(() => {
        console.log('Attempting to reconnect SSE...');
        window.location.reload(); // Simple reconnect by reloading
      }, 5000);
    };

    // Cleanup on unmount
    return () => {
      eventSource.close();
    };
  }, []);

  // Remove completed/old statuses after 10 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setLiveStatuses(prev =>
        prev.filter(status => {
          const age = Date.now() - status.timestamp.getTime();
          return age < 10000 || status.status === 'in_progress';
        })
      );
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const getActionIcon = (action) => {
    const icons = {
      sleep: '💤',
      wake: '🟢',
      prewarm: '🔥',
      error: '❌'
    };
    return icons[action] || '🔄';
  };

  const getStatusColor = (status) => {
    const colors = {
      in_progress: 'bg-blue-500',
      completed: 'bg-green-500',
      error: 'bg-red-500',
      scheduled: 'bg-yellow-500'
    };
    return colors[status] || 'bg-gray-500';
  };

  const getStatusLabel = (status) => {
    const labels = {
      in_progress: 'In Progress',
      completed: 'Completed',
      error: 'Error',
      scheduled: 'Scheduled'
    };
    return labels[status] || status;
  };

  if (liveStatuses.length === 0 && isConnected) {
    return (
      <div className="bg-gray-100 border-b border-gray-300 px-6 py-2">
        <div className="flex items-center space-x-2 text-sm text-gray-600">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
          <span>Connected • All schedules idle</span>
        </div>
      </div>
    );
  }

  if (!isConnected && liveStatuses.length === 0) {
    return (
      <div className="bg-yellow-100 border-b border-yellow-300 px-6 py-2">
        <div className="flex items-center space-x-2 text-sm text-yellow-800">
          <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></div>
          <span>Connecting to real-time updates...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-r from-blue-500 to-purple-600 text-white px-6 py-3 shadow-lg">
      <div className="flex items-center justify-between">
        {/* Left: Live Status Indicator */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <div className="w-3 h-3 bg-white rounded-full animate-pulse"></div>
            <span className="font-bold">LIVE</span>
          </div>

          {/* Active Statuses */}
          <div className="flex items-center space-x-4">
            {liveStatuses.map((status, index) => (
              <div
                key={`${status.schedule_id}-${index}`}
                className="flex items-center space-x-2 bg-white bg-opacity-20 px-3 py-1 rounded-full"
              >
                <span className="text-2xl">{getActionIcon(status.action)}</span>
                <div className="text-sm">
                  <div className="font-medium">
                    {status.cluster_name || status.schedule_name || 'Unknown'}
                  </div>
                  <div className="text-xs opacity-90">
                    {status.action?.toUpperCase()} • {getStatusLabel(status.status)}
                  </div>
                </div>

                {status.status === 'in_progress' && (
                  <div className="ml-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                  </div>
                )}

                {status.status === 'completed' && (
                  <div className="ml-2 text-green-300">✓</div>
                )}

                {status.status === 'error' && (
                  <div className="ml-2 text-red-300">✗</div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Right: Connection Status */}
        <div className="text-sm opacity-90">
          {lastUpdate && (
            <span>Last update: {lastUpdate.toLocaleTimeString()}</span>
          )}
        </div>
      </div>

      {/* Error Details (if any) */}
      {liveStatuses.some(s => s.status === 'error') && (
        <div className="mt-2 text-sm bg-red-500 bg-opacity-30 px-3 py-2 rounded">
          {liveStatuses
            .filter(s => s.status === 'error')
            .map((status, index) => (
              <div key={index} className="flex items-center space-x-2">
                <span>❌</span>
                <span>
                  {status.error_message || 'An error occurred during hibernation'}
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
};

export default StatusBanner;
