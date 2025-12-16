// Temporary fallback data for charts (until real API integration)
export const mockInstanceDetails = {
    priceHistory: Array.from({ length: 24 }, (_, i) => ({
        time: `${i}:00`,
        current: (0.05 + Math.random() * 0.02).toFixed(3),
        alt1: (0.04 + Math.random() * 0.02).toFixed(3),
        alt2: (0.045 + Math.random() * 0.02).toFixed(3)
    })),
    stressHistory: Array.from({ length: 24 }, (_, i) => ({
        time: `${i}:00`,
        cpu: Math.floor(Math.random() * 40) + 30,
        memory: Math.floor(Math.random() * 30) + 40
    })),
    decisionLog: [
        { time: '12:00', action: 'KEEP', reason: 'Price stable' },
        { time: '11:00', action: 'SWITCH', reason: 'Better alternative found' },
        { time: '10:00', action: 'KEEP', reason: 'High risk threshold' }
    ]
};

export const MOCK_CLIENTS = [
    {
        id: 'client-1',
        name: 'TechCorp Inc.',
        clusterCount: 3,
        nodeCount: 145,
        totalSavings: 12500,
        health: 98,
        clusters: [],
        policies: {
            spotFallback: true,
            maxSpotInterruption: 10,
            costCeiling: 5000
        }
    }
];

// Alias for lowercase import compatibility
export const mockClients = MOCK_CLIENTS;

export const DEMO_CLIENT = {
    id: 'demo-client',
    name: 'Demo Corp',
    clusters: [],
    policies: {
        spotFallback: false
    }
};
