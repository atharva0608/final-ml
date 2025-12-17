import React, { createContext, useContext, useState, useEffect } from 'react';
import * as api from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [accountScope, setAccountScope] = useState('production'); // 'production' | 'lab'

    useEffect(() => {
        // Check local storage for existing session
        const storedUser = localStorage.getItem('ecc_user');
        const storedToken = localStorage.getItem('auth_token');
        if (storedUser && storedToken) {
            try {
                setUser(JSON.parse(storedUser));
            } catch (error) {
                console.error("Failed to parse user session:", error);
                localStorage.removeItem('ecc_user');
                localStorage.removeItem('auth_token');
                setUser(null);
            }
        }
    }, []);

    const login = async (username, password) => {
        try {
            // Map username to email for test users
            const emailMap = {
                'admin': 'admin@test.com',
                'client': 'client@test.com'
            };
            const email = emailMap[username] || username;

            // Call real backend API
            const response = await api.login(email, password);

            // Store JWT token
            localStorage.setItem('auth_token', response.access_token);

            // Store user data
            const userData = {
                id: response.user.id,
                username: response.user.username,
                email: response.user.email,
                role: response.user.role
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
