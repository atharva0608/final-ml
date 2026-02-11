/**
 * ActiveJITBanner Component
 *
 * Displays active elevated access windows with countdown timers
 */
import React, { useState, useEffect } from 'react';
import { ShieldCheck, X, Clock } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { approvalsAPI } from '../../services/api';

const CountdownTimer = ({ targetDate }) => {
  const [timeLeft, setTimeLeft] = useState('');

  useEffect(() => {
    const updateTimer = () => {
      const now = new Date();
      const target = new Date(targetDate);
      const diff = target - now;

      if (diff <= 0) {
        setTimeLeft('Expired');
        return;
      }

      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diff % (1000 * 60)) / 1000);

      if (hours > 0) {
        setTimeLeft(`${hours}h ${minutes}m`);
      } else if (minutes > 0) {
        setTimeLeft(`${minutes}m ${seconds}s`);
      } else {
        setTimeLeft(`${seconds}s`);
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);

    return () => clearInterval(interval);
  }, [targetDate]);

  return (
    <span className="inline-flex items-center text-sm font-medium text-green-800">
      <Clock className="h-4 w-4 mr-1" />
      {timeLeft}
    </span>
  );
};

const ActiveJITBanner = () => {
  const [tickets, setTickets] = useState([]);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadActiveTickets();

    // Refresh every 30 seconds
    const interval = setInterval(loadActiveTickets, 30000);

    return () => clearInterval(interval);
  }, []);

  // Filter expired tickets every second
  useEffect(() => {
    const filterExpired = () => {
      const now = new Date();
      setTickets(prev => prev.filter(ticket => new Date(ticket.expires_at) > now));
    };

    const interval = setInterval(filterExpired, 1000);
    return () => clearInterval(interval);
  }, []);

  const loadActiveTickets = async () => {
    try {
      const response = await approvalsAPI.getMyJITTickets();
      const now = new Date();
      // Filter out any expired tickets from the response
      const activeTickets = (response.data || []).filter(
        ticket => new Date(ticket.expires_at) > now
      );
      setTickets(activeTickets);
      setLoading(false);
      // Reset dismissed state when new tickets arrive
      setDismissed(false);
    } catch (error) {
      console.error('Failed to load active tickets:', error);
      setLoading(false);
    }
  };

  if (loading || tickets.length === 0 || dismissed) {
    return null;
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className="bg-gradient-to-r from-green-50 to-green-100 border-l-4 border-green-500 p-4 mb-6 rounded-r-lg shadow-sm"
      >
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <ShieldCheck className="h-6 w-6 text-green-600" />
          </div>
          <div className="ml-3 flex-1">
            <h3 className="text-sm font-semibold text-green-900 mb-2">
              Active Elevated Access ({tickets.length})
            </h3>
            <div className="space-y-2">
              {tickets.map((ticket) => (
                <div
                  key={ticket.id}
                  className="flex items-center justify-between bg-white bg-opacity-60 rounded-md px-3 py-2"
                >
                  <div className="flex-1">
                    <span className="text-sm font-medium text-gray-900">
                      {ticket.feature_id}
                    </span>
                    {ticket.resource_id && (
                      <span className="ml-2 text-xs text-gray-500">
                        ({ticket.resource_id})
                      </span>
                    )}
                  </div>
                  <div className="flex items-center space-x-3">
                    <span className="text-xs text-gray-500">Expires in:</span>
                    <CountdownTimer targetDate={ticket.expires_at} />
                  </div>
                </div>
              ))}
            </div>
          </div>
          <button
            onClick={() => setDismissed(true)}
            className="ml-4 text-green-600 hover:text-green-800 transition-colors"
            aria-label="Dismiss banner"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

export default ActiveJITBanner;
