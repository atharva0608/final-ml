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
    const [currentStep, setCurrentStep] = useState(1);
    const [accountId, setAccountId] = useState(null);
    const [externalId, setExternalId] = useState('');
    const [roleArn, setRoleArn] = useState('');
    const [verificationStatus, setVerificationStatus] = useState('pending'); // pending, checking, connected, failed
    const [verificationMessage, setVerificationMessage] = useState('');
    const [discoveryStatus, setDiscoveryStatus] = useState(null);
    const [isLoading, setIsLoading] = useState(false);

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
                setVerificationMessage(`✅ Connected! AWS Account: ${response.aws_account_id}`);
                setCurrentStep(4);

                // Start resource discovery
                checkDiscoveryStatus();
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

    // Step 4: Check resource discovery status
    const checkDiscoveryStatus = async () => {
        try {
            const response = await api.getDiscoveryStatus(accountId);
            setDiscoveryStatus(response);
        } catch (error) {
            console.error('Failed to get discovery status:', error);
        }
    };

    // Copy to clipboard helper
    const copyToClipboard = (text) => {
        navigator.clipboard.writeText(text);
        alert('Copied to clipboard!');
    };

    // Auto-create onboarding request on mount
    useEffect(() => {
        if (!accountId) {
            createOnboardingRequest();
        }
    }, []);

    return (
        <div className="min-h-screen bg-gray-50 py-8 px-4">
            <div className="max-w-4xl mx-auto">
                {/* Header */}
                <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
                    <div className="flex items-center gap-3 mb-4">
                        <Cloud className="w-8 h-8 text-blue-600" />
                        <div>
                            <h1 className="text-2xl font-bold text-gray-900">Connect Your AWS Account</h1>
                            <p className="text-gray-600">Secure, agentless connection via IAM role</p>
                        </div>
                    </div>

                    {/* Progress Steps */}
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
                </div>

                {/* Step 1: ExternalID Display */}
                {currentStep >= 1 && (
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
                {currentStep >= 2 && (
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
                {currentStep >= 3 && (
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
                                        href="/"
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
