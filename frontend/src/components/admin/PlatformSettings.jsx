import React, { useState, useEffect } from 'react';
import { Card, Button } from '../shared';
import { FiCloud, FiCheck, FiX, FiAlertTriangle, FiLoader, FiEye, FiEyeOff } from 'react-icons/fi';
import { api } from '../../services/api';
import toast from 'react-hot-toast';

const PlatformSettings = () => {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [connected, setConnected] = useState(false);
    const [showSecret, setShowSecret] = useState(false);
    const [connectionInfo, setConnectionInfo] = useState(null);
    const [formData, setFormData] = useState({
        accessKeyId: '', secretAccessKey: '', region: 'us-east-1', roleArn: ''
    });

    const regions = ['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2', 'eu-west-1', 'eu-west-2', 'eu-central-1', 'ap-south-1', 'ap-southeast-1', 'ap-northeast-1'];

    useEffect(() => { fetchConnectionStatus(); }, []);

    const fetchConnectionStatus = async () => {
        try {
            const response = await api.get('/api/v1/admin/platform/connection');
            setConnected(response.data.connected);
            setConnectionInfo(response.data);
        } catch (error) {
            console.error('Failed to fetch platform connection status:', error);
            setConnected(false);
        } finally { setLoading(false); }
    };

    const handleConnect = async (e) => {
        e.preventDefault();
        if (!formData.accessKeyId || !formData.secretAccessKey) {
            toast.error('Access Key ID and Secret Access Key are required');
            return;
        }
        setSaving(true);
        try {
            const response = await api.post('/api/v1/admin/platform/connect', {
                access_key_id: formData.accessKeyId,
                secret_access_key: formData.secretAccessKey,
                region: formData.region,
                role_arn: formData.roleArn || null
            });
            toast.success('Platform Identity verified and connected!');
            setConnected(true);
            setConnectionInfo(response.data);
            setFormData(prev => ({ ...prev, secretAccessKey: '' }));
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Failed to connect - Invalid credentials');
        } finally { setSaving(false); }
    };

    const handleDisconnect = async () => {
        if (!window.confirm('⚠️ WARNING: Disconnecting will stop the platform from managing ALL client accounts immediately.\n\nAre you sure you want to revoke platform credentials?')) return;
        setSaving(true);
        try {
            await api.delete('/api/v1/admin/platform/disconnect');
            toast.success('Platform credentials removed');
            setConnected(false);
            setConnectionInfo(null);
            setFormData({ accessKeyId: '', secretAccessKey: '', region: 'us-east-1', roleArn: '' });
        } catch (error) { toast.error('Failed to disconnect'); }
        finally { setSaving(false); }
    };

    if (loading) return (<div className="flex items-center justify-center h-48"><FiLoader className="w-8 h-8 animate-spin text-blue-500" /></div>);

    return (
        <Card className="p-6">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center space-x-3">
                    <div className={`p-3 rounded-lg ${connected ? 'bg-green-100' : 'bg-gray-100'}`}>
                        <FiCloud className={`w-6 h-6 ${connected ? 'text-green-600' : 'text-gray-500'}`} />
                    </div>
                    <div>
                        <h2 className="text-lg font-bold text-gray-900">Platform AWS Identity</h2>
                        <p className="text-sm text-gray-500">Master credentials for managing all client accounts</p>
                    </div>
                </div>
                <div className={`flex items-center space-x-2 px-4 py-2 rounded-full ${connected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {connected ? (<><span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span><span className="font-medium">System Online</span></>)
                        : (<><span className="w-2 h-2 bg-red-500 rounded-full"></span><span className="font-medium">Offline</span></>)}
                </div>
            </div>

            {connected && connectionInfo ? (
                <div className="space-y-4">
                    <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                        <div className="flex items-center space-x-2 text-green-700 mb-3"><FiCheck className="w-5 h-5" /><span className="font-semibold">AWS Identity Verified</span></div>
                        <div className="grid grid-cols-2 gap-4 text-sm">
                            <div><span className="text-gray-500">Access Key ID:</span><p className="font-mono text-gray-900">{connectionInfo.access_key_id || 'N/A'}</p></div>
                            <div><span className="text-gray-500">Region:</span><p className="text-gray-900">{connectionInfo.region || 'us-east-1'}</p></div>
                            {connectionInfo.role_arn && (<div className="col-span-2"><span className="text-gray-500">Role ARN:</span><p className="font-mono text-gray-900 text-xs break-all">{connectionInfo.role_arn}</p></div>)}
                        </div>
                    </div>
                    <div className="border-t pt-4 mt-4">
                        <div className="flex items-center space-x-2 text-red-600 mb-3"><FiAlertTriangle className="w-5 h-5" /><span className="font-semibold">Danger Zone</span></div>
                        <Button variant="danger" onClick={handleDisconnect} disabled={saving} className="bg-red-600 hover:bg-red-700 text-white">
                            {saving ? <FiLoader className="w-4 h-4 animate-spin mr-2" /> : <FiX className="w-4 h-4 mr-2" />}Revoke Credentials
                        </Button>
                        <p className="text-xs text-gray-500 mt-2">This will immediately stop all background workers from accessing AWS.</p>
                    </div>
                </div>
            ) : (
                <form onSubmit={handleConnect} className="space-y-4">
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
                        <div className="flex items-start space-x-2 text-yellow-700"><FiAlertTriangle className="w-5 h-5 mt-0.5" />
                            <div><p className="font-semibold">No Platform Credentials Configured</p><p className="text-sm">Enter your AWS credentials below to enable account management.</p></div>
                        </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div><label className="block text-sm font-medium text-gray-700 mb-1">AWS Access Key ID <span className="text-red-500">*</span></label>
                            <input type="text" value={formData.accessKeyId} onChange={(e) => setFormData(prev => ({ ...prev, accessKeyId: e.target.value }))} placeholder="AKIAIOSFODNN7EXAMPLE" className="w-full border rounded-lg p-3 font-mono text-sm" required /></div>
                        <div><label className="block text-sm font-medium text-gray-700 mb-1">AWS Secret Access Key <span className="text-red-500">*</span></label>
                            <div className="relative"><input type={showSecret ? 'text' : 'password'} value={formData.secretAccessKey} onChange={(e) => setFormData(prev => ({ ...prev, secretAccessKey: e.target.value }))} placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" className="w-full border rounded-lg p-3 font-mono text-sm pr-10" required />
                                <button type="button" onClick={() => setShowSecret(!showSecret)} className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600">{showSecret ? <FiEyeOff /> : <FiEye />}</button></div></div>
                        <div><label className="block text-sm font-medium text-gray-700 mb-1">Default Region</label><select value={formData.region} onChange={(e) => setFormData(prev => ({ ...prev, region: e.target.value }))} className="w-full border rounded-lg p-3">{regions.map(r => (<option key={r} value={r}>{r}</option>))}</select></div>
                        <div><label className="block text-sm font-medium text-gray-700 mb-1">Platform Role ARN (Optional)</label><input type="text" value={formData.roleArn} onChange={(e) => setFormData(prev => ({ ...prev, roleArn: e.target.value }))} placeholder="arn:aws:iam::123456789:role/SpotOptimizer" className="w-full border rounded-lg p-3 font-mono text-sm" /></div>
                    </div>
                    <div className="flex justify-end pt-4"><Button type="submit" variant="primary" disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white px-6">{saving ? (<><FiLoader className="w-4 h-4 animate-spin mr-2" />Verifying...</>) : (<><FiCheck className="w-4 h-4 mr-2" />Establish Connection</>)}</Button></div>
                </form>
            )}
        </Card>
    );
};

export default PlatformSettings;
