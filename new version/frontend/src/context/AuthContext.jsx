import React, { createContext, useContext, useState, useEffect } from 'react';
import * as api from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true); // Add loading state
    const [accountScope, setAccountScope] = useState('production'); // 'production' | 'lab'

    useEffect(() => {
        // Check local storage for existing session and validate token
        const validateSession = async () => {
            const storedUser = localStorage.getItem('ecc_user');
            const storedToken = localStorage.getItem('auth_token');

            // If no stored credentials, immediately finish loading
            if (!storedUser || !storedToken) {
                setLoading(false);
                return;
            }

            try {
                // Parse stored user
                const parsedUser = JSON.parse(storedUser);

                // Validate token with backend (with timeout)
                const timeoutPromise = new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('Token validation timeout')), 3000)
                );

                try {
                    await Promise.race([api.verifyToken(), timeoutPromise]);
                    // Token is valid, restore session
                    setUser(parsedUser);
                } catch (error) {
                    // Token is invalid, expired, or backend unavailable - clear session
                    console.warn("Token validation failed, clearing session:", error.message);
                    localStorage.removeItem('ecc_user');
                    localStorage.removeItem('auth_token');
                    setUser(null);
                }
            } catch (error) {
                console.error("Failed to parse user session:", error);
                localStorage.removeItem('ecc_user');
                localStorage.removeItem('auth_token');
                setUser(null);
            }

            setLoading(false); // Finish loading after validation
        };

        validateSession();
    }, []);

    const login = async (identifier, password) => {
        try {
            setLoading(true);
            // Call real backend API with identifier (can be username or email)
            const response = await api.login(identifier, password);

            // Store JWT token
            localStorage.setItem('auth_token', response.access_token);

            // Store user data (map 'user' role to 'client' for frontend routing)
            const userData = {
                id: response.user.id,
                username: response.user.username,
                email: response.user.email,
                role: response.user.role === 'user' ? 'client' : response.user.role
            };
            setUser(userData);
            localStorage.setItem('ecc_user', JSON.stringify(userData));
            setLoading(false);

            return true;
        } catch (error) {
            console.error("Login failed:", error);
            setLoading(false);
            return false;
        }
    };

    const logout = () => {
        setUser(null);
        setAccountScope('production');
        localStorage.removeItem('ecc_user');
        localStorage.removeItem('auth_token');
    };

    const switchScope = (scope) => {
        setAccountScope(scope);
    };

    // Show loading screen while validating token
    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-slate-50">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p className="text-slate-600">Verifying session...</p>
                </div>
            </div>
        );
    }

    return (
        <AuthContext.Provider value={{ user, loading, login, logout, accountScope, switchScope }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
