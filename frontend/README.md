# SmartDevops Admin Dashboard

A modern, component-based React dashboard for managing cloud infrastructure optimization.

## Project Structure

```
src/
├── config/
│   └── api.jsx                 # API configuration
├── services/
│   ├── apiClient.jsx           # API client class
│   └── api.jsx                 # API client instance
├── components/
│   ├── common/                 # Reusable UI components
│   │   ├── LoadingSpinner.jsx
│   │   ├── StatCard.jsx
│   │   ├── Badge.jsx
│   │   ├── Button.jsx
│   │   ├── ToggleSwitch.jsx
│   │   ├── CustomTooltip.jsx
│   │   ├── ErrorMessage.jsx
│   │   └── EmptyState.jsx
│   ├── modals/                 # Modal dialogs
│   │   ├── AddClientModal.jsx
│   │   ├── ViewTokenModal.jsx
│   │   ├── DeleteClientModal.jsx
│   │   └── AgentConfigModal.jsx
│   ├── panels/                 # Side panels
│   │   ├── NotificationPanel.jsx
│   │   └── SearchResultsPanel.jsx
│   ├── layout/                 # Layout components
│   │   ├── AdminSidebar.jsx
│   │   └── AdminHeader.jsx
│   └── details/                # Detail views
│       ├── InstanceDetailPanel.jsx
│       ├── ClientDetailView.jsx
│       └── tabs/               # Client detail tabs
│           ├── ClientOverviewTab.jsx
│           ├── ClientAgentsTab.jsx
│           ├── ClientInstancesTab.jsx
│           ├── ClientSavingsTab.jsx
│           └── ClientHistoryTab.jsx
├── pages/                      # Top-level page components
│   ├── AdminOverview.jsx
│   ├── AllClientsPage.jsx
│   ├── AllAgentsPage.jsx
│   ├── AllInstancesPage.jsx
│   ├── GlobalSavingsPage.jsx
│   ├── ActivityLogPage.jsx
│   └── SystemHealthPage.jsx
├── App.jsx                     # Main application component
├── index.jsx                   # Application entry point
└── index.css                   # Global styles

## Features

- **Client Management**: Create, view, and manage client accounts
- **Agent Monitoring**: Real-time agent status and configuration
- **Instance Tracking**: Monitor and manage cloud instances
- **Cost Optimization**: Track savings and cost reduction
- **Activity Logging**: System-wide activity tracking
- **Health Monitoring**: System health and status

## Tech Stack

- **React 18** - UI framework
- **Vite** - Build tool and dev server
- **Tailwind CSS** - Utility-first CSS framework
- **Recharts** - Charting library
- **Lucide React** - Icon library

## Getting Started

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

### Build

```bash
npm run build
```

### Preview Production Build

```bash
npm run preview
```

## Component Organization

The application follows a modular component architecture:

- **Common Components**: Reusable UI elements used throughout the app
- **Modals**: Dialog windows for user interactions
- **Panels**: Sliding panels for notifications and search results
- **Layout**: App-wide layout components (sidebar, header)
- **Details**: Detailed views for specific entities
- **Pages**: Top-level route components

## API Integration

All API calls are centralized through the `apiClient` service, which provides:

- Admin APIs (stats, clients, activity, health)
- Client Management APIs
- Notification APIs
- Search APIs
- Client-specific APIs (agents, instances, savings, history)

## Styling

The project uses Tailwind CSS for styling with a custom configuration. All components use utility classes for consistent styling across the application.

## License

Proprietary - All rights reserved
