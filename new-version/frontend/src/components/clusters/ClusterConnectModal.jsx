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
import {
  SiAmazonaws, SiMicrosoftazure, SiGooglecloud,
  SiRedhat, SiKubernetes
} from 'react-icons/si';
import toast from 'react-hot-toast';
import { clusterAPI } from '../../services/api';

const ClusterConnectModal = ({ isOpen, onClose, onSuccess }) => {
  const [step, setStep] = useState(1); // 1: Provider, 2: Script, 3: Success/Costs
  const [provider, setProvider] = useState('');
  const [clusterName, setClusterName] = useState('');
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

  const providers = [
    { id: 'eks', name: 'EKS', icon: SiAmazonaws, color: 'orange' },
    { id: 'aks', name: 'AKS', icon: SiMicrosoftazure, color: 'blue' },
    { id: 'gke', name: 'GKE', icon: SiGooglecloud, color: 'blue' },
    { id: 'openshift', name: 'OpenShift', label: 'on AWS', icon: SiRedhat, color: 'red' },
    { id: 'kops', name: 'kOps', label: 'on AWS', icon: SiKubernetes, color: 'blue' },
    { id: 'other', name: 'Other', label: 'anywhere', icon: SiKubernetes, color: 'blue' },
  ];

  const handleProviderSelect = async () => {
    if (!provider || !clusterName.trim()) {
      toast.error('Please select provider and enter cluster name');
      return;
    }

    try {
      // Generate installation script
      const response = await clusterAPI.generateInstallScript({
        provider,
        cluster_name: clusterName
      });

      setInstallScript(response.data.script);
      setClusterId(response.data.cluster_id);
      setStep(2);
    } catch (error) {
      toast.error('Failed to generate installation script');
    }
  };

  const handleCopyScript = () => {
    navigator.clipboard.writeText(installScript);
    setScriptCopied(true);
    toast.success('Script copied to clipboard');
    setTimeout(() => setScriptCopied(false), 2000);
  };

  const handleVerifyConnection = async () => {
    setVerifying(true);
    try {
      const response = await clusterAPI.verifyConnection(clusterId);

      if (response.data.connected) {
        toast.success('Cluster connected successfully!');
        setStep(3);
      } else {
        toast.error('Agent not detected yet. Please run the script and try again.');
      }
    } catch (error) {
      toast.error('Connection verification failed');
    } finally {
      setVerifying(false);
    }
  };

  const handleSubmitCosts = async (e) => {
    e.preventDefault();

    try {
      await clusterAPI.updateResourceCosts(clusterId, costs);
      toast.success('Resource costs saved successfully');
      onSuccess && onSuccess();
      handleClose();
    } catch (error) {
      toast.error('Failed to save resource costs');
    }
  };

  const handleClose = () => {
    setStep(1);
    setProvider('');
    setClusterName('');
    setInstallScript('');
    setClusterId('');
    setCosts({
      cpu_cost: '',
      memory_cost: '',
      ingress_cost: '',
      egress_cost: '',
      storage_cost: ''
    });
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b">
          <h2 className="text-2xl font-bold text-gray-900">
            Connect your K8s cluster
          </h2>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <FiX className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Step 1: Provider Selection */}
          {step === 1 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-4">SELECT PROVIDER:</h3>
                <div className="grid grid-cols-3 gap-3">
                  {providers.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => setProvider(p.id)}
                      className={`p-4 border-2 rounded-lg transition-all ${
                        provider === p.id
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <div className="flex flex-col items-center space-y-2">
                        <p.icon className={`w-8 h-8 text-${p.color}-600`} />
                        <span className="font-medium text-gray-900">{p.name}</span>
                        {p.label && (
                          <span className="text-xs text-gray-500">{p.label}</span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-4">
                  Connect any Kubernetes cluster with internet access
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  Connect any Kubernetes cluster with internet access, whether it's on-premises,
                  self-hosted, or from other cloud provider.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  ENTER CLUSTER NAME:
                </label>
                <input
                  type="text"
                  value={clusterName}
                  onChange={(e) => setClusterName(e.target.value)}
                  placeholder="my-cluster-name"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex justify-end">
                <Button
                  variant="primary"
                  onClick={handleProviderSelect}
                  disabled={!provider || !clusterName.trim()}
                >
                  Generate Script →
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: Installation Script */}
          {step === 2 && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">RUN THE SCRIPT:</h3>
                <p className="text-sm text-gray-600 mb-4">
                  Make sure that kubectl is installed and that it can access your cluster. Copy the
                  script and run it in your cloud shell or terminal. CAST AI's read-only agent has no
                  access to your sensitive data, and doesn't change your cluster configuration.{' '}
                  <a href="#" className="text-blue-600 hover:underline">Read more about the security of our agent.</a>
                </p>
              </div>

              <div className="relative">
                <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
                  <code>{installScript}</code>
                </pre>
                <button
                  onClick={handleCopyScript}
                  className="absolute top-2 right-2 p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
                  title="Copy script"
                >
                  {scriptCopied ? (
                    <FiCheck className="w-5 h-5 text-green-400" />
                  ) : (
                    <FiCopy className="w-5 h-5 text-gray-300" />
                  )}
                </button>
              </div>

              <div className="flex items-center space-x-2 text-sm text-gray-600">
                <img src="/soc2-badge.png" alt="SOC2" className="w-8 h-8" onError={(e) => e.target.style.display = 'none'} />
                <span>SOC2, ISO27001 & CIS Benchmarks certified</span>
              </div>

              <div className="flex justify-between">
                <Button
                  variant="outline"
                  onClick={() => setStep(1)}
                >
                  ← Back
                </Button>
                <Button
                  variant="primary"
                  onClick={handleVerifyConnection}
                  loading={verifying}
                  disabled={verifying}
                  icon={verifying ? <FiRefreshCw className="animate-spin" /> : null}
                >
                  {verifying ? 'Verifying...' : 'I ran the script'}
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Success + Resource Costs */}
          {step === 3 && (
            <div className="space-y-6">
              <div className="flex items-center space-x-3 p-4 bg-green-50 border border-green-200 rounded-lg">
                <FiCheck className="w-6 h-6 text-green-600 flex-shrink-0" />
                <div>
                  <h3 className="font-semibold text-green-900">
                    {clusterName} connected successfully!
                  </h3>
                </div>
              </div>

              <form onSubmit={handleSubmitCosts} className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Provide Resource Costs</h3>
                  <p className="text-sm text-gray-600 mb-4">
                    Please enter the normalized costs for your resources. This will help us accurately
                    calculate your cloud costs.
                  </p>
                </div>

                <div>
                  <h4 className="text-sm font-semibold text-gray-700 mb-3">ENTER NORMALISED COSTS</h4>

                  <div className="space-y-4">
                    {/* Compute cost */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Compute cost
                      </label>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-xs text-gray-600 mb-1">CPU</label>
                          <div className="relative">
                            <input
                              type="number"
                              step="0.01"
                              value={costs.cpu_cost}
                              onChange={(e) => setCosts({...costs, cpu_cost: e.target.value})}
                              placeholder="3.56"
                              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 pr-12"
                            />
                            <span className="absolute right-3 top-2 text-gray-500">$/h</span>
                          </div>
                        </div>
                        <div>
                          <label className="block text-xs text-gray-600 mb-1">Memory</label>
                          <div className="relative">
                            <input
                              type="number"
                              step="0.01"
                              value={costs.memory_cost}
                              onChange={(e) => setCosts({...costs, memory_cost: e.target.value})}
                              placeholder="1.27"
                              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 pr-12"
                            />
                            <span className="absolute right-3 top-2 text-gray-500">$/h</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Network cost */}
                    <div>
                      <div className="flex items-center space-x-2 mb-2">
                        <label className="block text-sm font-medium text-gray-700">
                          Network cost
                        </label>
                        <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded">
                          COMING SOON
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Ingress</label>
                          <div className="relative">
                            <input
                              type="number"
                              disabled
                              placeholder="0.00"
                              className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-400 pr-12"
                            />
                            <span className="absolute right-3 top-2 text-gray-400">$/h</span>
                          </div>
                        </div>
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Egress</label>
                          <div className="relative">
                            <input
                              type="number"
                              disabled
                              placeholder="0.00"
                              className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-400 pr-12"
                            />
                            <span className="absolute right-3 top-2 text-gray-400">$/h</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Storage cost */}
                    <div>
                      <div className="flex items-center space-x-2 mb-2">
                        <label className="block text-sm font-medium text-gray-700">
                          Storage cost
                        </label>
                        <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded">
                          COMING SOON
                        </span>
                      </div>
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">Storage</label>
                        <div className="relative">
                          <input
                            type="number"
                            disabled
                            placeholder="0.00"
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-400 pr-12"
                          />
                          <span className="absolute right-3 top-2 text-gray-400">$/h</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex justify-end">
                  <Button
                    type="submit"
                    variant="primary"
                  >
                    Save
                  </Button>
                </div>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ClusterConnectModal;
