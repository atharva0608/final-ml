/**
 * Template Management Component
 */
import React, { useState, useEffect } from 'react';
import { templateAPI } from '../../services/api';
import { useTemplateStore } from '../../store/useStore';
import { Card, Button, Badge, Input } from '../shared';
import { FiPlus, FiEdit2, FiTrash2, FiCheck } from 'react-icons/fi';
import toast from 'react-hot-toast';

const TemplateList = () => {
  const { templates, setTemplates, setLoading, loading } = useTemplateStore();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    families: ['t3', 'm5', 'c5'],
    architecture: 'amd64',
    strategy: 'balanced',
    disk_type: 'gp3',
    disk_size: 100,
    is_default: false,
  });

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const response = await templateAPI.list();
      setTemplates(response.data.templates || []);
    } catch (error) {
      toast.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      await templateAPI.create(formData);
      toast.success('Template created successfully');
      setShowCreateModal(false);
      fetchTemplates();
      resetForm();
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to create template');
    }
  };

  const handleSetDefault = async (templateId) => {
    try {
      await templateAPI.setDefault(templateId);
      toast.success('Default template updated');
      fetchTemplates();
    } catch (error) {
      toast.error('Failed to set default template');
    }
  };

  const handleDelete = async (templateId) => {
    if (!window.confirm('Are you sure you want to delete this template?')) return;

    try {
      await templateAPI.delete(templateId);
      toast.success('Template deleted');
      fetchTemplates();
    } catch (error) {
      toast.error('Failed to delete template');
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      families: ['t3', 'm5', 'c5'],
      architecture: 'amd64',
      strategy: 'balanced',
      disk_type: 'gp3',
      disk_size: 100,
      is_default: false,
    });
  };

  const awsInstanceFamilies = [
    't2', 't3', 't3a', 't4g', 'm5', 'm5a', 'm6i', 'm6a', 'm7i',
    'c5', 'c5a', 'c6i', 'c6a', 'c7i', 'r5', 'r5a', 'r6i', 'r7i'
  ];

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
          <h1 className="text-3xl font-bold text-gray-900">Node Templates</h1>
          <p className="text-gray-600 mt-1">Define instance selection preferences</p>
        </div>
        <Button variant="primary" icon={<FiPlus />} onClick={() => setShowCreateModal(true)}>
          Create Template
        </Button>
      </div>

      {/* Template Grid */}
      {templates.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <p className="text-gray-500 text-lg">No templates found</p>
            <p className="text-gray-400 mt-2">Create your first template to get started</p>
            <Button variant="primary" className="mt-4" onClick={() => setShowCreateModal(true)}>
              Create Template
            </Button>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {templates.map((template) => (
            <Card key={template.id} className="hover:shadow-lg transition-shadow">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">{template.name}</h3>
                  {template.is_default && (
                    <Badge color="green" className="mt-1">
                      <FiCheck className="w-3 h-3 mr-1" />
                      Default
                    </Badge>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleDelete(template.id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <FiTrash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Architecture:</span>
                  <span className="font-medium">{template.architecture}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Strategy:</span>
                  <span className="font-medium capitalize">{template.strategy}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Disk:</span>
                  <span className="font-medium">{template.disk_type} {template.disk_size}GB</span>
                </div>
                <div>
                  <span className="text-gray-600">Families:</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {template.families.slice(0, 6).map((family) => (
                      <Badge key={family} color="blue" size="sm">{family}</Badge>
                    ))}
                    {template.families.length > 6 && (
                      <Badge color="gray" size="sm">+{template.families.length - 6}</Badge>
                    )}
                  </div>
                </div>
              </div>

              {!template.is_default && (
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full mt-4"
                  onClick={() => handleSetDefault(template.id)}
                >
                  Set as Default
                </Button>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">Create Template</h2>

            <form onSubmit={handleCreate} className="space-y-4">
              <Input
                label="Template Name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., Production Template"
                required
              />

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Architecture
                </label>
                <select
                  value={formData.architecture}
                  onChange={(e) => setFormData({ ...formData, architecture: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="amd64">AMD64 (x86_64)</option>
                  <option value="arm64">ARM64 (Graviton)</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Strategy
                </label>
                <select
                  value={formData.strategy}
                  onChange={(e) => setFormData({ ...formData, strategy: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="cost_optimized">Cost Optimized</option>
                  <option value="balanced">Balanced</option>
                  <option value="performance">Performance</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Instance Families (Select multiple)
                </label>
                <div className="grid grid-cols-4 gap-2">
                  {awsInstanceFamilies.map((family) => (
                    <label key={family} className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.families.includes(family)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setFormData({ ...formData, families: [...formData.families, family] });
                          } else {
                            setFormData({
                              ...formData,
                              families: formData.families.filter((f) => f !== family),
                            });
                          }
                        }}
                        className="rounded border-gray-300"
                      />
                      <span className="text-sm">{family}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Disk Type
                  </label>
                  <select
                    value={formData.disk_type}
                    onChange={(e) => setFormData({ ...formData, disk_type: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="gp2">GP2</option>
                    <option value="gp3">GP3</option>
                    <option value="io1">IO1</option>
                  </select>
                </div>

                <Input
                  label="Disk Size (GB)"
                  type="number"
                  value={formData.disk_size}
                  onChange={(e) => setFormData({ ...formData, disk_size: parseInt(e.target.value) })}
                  min="20"
                  max="1000"
                  required
                />
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
                  Set as default template
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setShowCreateModal(false);
                    resetForm();
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary">
                  Create Template
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default TemplateList;
