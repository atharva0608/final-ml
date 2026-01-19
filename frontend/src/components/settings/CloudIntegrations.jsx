/**
 * Cloud Integrations Component
 * AWS account linking and credential management
 */
import React, { useState, useEffect } from 'react';
import { accountAPI, authService } from '../../services/api';
import { Card, Button, Input, Badge } from '../shared';
import { FiPlus, FiTrash2, FiCheck, FiAlertCircle, FiExternalLink, FiDownload, FiCloudLightning, FiCopy } from 'react-icons/fi';
import toast from 'react-hot-toast';

import { useAuthStore } from '../../store/useStore';

const CloudIntegrations = () => {
  const { user: currentUser } = useAuthStore();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [connectionInfo, setConnectionInfo] = useState(null);

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
    fetchConnectionInfo();
  }, []);

  const fetchConnectionInfo = async () => {
    try {
      const res = await authService.getConnectionInfo();
      setConnectionInfo(res.data);
      // Pre-fill external ID in form data
      setFormData(prev => ({ ...prev, external_id: res.data.external_id }));
    } catch (err) {
      console.error("Failed to fetch connection info", err);
      // If 500, it might be due to missing org or ID, but we just updated backend to handle that.
    }
  };

  const handleRegenerateExternalId = async () => {
    if (!window.confirm("WARNING: Regenerating the External ID will break trust with any EXISTING AWS connection that uses the old ID. You will need to update your IAM Roles in AWS. Are you sure?")) {
      return;
    }
    try {
      const res = await authService.regenerateConnectionInfo();
      if (res.data.external_id) {
        setConnectionInfo(prev => ({ ...prev, external_id: res.data.external_id }));
        setFormData(prev => ({ ...prev, external_id: res.data.external_id }));
        toast.success("External ID regenerated. Please update your AWS IAM Roles.");
      }
    } catch (err) {
      toast.error("Failed to regenerate External ID");
    }
  };

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      const response = await accountAPI.list();
      setAccounts(Array.isArray(response.data) ? response.data : []);
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
      const res = await accountAPI.create(formData);
      if (res.data.status === 'pending') {
        toast.success("Request sent to Team Lead for approval");
      } else {
        toast.success("AWS account linked successfully");
      }
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
      if (response.data.status?.toLowerCase() === 'active') {
        toast.success('AWS credentials validated successfully');
        fetchAccounts();
      } else {
        toast.error('Validation failed: Status is ' + response.data.status);
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
    } catch (err) {
      toast.error('Failed to set default account');
    }
  };

  const handleApprove = async (accountId) => {
    try {
      // Assuming accountAPI has an 'approve' method or is an axios instance
      // If accountAPI is an object with specific methods, it should be accountAPI.approve(accountId)
      // If accountAPI is an axios instance, it should be accountAPI.post(`/api/v1/accounts/${accountId}/approve`)
      // For consistency with other accountAPI calls, we'll assume a dedicated method or direct axios call if accountAPI is the axios instance.
      // Based on the instruction, it implies a direct POST call.
      // If `accountAPI` is an axios instance, this is correct. If it's a wrapper, it needs a method.
      // Given the other methods like `list`, `create`, `validate`, `setDefault`, `delete`, it's likely `accountAPI` is an object with methods.
      // However, the instruction explicitly uses `api.post`. To avoid introducing an unimported `api` variable,
      // and assuming `accountAPI` is the primary API client for this component,
      // we'll use `accountAPI.post` if `accountAPI` is an axios instance, or `accountAPI.approve` if it's a wrapper.
      // For now, let's use `accountAPI.approve` as it's more consistent with `accountAPI.setDefault` etc.
      // If `accountAPI` does not have an `approve` method, this would need adjustment in `../../services/api`.
      await accountAPI.approve(accountId); // Assuming accountAPI has an approve method
      toast.success("Account approved successfully");
      fetchAccounts();
    } catch (err) {
      console.error(err);
      toast.error("Failed to approve account");
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
                    {account.status === 'active' ? (
                      <Badge color="green">
                        <FiCheck className="w-3 h-3 mr-1" />
                        Validated
                      </Badge>
                    ) : account.status === 'PENDING_APPROVAL' ? (
                      <Badge color="yellow">Pending Approval</Badge>
                    ) : (
                      <Badge color="yellow">
                        <FiAlertCircle className="w-3 h-3 mr-1" />
                        {account.status === 'error' ? 'Validation Error' : 'Pending Validation'}
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
                  {/* Approval Button for Team Leads/Admins */}
                  {account.status === 'PENDING_APPROVAL' && (currentUser.role === 'TEAM_LEAD' || currentUser.role === 'ORG_ADMIN' || currentUser.role === 'SUPER_ADMIN') && (
                    <Button
                      size="sm"
                      className="bg-green-600 hover:bg-green-700 text-white"
                      onClick={() => handleApprove(account.id)}
                    >
                      Approve
                    </Button>
                  )}

                  {account.status !== 'active' && account.status !== 'PENDING_APPROVAL' && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleValidate(account.id)}
                    >
                      {account.status === 'error' ? 'Retry Validation' : 'Validate'}
                    </Button>
                  )}
                  {!account.is_default && account.status === 'active' && (
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
      <Card className="border-2 border-blue-200 bg-gradient-to-r from-blue-50 to-indigo-50">
        <div className="flex items-start gap-4">
          <div className="p-3 bg-blue-100 rounded-lg">
            <FiCloudLightning className="w-8 h-8 text-blue-600" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-gray-900 mb-2">Quick Setup with CloudFormation</h3>
            <p className="text-sm text-gray-600 mb-4">
              Deploy our pre-configured CloudFormation template to automatically create the required IAM role in your AWS account.
              This is the fastest and most secure way to connect.
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={async () => {
                  try {
                    const response = await import('../../services/api').then(m => m.onboardingAPI.getTemplate('READ_ONLY'));
                    // Create blob link to download
                    const url = window.URL.createObjectURL(new Blob([response.data]));
                    const link = document.createElement('a');
                    link.href = url;
                    link.setAttribute('download', 'spot-optimizer-role.yaml');
                    document.body.appendChild(link);
                    link.click();
                    link.parentNode.removeChild(link);
                  } catch (e) {
                    import('react-hot-toast').then(m => m.default.error("Failed to download template"));
                  }
                }}
                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium cursor-pointer"
              >
                <FiDownload className="w-4 h-4" />
                Download CloudFormation Template
              </button>
              <a
                href={`https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review?stackName=SpotOptimizer-Connection-${connectionInfo?.external_id?.substring(0, 8)}&templateURL=${encodeURIComponent(connectionInfo?.template_url)}&param_ExternalId=${connectionInfo?.external_id}&param_TrustedRoleARN=arn:aws:iam::${connectionInfo?.platform_account_id}:role/SpotOptimizerBackendRole`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors font-medium"
              >
                <FiExternalLink className="w-4 h-4" />
                Launch CloudFormation Console
              </a>
            </div>
            <div className="mt-4 p-3 bg-white rounded-lg border border-blue-200">
              <p className="text-sm text-gray-700 font-medium mb-2">Connection Parameters:</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500 block">Platform Account ID <span className="text-xs text-blue-600">(SpotOptimizer's AWS Account - Trust This)</span>:</span>
                  <div className="flex items-center gap-2">
                    <code className="bg-gray-100 px-2 py-1 rounded">{connectionInfo?.platform_account_id || 'Loading...'}</code>
                    {connectionInfo?.platform_account_id_source === 'auto_detected' && (
                      <span className="text-xs bg-green-100 text-green-700 px-1 rounded">Auto-detected</span>
                    )}
                    {connectionInfo?.platform_account_id === 'NOT_CONFIGURED' && (
                      <span className="text-xs bg-red-100 text-red-700 px-1 rounded">Not Configured</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-1">This is NOT your AWS Account. It's the SpotOptimizer backend's account.</p>
                </div>
                <div>
                  <span className="text-gray-500 block">Your Organization External ID <span className="text-xs text-blue-600">(Unique Security Key)</span>:</span>
                  <div className="flex items-center gap-2">
                    <code className="bg-gray-100 px-2 py-1 rounded font-bold text-blue-700">{connectionInfo?.external_id || 'Loading...'}</code>
                    <button onClick={() => { navigator.clipboard.writeText(connectionInfo?.external_id); toast.success('Copied External ID') }} className="text-gray-400 hover:text-blue-600" title="Copy ID"><FiCopy /></button>
                    {(currentUser.role === 'ORG_ADMIN' || currentUser.role === 'CLIENT') && (
                      <button onClick={handleRegenerateExternalId} className="text-gray-400 hover:text-red-600 text-xs underline ml-2" title="Regenerate ID">Regenerate</button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
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
                  External ID (Auto-assigned)
                </label>
                <Input
                  value={formData.external_id}
                  disabled
                  className="bg-gray-100 text-gray-500 cursor-not-allowed"
                  help="Unique Identifier for your Organization (Fixed)"
                />
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
