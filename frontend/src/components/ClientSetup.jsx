import { useState, useEffect } from 'react';
import { Cloud, Copy, CheckCircle, XCircle, Download, RefreshCw, Server } from 'lucide-react';
import api from '../services/api';

/**
 * Client Onboarding Wizard
 *
 * Self-service setup flow for connecting AWS accounts:
 * 1. Generate unique ExternalID
 * 2. Download CloudFormation template
 * 3. Deploy stack in client's AWS account
 * 4. Verify cross-account access via STS AssumeRole
 * 5. Show resource discovery status
 */
const ClientSetup = () => {
    const [showOnboarding, setShowOnboarding] = useState(false); // Controls whether to show onboarding flow
    const [connectedAccounts, setConnectedAccounts] = useState([]); // List of connected accounts
    const [isLoadingAccounts, setIsLoadingAccounts] = useState(true); // Loading state for initial check

    const [connectionMethod, setConnectionMethod] = useState('cloudformation'); // 'cloudformation' or 'credentials'
    const [currentStep, setCurrentStep] = useState(1);
    const [accountId, setAccountId] = useState(null);
    const [externalId, setExternalId] = useState('');
    const [roleArn, setRoleArn] = useState('');

    // Credentials mode state
    const [accessKey, setAccessKey] = useState('');
    const [secretKey, setSecretKey] = useState('');
    const [region, setRegion] = useState('us-east-1');

    const [verificationStatus, setVerificationStatus] = useState('pending'); // pending, checking, connected, failed
    const [verificationMessage, setVerificationMessage] = useState('');
    const [discoveryStatus, setDiscoveryStatus] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [pollingIntervalId, setPollingIntervalId] = useState(null);

    // Step 1: Create onboarding request and get ExternalID
    const createOnboardingRequest = async () => {
        setIsLoading(true);
        try {
            const response = await api.createOnboardingRequest();
            setAccountId(response.id);
            setExternalId(response.external_id);
            setCurrentStep(2);
        } catch (error) {
            console.error('Failed to create onboarding request:', error);
            alert('Failed to start onboarding. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    // Step 2: Download CloudFormation template
    const downloadTemplate = async () => {
        setIsLoading(true);
        try {
            const response = await api.getOnboardingTemplate(accountId);
            const template = response.template;

            // Convert template to JSON string
            const templateJson = JSON.stringify(template, null, 2);

            // Create blob and download
            const blob = new Blob([templateJson], { type: 'application/json' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'spot-optimizer-role.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            setCurrentStep(3);
        } catch (error) {
            console.error('Failed to download template:', error);
            alert('Failed to generate template. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    // Step 3: Verify connection
    const verifyConnection = async () => {
        if (!roleArn.trim()) {
            alert('Please enter the Role ARN');
            return;
        }

        setIsLoading(true);
        setVerificationStatus('checking');
        setVerificationMessage('Verifying connection...');

        try {
            const response = await api.verifyOnboarding(accountId, roleArn);

            if (response.status === 'connected') {
                setVerificationStatus('connected');
                setVerificationMessage(`✅ Connected! Discovering resources...`);
                setCurrentStep(4);

                // Start resource discovery
                checkDiscoveryStatus();

                // Start polling to track activation status
                startPollingAccountStatus();

                // Refresh account list after successful connection
                setTimeout(() => {
                    checkConnectedAccounts();
                }, 2000);
            } else {
                setVerificationStatus('failed');
                setVerificationMessage(`❌ ${response.error || 'Connection failed'}`);
            }
        } catch (error) {
            console.error('Verification failed:', error);
            setVerificationStatus('failed');
            setVerificationMessage('❌ Verification failed. Please check your Role ARN.');
        } finally {
            setIsLoading(false);
        }
    };

    // Credentials mode: Connect with access keys
    const connectWithAccessKeys = async () => {
        if (!accessKey.trim() || !secretKey.trim()) {
            alert('Please enter both Access Key ID and Secret Access Key');
            return;
        }

        setIsLoading(true);
        setVerificationStatus('checking');
        setVerificationMessage('Validating credentials...');

        try {
            const response = await api.connectWithCredentials(accessKey, secretKey, region);

            if (response.status === 'connected') {
                setVerificationStatus('connected');
                setVerificationMessage(`✅ Connected! Discovering resources...`);
                setAccountId(response.account_id);
                setCurrentStep(4);

                // Start checking discovery status
                checkDiscoveryStatus();

                // Start polling to track activation status
                startPollingAccountStatus();

                // Refresh account list after successful connection
                setTimeout(() => {
                    checkConnectedAccounts();
                }, 2000);
            } else {
                setVerificationStatus('failed');
                setVerificationMessage(`❌ ${response.error || 'Connection failed'}`);
            }
        } catch (error) {
            console.error('Credentials connection failed:', error);
            setVerificationStatus('failed');
            setVerificationMessage('❌ Invalid credentials. Please check your Access Key and Secret Key.');
        } finally {
            setIsLoading(false);
        }
    };

    // Step 4: Check resource discovery status
    const checkDiscoveryStatus = async () => {
        try {
            const response = await api.getDiscoveryStatus(accountId);
            setDiscoveryStatus(response);
        } catch (error) {
            console.error('Failed to get discovery status:', error);
        }
    };

    // Polling function to verify account status
    const startPollingAccountStatus = () => {
        // Clear any existing interval
        if (pollingIntervalId) {
            clearInterval(pollingIntervalId);
        }

        let attempts = 0;
        const maxAttempts = 60; // Poll for up to 3 minutes (60 * 3s = 180s)

        const intervalId = setInterval(async () => {
            attempts++;

            try {
                // Check account status via /client/accounts
                const response = await api.get('/client/accounts');

                if (response.data && response.data.length > 0) {
                    const account = response.data[0]; // Get the first account

                    // Check if status has changed from 'connected' to 'active'
                    if (account.status === 'active') {
                        // Account is now active - stop polling
                        clearInterval(intervalId);
                        setPollingIntervalId(null);
                        setVerificationStatus('connected');
                        setVerificationMessage(`✅ Account fully activated! AWS Account: ${account.account_id}`);

                        // Update discovery status
                        checkDiscoveryStatus();
                    } else if (account.status === 'connected') {
                        // Still discovering
                        setVerificationMessage(`🔄 Discovering resources... (${attempts * 3}s elapsed)`);
                    }
                }
            } catch (error) {
                console.error('Polling error:', error);
            }

            // Stop polling after max attempts
            if (attempts >= maxAttempts) {
                clearInterval(intervalId);
                setPollingIntervalId(null);
                setVerificationMessage('⚠️ Discovery is taking longer than expected. Please refresh the page.');
            }
        }, 3000); // Poll every 3 seconds

        setPollingIntervalId(intervalId);
    };

    // Copy to clipboard helper
    const copyToClipboard = (text) => {
        navigator.clipboard.writeText(text);
        alert('Copied to clipboard!');
    };

    // Check for existing connected accounts
    const checkConnectedAccounts = async () => {
        setIsLoadingAccounts(true);
        try {
            // Use the new /accounts endpoint to get list of accounts
            const response = await api.get('/client/accounts');

            if (response.data && response.data.length > 0) {
                // User has connected account(s)
                const accounts = response.data.map(acc => ({
                    id: acc.account_id,
                    name: acc.account_name,
                    region: acc.region,
                    status: acc.status,
                    connectionType: acc.connection_method,
                    connectedAt: acc.created_at,
                    lastUpdated: acc.updated_at
                }));
                setConnectedAccounts(accounts);
                setShowOnboarding(false);
            } else {
                // No connected accounts - show onboarding
                setConnectedAccounts([]);
                setShowOnboarding(true);
            }
        } catch (error) {
            console.error('Failed to check accounts:', error);
            // If API fails, show onboarding by default
            setConnectedAccounts([]);
            setShowOnboarding(true);
        } finally {
            setIsLoadingAccounts(false);
        }
    };

    // Disconnect account
    const handleDisconnect = async (accountId) => {
        if (!window.confirm('Are you sure you want to disconnect this AWS account? All associated data will be removed.')) {
            return;
        }

        try {
            // Call DELETE /client/accounts/{account_id}
            await api.delete(`/client/accounts/${accountId}`);

            // Show success message
            alert(`AWS account disconnected successfully`);

            // Refresh the account list (will show onboarding if no accounts left)
            checkConnectedAccounts();
        } catch (error) {
            console.error('Failed to disconnect:', error);
            alert(`Failed to disconnect account: ${error.response?.data?.detail || error.message}`);
        }
    };

    // Start adding a new account
    const handleAddAccount = () => {
        setShowOnboarding(true);
        setCurrentStep(1);
        setVerificationStatus('pending');
        setVerificationMessage('');
    };

    // Auto-check for connected accounts on mount
    useEffect(() => {
        checkConnectedAccounts();
    }, []);

    // Auto-create onboarding request when entering CloudFormation mode
    useEffect(() => {
        if (showOnboarding && !accountId && connectionMethod === 'cloudformation') {
            createOnboardingRequest();
        }
    }, [showOnboarding, connectionMethod]);

    // Cleanup polling interval on unmount
    useEffect(() => {
        return () => {
            if (pollingIntervalId) {
                clearInterval(pollingIntervalId);
            }
        };
    }, [pollingIntervalId]);

    // Loading state
    if (isLoadingAccounts) {
        return (
            <div className="min-h-screen bg-gray-50 py-8 px-4">
                <div className="max-w-4xl mx-auto text-center py-12">
                    <RefreshCw className="w-12 h-12 text-blue-600 mx-auto mb-3 animate-spin" />
                    <p className="text-gray-600">Loading your accounts...</p>
                </div>
            </div>
        );
    }

    // Show connected accounts management UI
    if (!showOnboarding && connectedAccounts.length > 0) {
        return (
            <div className="min-h-screen bg-gray-50 py-8 px-4">
                <div className="max-w-4xl mx-auto">
                    {/* Header */}
                    <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-3">
                                <Cloud className="w-8 h-8 text-green-600" />
                                <div>
                                    <h1 className="text-2xl font-bold text-gray-900">Connected AWS Accounts</h1>
                                    <p className="text-gray-600">Manage your connected AWS accounts</p>
                                </div>
                            </div>
                            <button
                                onClick={handleAddAccount}
                                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
                            >
                                <Cloud className="w-5 h-5" />
                                Add Account
                            </button>
                        </div>
                    </div>

                    {/* Connected Accounts List */}
                    <div className="space-y-4">
                        {connectedAccounts.map((account, index) => (
                            <div key={index} className="bg-white rounded-lg shadow-sm p-6">
                                <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-2">
                                            {account.connectionType === 'iam_role' ? (
                                                <Cloud className="w-6 h-6 text-green-600" />
                                            ) : (
                                                <Server className="w-6 h-6 text-blue-600" />
                                            )}
                                            <h3 className="text-lg font-semibold text-gray-900">{account.name}</h3>
                                            <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                                                account.status === 'active' ? 'bg-green-100 text-green-800' :
                                                account.status === 'connected' ? 'bg-blue-100 text-blue-800' :
                                                account.status === 'discovering' ? 'bg-yellow-100 text-yellow-800' :
                                                'bg-gray-100 text-gray-800'
                                            }`}>
                                                {account.status === 'active' ? 'Active' :
                                                 account.status === 'connected' ? 'Discovering' :
                                                 account.status}
                                            </span>
                                        </div>

                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
                                            <div>
                                                <p className="text-sm text-gray-500">Account ID</p>
                                                <p className="text-sm font-mono text-gray-900">{account.id}</p>
                                            </div>
                                            <div>
                                                <p className="text-sm text-gray-500">Region</p>
                                                <p className="text-sm text-gray-900">{account.region}</p>
                                            </div>
                                            <div>
                                                <p className="text-sm text-gray-500">Connection Type</p>
                                                <p className="text-sm text-gray-900">
                                                    {account.connectionType === 'iam_role' ? 'CloudFormation (IAM Role)' : 'Access Keys'}
                                                </p>
                                            </div>
                                        </div>

                                        {account.connectedAt && (
                                            <div className="mt-4 text-sm text-gray-500">
                                                Connected: {new Date(account.connectedAt).toLocaleDateString()}
                                            </div>
                                        )}
                                    </div>

                                    <div className="ml-4">
                                        <button
                                            onClick={() => handleDisconnect(account.id)}
                                            className="text-red-600 hover:text-red-700 text-sm font-medium"
                                        >
                                            Disconnect
                                        </button>
                                    </div>
                                </div>

                                {account.status === 'connected' && (
                                    <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-center gap-3">
                                        <RefreshCw className="w-5 h-5 text-blue-600 animate-spin" />
                                        <div>
                                            <p className="text-sm text-blue-900 font-medium">Resource Discovery in Progress</p>
                                            <p className="text-xs text-blue-700">Scanning your AWS resources...</p>
                                        </div>
                                    </div>
                                )}

                                {account.status === 'active' && (
                                    <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg flex items-center gap-3">
                                        <CheckCircle className="w-5 h-5 text-green-600" />
                                        <div>
                                            <p className="text-sm text-green-900 font-medium">Account Active & Optimized</p>
                                            <p className="text-xs text-green-700">Your instances are being monitored</p>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Go to Dashboard Button */}
                    <div className="mt-6 text-center">
                        <a
                            href="/client"
                            className="inline-block bg-green-600 text-white px-8 py-3 rounded-lg hover:bg-green-700 transition-colors font-medium"
                        >
                            Go to Dashboard
                        </a>
                    </div>
                </div>
            </div>
        );
    }

    // Show onboarding flow (new account setup)
    return (
        <div className="min-h-screen bg-gray-50 py-8 px-4">
            <div className="max-w-4xl mx-auto">
                {/* Header */}
                <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
                    <div className="flex items-center gap-3 mb-4">
                        <Cloud className="w-8 h-8 text-blue-600" />
                        <div>
                            <h1 className="text-2xl font-bold text-gray-900">Connect Your AWS Account</h1>
                            <p className="text-gray-600">Choose your preferred connection method</p>
                        </div>
                    </div>

                    {/* Connection Method Toggle */}
                    <div className="flex gap-4 mb-6">
                        <button
                            onClick={() => {
                                setConnectionMethod('cloudformation');
                                setCurrentStep(1);
                                setVerificationStatus('pending');
                                setVerificationMessage('');
                            }}
                            className={`flex-1 px-6 py-4 rounded-lg border-2 transition-all ${
                                connectionMethod === 'cloudformation'
                                    ? 'border-blue-600 bg-blue-50'
                                    : 'border-gray-200 bg-white hover:border-gray-300'
                            }`}
                        >
                            <div className="flex items-center justify-center gap-2 mb-2">
                                <Cloud className={`w-5 h-5 ${connectionMethod === 'cloudformation' ? 'text-blue-600' : 'text-gray-500'}`} />
                                <h3 className={`font-semibold ${connectionMethod === 'cloudformation' ? 'text-blue-900' : 'text-gray-700'}`}>
                                    CloudFormation (Secure)
                                </h3>
                            </div>
                            <p className="text-sm text-gray-600">
                                IAM role with minimal permissions
                            </p>
                            <div className="mt-2 text-xs text-green-600 font-medium">
                                ✓ Recommended for production
                            </div>
                        </button>

                        <button
                            onClick={() => {
                                setConnectionMethod('credentials');
                                setCurrentStep(1);
                                setVerificationStatus('pending');
                                setVerificationMessage('');
                            }}
                            className={`flex-1 px-6 py-4 rounded-lg border-2 transition-all ${
                                connectionMethod === 'credentials'
                                    ? 'border-blue-600 bg-blue-50'
                                    : 'border-gray-200 bg-white hover:border-gray-300'
                            }`}
                        >
                            <div className="flex items-center justify-center gap-2 mb-2">
                                <Server className={`w-5 h-5 ${connectionMethod === 'credentials' ? 'text-blue-600' : 'text-gray-500'}`} />
                                <h3 className={`font-semibold ${connectionMethod === 'credentials' ? 'text-blue-900' : 'text-gray-700'}`}>
                                    Access Keys (Fast)
                                </h3>
                            </div>
                            <p className="text-sm text-gray-600">
                                Direct connection with AWS credentials
                            </p>
                            <div className="mt-2 text-xs text-blue-600 font-medium">
                                ✓ Quick setup for testing
                            </div>
                        </button>
                    </div>

                    {/* Progress Steps (only show for CloudFormation) */}
                    {connectionMethod === 'cloudformation' && (
                        <>
                            <div className="flex items-center gap-2 mt-6">
                                {[1, 2, 3, 4].map((step) => (
                                    <div key={step} className="flex items-center flex-1">
                                        <div className={`
                                            flex items-center justify-center w-8 h-8 rounded-full
                                            ${currentStep >= step ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'}
                                        `}>
                                            {currentStep > step ? <CheckCircle className="w-5 h-5" /> : step}
                                        </div>
                                        {step < 4 && (
                                            <div className={`flex-1 h-1 mx-2 ${currentStep > step ? 'bg-blue-600' : 'bg-gray-200'}`} />
                                        )}
                                    </div>
                                ))}
                            </div>

                            <div className="flex justify-between mt-2 text-xs text-gray-600">
                                <span>Generate ID</span>
                                <span>Download</span>
                                <span>Verify</span>
                                <span>Discovery</span>
                            </div>
                        </>
                    )}
                </div>

                {/* Credentials Mode Form */}
                {connectionMethod === 'credentials' && currentStep < 4 && (
                    <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
                        <h2 className="text-lg font-semibold text-gray-900 mb-4">Enter AWS Credentials</h2>

                        {/* IAM Policy Instructions */}
                        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                            <h3 className="font-semibold text-blue-900 mb-2">📋 Required IAM Permissions</h3>
                            <p className="text-sm text-blue-800 mb-3">
                                Create an IAM user with programmatic access and attach this policy for full functionality:
                            </p>
                            <details className="text-sm">
                                <summary className="cursor-pointer text-blue-700 hover:text-blue-900 font-medium mb-2">
                                    Click to view IAM Policy JSON (Copy & Paste to AWS IAM)
                                </summary>
                                <pre className="bg-gray-900 text-green-400 p-4 rounded overflow-x-auto text-xs mt-2">
{`{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EC2Discovery",
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*",
        "autoscaling:Describe*",
        "eks:Describe*",
        "eks:ListClusters"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchMetrics",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SpotOptimization",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:StopInstances",
        "ec2:StartInstances",
        "ec2:CreateTags",
        "ec2:DeleteTags",
        "autoscaling:SetDesiredCapacity",
        "autoscaling:TerminateInstanceInAutoScalingGroup",
        "autoscaling:AttachInstances",
        "autoscaling:DetachInstances"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassRoleForEC2",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "*",
      "Condition": {
        "StringLike": {
          "iam:PassedToService": "ec2.amazonaws.com"
        }
      }
    },
    {
      "Sid": "ServiceLinkedRole",
      "Effect": "Allow",
      "Action": "iam:CreateServiceLinkedRole",
      "Resource": "arn:aws:iam::*:role/aws-service-role/spot.amazonaws.com/*"
    },
    {
      "Sid": "PricingAndCost",
      "Effect": "Allow",
      "Action": [
        "pricing:GetProducts",
        "ce:GetCostAndUsage"
      ],
      "Resource": "*"
    }
  ]
}`}
                                </pre>
                            </details>
                        </div>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    AWS Access Key ID
                                </label>
                                <input
                                    type="text"
                                    value={accessKey}
                                    onChange={(e) => setAccessKey(e.target.value)}
                                    placeholder="AKIA..."
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    AWS Secret Access Key
                                </label>
                                <input
                                    type="password"
                                    value={secretKey}
                                    onChange={(e) => setSecretKey(e.target.value)}
                                    placeholder="Enter your secret key"
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    AWS Region
                                </label>
                                <select
                                    value={region}
                                    onChange={(e) => setRegion(e.target.value)}
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                >
                                    <option value="us-east-1">US East (N. Virginia)</option>
                                    <option value="us-east-2">US East (Ohio)</option>
                                    <option value="us-west-1">US West (N. California)</option>
                                    <option value="us-west-2">US West (Oregon)</option>
                                    <option value="ap-south-1">Asia Pacific (Mumbai)</option>
                                    <option value="ap-southeast-1">Asia Pacific (Singapore)</option>
                                    <option value="ap-southeast-2">Asia Pacific (Sydney)</option>
                                    <option value="ap-northeast-1">Asia Pacific (Tokyo)</option>
                                    <option value="eu-west-1">Europe (Ireland)</option>
                                    <option value="eu-central-1">Europe (Frankfurt)</option>
                                </select>
                            </div>

                            <button
                                onClick={connectWithAccessKeys}
                                disabled={isLoading || !accessKey.trim() || !secretKey.trim()}
                                className="w-full bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition-colors flex items-center justify-center gap-2"
                            >
                                {isLoading ? (
                                    <>
                                        <RefreshCw className="w-5 h-5 animate-spin" />
                                        Connecting...
                                    </>
                                ) : (
                                    <>
                                        <CheckCircle className="w-5 h-5" />
                                        Connect & Verify
                                    </>
                                )}
                            </button>

                            {verificationMessage && (
                                <div className={`mt-4 p-4 rounded-lg ${
                                    verificationStatus === 'connected' ? 'bg-green-50 border border-green-200 text-green-800' :
                                    verificationStatus === 'failed' ? 'bg-red-50 border border-red-200 text-red-800' :
                                    'bg-blue-50 border border-blue-200 text-blue-800'
                                }`}>
                                    {verificationMessage}
                                </div>
                            )}

                            <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                                <p className="text-sm text-yellow-800">
                                    <strong>Security Note:</strong> Your credentials are encrypted before storage using AES-256 encryption.
                                    We recommend using IAM users with minimal required permissions.
                                </p>
                            </div>
                        </div>
                    </div>
                )}

                {/* CloudFormation Mode Steps */}
                {/* Step 1: ExternalID Display */}
                {connectionMethod === 'cloudformation' && currentStep >= 1 && (
                    <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold text-gray-900">Step 1: Your Unique External ID</h2>
                            {currentStep > 1 && <CheckCircle className="w-6 h-6 text-green-600" />}
                        </div>

                        <p className="text-gray-600 mb-4">
                            This ID ensures secure cross-account access. It will be embedded in your CloudFormation template.
                        </p>

                        <div className="flex items-center gap-2 bg-gray-50 p-4 rounded-lg">
                            <code className="flex-1 text-sm font-mono text-gray-800">
                                {externalId || 'Loading...'}
                            </code>
                            <button
                                onClick={() => copyToClipboard(externalId)}
                                className="p-2 hover:bg-gray-200 rounded transition-colors"
                                title="Copy to clipboard"
                            >
                                <Copy className="w-5 h-5 text-gray-600" />
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 2: Download Template */}
                {connectionMethod === 'cloudformation' && currentStep >= 2 && (
                    <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold text-gray-900">Step 2: Download CloudFormation Template</h2>
                            {currentStep > 2 && <CheckCircle className="w-6 h-6 text-green-600" />}
                        </div>

                        <p className="text-gray-600 mb-4">
                            This template creates an IAM role in your AWS account with the minimum permissions required for optimization.
                        </p>

                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                            <h3 className="font-medium text-blue-900 mb-2">Permissions Granted:</h3>
                            <ul className="text-sm text-blue-800 space-y-1">
                                <li>• EC2: Describe, Create Tags, Run/Terminate Instances</li>
                                <li>• Auto Scaling: Describe, Attach/Detach Instances</li>
                                <li>• EKS: Describe Clusters</li>
                                <li>• Pricing: Get Product Information</li>
                            </ul>
                        </div>

                        {currentStep === 2 && (
                            <>
                                <button
                                    onClick={downloadTemplate}
                                    disabled={isLoading}
                                    className="w-full bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition-colors flex items-center justify-center gap-2"
                                >
                                    <Download className="w-5 h-5" />
                                    {isLoading ? 'Generating...' : 'Download Template'}
                                </button>

                                <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                                    <p className="text-sm text-yellow-800">
                                        <strong>Next:</strong> After downloading, go to your AWS CloudFormation console,
                                        create a new stack, and upload this template.
                                    </p>
                                </div>
                            </>
                        )}

                        {currentStep > 2 && (
                            <div className="text-green-700 flex items-center gap-2">
                                <CheckCircle className="w-5 h-5" />
                                Template downloaded
                            </div>
                        )}
                    </div>
                )}

                {/* Step 3: Verify Connection */}
                {connectionMethod === 'cloudformation' && currentStep >= 3 && (
                    <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold text-gray-900">Step 3: Verify Connection</h2>
                            {verificationStatus === 'connected' && <CheckCircle className="w-6 h-6 text-green-600" />}
                        </div>

                        <p className="text-gray-600 mb-4">
                            After your CloudFormation stack is created, copy the Role ARN from the stack outputs and paste it below.
                        </p>

                        {currentStep === 3 && (
                            <>
                                <div className="mb-4">
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Role ARN (from CloudFormation Outputs)
                                    </label>
                                    <input
                                        type="text"
                                        value={roleArn}
                                        onChange={(e) => setRoleArn(e.target.value)}
                                        placeholder="arn:aws:iam::123456789012:role/SpotOptimizerCrossAccountRole"
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                    />
                                </div>

                                <button
                                    onClick={verifyConnection}
                                    disabled={isLoading || !roleArn.trim()}
                                    className="w-full bg-green-600 text-white px-6 py-3 rounded-lg hover:bg-green-700 disabled:bg-gray-400 transition-colors flex items-center justify-center gap-2"
                                >
                                    {isLoading ? (
                                        <>
                                            <RefreshCw className="w-5 h-5 animate-spin" />
                                            Verifying...
                                        </>
                                    ) : (
                                        <>
                                            <CheckCircle className="w-5 h-5" />
                                            Verify Connection
                                        </>
                                    )}
                                </button>

                                {verificationMessage && (
                                    <div className={`mt-4 p-4 rounded-lg ${
                                        verificationStatus === 'connected' ? 'bg-green-50 border border-green-200 text-green-800' :
                                        verificationStatus === 'failed' ? 'bg-red-50 border border-red-200 text-red-800' :
                                        'bg-blue-50 border border-blue-200 text-blue-800'
                                    }`}>
                                        {verificationMessage}
                                    </div>
                                )}
                            </>
                        )}

                        {verificationStatus === 'connected' && currentStep > 3 && (
                            <div className="text-green-700 flex items-center gap-2">
                                <CheckCircle className="w-5 h-5" />
                                Connection verified successfully
                            </div>
                        )}
                    </div>
                )}

                {/* Step 4: Resource Discovery */}
                {currentStep >= 4 && (
                    <div className="bg-white rounded-lg shadow-sm p-6">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-lg font-semibold text-gray-900">Step 4: Resource Discovery</h2>
                            <button
                                onClick={checkDiscoveryStatus}
                                className="text-blue-600 hover:text-blue-700 flex items-center gap-2"
                            >
                                <RefreshCw className="w-4 h-4" />
                                Refresh
                            </button>
                        </div>

                        {discoveryStatus ? (
                            <div>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                                    <div className="bg-blue-50 p-4 rounded-lg">
                                        <div className="text-2xl font-bold text-blue-600">
                                            {discoveryStatus.resources?.eks_clusters || 0}
                                        </div>
                                        <div className="text-sm text-gray-600">EKS Clusters</div>
                                    </div>
                                    <div className="bg-green-50 p-4 rounded-lg">
                                        <div className="text-2xl font-bold text-green-600">
                                            {discoveryStatus.resources?.auto_scaling_groups || 0}
                                        </div>
                                        <div className="text-sm text-gray-600">Auto Scaling Groups</div>
                                    </div>
                                    <div className="bg-purple-50 p-4 rounded-lg">
                                        <div className="text-2xl font-bold text-purple-600">
                                            {discoveryStatus.resources?.ec2_instances || 0}
                                        </div>
                                        <div className="text-sm text-gray-600">EC2 Instances</div>
                                    </div>
                                    <div className="bg-yellow-50 p-4 rounded-lg">
                                        <div className="text-2xl font-bold text-yellow-600">
                                            {discoveryStatus.resources?.optimizable_instances || 0}
                                        </div>
                                        <div className="text-sm text-gray-600">Optimizable</div>
                                    </div>
                                </div>

                                <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
                                    <CheckCircle className="w-12 h-12 text-green-600 mx-auto mb-3" />
                                    <h3 className="text-lg font-semibold text-green-900 mb-2">
                                        Setup Complete!
                                    </h3>
                                    <p className="text-green-800 mb-4">
                                        Your AWS account is now connected and ready for optimization.
                                    </p>
                                    <a
                                        href="/client"
                                        className="inline-block bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700 transition-colors"
                                    >
                                        Go to Dashboard
                                    </a>
                                </div>
                            </div>
                        ) : (
                            <div className="text-center py-8">
                                <RefreshCw className="w-12 h-12 text-gray-400 mx-auto mb-3 animate-spin" />
                                <p className="text-gray-600">Scanning your AWS resources...</p>
                                <p className="text-sm text-gray-500 mt-2">This may take a few minutes</p>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ClientSetup;
