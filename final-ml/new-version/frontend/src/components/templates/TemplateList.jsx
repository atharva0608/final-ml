/**
 * Template Management Component
 */
import React, { useState, useEffect } from 'react';
import { templateAPI } from '../../services/api';
import { useTemplateStore } from '../../store/useStore';
import { Card, Button, Badge, Input } from '../shared';
import { FiPlus, FiEdit2, FiTrash2, FiCheck } from 'react-icons/fi';
import toast from 'react-hot-toast';

import TemplateBuilder from './TemplateBuilder';

const TemplateList = () => {
  const { templates, setTemplates, setLoading, loading } = useTemplateStore();
  const [showCreateModal, setShowCreateModal] = useState(false);

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

  const handleCreate = async (formData) => {
    try {
      await templateAPI.create(formData);
      toast.success('Template created successfully');
      setShowCreateModal(false);
      fetchTemplates();
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
                  <span className="text-gray-600">Disk:</span>
                  <span className="font-medium">{template.root_volume_type} {template.root_volume_size}GB</span>
                </div>
                <div>
                  <span className="text-gray-600">Families:</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {template.instance_families?.slice(0, 6).map((family) => (
                      <Badge key={family} color="blue" size="sm">{family}</Badge>
                    ))}
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
          <div className="bg-white rounded-lg w-full max-w-4xl h-[90vh] overflow-hidden">
            <TemplateBuilder
              onSave={handleCreate}
              onCancel={() => setShowCreateModal(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default TemplateList;
