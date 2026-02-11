/**
 * Authentication Hook
 */
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/useStore';
import { authAPI } from '../services/api';
import toast from 'react-hot-toast';

export const useAuth = () => {
  const navigate = useNavigate();
  const { user, isAuthenticated, setAuth, logout: clearAuth, updateUser } = useAuthStore();

  const login = async (email, password) => {
    try {
      const response = await authAPI.login({ email, password });
      const { user: userData, access_token, refresh_token } = response.data;

      // Transform user object: map user_id to id for frontend consistency
      const transformedUser = {
        ...userData,
        id: userData.user_id || userData.id
      };

      // Store tokens
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      localStorage.setItem('user', JSON.stringify(transformedUser));

      // Update store
      setAuth(transformedUser, access_token, refresh_token);

      toast.success('Login successful!');

      // Navigate based on user role
      if (userData.role === 'super_admin' || userData.role === 'SUPER_ADMIN') {
        navigate('/admin');
      } else {
        navigate('/dashboard');
      }

      return { success: true };
    } catch (error) {
      const message = error.response?.data?.message || 'Login failed';
      toast.error(message);
      return { success: false, error: message };
    }
  };

  const signup = async (email, password, organizationName, fullName) => {
    try {
      const response = await authAPI.signup({
        email,
        password,
        organization_name: organizationName,
        full_name: fullName
      });
      const { user: userData, access_token, refresh_token } = response.data;

      // Transform user object: map user_id to id for frontend consistency
      const transformedUser = {
        ...userData,
        id: userData.user_id || userData.id
      };

      // Store tokens
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      localStorage.setItem('user', JSON.stringify(transformedUser));

      // Update store
      setAuth(transformedUser, access_token, refresh_token);

      toast.success('Account created successfully!');

      // Navigate based on user role
      if (userData.role === 'super_admin' || userData.role === 'SUPER_ADMIN') {
        navigate('/admin');
      } else {
        navigate('/dashboard');
      }

      return { success: true };
    } catch (error) {
      const message = error.response?.data?.message || 'Signup failed';
      toast.error(message);
      return { success: false, error: message };
    }
  };

  const logout = async () => {
    try {
      await authAPI.logout();
    } catch (error) {
      // Continue logout even if API call fails
    } finally {
      // Clear storage
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');

      // Clear store
      clearAuth();

      toast.success('Logged out successfully');
      navigate('/login');
    }
  };

  const changePassword = async (oldPassword, newPassword) => {
    try {
      await authAPI.changePassword({
        old_password: oldPassword,
        new_password: newPassword,
      });
      toast.success('Password changed successfully');
      return { success: true };
    } catch (error) {
      const message = error.response?.data?.message || 'Failed to change password';
      toast.error(message);
      return { success: false, error: message };
    }
  };

  const refreshUser = async () => {
    try {
      const response = await authAPI.getMe();
      const userData = response.data;

      // Transform user object: map user_id to id for frontend consistency
      const transformedUser = {
        ...userData,
        id: userData.user_id || userData.id
      };

      localStorage.setItem('user', JSON.stringify(transformedUser));
      updateUser(transformedUser);
      return transformedUser;
    } catch (error) {
      console.error('Failed to refresh user:', error);
      return null;
    }
  };

  return {
    user,
    isAuthenticated,
    login,
    signup,
    logout,
    changePassword,
    refreshUser,
  };
};
