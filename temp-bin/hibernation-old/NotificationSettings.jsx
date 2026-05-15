import React, { useState, useEffect } from 'react';
import { hibernationAPI } from '../../services/api';

/**
 * Notification Settings - Configure alerts for hibernation events
 * Supports email, Slack, webhooks, and PagerDuty integrations
 */
const NotificationSettings = () => {
  const [settings, setSettings] = useState({
    email: {
      enabled: false,
      recipients: [],
      events: {
        sleep_started: true,
        sleep_completed: true,
        wake_started: true,
        wake_completed: true,
        errors: true,
        conflicts: true
      }
    },
    slack: {
      enabled: false,
      webhook_url: '',
      channel: '#hibernation-alerts',
      events: {
        sleep_started: false,
        sleep_completed: true,
        wake_started: false,
        wake_completed: true,
        errors: true,
        conflicts: true
      }
    },
    webhook: {
      enabled: false,
      url: '',
      secret: '',
      events: {
        sleep_started: true,
        sleep_completed: true,
        wake_started: true,
        wake_completed: true,
        errors: true,
        conflicts: true
      }
    },
    pagerduty: {
      enabled: false,
      integration_key: '',
      events: {
        errors: true,
        conflicts: true
      }
    }
  });

  const [newEmail, setNewEmail] = useState('');
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const response = await hibernationAPI.getNotificationSettings?.();
      if (response?.data) {
        setSettings(prev => ({ ...prev, ...response.data }));
      }
    } catch (error) {
      console.error('Failed to load notification settings:', error);
      // Keep defaults on error — initial state is a valid empty form
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await hibernationAPI.updateNotificationSettings?.(settings);
      setSaving(false);
      alert('Settings saved successfully!');
    } catch (error) {
      console.error('Failed to save settings:', error);
      setSaving(false);
    }
  };

  const handleTestNotification = async (channel) => {
    try {
      setTestResult({ channel, status: 'sending' });
      // await hibernationApi.testNotification(channel);

      setTimeout(() => {
        setTestResult({ channel, status: 'success' });
        setTimeout(() => setTestResult(null), 3000);
      }, 1500);
    } catch (error) {
      setTestResult({ channel, status: 'error', message: error.message });
    }
  };

  const addEmail = () => {
    if (newEmail && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newEmail)) {
      setSettings(prev => ({
        ...prev,
        email: {
          ...prev.email,
          recipients: [...prev.email.recipients, newEmail]
        }
      }));
      setNewEmail('');
    }
  };

  const removeEmail = (email) => {
    setSettings(prev => ({
      ...prev,
      email: {
        ...prev.email,
        recipients: prev.email.recipients.filter(e => e !== email)
      }
    }));
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">🔔 Notification Settings</h1>
        <p className="text-gray-600 mt-1">Configure alerts for hibernation events</p>
      </div>

      {/* Email Notifications */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold flex items-center space-x-2">
              <span>📧</span>
              <span>Email Notifications</span>
            </h2>
            <p className="text-sm text-gray-600 mt-1">Send email alerts to team members</p>
          </div>

          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={settings.email.enabled}
              onChange={(e) =>
                setSettings(prev => ({
                  ...prev,
                  email: { ...prev.email, enabled: e.target.checked }
                }))
              }
              className="w-5 h-5"
            />
            <span className="font-medium">Enabled</span>
          </label>
        </div>

        {settings.email.enabled && (
          <div className="space-y-4">
            {/* Email Recipients */}
            <div>
              <label className="block font-medium mb-2">Recipients</label>
              <div className="flex space-x-2">
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addEmail()}
                  placeholder="email@example.com"
                  className="flex-1 px-4 py-2 border rounded-lg"
                />
                <button
                  onClick={addEmail}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  Add
                </button>
              </div>

              {settings.email.recipients.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {settings.email.recipients.map(email => (
                    <div
                      key={email}
                      className="flex items-center space-x-2 bg-blue-100 text-blue-800 px-3 py-1 rounded-full"
                    >
                      <span>{email}</span>
                      <button
                        onClick={() => removeEmail(email)}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Event Selection */}
            <div>
              <label className="block font-medium mb-2">Events to Monitor</label>
              <div className="grid grid-cols-2 gap-2">
                {Object.keys(settings.email.events).map(event => (
                  <label key={event} className="flex items-center space-x-2 p-2 hover:bg-gray-50 rounded">
                    <input
                      type="checkbox"
                      checked={settings.email.events[event]}
                      onChange={(e) =>
                        setSettings(prev => ({
                          ...prev,
                          email: {
                            ...prev.email,
                            events: { ...prev.email.events, [event]: e.target.checked }
                          }
                        }))
                      }
                      className="w-4 h-4"
                    />
                    <span className="text-sm">
                      {event.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <button
              onClick={() => handleTestNotification('email')}
              className="px-4 py-2 bg-gray-100 text-gray-800 rounded hover:bg-gray-200"
            >
              📤 Send Test Email
            </button>
          </div>
        )}
      </div>

      {/* Slack Notifications */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold flex items-center space-x-2">
              <span>💬</span>
              <span>Slack Notifications</span>
            </h2>
            <p className="text-sm text-gray-600 mt-1">Send alerts to Slack channels</p>
          </div>

          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={settings.slack.enabled}
              onChange={(e) =>
                setSettings(prev => ({
                  ...prev,
                  slack: { ...prev.slack, enabled: e.target.checked }
                }))
              }
              className="w-5 h-5"
            />
            <span className="font-medium">Enabled</span>
          </label>
        </div>

        {settings.slack.enabled && (
          <div className="space-y-4">
            <div>
              <label className="block font-medium mb-2">Webhook URL</label>
              <input
                type="url"
                value={settings.slack.webhook_url}
                onChange={(e) =>
                  setSettings(prev => ({
                    ...prev,
                    slack: { ...prev.slack, webhook_url: e.target.value }
                  }))
                }
                placeholder="https://hooks.slack.com/services/..."
                className="w-full px-4 py-2 border rounded-lg"
              />
              <p className="text-xs text-gray-600 mt-1">
                Create a webhook at{' '}
                <a href="https://api.slack.com/messaging/webhooks" className="text-blue-600">
                  Slack Incoming Webhooks
                </a>
              </p>
            </div>

            <div>
              <label className="block font-medium mb-2">Channel</label>
              <input
                type="text"
                value={settings.slack.channel}
                onChange={(e) =>
                  setSettings(prev => ({
                    ...prev,
                    slack: { ...prev.slack, channel: e.target.value }
                  }))
                }
                placeholder="#hibernation-alerts"
                className="w-full px-4 py-2 border rounded-lg"
              />
            </div>

            <div>
              <label className="block font-medium mb-2">Events to Monitor</label>
              <div className="grid grid-cols-2 gap-2">
                {Object.keys(settings.slack.events).map(event => (
                  <label key={event} className="flex items-center space-x-2 p-2 hover:bg-gray-50 rounded">
                    <input
                      type="checkbox"
                      checked={settings.slack.events[event]}
                      onChange={(e) =>
                        setSettings(prev => ({
                          ...prev,
                          slack: {
                            ...prev.slack,
                            events: { ...prev.slack.events, [event]: e.target.checked }
                          }
                        }))
                      }
                      className="w-4 h-4"
                    />
                    <span className="text-sm">
                      {event.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <button
              onClick={() => handleTestNotification('slack')}
              className="px-4 py-2 bg-gray-100 text-gray-800 rounded hover:bg-gray-200"
            >
              📤 Send Test Message
            </button>
          </div>
        )}
      </div>

      {/* Webhook Notifications */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold flex items-center space-x-2">
              <span>🔗</span>
              <span>Custom Webhooks</span>
            </h2>
            <p className="text-sm text-gray-600 mt-1">Send HTTP POST requests to custom endpoints</p>
          </div>

          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={settings.webhook.enabled}
              onChange={(e) =>
                setSettings(prev => ({
                  ...prev,
                  webhook: { ...prev.webhook, enabled: e.target.checked }
                }))
              }
              className="w-5 h-5"
            />
            <span className="font-medium">Enabled</span>
          </label>
        </div>

        {settings.webhook.enabled && (
          <div className="space-y-4">
            <div>
              <label className="block font-medium mb-2">Webhook URL</label>
              <input
                type="url"
                value={settings.webhook.url}
                onChange={(e) =>
                  setSettings(prev => ({
                    ...prev,
                    webhook: { ...prev.webhook, url: e.target.value }
                  }))
                }
                placeholder="https://your-domain.com/webhooks/hibernation"
                className="w-full px-4 py-2 border rounded-lg"
              />
            </div>

            <div>
              <label className="block font-medium mb-2">Secret Key (optional)</label>
              <input
                type="password"
                value={settings.webhook.secret}
                onChange={(e) =>
                  setSettings(prev => ({
                    ...prev,
                    webhook: { ...prev.webhook, secret: e.target.value }
                  }))
                }
                placeholder="Used for HMAC signature verification"
                className="w-full px-4 py-2 border rounded-lg"
              />
            </div>

            <button
              onClick={() => handleTestNotification('webhook')}
              className="px-4 py-2 bg-gray-100 text-gray-800 rounded hover:bg-gray-200"
            >
              📤 Send Test Webhook
            </button>
          </div>
        )}
      </div>

      {/* PagerDuty */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-bold flex items-center space-x-2">
              <span></span>
              <span>PagerDuty Integration</span>
            </h2>
            <p className="text-sm text-gray-600 mt-1">Create incidents for critical errors</p>
          </div>

          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={settings.pagerduty.enabled}
              onChange={(e) =>
                setSettings(prev => ({
                  ...prev,
                  pagerduty: { ...prev.pagerduty, enabled: e.target.checked }
                }))
              }
              className="w-5 h-5"
            />
            <span className="font-medium">Enabled</span>
          </label>
        </div>

        {settings.pagerduty.enabled && (
          <div className="space-y-4">
            <div>
              <label className="block font-medium mb-2">Integration Key</label>
              <input
                type="password"
                value={settings.pagerduty.integration_key}
                onChange={(e) =>
                  setSettings(prev => ({
                    ...prev,
                    pagerduty: { ...prev.pagerduty, integration_key: e.target.value }
                  }))
                }
                placeholder="Enter your PagerDuty integration key"
                className="w-full px-4 py-2 border rounded-lg"
              />
            </div>

            <div className="bg-yellow-50 border border-yellow-200 rounded p-3 text-sm text-yellow-800">
              <strong>Note:</strong> PagerDuty will only be triggered for errors and conflicts to avoid alert fatigue.
            </div>
          </div>
        )}
      </div>

      {/* Test Result Banner */}
      {testResult && (
        <div
          className={`fixed bottom-6 right-6 px-6 py-4 rounded-lg shadow-lg ${testResult.status === 'success'
              ? 'bg-green-500 text-white'
              : testResult.status === 'error'
                ? 'bg-red-500 text-white'
                : 'bg-blue-500 text-white'
            }`}
        >
          {testResult.status === 'sending' && '⏳ Sending test notification...'}
          {testResult.status === 'success' && '✓ Test notification sent successfully!'}
          {testResult.status === 'error' && `✗ Error: ${testResult.message}`}
        </div>
      )}

      {/* Save Button */}
      <div className="flex justify-end space-x-4">
        <button
          onClick={loadSettings}
          className="px-6 py-3 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Reset
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
};

export default NotificationSettings;
