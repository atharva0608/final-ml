import React, { useState, useEffect } from 'react';
import { useHibernationStore } from '../../store/useHibernationStore';
import { FiClock, FiSun, FiBriefcase, FiGlobe, FiMoon, FiDollarSign, FiPlus, FiTrash2, FiEdit2, FiX } from 'react-icons/fi';
import toast from 'react-hot-toast';

const BUILT_IN_TEMPLATES = [
    {
        id: 'business_hours',
        name: 'Business Hours',
        description: 'Mon-Fri, 9AM - 6PM Active',
        icon: FiBriefcase,
        savings: '54%',
        builtIn: true,
        apply: () => {
            const newMatrix = Array(168).fill(0); // Default sleep
            for (let day = 0; day < 5; day++) { // Mon-Fri
                for (let hour = 9; hour < 18; hour++) {
                    newMatrix[day * 24 + hour] = 1; // Active 9-18
                }
            }
            return newMatrix;
        }
    },
    {
        id: 'nights_only',
        name: 'Nights Only',
        description: 'Sleep 6PM - 8AM Daily',
        icon: FiMoon,
        savings: '67%',
        builtIn: true,
        apply: () => {
            const newMatrix = Array(168).fill(1); // Default awake
            for (let day = 0; day < 7; day++) {
                for (let hour = 18; hour < 24; hour++) newMatrix[day * 24 + hour] = 0;
                for (let hour = 0; hour < 8; hour++) newMatrix[day * 24 + hour] = 0;
            }
            return newMatrix;
        }
    },
    {
        id: 'weekends',
        name: 'Weekends Off',
        description: 'Sleep Sat-Sun fully',
        icon: FiSun,
        savings: '29%',
        builtIn: true,
        apply: () => {
            const newMatrix = Array(168).fill(1);
            for (let hour = 120; hour < 168; hour++) newMatrix[hour] = 0; // Sat starts at 5 * 24 = 120
            return newMatrix;
        }
    },
    {
        id: 'global_teams',
        name: 'Global Teams',
        description: '24/7 Mon-Fri',
        icon: FiGlobe,
        savings: '29%',
        builtIn: true,
        apply: () => {
            const newMatrix = Array(168).fill(1);
            for (let hour = 120; hour < 168; hour++) newMatrix[hour] = 0; // Only sleep weekends
            return newMatrix;
        }
    }
];

const ScheduleTemplates = () => {
    const { updateScheduleLocal, schedule } = useHibernationStore();
    const [customTemplates, setCustomTemplates] = useState([]);
    const [showSaveModal, setShowSaveModal] = useState(false);
    const [templateName, setTemplateName] = useState('');
    const [templateDescription, setTemplateDescription] = useState('');

    // Load custom templates from localStorage
    useEffect(() => {
        const saved = localStorage.getItem('hibernation_custom_templates');
        if (saved) {
            try {
                setCustomTemplates(JSON.parse(saved));
            } catch (e) {
                console.error('Failed to load custom templates', e);
            }
        }
    }, []);

    // Save custom templates to localStorage
    const saveCustomTemplates = (templates) => {
        localStorage.setItem('hibernation_custom_templates', JSON.stringify(templates));
        setCustomTemplates(templates);
    };

    const handleSaveTemplate = () => {
        if (!templateName.trim()) {
            toast.error('Please enter a template name');
            return;
        }
        if (!schedule || !schedule.schedule_matrix) {
            toast.error('No schedule to save');
            return;
        }

        const newTemplate = {
            id: `custom_${Date.now()}`,
            name: templateName,
            description: templateDescription || 'Custom schedule',
            icon: FiClock,
            savings: calculateSavings(schedule.schedule_matrix),
            builtIn: false,
            matrix: [...schedule.schedule_matrix]
        };

        saveCustomTemplates([...customTemplates, newTemplate]);
        toast.success('Template saved successfully');
        setShowSaveModal(false);
        setTemplateName('');
        setTemplateDescription('');
    };

    const handleDeleteTemplate = (templateId) => {
        if (window.confirm('Delete this template?')) {
            saveCustomTemplates(customTemplates.filter(t => t.id !== templateId));
            toast.success('Template deleted');
        }
    };

    const calculateSavings = (matrix) => {
        const sleepHours = matrix.filter(h => h === 0).length;
        const pct = Math.round((sleepHours / 168) * 100);
        return `${pct}%`;
    };

    const allTemplates = [
        ...BUILT_IN_TEMPLATES,
        ...customTemplates.map(t => ({
            ...t,
            apply: () => t.matrix
        }))
    ];

    return (
        <>
            <div className="mb-8">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold text-gray-900">Quick Schedule Templates</h3>
                    <button
                        onClick={() => setShowSaveModal(true)}
                        className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
                    >
                        <FiPlus className="w-4 h-4" />
                        Save as Template
                    </button>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {allTemplates.map((template) => {
                        const Icon = template.icon;
                        return (
                            <div
                                key={template.id}
                                className="group relative flex flex-col items-start p-4 bg-white border border-gray-200 rounded-xl hover:border-blue-400 hover:shadow-md transition-all"
                            >
                                <button
                                    onClick={() => {
                                        try {
                                            console.log('Applying template:', template.name);
                                            const newMatrix = template.apply();
                                            console.log('New matrix:', newMatrix);
                                            updateScheduleLocal({ schedule_matrix: newMatrix });
                                            toast.success(`${template.name} applied`);
                                        } catch (error) {
                                            console.error('Error applying template:', error);
                                            toast.error('Failed to apply template');
                                        }
                                    }}
                                    className="w-full text-left"
                                >
                                    <div className="p-2 bg-gray-50 rounded-lg group-hover:bg-blue-50 transition-colors mb-3">
                                        <Icon className="w-5 h-5 text-gray-600 group-hover:text-blue-600" />
                                    </div>
                                    <h4 className="font-semibold text-gray-900 text-sm">{template.name}</h4>
                                    <p className="text-xs text-gray-500 mt-1">{template.description}</p>

                                    <div className="mt-3 flex items-center gap-1 text-green-600 font-bold text-sm">
                                        <FiDollarSign className="w-3 h-3" />
                                        <span>Save {template.savings}</span>
                                    </div>
                                </button>

                                {!template.builtIn && (
                                    <div className="absolute top-2 right-2 flex gap-1">
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleDeleteTemplate(template.id);
                                            }}
                                            className="p-1 bg-white rounded hover:bg-red-50 text-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                                            title="Delete template"
                                        >
                                            <FiTrash2 className="w-3 h-3" />
                                        </button>
                                    </div>
                                )}

                                <div className="absolute bottom-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <span className="text-[10px] uppercase font-bold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">Apply</span>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Save Template Modal */}
            {showSaveModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
                        <div className="flex items-center justify-between p-6 border-b">
                            <h3 className="text-lg font-semibold">Save as Template</h3>
                            <button
                                onClick={() => setShowSaveModal(false)}
                                className="text-gray-400 hover:text-gray-600"
                            >
                                <FiX className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="p-6 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Template Name *
                                </label>
                                <input
                                    type="text"
                                    value={templateName}
                                    onChange={(e) => setTemplateName(e.target.value)}
                                    placeholder="e.g., Dev Environment Schedule"
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                    autoFocus
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Description (optional)
                                </label>
                                <input
                                    type="text"
                                    value={templateDescription}
                                    onChange={(e) => setTemplateDescription(e.target.value)}
                                    placeholder="e.g., Weekdays 8AM-8PM only"
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                />
                            </div>

                            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                                <p className="text-sm text-blue-700">
                                    Current schedule will be saved as a reusable template. You can apply it to any cluster later.
                                </p>
                            </div>
                        </div>

                        <div className="flex gap-3 p-6 border-t bg-gray-50 rounded-b-lg">
                            <button
                                onClick={() => setShowSaveModal(false)}
                                className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSaveTemplate}
                                className="flex-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
                            >
                                Save Template
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default ScheduleTemplates;
