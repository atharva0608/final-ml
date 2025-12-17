import React, { createContext, useContext, useState, useEffect } from 'react';
import * as api from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [accountScope, setAccountScope] = useState('production'); // 'production' | 'lab'

    useEffect(() => {
        // Check local storage for existing session and validate token
        const validateSession = async () => {
            const storedUser = localStorage.getItem('ecc_user');
            const storedToken = localStorage.getItem('auth_token');

            if (storedUser && storedToken) {
                try {
                    // Parse stored user
                    const parsedUser = JSON.parse(storedUser);

                    // Validate token with backend
                    try {
                        await api.verifyToken();
                        // Token is valid, restore session
                        setUser(parsedUser);
                    } catch (error) {
                        // Token is invalid or expired, clear session
                        console.warn("Stored token is invalid or expired, clearing session");
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
            }
        };

        validateSession();
    }, []);

    const login = async (identifier, password) => {
        try {
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

            return true;
        } catch (error) {
            console.error("Login failed:", error);
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

    return (
        <AuthContext.Provider value={{ user, login, logout, accountScope, switchScope }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
