import React, { useState, useEffect } from 'react';
import { Key, X, Copy, CheckCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import Button from '../common/Button';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';
import api from '../../services/api';

const ViewTokenModal = ({ client, onClose, onRegenerate }) => {
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadToken();
  }, [client.id]);

  const loadToken = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getClientToken(client.id);
      setToken(result.token);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async () => {
    if (!window.confirm(
      `⚠️ WARNING: Regenerating the token will invalidate the current token.\n\n` +
      `All agents using the old token will lose connection and need to be updated.\n\n` +
      `Are you sure you want to continue?`
    )) {
      return;
    }

    setRegenerating(true);
    try {
      const result = await api.regenerateClientToken(client.id);
      setToken(result.token);
      if (onRegenerate) onRegenerate();
      alert('✓ Token regenerated successfully!\n\nMake sure to update all agents with the new token.');
    } catch (err) {
      alert('Failed to regenerate token: ' + err.message);
    } finally {
      setRegenerating(false);
    }
  };

  const handleCopy = () => {
    if (token) {
      // Try modern clipboard API first (works with HTTPS)
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(token)
          .then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          })
          .catch(err => {
            console.error('Clipboard API failed:', err);
            fallbackCopy(token);
          });
      } else {
        // Fallback for HTTP or older browsers
        fallbackCopy(token);
      }
    }
  };

  const fallbackCopy = (text) => {
    try {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();

      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);

      if (successful) {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } else {
        alert('Failed to copy. Please copy manually: ' + text);
      }
    } catch (err) {
      console.error('Fallback copy failed:', err);
      alert('Failed to copy. Please copy manually: ' + text);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-yellow-100 p-2 rounded-lg">
                <Key size={24} className="text-yellow-600" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-900">Client Token</h3>
                <p className="text-sm text-gray-500 mt-1">{client.name}</p>
              </div>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X size={24} />
            </button>
          </div>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="flex justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : error ? (
            <ErrorMessage message={error} onRetry={loadToken} />
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-600 uppercase mb-2">
                  API Token
                </label>
                <div className="relative">
                  <div className="bg-gray-50 px-4 py-3 rounded-lg border border-gray-300 pr-24">
                    <code className="text-sm font-mono text-gray-800 break-all">{token}</code>
                  </div>
                  <button
                    onClick={handleCopy}
                    className="absolute right-2 top-1/2 -translate-y-1/2 bg-white px-3 py-1.5 rounded border border-gray-300 hover:bg-gray-50 flex items-center space-x-1"
                  >
                    {copied ? (
                      <>
                        <CheckCircle size={14} className="text-green-600" />
                        <span className="text-xs font-medium text-green-600">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy size={14} className="text-gray-600" />
                        <span className="text-xs font-medium text-gray-600">Copy</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
                <div className="flex items-start space-x-2">
                  <AlertTriangle size={16} className="text-orange-600 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-orange-800">
                    Keep this token secure. Anyone with this token can register agents and access this client's data.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 flex justify-between">
          <Button
            variant="danger"
            size="sm"
            onClick={handleRegenerate}
            loading={regenerating}
            icon={<RefreshCw size={14} />}
          >
            Regenerate Token
          </Button>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ViewTokenModal;
