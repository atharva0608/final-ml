import React, { createContext, useContext, useState } from 'react';

const ModelContext = createContext(null);

export const ModelProvider = ({ children }) => {
    // Initial Mock Data
    const [models, setModels] = useState([
        { id: 'm-1', name: 'Legacy Linear', version: 'v1.0.0', type: 'stable', scope: 'prod', uploadedAt: '2023-10-01' },
        { id: 'm-2', name: 'DeepSpot V1', version: 'v1.1.0', type: 'stable', scope: 'prod', uploadedAt: '2023-11-15' },
        { id: 'm-3', name: 'DeepSpot V2-Beta', version: 'v2.0.0-beta', type: 'beta', scope: 'lab', uploadedAt: '2023-12-01' }
    ]);

    const [activeProdModelId, setActiveProdModelId] = useState('m-2');

    const uploadModel = (file, scope) => {
        const newModel = {
            id: `m-${Date.now()}`,
            name: file.name.replace('.pkl', ''),
            version: 'v' + (models.length + 1) + '.0.0-dev',
            type: scope === 'lab' ? 'beta' : 'stable',
            scope: scope,
            uploadedAt: new Date().toISOString().split('T')[0]
        };
        setModels(prev => [...prev, newModel]);
        return newModel;
    };

    const graduateModel = (modelId) => {
        setModels(prev => prev.map(m => {
            if (m.id === modelId) {
                return { ...m, scope: 'prod', type: 'stable', version: m.version.replace('-dev', '').replace('-beta', '') + '-R' };
            }
            return m;
        }));
    };

    const getLabModels = () => models.filter(m => m.scope === 'lab');
    const getProdModels = () => models.filter(m => m.scope === 'prod');
    const getActiveProdModel = () => models.find(m => m.id === activeProdModelId);

    return (
        <ModelContext.Provider value={{
            models,
            activeProdModelId,
            setActiveProdModelId,
            uploadModel,
            graduateModel,
            getLabModels,
            getProdModels,
            getActiveProdModel
        }}>
            {children}
        </ModelContext.Provider>
    );
};

export const useModel = () => useContext(ModelContext);
