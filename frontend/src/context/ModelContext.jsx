import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const ModelContext = createContext(null);

export const ModelProvider = ({ children }) => {
    const [models, setModels] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [activeProdModelId, _setActiveState] = useState(null);

    const fetchModels = async () => {
        try {
            const data = await api.getModels();
            // Map API data to context format
            const mapped = data.map(m => ({
                ...m,
                uploadedAt: new Date(m.created_at).toLocaleDateString(),
                type: (m.status === 'enabled') ? 'stable' : 'beta',
                scope: (m.status === 'enabled') ? 'prod' : 'lab'
            }));
            setModels(mapped);

            // Sync active state from backend
            const activeModel = mapped.find(m => m.is_active);
            if (activeModel) {
                _setActiveState(activeModel.id);
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

    const setActiveProdModelId = async (modelId) => {
        if (!modelId) {
            console.warn("Attempted to set active model with empty ID");
            return;
        }
        await api.activateModel(modelId);
        await fetchModels();
    };

    const acceptModel = async (modelId) => {
        await api.acceptModel(modelId);
        await fetchModels();
    };

    const graduateModel = async (modelId) => {
        await api.graduateModel(modelId);
        await fetchModels();
    };

    const enableModel = async (modelId) => {
        await api.enableModel(modelId);
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
            acceptModel,
            graduateModel,
            enableModel,
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
