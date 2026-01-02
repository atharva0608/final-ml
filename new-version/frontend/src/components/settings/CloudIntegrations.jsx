/**
 * Cloud Integrations Component
 * AWS account linking and credential management
 */
import React, { useState, useEffect } from 'react';
import { accountAPI } from '../../services/api';
import { Card, Button, Input, Badge } from '../shared';
import { FiPlus, FiTrash2, FiCheck, FiAlertCircle, FiExternalLink } from 'react-icons/fi';
import toast from 'react-hot-toast';

const CloudIntegrations = () => {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);

  const [formData, setFormData] = useState({
    aws_account_id: '',
    role_arn: '',
    external_id: '',
    region: 'us-east-1',
    is_default: false,
  });

  const AWS_REGIONS = [
    'us-east-1',
    'us-east-2',
    'us-west-1',
    'us-west-2',
    'eu-west-1',
    'eu-west-2',
    'eu-central-1',
    'ap-southeast-1',
    'ap-southeast-2',
    'ap-northeast-1',
    'ap-south-1',
  ];

  useEffect(() => {
    fetchAccounts();
  }, []);

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      const response = await accountAPI.list();
      setAccounts(response.data.accounts || []);
    } catch (error) {
      toast.error('Failed to load AWS accounts');
    } finally {
      setLoading(false);
    }
  };

  const handleAddAccount = async (e) => {
    e.preventDefault();

    // Validation
    if (!/^\d{12}$/.test(formData.aws_account_id)) {
      toast.error('AWS Account ID must be 12 digits');
      return;
    }

    if (!formData.role_arn.startsWith('arn:aws:iam::')) {
      toast.error('Invalid IAM Role ARN format');
      return;
    }

    try {
      await accountAPI.create(formData);
      toast.success('AWS account linked successfully');
      setShowAddModal(false);
      fetchAccounts();
      resetForm();
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to link AWS account');
    }
  };

  const handleValidate = async (accountId) => {
    try {
      const response = await accountAPI.validate(accountId);
      if (response.data.is_valid) {
        toast.success('AWS credentials validated successfully');
        fetchAccounts();
      } else {
        toast.error(response.data.error_message || 'Validation failed');
      }
    } catch (error) {
      toast.error('Failed to validate credentials');
    }
  };

  const handleSetDefault = async (accountId) => {
    try {
      await accountAPI.setDefault(accountId);
      toast.success('Default account updated');
      fetchAccounts();
    } catch (error) {
      toast.error('Failed to set default account');
    }
  };

  const handleDelete = async (accountId) => {
    if (!window.confirm('Are you sure you want to unlink this AWS account?')) return;

    try {
      await accountAPI.delete(accountId);
      toast.success('AWS account unlinked');
      fetchAccounts();
    } catch (error) {
      toast.error('Failed to delete account');
    }
  };

  const resetForm = () => {
    setFormData({
      aws_account_id: '',
      role_arn: '',
      external_id: '',
      region: 'us-east-1',
      is_default: false,
    });
  };

  const generateExternalId = () => {
    const externalId = `spot-optimizer-${Math.random().toString(36).substring(2, 15)}`;
    setFormData({ ...formData, external_id: externalId });
    toast.success('External ID generated');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Cloud Integrations</h1>
          <p className="text-gray-600 mt-1">Connect your AWS accounts for optimization</p>
        </div>
        <Button variant="primary" icon={<FiPlus />} onClick={() => setShowAddModal(true)}>
          Link AWS Account
        </Button>
      </div>

      {/* Accounts List */}
      {accounts.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <p className="text-gray-500 text-lg">No AWS accounts linked</p>
            <p className="text-gray-400 mt-2">Link your first AWS account to start optimizing</p>
            <Button variant="primary" className="mt-4" onClick={() => setShowAddModal(true)}>
              Link AWS Account
            </Button>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6">
          {accounts.map((account) => (
            <Card key={account.id} className="hover:shadow-lg transition-shadow">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-3">
                    <h3 className="text-lg font-semibold text-gray-900">
                      AWS Account: {account.aws_account_id}
                    </h3>
                    {account.is_default && (
                      <Badge color="green">
                        <FiCheck className="w-3 h-3 mr-1" />
                        Default
                      </Badge>
                    )}
                    {account.is_validated ? (
                      <Badge color="green">
                        <FiCheck className="w-3 h-3 mr-1" />
                        Validated
                      </Badge>
                    ) : (
                      <Badge color="yellow">
                        <FiAlertCircle className="w-3 h-3 mr-1" />
                        Pending Validation
                      </Badge>
                    )}
                  </div>

                  <div className="space-y-2 text-sm">
                    <div className="flex items-start gap-2">
                      <span className="text-gray-600 w-32">Role ARN:</span>
                      <span className="font-mono text-xs text-gray-900 break-all">{account.role_arn}</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-gray-600 w-32">External ID:</span>
                      <span className="font-mono text-xs text-gray-700">{account.external_id || 'N/A'}</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-gray-600 w-32">Primary Region:</span>
                      <span className="font-medium text-gray-900">{account.region}</span>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="text-gray-600 w-32">Linked:</span>
                      <span className="text-gray-700">
                        {new Date(account.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col gap-2 ml-4">
                  {!account.is_validated && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleValidate(account.id)}
                    >
                      Validate
                    </Button>
                  )}
                  {!account.is_default && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleSetDefault(account.id)}
                    >
                      Set Default
                    </Button>
                  )}
                  <button
                    onClick={() => handleDelete(account.id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <FiTrash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Setup Instructions */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 mb-3">How to Link AWS Account</h3>
        <div className="text-sm text-gray-600 space-y-3">
          <p>To allow Spot Optimizer to access your AWS account, you need to create an IAM role with the following steps:</p>
          <ol className="list-decimal list-inside space-y-2 ml-2">
            <li>
              Open the{' '}
              <a
                href="https://console.aws.amazon.com/iam/home#/roles"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline inline-flex items-center gap-1"
              >
                IAM Console <FiExternalLink className="w-3 h-3" />
              </a>
            </li>
            <li>Click "Create role" and select "Another AWS account"</li>
            <li>Enter our AWS account ID: <code className="bg-gray-100 px-2 py-1 rounded">123456789012</code></li>
            <li>Check "Require external ID" and use the generated External ID from the form</li>
            <li>Attach the following managed policies:
              <ul className="list-disc list-inside ml-4 mt-1">
                <li><code className="text-xs bg-gray-100 px-1 py-0.5 rounded">AmazonEKSClusterPolicy</code></li>
                <li><code className="text-xs bg-gray-100 px-1 py-0.5 rounded">AmazonEC2ReadOnlyAccess</code></li>
                <li><code className="text-xs bg-gray-100 px-1 py-0.5 rounded">CloudWatchReadOnlyAccess</code></li>
              </ul>
            </li>
            <li>Name the role (e.g., "SpotOptimizerRole") and create it</li>
            <li>Copy the Role ARN and paste it in the form below</li>
          </ol>
        </div>
      </Card>

      {/* Add Account Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">Link AWS Account</h2>

            <form onSubmit={handleAddAccount} className="space-y-4">
              <Input
                label="AWS Account ID"
                value={formData.aws_account_id}
                onChange={(e) => setFormData({ ...formData, aws_account_id: e.target.value })}
                placeholder="123456789012"
                pattern="\d{12}"
                required
                help="12-digit AWS account number"
              />

              <Input
                label="IAM Role ARN"
                value={formData.role_arn}
                onChange={(e) => setFormData({ ...formData, role_arn: e.target.value })}
                placeholder="arn:aws:iam::123456789012:role/SpotOptimizerRole"
                required
                help="Full ARN of the IAM role created for Spot Optimizer"
              />

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  External ID
                </label>
                <div className="flex gap-2">
                  <Input
                    value={formData.external_id}
                    onChange={(e) => setFormData({ ...formData, external_id: e.target.value })}
                    placeholder="spot-optimizer-xxxxx"
                    required
                    help="Used for secure cross-account access"
                  />
                  <Button type="button" variant="outline" onClick={generateExternalId}>
                    Generate
                  </Button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Primary Region
                </label>
                <select
                  value={formData.region}
                  onChange={(e) => setFormData({ ...formData, region: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {AWS_REGIONS.map((region) => (
                    <option key={region} value={region}>
                      {region}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center">
                <input
                  id="is_default"
                  type="checkbox"
                  checked={formData.is_default}
                  onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                />
                <label htmlFor="is_default" className="ml-2 text-sm text-gray-900">
                  Set as default account
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setShowAddModal(false);
                    resetForm();
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary">
                  Link Account
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CloudIntegrations;
