import React, { useState, useEffect } from 'react';
import { FiPlus, FiEdit2, FiTrash2, FiTag, FiCheck, FiX } from 'react-icons/fi';
import { toast } from 'react-hot-toast';
import { tagTemplateAPI } from '../../services/api';
import Card from '../shared/Card';
import Input from '../shared/Input';
import Button from '../shared/Button';
import Badge from '../shared/Badge';

const TagTemplateManager = () => {
    const [templates, setTemplates] = useState([]);
    const [loading, setLoading] = useState(true);
    const [isEditing, setIsEditing] = useState(false);
    const [currentTemplate, setCurrentTemplate] = useState(null);
    const [formData, setFormData] = useState({
        name: '',
        description: '',
        tags: {},
        is_default: false
    });

    const [newTagKey, setNewTagKey] = useState('');
    const [newTagValue, setNewTagValue] = useState('');

    useEffect(() => {
        fetchTemplates();
    }, []);

    const fetchTemplates = async () => {
        try {
            setLoading(true);
            const response = await tagTemplateAPI.listTemplates();
            setTemplates(response.data || []);
        } catch (error) {
            console.error("Failed to fetch templates:", error);
            toast.error("Failed to load tag templates");
        } finally {
            setLoading(false);
        }
    };

    const handleCreateClick = () => {
        setCurrentTemplate(null);
        setFormData({
            name: '',
            description: '',
            tags: {},
            is_default: false
        });
        setIsEditing(true);
    };

    const handleEditClick = (template) => {
        setCurrentTemplate(template);
        setFormData({
            name: template.name,
            description: template.description || '',
            tags: { ...template.tags },
            is_default: template.is_default
        });
        setIsEditing(true);
    };

    const handleDeleteClick = async (id) => {
        if (!window.confirm("Are you sure you want to delete this template?")) return;
        try {
            await tagTemplateAPI.deleteTemplate(id);
            toast.success("Template deleted successfully");
            fetchTemplates();
        } catch (error) {
            console.error("Failed to delete template:", error);
            toast.error("Failed to delete template");
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            if (currentTemplate) {
                await tagTemplateAPI.updateTemplate(currentTemplate.id, formData);
                toast.success("Template updated successfully");
            } else {
                await tagTemplateAPI.createTemplate(formData);
                toast.success("Template created successfully");
            }
            setIsEditing(false);
            fetchTemplates();
        } catch (error) {
            console.error("Failed to save template:", error);
            toast.error("Failed to save template");
        }
    };

    const addTag = () => {
        if (!newTagKey || !newTagValue) return;
        setFormData({
            ...formData,
            tags: {
                ...formData.tags,
                [newTagKey]: newTagValue
            }
        });
        setNewTagKey('');
        setNewTagValue('');
    };

    const removeTag = (key) => {
        const newTags = { ...formData.tags };
        delete newTags[key];
        setFormData({ ...formData, tags: newTags });
    };

    if (loading) return <div className="p-4">Loading templates...</div>;

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-lg font-medium text-gray-900">Tag Templates</h2>
                    <p className="text-sm text-gray-500">Manage reusable sets of tags for quick application.</p>
                </div>
                {!isEditing && (
                    <Button onClick={handleCreateClick} icon={FiPlus} variant="primary">
                        Create Template
                    </Button>
                )}
            </div>

            {isEditing ? (
                <Card className="p-6">
                    <form onSubmit={handleSubmit} className="space-y-6">
                        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                            <Input
                                label="Template Name"
                                value={formData.name}
                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                required
                            />
                            <Input
                                label="Description"
                                value={formData.description}
                                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">Default Tags</label>
                            <div className="bg-gray-50 p-4 rounded-lg space-y-3">
                                <div className="flex gap-2">
                                    <Input
                                        placeholder="Key (e.g., Environment)"
                                        value={newTagKey}
                                        onChange={(e) => setNewTagKey(e.target.value)}
                                        className="flex-1"
                                    />
                                    <Input
                                        placeholder="Value (e.g., Production)"
                                        value={newTagValue}
                                        onChange={(e) => setNewTagValue(e.target.value)}
                                        className="flex-1"
                                    />
                                    <Button type="button" onClick={addTag} icon={FiPlus} variant="secondary">Add</Button>
                                </div>
                                <div className="flex flex-wrap gap-2 mt-2">
                                    {Object.entries(formData.tags).map(([key, value]) => (
                                        <div key={key} className="flex items-center gap-1 px-3 py-1 bg-white border border-gray-200 rounded-full text-sm">
                                            <span className="font-medium text-gray-700">{key}:</span>
                                            <span className="text-gray-600">{value}</span>
                                            <button type="button" onClick={() => removeTag(key)} className="ml-1 text-gray-400 hover:text-red-500">
                                                <FiX size={14} />
                                            </button>
                                        </div>
                                    ))}
                                    {Object.keys(formData.tags).length === 0 && (
                                        <span className="text-sm text-gray-400 italic">No tags added yet</span>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="flex items-center gap-2">
                            <input
                                type="checkbox"
                                id="is_default"
                                checked={formData.is_default}
                                onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                            />
                            <label htmlFor="is_default" className="text-sm text-gray-700">Set as default template for new resources</label>
                        </div>

                        <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
                            <Button type="button" variant="ghost" onClick={() => setIsEditing(false)}>Cancel</Button>
                            <Button type="submit" variant="primary" icon={FiCheck}>Save Template</Button>
                        </div>
                    </form>
                </Card>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {templates.map((template) => (
                        <Card key={template.id} className="hover:shadow-md transition-shadow">
                            <div className="p-5 space-y-4">
                                <div className="flex justify-between items-start">
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <h3 className="text-lg font-medium text-gray-900">{template.name}</h3>
                                            {template.is_default && (
                                                <Badge variant="success" size="sm">Default</Badge>
                                            )}
                                        </div>
                                        <p className="text-sm text-gray-500 mt-1">{template.description || "No description"}</p>
                                    </div>
                                    <div className="flex gap-1">
                                        <button onClick={() => handleEditClick(template)} className="p-1.5 text-gray-400 hover:text-blue-600 rounded-md hover:bg-blue-50">
                                            <FiEdit2 size={16} />
                                        </button>
                                        <button onClick={() => handleDeleteClick(template.id)} className="p-1.5 text-gray-400 hover:text-red-600 rounded-md hover:bg-red-50">
                                            <FiTrash2 size={16} />
                                        </button>
                                    </div>
                                </div>

                                <div className="border-t border-gray-100 pt-3">
                                    <div className="flex flex-wrap gap-2">
                                        {Object.entries(template.tags).slice(0, 5).map(([key, value]) => (
                                            <span key={key} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                                                {key}={value}
                                            </span>
                                        ))}
                                        {Object.keys(template.tags).length > 5 && (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-50 text-gray-500">
                                                +{Object.keys(template.tags).length - 5} more
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </Card>
                    ))}
                    {templates.length === 0 && (
                        <div className="col-span-full py-12 text-center bg-gray-50 rounded-lg border-2 border-dashed border-gray-200">
                            <FiTag className="mx-auto h-12 w-12 text-gray-400" />
                            <h3 className="mt-2 text-sm font-medium text-gray-900">No templates yet</h3>
                            <p className="mt-1 text-sm text-gray-500">Create a template to quickly apply standard tags.</p>
                            <div className="mt-6">
                                <Button onClick={handleCreateClick} variant="primary" size="sm" icon={FiPlus}>
                                    Create Template
                                </Button>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default TagTemplateManager;
