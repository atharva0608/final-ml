/**
 * Account Settings Component
 * User profile, password change, and preferences
 */
import React, { useState } from 'react';
import { authAPI } from '../../services/api';
import { useAuthStore } from '../../store/useStore';
import { Card, Button, Input } from '../shared';
import { FiSave, FiLock, FiUser, FiBell, FiGlobe } from 'react-icons/fi';
import toast from 'react-hot-toast';

const AccountSettings = () => {
  const { user, setAuth } = useAuthStore();

  // Password change form
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });

  // Preferences
  const [preferences, setPreferences] = useState({
    timezone: 'UTC',
    email_notifications: true,
    optimization_alerts: true,
    weekly_reports: false,
    cost_threshold_alerts: true,
  });

  const [savingPassword, setSavingPassword] = useState(false);
  const [savingPreferences, setSavingPreferences] = useState(false);

  const handlePasswordChange = async (e) => {
    e.preventDefault();

    // Validation
    if (passwordData.new_password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    if (passwordData.new_password !== passwordData.confirm_password) {
      toast.error('Passwords do not match');
      return;
    }

    setSavingPassword(true);
    try {
      await authAPI.changePassword({
        current_password: passwordData.current_password,
        new_password: passwordData.new_password,
      });

      toast.success('Password updated successfully');
      setPasswordData({
        current_password: '',
        new_password: '',
        confirm_password: '',
      });
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to update password');
    } finally {
      setSavingPassword(false);
    }
  };

  const handleSavePreferences = async (e) => {
    e.preventDefault();

    setSavingPreferences(true);
    try {
      // In a real implementation, this would call a preferences API endpoint
      // For now, we'll just store it locally
      localStorage.setItem('user_preferences', JSON.stringify(preferences));
      toast.success('Preferences saved successfully');
    } catch (error) {
      toast.error('Failed to save preferences');
    } finally {
      setSavingPreferences(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Account Settings</h1>
        <p className="text-gray-600 mt-1">Manage your profile and preferences</p>
      </div>

      {/* User Profile Card */}
      <Card>
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-blue-600 rounded-full flex items-center justify-center text-white text-2xl font-bold">
            {user?.email?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-900">{user?.email}</h3>
            <p className="text-sm text-gray-600">
              Role: <span className="font-medium">{user?.role || 'CLIENT'}</span>
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Organization: {user?.organization_name || 'Default Organization'}
            </p>
          </div>
        </div>
      </Card>

      {/* Password Change Card */}
      <Card>
        <div className="flex items-center gap-3 mb-4">
          <FiLock className="w-5 h-5 text-gray-700" />
          <h3 className="text-lg font-semibold text-gray-900">Change Password</h3>
        </div>

        <form onSubmit={handlePasswordChange} className="space-y-4">
          <Input
            label="Current Password"
            type="password"
            value={passwordData.current_password}
            onChange={(e) => setPasswordData({ ...passwordData, current_password: e.target.value })}
            required
            autoComplete="current-password"
          />

          <Input
            label="New Password"
            type="password"
            value={passwordData.new_password}
            onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })}
            required
            minLength="8"
            help="At least 8 characters"
            autoComplete="new-password"
          />

          <Input
            label="Confirm New Password"
            type="password"
            value={passwordData.confirm_password}
            onChange={(e) => setPasswordData({ ...passwordData, confirm_password: e.target.value })}
            required
            minLength="8"
            autoComplete="new-password"
          />

          <div className="flex justify-end pt-2">
            <Button type="submit" variant="primary" icon={<FiSave />} disabled={savingPassword}>
              {savingPassword ? 'Updating...' : 'Update Password'}
            </Button>
          </div>
        </form>
      </Card>

      {/* Preferences Card */}
      <Card>
        <div className="flex items-center gap-3 mb-4">
          <FiUser className="w-5 h-5 text-gray-700" />
          <h3 className="text-lg font-semibold text-gray-900">Preferences</h3>
        </div>

        <form onSubmit={handleSavePreferences} className="space-y-6">
          {/* Timezone */}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
              <FiGlobe className="w-4 h-4" />
              Timezone
            </label>
            <select
              value={preferences.timezone}
              onChange={(e) => setPreferences({ ...preferences, timezone: e.target.value })}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="UTC">UTC</option>
              <option value="America/New_York">America/New_York (EST/EDT)</option>
              <option value="America/Chicago">America/Chicago (CST/CDT)</option>
              <option value="America/Denver">America/Denver (MST/MDT)</option>
              <option value="America/Los_Angeles">America/Los_Angeles (PST/PDT)</option>
              <option value="Europe/London">Europe/London (GMT/BST)</option>
              <option value="Europe/Paris">Europe/Paris (CET/CEST)</option>
              <option value="Asia/Tokyo">Asia/Tokyo (JST)</option>
              <option value="Asia/Shanghai">Asia/Shanghai (CST)</option>
              <option value="Australia/Sydney">Australia/Sydney (AEDT/AEST)</option>
            </select>
          </div>

          {/* Notification Preferences */}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-3">
              <FiBell className="w-4 h-4" />
              Email Notifications
            </label>

            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <h4 className="text-sm font-medium text-gray-900">All Notifications</h4>
                  <p className="text-xs text-gray-600 mt-0.5">Receive all email notifications</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setPreferences({ ...preferences, email_notifications: !preferences.email_notifications })
                  }
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    preferences.email_notifications ? 'bg-blue-600' : 'bg-gray-300'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      preferences.email_notifications ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <h4 className="text-sm font-medium text-gray-900">Optimization Alerts</h4>
                  <p className="text-xs text-gray-600 mt-0.5">Notify when optimization jobs complete</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setPreferences({ ...preferences, optimization_alerts: !preferences.optimization_alerts })
                  }
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    preferences.optimization_alerts ? 'bg-blue-600' : 'bg-gray-300'
                  }`}
                  disabled={!preferences.email_notifications}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      preferences.optimization_alerts ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <h4 className="text-sm font-medium text-gray-900">Weekly Reports</h4>
                  <p className="text-xs text-gray-600 mt-0.5">Receive weekly cost and savings summaries</p>
                </div>
                <button
                  type="button"
                  onClick={() => setPreferences({ ...preferences, weekly_reports: !preferences.weekly_reports })}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    preferences.weekly_reports ? 'bg-blue-600' : 'bg-gray-300'
                  }`}
                  disabled={!preferences.email_notifications}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      preferences.weekly_reports ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <h4 className="text-sm font-medium text-gray-900">Cost Threshold Alerts</h4>
                  <p className="text-xs text-gray-600 mt-0.5">Alert when costs exceed defined thresholds</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setPreferences({ ...preferences, cost_threshold_alerts: !preferences.cost_threshold_alerts })
                  }
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    preferences.cost_threshold_alerts ? 'bg-blue-600' : 'bg-gray-300'
                  }`}
                  disabled={!preferences.email_notifications}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      preferences.cost_threshold_alerts ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-4 border-t">
            <Button type="submit" variant="primary" icon={<FiSave />} disabled={savingPreferences}>
              {savingPreferences ? 'Saving...' : 'Save Preferences'}
            </Button>
          </div>
        </form>
      </Card>

      {/* Danger Zone */}
      <Card>
        <div className="border border-red-300 rounded-lg p-4 bg-red-50">
          <h3 className="text-lg font-semibold text-red-900 mb-2">Danger Zone</h3>
          <p className="text-sm text-red-700 mb-4">
            Once you delete your account, there is no going back. Please be certain.
          </p>
          <Button variant="secondary" className="border-red-300 text-red-700 hover:bg-red-100">
            Delete Account
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default AccountSettings;
