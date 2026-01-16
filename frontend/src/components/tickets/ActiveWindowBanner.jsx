import React, { useState, useEffect } from 'react';
import { ticketsAPI } from '../../services/api';
import { formatDistanceToNow } from 'date-fns';

const ActiveWindowBanner = () => {
    const [ticket, setTicket] = useState(null);

    const checkWindow = async () => {
        try {
            const res = await ticketsAPI.getActiveWindow();
            setTicket(res.data); // Null or ticket object
        } catch (err) {
            console.error("Failed to check active window", err);
        }
    };

    useEffect(() => {
        checkWindow();
        const interval = setInterval(checkWindow, 60000); // Check every minute
        return () => clearInterval(interval);
    }, []);

    if (!ticket) return null;

    const expiresAt = new Date(ticket.expires_at);
    // If expired, don't show (backend filters, but safety check)
    if (expiresAt < new Date()) return null;

    return (
        <div className="bg-green-600 text-white px-4 py-3 shadow-lg fixed top-0 w-full z-50 flex justify-between items-center">
            <div className="flex items-center space-x-2">
                <span className="font-bold">🔓 Active Access Window:</span>
                <span>You have unrestricted access for the next {formatDistanceToNow(expiresAt)}.</span>
            </div>
            <div className="text-sm opacity-90">
                Ticket #{ticket.id.slice(0, 8)}
            </div>
        </div>
    );
};

export default ActiveWindowBanner;
