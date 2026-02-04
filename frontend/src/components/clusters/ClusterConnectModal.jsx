/**
 * Cluster Connect Modal Component
 * Agent-based cluster connection flow for CLIENT users only
 *
 * Flow:
 * 1. Select K8s provider (EKS, AKS, GKE, OpenShift, kOps, Other)
 * 2. Enter cluster name
 * 3. Show agent installation script
 * 4. "I ran the script" button
 * 5. Success + Resource cost inputs
 *
 * Uses AWS STS assume role for read-only monitoring
 */
import React, { useState } from 'react';
import { Card, Button } from '../shared';
import {
  FiX, FiCopy, FiCheck, FiAlertCircle, FiRefreshCw
} from 'react-icons/fi';
import toast from 'react-hot-toast';
import { clusterAPI } from '../../services/api';

// Backend URL for agent connection (update with your ngrok URL)
const BACKEND_URL = 'https://34c3-103-147-161-240.ngrok-free.app';

const ClusterConnectModal = ({ isOpen, onClose, onSuccess }) => {
  const [step, setStep] = useState(1); // 1: Details, 2: Command, 3: Success
  const [clusterName, setClusterName] = useState('');
  const [region, setRegion] = useState('');

  const [installScript, setInstallScript] = useState('');
  const [clusterId, setClusterId] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [scriptCopied, setScriptCopied] = useState(false);

  const [costs, setCosts] = useState({
    cpu_cost: '',
    memory_cost: '',
    ingress_cost: '',
    egress_cost: '',
    storage_cost: ''
  });



  const handleConnect = async () => {
    if (!clusterName.trim()) {
      toast.error('Please enter a cluster name');
      return;
    }

    try {
      setVerifying(true);

      // Use default region if not provided
      const actualRegion = region || 'us-east-1';

      // 1. Create Cluster in Backend and get API key + Config
      const response = await clusterAPI.generateInstallScript({
        provider: 'k8s', // Default generic provider
        cluster_name: clusterName,
        region: actualRegion
      });

      const { cluster_id, api_key, script: chartUri } = response.data;
      setClusterId(cluster_id);

      const WS_URL = BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://');

      const INSTALL_SCRIPT_URL = "https://raw.githubusercontent.com/atharva0608/final-ml/main/install.sh";

      // Ensure backendUrl uses wss:// if it's the websocket endpoint
      const wsUrl = BACKEND_URL.replace('http', 'ws').replace('https', 'wss');

      const oneLiner = `curl -sL ${INSTALL_SCRIPT_URL} | CLUSTER_ID=${cluster_id} API_KEY=${api_key} BACKEND_URL=${wsUrl}/ws/cluster/${cluster_id} sh`;

      setInstallScript(oneLiner);
      setStep(2);
    } catch (error) {
      toast.error('Failed to register cluster');
      console.error(error);
    } finally {
      setVerifying(false);
    }
  };

  const handleCopyScript = () => {
    navigator.clipboard.writeText(installScript);
    setScriptCopied(true);
    toast.success('Helm command copied!');
    setTimeout(() => setScriptCopied(false), 2000);
  };

  const handleVerifyConnection = async () => {
    setVerifying(true);
    try {
      const response = await clusterAPI.verifyConnection(clusterId);

      if (response.data.status === 'connected') {
        toast.success('Cluster connected successfully!');
        setStep(3);
      } else {
        toast.error('Agent not detected yet. Please wait a moment and try again.');
      }
    } catch (error) {
      toast.error('Verification failed');
    } finally {
      setVerifying(false);
    }
  };

  const handleSubmitCosts = async (e) => {
    e.preventDefault();
    try {
      await clusterAPI.updateResourceCosts(clusterId, costs);
      toast.success('Resource costs saved');
      onSuccess && onSuccess();
      handleClose();
    } catch (error) {
      toast.error('Failed to save costs');
    }
  };

  const handleClose = () => {
    setStep(1);
    setClusterName('');
    setRegion('');
    setInstallScript('');
    setClusterId('');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-xl font-bold text-gray-900">
            Connect Kubernetes Cluster
          </h2>
          <button onClick={handleClose} className="text-gray-400 hover:text-gray-600">
            <FiX className="w-6 h-6" />
          </button>
        </div>

        <div className="p-6">
          {step === 1 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-4">
                  1. CLUSTER DETAILS
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Cluster Name
                    </label>
                    <input
                      type="text"
                      value={clusterName}
                      onChange={(e) => setClusterName(e.target.value)}
                      placeholder="e.g. production-cluster"
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Region (Optional)
                    </label>
                    <input
                      type="text"
                      value={region}
                      onChange={(e) => setRegion(e.target.value)}
                      placeholder="e.g. us-east-1"
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end">
                <Button
                  variant="primary"
                  onClick={handleConnect}
                  disabled={!clusterName.trim()}
                  loading={verifying}
                >
                  Generate Installation Command →
                </Button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">
                  2. INSTALL AGENT
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  Run this Helm command in your cluster terminal. It installs the Spot Optimizer Agent and connects it to this dashboard.
                </p>
              </div>

              <div className="relative">
                <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm font-mono whitespace-pre-wrap">
                  <code>{installScript}</code>
                </pre>
                <button
                  onClick={handleCopyScript}
                  className="absolute top-2 right-2 p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors group"
                  title="Copy command"
                >
                  {scriptCopied ? (
                    <FiCheck className="w-5 h-5 text-green-400" />
                  ) : (
                    <div className="flex items-center space-x-1">
                      <span className="text-xs text-gray-300 hidden group-hover:inline">Copy Helm Command</span>
                      <FiCopy className="w-5 h-5 text-gray-300" />
                    </div>
                  )}
                </button>
              </div>

              <div className="flex justify-between items-center pt-4">
                <Button variant="outline" onClick={() => setStep(1)}>
                  ← Back
                </Button>
                <Button
                  variant="primary"
                  onClick={handleVerifyConnection}
                  loading={verifying}
                  disabled={verifying}
                  icon={verifying ? <FiRefreshCw className="animate-spin" /> : null}
                >
                  {verifying ? 'Verifying...' : 'I ran the command'}
                </Button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6">
              <div className="flex items-center space-x-3 p-4 bg-green-50 border border-green-200 rounded-lg">
                <FiCheck className="w-6 h-6 text-green-600 flex-shrink-0" />
                <div>
                  <h3 className="font-semibold text-green-900">
                    Connected Successfully!
                  </h3>
                  <p className="text-sm text-green-700">The agent is now sending metrics.</p>
                </div>
              </div>

              <div className="flex justify-end">
                <Button variant="primary" onClick={handleClose}>
                  Done
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ClusterConnectModal;
