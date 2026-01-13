
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { FiCheck, FiX, FiShield, FiAlertTriangle } from 'react-icons/fi';
import { authAPI } from '../../services/api';
import { useAuthStore } from '../../store/useStore';
import toast from 'react-hot-toast';

const InviteAcceptance = () => {
    const navigate = useNavigate();
    const { logout, user } = useAuthStore();
    const [loading, setLoading] = useState(false);

    const handleResponse = async (accept) => {
        setLoading(true);
        try {
            const response = await authAPI.respondToInvitation({ accept });
            if (accept) {
                toast.success(response.data?.message || "Welcome to the team!");
                // Update user status in store to ACTIVE
                useAuthStore.getState().updateUser({ ...user, status: 'ACTIVE' });
                // Also update localStorage
                const storedUser = JSON.parse(localStorage.getItem('user') || '{}');
                localStorage.setItem('user', JSON.stringify({ ...storedUser, status: 'ACTIVE' }));
                navigate('/dashboard');
            } else {
                toast.success("Invitation declined.");
                logout();
                navigate('/login');
            }
        } catch (error) {
            console.error("Invitation response failed:", error);
            toast.error(error.response?.data?.detail || "Failed to process response");
            if (error.response?.status === 401) {
                logout();
                navigate('/login');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-gray-800 rounded-xl shadow-2xl p-8 max-w-md w-full border border-gray-700 text-center"
            >
                <div className="w-16 h-16 bg-purple-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
                    <FiShield className="w-8 h-8 text-purple-400" />
                </div>

                <h2 className="text-2xl font-bold text-white mb-2">You've Been Invited!</h2>
                <p className="text-gray-400 mb-8">
                    You have been invited to join <span className="text-purple-400 font-semibold">{user?.organization_name || "an organization"}</span>.
                    Please accept to access the platform.
                </p>

                <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 mb-8 text-left flex gap-3">
                    <FiAlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-yellow-200/80">
                        Declining this invitation will <strong>permanently delete</strong> your account. You will need to be re-invited to join later.
                    </p>
                </div>

                <div className="space-y-3">
                    <button
                        onClick={() => handleResponse(true)}
                        disabled={loading}
                        className="w-full bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white font-medium py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50"
                    >
                        {loading ? 'Processing...' : (
                            <>
                                <FiCheck className="w-5 h-5" />
                                Accept Invitation
                            </>
                        )}
                    </button>

                    <button
                        onClick={() => handleResponse(false)}
                        disabled={loading}
                        className="w-full bg-gray-700 hover:bg-red-900/30 text-gray-300 hover:text-red-400 font-medium py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-all disabled:opacity-50 border border-transparent hover:border-red-500/30"
                    >
                        <FiX className="w-5 h-5" />
                        Decline & Delete Account
                    </button>
                </div>
            </motion.div>
        </div>
    );
};

export default InviteAcceptance;
