import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const ModelContext = createContext(null);

export const ModelProvider = ({ children }) => {
    const [models, setModels] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [activeProdModelId, setActiveProdModelId] = useState(null);

    const fetchModels = async () => {
        try {
            const data = await api.getModels();
            // Map API data to context format
            const mapped = data.map(m => ({
                ...m,
                uploadedAt: new Date(m.created_at).toLocaleDateString(),
                type: m.status === 'graduated' ? 'stable' : 'beta',
                scope: m.status === 'graduated' ? 'prod' : 'lab'
            }));
            setModels(mapped);

            // Set default active prod model if none
            if (!activeProdModelId) {
                const prod = mapped.find(m => m.scope === 'prod');
                if (prod) setActiveProdModelId(prod.id);
            }
        } catch (e) {
            console.error("Failed to fetch models", e);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchModels();
    }, []);

    const uploadModel = async (file, scope) => {
        const formData = new FormData();
        formData.append('file', file);
        // Scope is handled by backend logic (new uploads are lab by default)
        await api.uploadModel(formData);
        await fetchModels();
    };

    const graduateModel = async (modelId) => {
        await api.graduateModel(modelId);
        await fetchModels();
    };

    const rejectModel = async (modelId) => {
        await api.rejectModel(modelId);
        await fetchModels();
    };

    const getLabModels = () => models.filter(m => m.scope === 'lab');
    const getProdModels = () => models.filter(m => m.scope === 'prod');
    const getActiveProdModel = () => models.find(m => m.id === activeProdModelId);

    return (
        <ModelContext.Provider value={{
            models,
            isLoading,
            activeProdModelId,
            setActiveProdModelId,
            uploadModel,
            graduateModel,
            rejectModel,
            getLabModels,
            getProdModels,
            getActiveProdModel,
            refreshModels: fetchModels
        }}>
            {children}
        </ModelContext.Provider>
    );
};

export const useModel = () => useContext(ModelContext);
