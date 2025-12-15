import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);

    useEffect(() => {
        // Check local storage for existing session
        const storedUser = localStorage.getItem('ecc_user');
        if (storedUser) {
            setUser(JSON.parse(storedUser));
        }
    }, []);

    const login = (username, password) => {
        // Mock Authentication Logic
        if (username === 'admin' && password === 'admin') {
            const userData = { username: 'admin', role: 'admin' };
            setUser(userData);
            localStorage.setItem('ecc_user', JSON.stringify(userData));
            return true;
        } else if (username === 'ath' && password === 'ath') {
            const userData = { username: 'ath', role: 'client', clientId: 'client-demo-001' }; // Map to TechCorp Solutions
            setUser(userData);
            localStorage.setItem('ecc_user', JSON.stringify(userData));
            return true;
        }

        // Check for custom created users
        const customUsers = JSON.parse(localStorage.getItem('ecc_custom_users') || '[]');
        const foundUser = customUsers.find(u => u.username === username && u.password === password);
        if (foundUser) {
            const userData = { username: foundUser.username, role: foundUser.role, clientId: foundUser.clientId };
            setUser(userData);
            localStorage.setItem('ecc_user', JSON.stringify(userData));
            return true;
        }

        return false;
    };

    const logout = () => {
        setUser(null);
        localStorage.removeItem('ecc_user');
    };

    return (
        <AuthContext.Provider value={{ user, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
