import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { FiExternalLink, FiCopy, FiCheckCircle, FiAlertCircle, FiDownload } from 'react-icons/fi';
import { Button } from '../shared';
import { onboardingAPI, authAPI } from '../../services/api';
import toast from 'react-hot-toast';

const ConnectStep = ({ onNext }) => {
    const [awsLink, setAwsLink] = useState('');
    const [externalId, setExternalId] = useState(''); // New state
    const [roleArn, setRoleArn] = useState('');
    const [verifying, setVerifying] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Fetch Standardized Connection Info using Organization External ID
        const fetchConnectionInfo = async () => {
            try {
                // Use the standardized organization endpoint
                // This ensures every user in the org uses the SAME External ID
                const res = await authAPI.getConnectionInfo();

                if (res.data.external_id) {
                    setExternalId(res.data.external_id);

                    // Construct CloudFormation Quick-Create Link with auto-filled parameters
                    const stackName = `SpotOptimizer-${res.data.external_id.substring(0, 8)}`;
                    const templateUrl = res.data.template_url || `${window.location.origin}/api/v1/templates/aws-onboarding`;

                    const params = new URLSearchParams({
                        stackName: stackName,
                        templateURL: templateUrl,
                        'param_ExternalId': res.data.external_id,
                        'param_PlatformAccountId': res.data.platform_account_id || '123456789012'
                    });

                    setAwsLink(`https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review?${params.toString()}`);
                }
            } catch (err) {
                console.error("Failed to load connection info:", err);
                // Fallback: Try onboarding state endpoint
                try {
                    const fallbackRes = await onboardingAPI.getState();
                    if (fallbackRes.data.external_id) {
                        setExternalId(fallbackRes.data.external_id);
                    }
                } catch (fallbackErr) {
                    toast.error("Failed to load connection info. Please refresh the page.");
                }
            }
        };

        fetchConnectionInfo();
    }, []);

    const handleDownloadTemplate = () => {
        // Direct download link logic or open info modal
        toast.success("Please use the 'Launch Console' button for the most secure setup.");
    };

    const copyExternalId = () => {
        navigator.clipboard.writeText(externalId);
        toast.success("External ID copied!");
    };

    const handleVerify = async () => {
        if (!roleArn.startsWith('arn:aws:iam::')) {
            setError("Invalid Role ARN format");
            return;
        }

        setVerifying(true);
        setError(null);

        try {
            await onboardingAPI.verify(roleArn);
            toast.success("Successfully Connected!");
            onNext();
        } catch (err) {
            console.error(err);
            setError("Verification failed. Please check the ARN and try again.");
            toast.error("Could not verify Role access");
        } finally {
            setVerifying(false);
        }
    };

    return (
        <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="bg-white rounded-2xl shadow-xl p-10"
        >
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Connect your AWS Account</h2>
            <p className="text-gray-500 mb-8">Create a secure IAM Role to grant SpotOptimizer visibility.</p>

            {/* External ID Display - CRITICAL for user trust/manual setup */}
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-8 flex items-center justify-between">
                <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Your Unique External ID</label>
                    <code className="text-lg font-mono font-bold text-gray-800">{externalId || 'Loading...'}</code>
                </div>
                <button
                    onClick={copyExternalId}
                    className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
                >
                    <FiCopy size={20} />
                </button>
            </div>

            <div className="space-y-8">
                {/* Step 1 */}
                <div className="flex gap-4">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-bold">1</div>
                    <div className="flex-1">
                        <h3 className="font-semibold text-gray-900 mb-1">Launch CloudFormation Stack</h3>
                        <p className="text-sm text-gray-500 mb-3">
                            Check the pre-filled parameters in the CloudFormation console (External ID is auto-injected).
                        </p>
                        <div className="flex gap-3">
                            <a
                                href={awsLink}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition-colors font-medium text-sm"
                            >
                                <FiExternalLink /> Launch Console
                            </a>
                            <button
                                onClick={handleDownloadTemplate}
                                className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 bg-white rounded-lg hover:bg-gray-50 transition-colors font-medium text-sm"
                            >
                                <FiDownload /> Download YAML
                            </button>
                        </div>
                    </div>
                </div>

                {/* Step 2 */}
                <div className="flex gap-4">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-bold">2</div>
                    <div className="flex-1">
                        <h3 className="font-semibold text-gray-900 mb-1">Enter Role ARN</h3>
                        <p className="text-sm text-gray-500 mb-3">
                            Copy the <code>RoleArn</code> from the CloudFormation <strong>Outputs</strong> tab.
                        </p>

                        <div className="relative">
                            <input
                                type="text"
                                value={roleArn}
                                onChange={(e) => setRoleArn(e.target.value)}
                                placeholder="arn:aws:iam::123456789012:role/SpotOptimizer-Access-Role..."
                                className={`w-full px-4 py-3 rounded-lg border ${error ? 'border-red-300 focus:ring-red-500' : 'border-gray-300 focus:ring-blue-500'} focus:outline-none focus:ring-2`}
                            />
                        </div>
                        {error && (
                            <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                                <FiAlertCircle /> {error}
                            </p>
                        )}
                    </div>
                </div>
            </div>

            <div className="mt-8 pt-6 border-t border-gray-100 flex justify-end">
                <Button
                    variant="primary"
                    size="lg"
                    onClick={handleVerify}
                    isLoading={verifying}
                    disabled={!roleArn}
                >
                    Verify Connection
                </Button>
            </div>
        </motion.div>
    );
};

export default ConnectStep;
