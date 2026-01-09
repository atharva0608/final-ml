import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { FiExternalLink, FiCopy, FiCheckCircle, FiAlertCircle } from 'react-icons/fi';
import { Button } from '../shared';
import { onboardingAPI } from '../../services/api';
import toast from 'react-hot-toast';

const ConnectStep = ({ onNext }) => {
    const [awsLink, setAwsLink] = useState('');
    const [roleArn, setRoleArn] = useState('');
    const [verifying, setVerifying] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Generate Deep Link on mount
        const getLink = async () => {
            try {
                const res = await onboardingAPI.getAwsLink('READ_ONLY');
                setAwsLink(res.data.url);
            } catch (err) {
                toast.error("Failed to generate AWS Link");
            }
        };
        getLink();
    }, []);

    const handleVerify = async () => {
        if (!roleArn.startsWith('arn:aws:iam::')) {
            setError("Invalid Role ARN format");
            return;
        }

        setVerifying(true);
        setError(null);

        try {
            await onboardingAPI.verify(roleArn);
            onNext(); // Move to next step (or success)
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
            <h2 className="text-2xl font-bold text-gray-900 mb-6">Connect your AWS Account</h2>

            <div className="space-y-8">
                {/* Step 1 */}
                <div className="flex gap-4">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-bold">1</div>
                    <div className="flex-1">
                        <h3 className="font-semibold text-gray-900 mb-1">Launch CloudFormation Stack</h3>
                        <p className="text-sm text-gray-500 mb-3">
                            Click below to open the AWS Console. This will create a read-only IAM Role with a unique External ID.
                        </p>
                        <a
                            href={awsLink}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition-colors font-medium text-sm"
                        >
                            <FiExternalLink /> Launch AWS Console
                        </a>
                    </div>
                </div>

                {/* Step 2 */}
                <div className="flex gap-4">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-bold">2</div>
                    <div className="flex-1">
                        <h3 className="font-semibold text-gray-900 mb-1">Review & Create</h3>
                        <p className="text-sm text-gray-500">
                            In the AWS Console, scroll to the bottom, check the "I acknowledge..." box, and click <strong>Create stack</strong>. Wait for the status to reach <strong>CREATE_COMPLETE</strong>.
                        </p>
                    </div>
                </div>

                {/* Step 3 */}
                <div className="flex gap-4">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-bold">3</div>
                    <div className="flex-1">
                        <h3 className="font-semibold text-gray-900 mb-1">Enter Role ARN</h3>
                        <p className="text-sm text-gray-500 mb-3">
                            Go to the <strong>Outputs</strong> tab in CloudFormation and copy the value of <code>RoleArn</code>.
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
