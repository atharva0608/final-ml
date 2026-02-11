import React, { useState, useEffect } from 'react';
import { approvalsAPI } from '../../services/api';
import { formatDistanceToNow } from 'date-fns';
import { useAuthStore } from '../../store/useStore';
import { FiCheck, FiClock, FiShield } from 'react-icons/fi';

const ActiveWindowBanner = () => {
    const [ticket, setTicket] = useState(null);
    const { isAuthenticated, accessToken } = useAuthStore();

    const checkWindow = async () => {
        if (!isAuthenticated || !accessToken) return;

        try {
            const res = await approvalsAPI.getActiveWindow();
            setTicket(res.data); // Null or ticket object
        } catch (err) {
            // Silently handle 401s as they are caught by the global interceptor
            if (err.response?.status !== 401) {
                console.error("Failed to check active window", err);
            }
        }
    };

    useEffect(() => {
        if (isAuthenticated && accessToken) {
            checkWindow();
            const interval = setInterval(checkWindow, 60000); // Check every minute
            return () => clearInterval(interval);
        }
    }, [isAuthenticated, accessToken]);

    if (!ticket || !ticket.has_active_window) return null;

    // Validate expires_at before trying to parse it
    if (!ticket.expires_at) return null;

    const expiresAt = new Date(ticket.expires_at);

    // Check if date is valid
    if (isNaN(expiresAt.getTime())) {
        console.error('Invalid expires_at date:', ticket.expires_at);
        return null;
    }

    // If expired, don't show (backend filters, but safety check)
    if (expiresAt < new Date()) return null;

    return (
        <div className="bg-gradient-to-r from-green-600 to-green-700 text-white px-6 py-3 shadow-lg fixed top-0 w-full z-50 flex justify-between items-center">
            <div className="flex items-center space-x-3">
                <div className="bg-white/20 rounded-full p-2">
                    <FiShield className="h-5 w-5" />
                </div>
                <div>
                    <div className="flex items-center space-x-2">
                        <FiCheck className="h-4 w-4" />
                        <span className="font-semibold">Active Access Window</span>
                    </div>
                    <div className="flex items-center space-x-2 text-sm text-green-100 mt-0.5">
                        <FiClock className="h-3 w-3" />
                        <span>Expires {formatDistanceToNow(expiresAt, { addSuffix: true })}</span>
                    </div>
                </div>
            </div>
            <div className="text-sm text-green-100 font-mono">
                Ticket #{ticket.approval_id?.slice(0, 8) || 'N/A'}
            </div>
        </div>
    );
};

export default ActiveWindowBanner;
