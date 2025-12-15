
// --- Mock Data ---

export const generatePriceHistory = () => Array.from({ length: 24 }, (_, i) => ({
    time: `${i}:00`,
    current: (Math.random() * 0.05 + 0.08).toFixed(4),
    alt1: (Math.random() * 0.03 + 0.06).toFixed(4), // Cheaper
    alt2: (Math.random() * 0.06 + 0.09).toFixed(4), // More expensive
}));

export const generateStressHistory = () => Array.from({ length: 24 }, (_, i) => ({
    time: `${i}:00`,
    cpu: Math.floor(Math.random() * 60) + 20,
    memory: Math.floor(Math.random() * 40) + 30,
}));

export const mockInstanceDetails = {
    priceHistory: generatePriceHistory(),
    stressHistory: generateStressHistory(),
    decisionLog: [
        { time: "14:30", action: "Scale Up", reason: "CPU > 80% for 5m", type: "Performance" },
        { time: "10:15", action: "Market Check", reason: "Stable price detected in eu-west-1b", type: "Info" },
        { time: "08:00", action: "Launched", reason: "Replenishing fleet capacity", type: "Lifecycle" },
    ]
};

export const mockHistory = Array.from({ length: 12 }, (_, i) => ({
    month: `Month ${i + 1} `,
    savings: Math.floor(Math.random() * 5000) + 2000,
    cost: Math.floor(Math.random() * 3000) + 1000,
}));

export const mockClients = [
    {
        id: 'c-1',
        name: "Acme Corp",
        joinedAt: "2023-01-15",
        status: "Active",
        totalNodes: 85,
        potentialSavings: "$12,450/mo",
        savingsHistory: mockHistory,
        policies: {
            spotFallback: true,
            rebalanceAggressive: false,
            autoBinpacking: true,
        },
        clusters: [
            {
                id: 'cl-1',
                name: "production-us-east-1",
                region: "us-east-1",
                nodeCount: 45,
                nodes: [
                    { id: 'i-0a1b2c3d4e5f6', zone: 'us-east-1a', family: 'c5.large', stress: 0.85, risk: 'High', status: 'Active' },
                    { id: 'i-0b2c3d4e5f6g7', zone: 'us-east-1b', family: 'm5.large', stress: 0.12, risk: 'Safe', status: 'Active' },
                    { id: 'i-0c3d4e5f6g7h8', zone: 'us-east-1a', family: 'r5.xlarge', stress: 0.45, risk: 'Safe', status: 'Active' },
                ]
            },
            {
                id: 'cl-2',
                name: "staging-eu-west-1",
                region: "eu-west-1",
                nodeCount: 40,
                nodes: [
                    { id: 'i-0d4e5f6g7h8i9', zone: 'eu-west-1c', family: 'c6g.medium', stress: 0.92, risk: 'Critical', status: 'Draining' },
                    { id: 'i-0e5f6g7h8i9j0', zone: 'eu-west-1b', family: 't3.medium', stress: 0.05, risk: 'Safe', status: 'Active' },
                ]
            }
        ]
    },
    {
        id: 'c-2',
        name: "Globex Inc",
        joinedAt: "2023-03-10",
        status: "Active",
        totalNodes: 57,
        potentialSavings: "$8,230/mo",
        savingsHistory: mockHistory.map(h => ({ ...h, savings: h.savings * 0.7 })),
        policies: {
            spotFallback: true,
            rebalanceAggressive: true,
            autoBinpacking: false,
        },
        clusters: [
            {
                id: 'cl-3',
                name: "dev-cluster-01",
                region: "us-west-2",
                nodeCount: 57,
                nodes: [
                    { id: 'i-f6e5d4c3b2a10', zone: 'us-west-2a', family: 't3.small', stress: 0.20, risk: 'Safe', status: 'Active' },
                    { id: 'i-g7h8i9j0k1l2m', zone: 'us-west-2b', family: 'm6g.large', stress: 0.15, risk: 'Safe', status: 'Active' },
                ]
            }
        ]
    }
];

export const DEMO_CLIENT = {
    id: 'client-demo-001',
    name: 'TechCorp Solutions',
    status: 'Active',
    joinedAt: 'Just now',
    totalNodes: 156,
    potentialSavings: '$12,450',
    policies: { spotFallback: true, rebalanceAggressive: true, autoBinpacking: false },
    savingsHistory: [
        { month: 'Jan', savings: 4000, cost: 8000 },
        { month: 'Feb', savings: 5500, cost: 7500 },
        { month: 'Mar', savings: 8000, cost: 6000 },
    ],
    clusters: [
        {
            id: 'c-demo-1',
            name: 'Production-East',
            region: 'us-east-1',
            nodeCount: 84,
            nodes: [
                { id: 'i-demo-01', zone: 'us-east-1a', family: 'c5.2xlarge', stress: 0.75, risk: 'Safe', status: 'Active' },
                { id: 'i-demo-02', zone: 'us-east-1b', family: 'm5.xlarge', stress: 0.45, risk: 'High', status: 'Active' },
                { id: 'i-demo-03', zone: 'us-east-1c', family: 'r6g.large', stress: 0.20, risk: 'Safe', status: 'Active' },
            ]
        },
        {
            id: 'c-demo-2',
            name: 'Staging-West',
            region: 'us-west-2',
            nodeCount: 72,
            nodes: [
                { id: 'i-demo-11', zone: 'us-west-2a', family: 't3.medium', stress: 0.10, risk: 'Safe', status: 'Active' },
                { id: 'i-demo-12', zone: 'us-west-2b', family: 't3.large', stress: 0.90, risk: 'Critical', status: 'Active' },
            ]
        }
    ]
};
