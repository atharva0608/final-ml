Rebalancing [<!DOCTYPE html>

<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Infrastructure Console - Rebalancing</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script id="tailwind-config">
        tailwind.config = {
            darkMode: "class",
            theme: {
                extend: {
                    colors: {
                        "primary-fixed-dim": "#c1d5ff",
                        "on-primary": "#f7f7ff",
                        "on-background": "#2d3338",
                        "surface-bright": "#f9f9fb",
                        "inverse-on-surface": "#9c9d9f",
                        "background": "#f9f9fb",
                        "surface-container-lowest": "#ffffff",
                        "tertiary-fixed": "#f4f3f8",
                        "surface-variant": "#dde3e9",
                        "primary": "#005cba",
                        "surface-container": "#ebeef2",
                        "surface-container-highest": "#dde3e9",
                        "outline": "#757c81",
                        "on-tertiary-fixed": "#49494e",
                        "on-tertiary": "#faf8fe",
                        "secondary-fixed-dim": "#d6d3d6",
                        "primary-container": "#d7e3ff",
                        "on-surface-variant": "#596065",
                        "secondary": "#5f5f61",
                        "tertiary": "#5e5f63",
                        "tertiary-fixed-dim": "#e6e5ea",
                        "on-surface": "#2d3338",
                        "on-secondary": "#fbf8fa",
                        "surface-tint": "#005cba",
                        "on-secondary-container": "#525154",
                        "on-secondary-fixed": "#3f3f41",
                        "error-dim": "#4e0309",
                        "surface-dim": "#d3dbe2",
                        "on-error": "#fff7f6",
                        "inverse-primary": "#5095fe",
                        "inverse-surface": "#0c0e10",
                        "surface-container-high": "#e4e9ee",
                        "outline-variant": "#acb3b8",
                        "surface": "#f9f9fb",
                        "on-tertiary-container": "#5b5b60",
                        "on-primary-fixed": "#003e80",
                        "on-tertiary-fixed-variant": "#65666a",
                        "secondary-fixed": "#e4e2e4",
                        "primary-dim": "#0051a4",
                        "secondary-container": "#e4e2e4",
                        "error": "#9f403d",
                        "error-container": "#fe8983",
                        "surface-container-low": "#f2f4f6",
                        "primary-fixed": "#d7e3ff",
                        "secondary-dim": "#535355",
                        "on-secondary-fixed-variant": "#5c5b5d",
                        "on-error-container": "#752121",
                        "on-primary-fixed-variant": "#005ab4",
                        "tertiary-dim": "#525357",
                        "tertiary-container": "#f4f3f8",
                        "on-primary-container": "#0050a2"
                    },
                    borderRadius: {
                        "DEFAULT": "0.25rem",
                        "lg": "0.5rem",
                        "xl": "0.75rem",
                        "full": "9999px"
                    },
                    fontFamily: {
                        "headline": ["Inter", "sans-serif"],
                        "display": ["Inter", "sans-serif"],
                        "body": ["Inter", "sans-serif"],
                        "label": ["Inter", "sans-serif"]
                    }
                }
            }
        }
    </script>
<style>
        /* Custom Donut Chart for Status Distribution */
        .donut-chart {
            background: conic-gradient(
                #005cba 0% 60%,      /* Completed: primary */
                #0051a4 60% 80%,     /* Running: primary-dim */
                #9f403d 80% 90%,     /* Blocked: error */
                #dde3e9 90% 100%     /* Pending: surface-variant */
            );
            border-radius: 50%;
            position: relative;
        }
        .donut-chart::before {
            content: "";
            position: absolute;
            inset: 16px; /* Width of the donut ring */
            background-color: #ffffff; /* surface-container-lowest */
            border-radius: 50%;
        }
    </style>
</head>
<body class="bg-background text-on-surface font-body antialiased min-h-screen flex selection:bg-primary-fixed-dim selection:text-on-primary-fixed">
<!-- SideNavBar -->
<!-- TopAppBar -->
<!-- Main Content Canvas -->
<main class="px-8 pb-16 w-full max-w-[1600px] mx-auto flex flex-col gap-12 py-12">
<!-- Page Header & Global CTA -->
<div class="flex items-end justify-between">
<div>
<h1 class="text-2xl font-semibold tracking-[-0.6px] text-on-surface mb-2">Rebalancing</h1>
<p class="text-base font-normal text-on-surface-variant">Parallel node eviction and pod scheduling in progress.</p>
</div>
<!-- Direct Action CTA for Blocked Nodes -->
<button class="bg-surface-container-highest hover:bg-surface-dim transition-colors px-6 py-3 rounded-[12px] flex items-center gap-3 group">
<div class="w-2 h-2 rounded-full bg-error"></div>
<span class="text-[17px] font-bold tracking-[-0.4px] text-on-surface group-hover:text-error transition-colors">5 nodes blocked</span>
<span class="text-sm font-medium text-on-surface-variant flex items-center gap-1">
                    Click to fix <span class="material-symbols-outlined text-[16px]">arrow_forward</span>
</span>
</button>
</div>
<!-- Top Section: Aggregated Metrics -->
<section class="grid grid-cols-1 lg:grid-cols-3 gap-6">
<!-- Rebalancing Progress Bar Card -->
<div class="lg:col-span-2 bg-surface-container-lowest rounded-lg p-6 flex flex-col justify-between">
<div>
<h2 class="text-[17px] font-bold tracking-[-0.4px] text-on-surface mb-6">Rebalancing Progress</h2>
<div class="flex items-center gap-8 mb-6">
<div class="flex flex-col">
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-on-surface-variant mb-1">Completed</span>
<span class="text-[17px] font-bold tracking-[-0.4px] text-primary">35</span>
</div>
<div class="flex flex-col">
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-on-surface-variant mb-1">Running</span>
<span class="text-[17px] font-bold tracking-[-0.4px] text-primary-dim">10</span>
</div>
<div class="flex flex-col">
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-on-surface-variant mb-1">Blocked</span>
<span class="text-[17px] font-bold tracking-[-0.4px] text-error">5</span>
</div>
<div class="flex flex-col">
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-on-surface-variant mb-1">Pending</span>
<span class="text-[17px] font-bold tracking-[-0.4px] text-outline">50</span>
</div>
</div>
</div>
<div class="w-full">
<div class="flex justify-between items-center mb-2">
<span class="text-sm font-medium text-on-surface">Overall Completion</span>
<span class="text-sm font-bold text-on-surface">45%</span>
</div>
<div class="h-3 w-full bg-surface-variant rounded-full overflow-hidden flex">
<div class="h-full bg-primary transition-all duration-500 ease-out" style="width: 35%"></div>
<div class="h-full bg-primary-dim opacity-80 transition-all duration-500 ease-out" style="width: 10%"></div>
</div>
</div>
</div>
<!-- Status Distribution Donut -->
<div class="bg-surface-container-lowest rounded-lg p-6 flex items-center justify-between">
<div class="flex flex-col gap-4">
<h2 class="text-[17px] font-bold tracking-[-0.4px] text-on-surface mb-2">Status Distribution</h2>
<ul class="flex flex-col gap-3">
<li class="flex items-center gap-2 text-sm text-on-surface">
<span class="w-2.5 h-2.5 rounded-full bg-primary"></span> Completed (60%)
                        </li>
<li class="flex items-center gap-2 text-sm text-on-surface">
<span class="w-2.5 h-2.5 rounded-full bg-primary-dim"></span> Running (20%)
                        </li>
<li class="flex items-center gap-2 text-sm text-on-surface">
<span class="w-2.5 h-2.5 rounded-full bg-error"></span> Blocked (10%)
                        </li>
<li class="flex items-center gap-2 text-sm text-on-surface">
<span class="w-2.5 h-2.5 rounded-full bg-surface-variant"></span> Pending (10%)
                        </li>
</ul>
</div>
<div class="w-32 h-32 donut-chart flex-shrink-0"></div>
</div>
</section>
<!-- Main Section: Node Progress Grid -->
<section class="flex flex-col gap-12">
<!-- Group: Blocked -->
<div class="flex flex-col gap-6">
<div class="flex items-center gap-3 px-2">
<div class="w-2.5 h-2.5 rounded-full bg-error"></div>
<h3 class="text-[17px] font-bold tracking-[-0.4px] text-on-surface">Blocked (5 nodes)</h3>
<div class="h-px bg-surface-variant flex-grow ml-4 opacity-50"></div>
</div>
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
<!-- Blocked Node Card 1 -->
<div class="bg-surface-container-lowest rounded-lg p-5 flex flex-col gap-4">
<div class="flex justify-between items-start">
<div class="flex flex-col gap-1">
<span class="text-[17px] font-bold tracking-[-0.4px] text-on-surface">node-3</span>
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-error">PDB Violation</span>
</div>
<button class="text-primary hover:text-primary-dim transition-colors">
<span class="material-symbols-outlined text-[20px]">engineering</span>
</button>
</div>
<div class="text-sm text-on-surface-variant">Cannot evict pod: api-gateway-7b9x. Breaks minAvailable constraint.</div>
<div class="flex items-center justify-between mt-auto pt-2">
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-on-surface-variant">Pods</span>
<span class="text-sm font-medium text-on-surface">8/12 evicted</span>
</div>
</div>
<!-- Blocked Node Card 2 -->
<div class="bg-surface-container-lowest rounded-lg p-5 flex flex-col gap-4">
<div class="flex justify-between items-start">
<div class="flex flex-col gap-1">
<span class="text-[17px] font-bold tracking-[-0.4px] text-on-surface">node-8</span>
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-error">Capacity</span>
</div>
<button class="text-primary hover:text-primary-dim transition-colors">
<span class="material-symbols-outlined text-[20px]">engineering</span>
</button>
</div>
<div class="text-sm text-on-surface-variant">Insufficient resources in target zone to reschedule remaining pods.</div>
<div class="flex items-center justify-between mt-auto pt-2">
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-on-surface-variant">Pods</span>
<span class="text-sm font-medium text-on-surface">2/5 evicted</span>
</div>
</div>
</div>
</div>
<!-- Group: Running -->
<div class="flex flex-col gap-6">
<div class="flex items-center gap-3 px-2">
<div class="w-2.5 h-2.5 rounded-full bg-primary-dim"></div>
<h3 class="text-[17px] font-bold tracking-[-0.4px] text-on-surface">Running (12 nodes)</h3>
<div class="h-px bg-surface-variant flex-grow ml-4 opacity-50"></div>
</div>
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
<!-- Running Node Card 1 -->
<div class="bg-surface-container-lowest rounded-lg p-5 flex flex-col gap-4 border border-transparent hover:border-outline-variant/30 transition-colors cursor-pointer relative overflow-hidden">
<!-- Active Indicator subtle background shift -->
<div class="absolute inset-0 bg-primary/5 pointer-events-none"></div>
<div class="flex justify-between items-center relative z-10">
<span class="text-[17px] font-bold tracking-[-0.4px] text-on-surface">node-1</span>
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-primary-dim">Draining</span>
</div>
<div class="flex flex-col gap-2 relative z-10">
<div class="flex justify-between items-center">
<span class="text-sm text-on-surface-variant">Progress</span>
<span class="text-sm font-medium text-on-surface">65%</span>
</div>
<div class="h-1.5 w-full bg-surface-variant rounded-full overflow-hidden">
<div class="h-full bg-primary-dim" style="width: 65%"></div>
</div>
</div>
<div class="flex items-center justify-between mt-auto pt-2 relative z-10">
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-on-surface-variant">Pods</span>
<span class="text-sm font-medium text-on-surface">3/10 evicted</span>
</div>
</div>
<!-- Running Node Card 2 -->
<div class="bg-surface-container-lowest rounded-lg p-5 flex flex-col gap-4 border border-transparent hover:border-outline-variant/30 transition-colors cursor-pointer">
<div class="flex justify-between items-center">
<span class="text-[17px] font-bold tracking-[-0.4px] text-on-surface">node-14</span>
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-primary-dim">Draining</span>
</div>
<div class="flex flex-col gap-2">
<div class="flex justify-between items-center">
<span class="text-sm text-on-surface-variant">Progress</span>
<span class="text-sm font-medium text-on-surface">80%</span>
</div>
<div class="h-1.5 w-full bg-surface-variant rounded-full overflow-hidden">
<div class="h-full bg-primary-dim" style="width: 80%"></div>
</div>
</div>
<div class="flex items-center justify-between mt-auto pt-2">
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-on-surface-variant">Pods</span>
<span class="text-sm font-medium text-on-surface">8/10 evicted</span>
</div>
</div>
<!-- Running Node Card 3 -->
<div class="bg-surface-container-lowest rounded-lg p-5 flex flex-col gap-4 border border-transparent hover:border-outline-variant/30 transition-colors cursor-pointer">
<div class="flex justify-between items-center">
<span class="text-[17px] font-bold tracking-[-0.4px] text-on-surface">node-22</span>
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-primary-dim">Scheduling</span>
</div>
<div class="flex flex-col gap-2">
<div class="flex justify-between items-center">
<span class="text-sm text-on-surface-variant">Progress</span>
<span class="text-sm font-medium text-on-surface">15%</span>
</div>
<div class="h-1.5 w-full bg-surface-variant rounded-full overflow-hidden">
<div class="h-full bg-primary-dim" style="width: 15%"></div>
</div>
</div>
<div class="flex items-center justify-between mt-auto pt-2">
<span class="text-xs font-semibold tracking-[0.2px] uppercase text-on-surface-variant">Pods</span>
<span class="text-sm font-medium text-on-surface">1/7 assigned</span>
</div>
</div>
</div>
</div>
<!-- Group: Completed (Summary) -->
<div class="flex flex-col gap-6">
<div class="flex items-center gap-3 px-2">
<div class="w-2.5 h-2.5 rounded-full bg-primary"></div>
<h3 class="text-[17px] font-bold tracking-[-0.4px] text-on-surface">Completed (40 nodes)</h3>
<div class="h-px bg-surface-variant flex-grow ml-4 opacity-50"></div>
</div>
<div class="flex flex-wrap gap-3">
<!-- Completed node chips -->
<div class="bg-surface-container-low px-4 py-2 rounded-full flex items-center gap-2">
<span class="text-sm font-medium text-on-surface">node-2</span>
<span class="material-symbols-outlined text-[16px] text-primary">check_circle</span>
</div>
<div class="bg-surface-container-low px-4 py-2 rounded-full flex items-center gap-2">
<span class="text-sm font-medium text-on-surface">node-5</span>
<span class="material-symbols-outlined text-[16px] text-primary">check_circle</span>
</div>
<div class="bg-surface-container-low px-4 py-2 rounded-full flex items-center gap-2">
<span class="text-sm font-medium text-on-surface">node-7</span>
<span class="material-symbols-outlined text-[16px] text-primary">check_circle</span>
</div>
<div class="bg-surface-container-low px-4 py-2 rounded-full flex items-center gap-2">
<span class="text-sm font-medium text-on-surface">node-9</span>
<span class="material-symbols-outlined text-[16px] text-primary">check_circle</span>
</div>
<div class="bg-surface-container-low px-4 py-2 rounded-full flex items-center gap-2 text-on-surface-variant hover:bg-surface-container-highest cursor-pointer transition-colors">
<span class="text-sm font-medium">+36 more</span>
</div>
</div>
</div>
</section>
<!-- Bottom Section: Feed & Timeline -->
</main>
</body></html>
]



Scaling Activity [<!DOCTYPE html>

<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Node-Centric Scaling Control Surface</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script id="tailwind-config">
        tailwind.config = {
          darkMode: "class",
          theme: {
            extend: {
              "colors": {
                      "primary-dim": "#0051a4",
                      "surface-container-high": "#e4e9ee",
                      "on-secondary-fixed": "#3f3f41",
                      "inverse-surface": "#0c0e10",
                      "on-primary-container": "#0050a2",
                      "surface-tint": "#005cba",
                      "on-error-container": "#752121",
                      "error-container": "#fe8983",
                      "on-surface": "#2d3338",
                      "inverse-on-surface": "#9c9d9f",
                      "secondary-dim": "#535355",
                      "primary-fixed": "#d7e3ff",
                      "on-tertiary-fixed": "#49494e",
                      "surface-bright": "#f9f9fb",
                      "on-primary": "#f7f7ff",
                      "outline": "#757c81",
                      "on-secondary-container": "#525154",
                      "error": "#9f403d",
                      "on-tertiary-fixed-variant": "#65666a",
                      "on-background": "#2d3338",
                      "tertiary-fixed": "#f4f3f8",
                      "secondary": "#5f5f61",
                      "surface": "#f9f9fb",
                      "on-secondary": "#fbf8fa",
                      "on-tertiary-container": "#5b5b60",
                      "primary-fixed-dim": "#c1d5ff",
                      "secondary-fixed-dim": "#d6d3d6",
                      "surface-container-low": "#f2f4f6",
                      "outline-variant": "#acb3b8",
                      "tertiary-fixed-dim": "#e6e5ea",
                      "on-surface-variant": "#596065",
                      "surface-variant": "#dde3e9",
                      "on-tertiary": "#faf8fe",
                      "inverse-primary": "#5095fe",
                      "tertiary": "#5e5f63",
                      "surface-dim": "#d3dbe2",
                      "on-secondary-fixed-variant": "#5c5b5d",
                      "on-error": "#fff7f6",
                      "on-primary-fixed": "#003e80",
                      "background": "#f9f9fb",
                      "surface-container-lowest": "#ffffff",
                      "surface-container": "#ebeef2",
                      "tertiary-dim": "#525357",
                      "primary-container": "#d7e3ff",
                      "error-dim": "#4e0309",
                      "tertiary-container": "#f4f3f8",
                      "surface-container-highest": "#dde3e9",
                      "primary": "#005cba",
                      "secondary-fixed": "#e4e2e4",
                      "secondary-container": "#e4e2e4",
                      "on-primary-fixed-variant": "#005ab4"
              },
              "borderRadius": {
                      "DEFAULT": "0.25rem",
                      "lg": "0.5rem",
                      "xl": "0.75rem",
                      "full": "9999px"
              },
              "spacing": {},
              "fontFamily": {
                      "headline": [
                              "Inter"
                      ],
                      "display": [
                              "Inter"
                      ],
                      "body": [
                              "Inter"
                      ],
                      "label": [
                              "Inter"
                      ]
              },
              "fontSize": {}
      },
          },
        }
    </script>
<style>
        body { font-family: 'Inter', sans-serif; }
    </style>
</head>
<body class="bg-background text-on-background antialiased h-screen flex overflow-hidden">
<!-- SideNavBar (Shared Component) -->
<nav class="h-screen w-64 fixed left-0 top-0 bg-surface-container-low flex flex-col p-4 space-y-6 z-40 border-r border-outline-variant/15 hidden md:flex">
<!-- Header -->
<div class="px-2 pt-2">
<h1 class="text-[17px] font-bold tracking-[-0.4px] text-on-background">Core Fleet</h1>
<p class="text-sm text-on-surface-variant mt-1">Active Nodes: 1,248</p>
</div>
<!-- Navigation Tabs -->
<div class="flex-1 space-y-2 mt-8">
<a class="flex items-center space-x-3 px-3 py-2 rounded-lg bg-surface-container-lowest text-primary shadow-sm font-medium transition-colors ease-out duration-150" href="#">
<span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 0;">monitoring</span>
<span>Observability</span>
</a>
<a class="flex items-center space-x-3 px-3 py-2 rounded-lg text-on-surface-variant hover:bg-surface-variant/50 transition-colors ease-out duration-150" href="#">
<span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 0;">psychology</span>
<span>Intelligence</span>
</a>
<a class="flex items-center space-x-3 px-3 py-2 rounded-lg text-on-surface-variant hover:bg-surface-variant/50 transition-colors ease-out duration-150" href="#">
<span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 0;">leaderboard</span>
<span>Capacity</span>
</a>
<a class="flex items-center space-x-3 px-3 py-2 rounded-lg text-on-surface-variant hover:bg-surface-variant/50 transition-colors ease-out duration-150" href="#">
<span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 0;">terminal</span>
<span>Execution</span>
</a>
<a class="flex items-center space-x-3 px-3 py-2 rounded-lg text-on-surface-variant hover:bg-surface-variant/50 transition-colors ease-out duration-150" href="#">
<span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 0;">view_quilt</span>
<span>Workloads</span>
</a>
</div>
<!-- CTA -->
<div class="px-2 pb-4">
<button class="w-full bg-primary text-on-primary py-2 px-4 rounded-lg text-sm font-medium hover:bg-primary-dim transition-colors">
                Add Scaling Policy
            </button>
</div>
<!-- Footer Tabs -->
<div class="pt-4 border-t border-outline-variant/15 space-y-1">
<a class="flex items-center space-x-3 px-3 py-2 text-sm text-on-surface-variant hover:bg-surface-variant/50 rounded-lg transition-colors" href="#">
<span class="material-symbols-outlined text-[18px]">menu_book</span>
<span>Documentation</span>
</a>
<a class="flex items-center space-x-3 px-3 py-2 text-sm text-on-surface-variant hover:bg-surface-variant/50 rounded-lg transition-colors" href="#">
<span class="material-symbols-outlined text-[18px]">help_outline</span>
<span>Support</span>
</a>
</div>
</nav>
<!-- Main Content Area -->
<main class="flex-1 flex flex-col ml-0 md:ml-64 bg-background overflow-y-auto">
<!-- TopAppBar (Shared Component) -->
<header class="sticky top-0 w-full z-50 bg-surface-bright/80 backdrop-blur-lg border-none flex justify-between items-center px-8 py-3 shadow-[0_20px_40px_rgba(45,51,56,0.06)]">
<div class="flex items-center space-x-6">
<div class="text-[17px] font-bold tracking-[-0.4px] text-on-background mr-4">ScaleControl</div>
<nav class="hidden md:flex space-x-1">
<a class="px-3 py-2 text-on-surface-variant hover:text-on-background transition-all duration-200" href="#">Clusters</a>
<a class="px-3 py-2 text-on-surface-variant hover:text-on-background transition-all duration-200" href="#">Fleet</a>
<a class="px-3 py-2 text-primary font-semibold border-b-2 border-primary transition-all duration-200" href="#">Global View</a>
</nav>
</div>
<div class="flex items-center space-x-4">
<div class="hidden lg:flex items-center bg-surface-container-low px-3 py-1.5 rounded-lg border border-outline-variant/15 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-all">
<span class="material-symbols-outlined text-on-surface-variant text-[18px] mr-2">search</span>
<input class="bg-transparent border-none focus:ring-0 text-sm text-on-background placeholder-on-surface-variant outline-none w-48" placeholder="Search resources..." type="text"/>
</div>
<button class="text-sm font-medium text-on-surface-variant hover:text-on-background px-3 py-1.5 rounded-md hover:bg-surface-variant/50 transition-colors">
                    Logs
                </button>
<div class="flex items-center space-x-2 text-on-surface-variant border-l border-outline-variant/15 pl-4">
<button class="p-1.5 hover:bg-surface-variant/50 rounded-md transition-colors relative">
<span class="material-symbols-outlined">notifications</span>
<span class="absolute top-1.5 right-1.5 w-2 h-2 bg-error rounded-full"></span>
</button>
<button class="p-1.5 hover:bg-surface-variant/50 rounded-md transition-colors">
<span class="material-symbols-outlined">history</span>
</button>
<img alt="Administrator Profile" class="w-8 h-8 rounded-full ml-2 border border-outline-variant/20" data-alt="professional headshot of a man with short hair wearing a dark shirt against a blurred office background" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAEomUvcUQNZtS-scB_ItX9TqpG-s6Niuq_LOWar7uMlu0eVVzdWeC3gW7HuRxlZolXfjTj34po_g5nRWGswcupzeMdYOxY-F4UKqED8NeXkrdN5cdKJuyIyR5MrUliFU0ddnwEUaLcm8wJbwrW-V5g1IWvOH2oTDY2zoJUYCebPsZXC14C2jQfuR-WmkH2jot0L_vmHeRlSKN989si2iMHub8gTOLe6PIqENVV5xjw2Ue8N8WJH1Ao9i2_OkX9DXUPO9RkjpEoECk"/>
</div>
</div>
</header>
<!-- Canvas / Dashboard Content -->
<div class="p-8 max-w-[1600px] mx-auto w-full space-y-8">
<!-- High-Density Status Bar -->
<section class="flex flex-col md:flex-row justify-between items-start md:items-center bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/15">
<div class="flex flex-wrap items-center gap-6">
<div class="flex items-center space-x-2">
<span class="w-2.5 h-2.5 bg-primary rounded-full animate-pulse"></span>
<span class="text-sm font-medium text-on-background">Scaling Active</span>
<span class="text-xs text-on-surface-variant ml-2">(updated Just now)</span>
</div>
<div class="h-4 w-px bg-outline-variant/30 hidden md:block"></div>
<div class="flex items-center space-x-4 text-sm">
<div class="flex items-center"><span class="text-on-surface-variant mr-1.5">Nodes:</span><span class="font-semibold text-on-background">18</span> <span class="text-xs text-on-surface-variant ml-1.5">Active</span></div>
<div class="flex items-center"><span class="font-semibold text-primary">3</span> <span class="text-xs text-primary/80 ml-1.5">Provisioning</span></div>
<div class="flex items-center"><span class="font-semibold text-secondary">2</span> <span class="text-xs text-secondary/80 ml-1.5">Draining</span></div>
<div class="flex items-center"><span class="font-semibold text-error">1</span> <span class="text-xs text-error/80 ml-1.5">Blocked</span></div>
</div>
</div>
<div class="mt-4 md:mt-0 flex space-x-2">
<button class="px-3 py-1.5 bg-surface-container-high hover:bg-surface-variant text-on-background text-sm font-medium rounded-lg transition-colors flex items-center">
<span class="material-symbols-outlined text-[16px] mr-1.5">pause</span> Pause
                    </button>
<button class="px-3 py-1.5 bg-surface-container-high hover:bg-surface-variant text-on-background text-sm font-medium rounded-lg transition-colors flex items-center">
<span class="material-symbols-outlined text-[16px] mr-1.5">settings</span> Config
                    </button>
</div>
</section>
<!-- Primary Observability Layer -->
<section class="grid grid-cols-1 lg:grid-cols-3 gap-6">
<!-- Node Scaling Graph (Mockup) -->
<div class="lg:col-span-2 bg-surface-container-lowest rounded-xl p-6 border border-outline-variant/15 flex flex-col">
<div class="flex justify-between items-center mb-6">
<h2 class="text-[17px] font-bold tracking-[-0.4px] text-on-background">Scaling Trajectory</h2>
<div class="flex items-center space-x-4 text-xs font-medium">
<div class="flex items-center"><span class="w-2 h-2 rounded-full bg-primary mr-1.5"></span>Active</div>
<div class="flex items-center"><span class="w-2 h-2 rounded-full bg-primary-dim mr-1.5"></span>Pending Pods</div>
</div>
</div>
<div class="flex-1 min-h-[240px] relative border-b border-l border-outline-variant/20">
<!-- Simulated Chart Area -->
<div class="absolute bottom-0 left-0 w-full h-[60%] bg-gradient-to-t from-primary/10 to-transparent"></div>
<svg class="absolute inset-0 w-full h-full" preserveaspectratio="none">
<path class="text-primary" d="M0,150 C50,140 100,100 150,110 C200,120 250,80 300,90 C350,100 400,60 450,40 C500,20 550,50 600,30 L600,240 L0,240 Z" fill="none" stroke="currentColor" stroke-width="2"></path>
<path class="text-primary-dim" d="M0,200 C100,190 200,210 300,100 C350,40 400,20 450,150 C500,200 550,190 600,180" fill="none" stroke="currentColor" stroke-dasharray="4 4" stroke-width="1.5"></path>
</svg>
<!-- Y-axis labels -->
<div class="absolute -left-6 bottom-0 text-[10px] text-on-surface-variant">0</div>
<div class="absolute -left-6 top-1/2 text-[10px] text-on-surface-variant">10</div>
<div class="absolute -left-6 top-0 text-[10px] text-on-surface-variant">20</div>
<!-- X-axis labels -->
<div class="absolute -bottom-6 left-0 text-[10px] text-on-surface-variant">-1h</div>
<div class="absolute -bottom-6 left-1/2 text-[10px] text-on-surface-variant">-30m</div>
<div class="absolute -bottom-6 right-0 text-[10px] text-on-surface-variant">Now</div>
</div>
</div>
<!-- Node Behavior & State Panels -->
<div class="flex flex-col space-y-4">
<div class="bg-surface-container-lowest rounded-xl p-5 border border-outline-variant/15 flex-1">
<h3 class="text-sm font-semibold text-on-background mb-4 uppercase tracking-wider">State Transition</h3>
<div class="space-y-3">
<div class="flex justify-between items-center">
<span class="text-sm text-on-surface-variant flex items-center"><span class="w-1.5 h-1.5 rounded-full bg-secondary mr-2"></span>Draining</span>
<span class="text-sm font-medium">8</span>
</div>
<div class="flex justify-between items-center">
<span class="text-sm text-on-surface-variant flex items-center"><span class="w-1.5 h-1.5 rounded-full bg-primary mr-2"></span>Provisioning</span>
<span class="text-sm font-medium">5</span>
</div>
<div class="flex justify-between items-center">
<span class="text-sm text-on-surface-variant flex items-center"><span class="w-1.5 h-1.5 rounded-full bg-on-tertiary-fixed-variant mr-2"></span>Terminating</span>
<span class="text-sm font-medium">3</span>
</div>
<div class="flex justify-between items-center">
<span class="text-sm text-on-surface-variant flex items-center"><span class="w-1.5 h-1.5 rounded-full bg-error mr-2"></span>Blocked</span>
<span class="text-sm font-medium text-error">2</span>
</div>
</div>
</div>
<div class="bg-surface-container-lowest rounded-xl p-5 border border-outline-variant/15 flex-1">
<h3 class="text-sm font-semibold text-on-background mb-4 uppercase tracking-wider">Behavior Profile</h3>
<div class="space-y-3">
<div class="flex justify-between items-center">
<span class="text-sm text-on-surface-variant">Fast (&lt; 30s)</span>
<span class="text-sm font-medium">12</span>
</div>
<div class="w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden">
<div class="bg-primary h-full" style="width: 75%"></div>
</div>
<div class="flex justify-between items-center mt-2">
<span class="text-sm text-on-surface-variant">Slow (&gt; 60s)</span>
<span class="text-sm font-medium">4</span>
</div>
<div class="w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden">
<div class="bg-secondary h-full" style="width: 25%"></div>
</div>
</div>
</div>
</div>
</section>
<!-- Intelligence & Impact Layer -->
<section class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
<!-- Node Intelligence -->
<div class="bg-surface-container-lowest rounded-xl p-6 border border-outline-variant/15">
<h2 class="text-[17px] font-bold tracking-[-0.4px] text-on-background mb-6">Resource Saturation</h2>
<div class="space-y-5">
<div>
<div class="flex justify-between text-sm mb-1.5">
<span class="text-on-surface-variant">CPU Aggregate</span>
<span class="font-medium">72%</span>
</div>
<div class="w-full bg-surface-container-high h-2 rounded-full overflow-hidden">
<div class="bg-primary h-full" style="width: 72%"></div>
</div>
</div>
<div>
<div class="flex justify-between text-sm mb-1.5">
<span class="text-on-surface-variant">Memory Aggregate</span>
<span class="font-medium">58%</span>
</div>
<div class="w-full bg-surface-container-high h-2 rounded-full overflow-hidden">
<div class="bg-primary h-full" style="width: 58%"></div>
</div>
</div>
<div>
<div class="flex justify-between text-sm mb-1.5">
<span class="text-on-surface-variant">Pod Density</span>
<span class="font-medium">80/110</span>
</div>
<div class="w-full bg-surface-container-high h-2 rounded-full overflow-hidden">
<div class="bg-primary-dim h-full" style="width: 72%"></div>
</div>
</div>
<div class="pt-2 border-t border-outline-variant/15 flex justify-between items-center">
<span class="text-sm text-on-surface-variant">Fragmentation Risk</span>
<span class="px-2 py-0.5 bg-error-container/30 text-error rounded-full text-xs font-bold tracking-wider">HIGH</span>
</div>
</div>
</div>
<!-- Capacity Impact -->
<div class="bg-surface-container-lowest rounded-xl p-6 border border-outline-variant/15">
<h2 class="text-[17px] font-bold tracking-[-0.4px] text-on-background mb-6">Capacity Delta</h2>
<div class="grid grid-cols-2 gap-4 mb-6">
<div class="p-4 bg-surface-container-low rounded-lg">
<div class="text-xs text-on-surface-variant mb-1 uppercase tracking-wider">Available</div>
<div class="text-2xl font-bold text-on-background">124 <span class="text-sm font-normal text-on-surface-variant">cores</span></div>
<div class="text-sm text-on-surface-variant mt-1">512 GB mem</div>
</div>
<div class="p-4 bg-primary/5 rounded-lg border border-primary/20">
<div class="text-xs text-primary mb-1 uppercase tracking-wider">Required</div>
<div class="text-2xl font-bold text-primary">168 <span class="text-sm font-normal opacity-80">cores</span></div>
<div class="text-sm text-primary mt-1 opacity-80">680 GB mem</div>
</div>
</div>
<div class="bg-surface-variant/30 p-3 rounded-lg flex items-start">
<span class="material-symbols-outlined text-primary mr-2 text-[20px]">info</span>
<p class="text-sm text-on-background font-medium">Pending Pods: 42 → Requires ~5 nodes</p>
</div>
</div>
<!-- Outliers & Alerts -->
<div class="bg-surface-container-lowest rounded-xl p-6 border border-outline-variant/15 md:col-span-2 xl:col-span-1">
<h2 class="text-[17px] font-bold tracking-[-0.4px] text-on-background mb-4">Critical Anomalies</h2>
<div class="space-y-3">
<div class="flex items-start p-3 bg-error/5 rounded-lg border border-error/10">
<span class="material-symbols-outlined text-error mr-3 text-[20px]">warning</span>
<div>
<h4 class="text-sm font-semibold text-error">2 nodes blocked (PDB)</h4>
<p class="text-xs text-on-surface-variant mt-0.5">PodDisruptionBudget preventing drain on node-group-alpha.</p>
</div>
</div>
<div class="flex items-start p-3 bg-secondary/5 rounded-lg border border-secondary/10">
<span class="material-symbols-outlined text-secondary mr-3 text-[20px]">timer</span>
<div>
<h4 class="text-sm font-semibold text-on-background">1 node slow draining (&gt;60s)</h4>
<p class="text-xs text-on-surface-variant mt-0.5">Termination grace period extended by workload: payment-svc.</p>
</div>
</div>
<div class="flex items-start p-3 bg-error/5 rounded-lg border border-error/10">
<span class="material-symbols-outlined text-error mr-3 text-[20px]">cloud_off</span>
<div>
<h4 class="text-sm font-semibold text-error">1 provisioning delay</h4>
<p class="text-xs text-on-surface-variant mt-0.5">Instance capacity issue in us-east-1a.</p>
</div>
</div>
</div>
</div>
</section>
<!-- Workload Scaling Table -->
<section class="bg-surface-container-lowest rounded-xl border border-outline-variant/15 overflow-hidden">
<div class="px-6 py-5 border-b border-outline-variant/15 flex justify-between items-center">
<h2 class="text-[17px] font-bold tracking-[-0.4px] text-on-background">Execution Streams</h2>
<button class="text-sm text-primary font-medium hover:text-primary-dim">View All Streams</button>
</div>
<div class="overflow-x-auto">
<table class="w-full text-left border-collapse">
<thead>
<tr class="bg-surface-container-low/50">
<th class="px-6 py-3 text-xs font-semibold text-on-surface-variant uppercase tracking-wider border-b border-outline-variant/15">Workload</th>
<th class="px-6 py-3 text-xs font-semibold text-on-surface-variant uppercase tracking-wider border-b border-outline-variant/15">Replicas</th>
<th class="px-6 py-3 text-xs font-semibold text-on-surface-variant uppercase tracking-wider border-b border-outline-variant/15">Trigger</th>
<th class="px-6 py-3 text-xs font-semibold text-on-surface-variant uppercase tracking-wider border-b border-outline-variant/15">Status</th>
<th class="px-6 py-3 text-xs font-semibold text-on-surface-variant uppercase tracking-wider border-b border-outline-variant/15">Node Impact</th>
</tr>
</thead>
<tbody class="divide-y divide-outline-variant/10">
<tr class="hover:bg-surface-variant/20 transition-colors">
<td class="px-6 py-4">
<div class="flex items-center">
<span class="material-symbols-outlined text-on-surface-variant mr-3 text-[20px]">deployed_code</span>
<span class="text-sm font-medium text-on-background">payment-processing-api</span>
</div>
</td>
<td class="px-6 py-4 text-sm text-on-surface-variant">12 → <span class="font-semibold text-primary">24</span></td>
<td class="px-6 py-4 text-sm text-on-surface-variant">CPU &gt; 85% (HPA)</td>
<td class="px-6 py-4">
<span class="px-2.5 py-1 bg-primary/10 text-primary rounded-full text-xs font-medium border border-primary/20">Scaling Up</span>
</td>
<td class="px-6 py-4 text-sm text-on-surface-variant">+2 Nodes Req.</td>
</tr>
<tr class="hover:bg-surface-variant/20 transition-colors">
<td class="px-6 py-4">
<div class="flex items-center">
<span class="material-symbols-outlined text-on-surface-variant mr-3 text-[20px]">database</span>
<span class="text-sm font-medium text-on-background">user-session-cache</span>
</div>
</td>
<td class="px-6 py-4 text-sm text-on-surface-variant">8 → <span class="font-semibold text-secondary">4</span></td>
<td class="px-6 py-4 text-sm text-on-surface-variant">Memory &lt; 30% (HPA)</td>
<td class="px-6 py-4">
<span class="px-2.5 py-1 bg-secondary/10 text-secondary rounded-full text-xs font-medium border border-secondary/20">Scaling Down</span>
</td>
<td class="px-6 py-4 text-sm text-on-surface-variant">-1 Node Cand.</td>
</tr>
<tr class="hover:bg-surface-variant/20 transition-colors">
<td class="px-6 py-4">
<div class="flex items-center">
<span class="material-symbols-outlined text-on-surface-variant mr-3 text-[20px]">lan</span>
<span class="text-sm font-medium text-on-background">ingress-controller-ext</span>
</div>
</td>
<td class="px-6 py-4 text-sm text-on-surface-variant">3 → <span class="font-semibold text-on-background">5</span></td>
<td class="px-6 py-4 text-sm text-on-surface-variant">Network RPS Spike</td>
<td class="px-6 py-4">
<span class="px-2.5 py-1 bg-surface-container-high text-on-surface-variant rounded-full text-xs font-medium border border-outline-variant/30">Pending</span>
</td>
<td class="px-6 py-4 text-sm text-on-surface-variant">Evaluating...</td>
</tr>
</tbody>
</table>
</div>
</section>
</div>
</main>
</body></html>
]

Rightsizing [<!DOCTYPE html>

<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>InfraSize - Rightsizing Dashboard</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<style>
        .material-symbols-outlined {
            font-family: 'Material Symbols Outlined';
            font-weight: normal;
            font-style: normal;
            font-size: 20px;
            line-height: 1;
            letter-spacing: normal;
            text-transform: none;
            display: inline-block;
            white-space: nowrap;
            word-wrap: normal;
            direction: ltr;
            -webkit-font-feature-settings: 'liga';
            -webkit-font-smoothing: antialiased;
        }
        .icon-fill { font-variation-settings: 'FILL' 1; }
    </style>
<script id="tailwind-config">
        tailwind.config = {
            darkMode: "class",
            theme: {
                extend: {
                    "colors": {
                        "tertiary-container": "#f4f3f8", "on-secondary": "#fbf8fa", "surface-container": "#ebeef2",
                        "on-error": "#fff7f6", "inverse-surface": "#0c0e10", "error-dim": "#4e0309",
                        "surface-tint": "#005cba", "on-surface-variant": "#596065", "inverse-on-surface": "#9c9d9f",
                        "primary-container": "#d7e3ff", "surface-dim": "#d3dbe2", "on-secondary-fixed": "#3f3f41",
                        "on-primary": "#f7f7ff", "on-primary-container": "#0050a2", "inverse-primary": "#5095fe",
                        "on-background": "#2d3338", "on-tertiary-fixed-variant": "#65666a", "secondary": "#5f5f61",
                        "surface": "#f9f9fb", "on-primary-fixed-variant": "#005ab4", "on-primary-fixed": "#003e80",
                        "surface-container-highest": "#dde3e9", "secondary-fixed-dim": "#d6d3d6", "surface-bright": "#f9f9fb",
                        "on-tertiary-fixed": "#49494e", "secondary-dim": "#535355", "outline-variant": "#acb3b8",
                        "tertiary-dim": "#525357", "on-tertiary": "#faf8fe", "tertiary-fixed-dim": "#e6e5ea",
                        "error": "#9f403d", "background": "#f9f9fb", "tertiary": "#5e5f63", "primary-fixed": "#d7e3ff",
                        "on-tertiary-container": "#5b5b60", "on-surface": "#2d3338", "primary": "#005cba",
                        "on-error-container": "#752121", "surface-container-high": "#e4e9ee", "secondary-container": "#e4e2e4",
                        "on-secondary-container": "#525154", "surface-container-lowest": "#ffffff", "primary-dim": "#0051a4",
                        "error-container": "#fe8983", "primary-fixed-dim": "#c1d5ff", "outline": "#757c81",
                        "on-secondary-fixed-variant": "#5c5b5d", "surface-variant": "#dde3e9", "secondary-fixed": "#e4e2e4",
                        "surface-container-low": "#f2f4f6", "tertiary-fixed": "#f4f3f8"
                    },
                    "borderRadius": {
                        "DEFAULT": "0.25rem", "lg": "0.5rem", "xl": "0.75rem", "full": "9999px"
                    },
                    "fontFamily": {
                        "headline": ["Inter"], "display": ["Inter"], "body": ["Inter"], "label": ["Inter"]
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-background text-on-surface font-body antialiased flex h-screen overflow-hidden">
<!-- SideNavBar (From JSON) -->
<nav class="bg-slate-50 dark:bg-slate-900 flex flex-col border-r border-slate-200 dark:border-slate-800 p-6 space-y-8 docked left-0 h-screen w-64 flex-shrink-0 z-40 transition-all duration-300 ease-in-out">
<!-- Header -->
<div class="flex items-center space-x-3 mb-2">
<div class="w-8 h-8 rounded bg-primary flex items-center justify-center flex-shrink-0">
<span class="material-symbols-outlined text-on-primary icon-fill text-[18px]">bolt</span>
</div>
<div>
<div class="text-lg font-black tracking-tighter text-slate-900 dark:text-slate-50 leading-tight">Infrastructure</div>
<div class="text-xs font-semibold tracking-wider text-slate-500">Rightsizing Engine</div>
</div>
</div>
<!-- Main Navigation -->
<div class="flex-1 space-y-2">
<!-- Observability -->
<a class="flex items-center space-x-3 px-4 py-3 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 transition-all duration-300 ease-in-out rounded font-medium" href="#">
<span class="material-symbols-outlined" data-icon="monitoring">monitoring</span>
<span class="text-sm font-medium">Observability</span>
</a>
<!-- Intelligence -->
<a class="flex items-center space-x-3 px-4 py-3 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 transition-all duration-300 ease-in-out rounded font-medium" href="#">
<span class="material-symbols-outlined" data-icon="psychology">psychology</span>
<span class="text-sm font-medium">Intelligence</span>
</a>
<!-- Capacity (Active) -->
<a class="flex items-center space-x-3 px-4 py-3 bg-white dark:bg-slate-950 text-blue-600 dark:text-blue-400 rounded-lg shadow-sm font-bold transition-all duration-300 ease-in-out" href="#">
<span class="material-symbols-outlined icon-fill" data-icon="storage">storage</span>
<span class="text-sm">Capacity</span>
</a>
</div>
<!-- Footer Navigation -->
<div class="space-y-2 pt-6 border-t border-slate-200 dark:border-slate-800">
<a class="flex items-center space-x-3 px-4 py-2 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 transition-all duration-300 ease-in-out rounded font-medium" href="#">
<span class="material-symbols-outlined text-[18px]" data-icon="help_outline">help_outline</span>
<span class="text-sm font-medium">Support</span>
</a>
<a class="flex items-center space-x-3 px-4 py-2 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-200/50 dark:hover:bg-slate-800/50 transition-all duration-300 ease-in-out rounded font-medium" href="#">
<span class="material-symbols-outlined text-[18px]" data-icon="description">description</span>
<span class="text-sm font-medium">Documentation</span>
</a>
</div>
</nav>
<!-- Main Canvas -->
<main class="flex-1 flex flex-col h-full overflow-hidden bg-background">
<!-- TopAppBar Context (High-Density Header Summary) -->
<header class="flex items-center justify-between px-8 py-4 bg-surface-container-low z-10 sticky top-0">
<div class="flex items-center space-x-4">
<h1 class="text-[17px] font-bold tracking-tight text-on-surface">RIGHTSIZING</h1>
<div class="h-4 w-px bg-outline-variant/30"></div>
<div class="flex items-center space-x-6 text-xs font-semibold tracking-wider text-on-surface-variant uppercase">
<span class="flex items-center gap-1"><span class="text-on-surface">48</span> Workloads</span>
<span class="flex items-center gap-1 text-primary"><span class="material-symbols-outlined text-[14px]">tune</span> 21 Optimizable</span>
<span class="flex items-center gap-1"><span class="text-on-surface">12</span> Auto</span>
<span class="flex items-center gap-1 text-on-surface"><span class="w-2 h-2 rounded-full bg-secondary-dim"></span> 9 Pending</span>
</div>
</div>
<div class="flex items-center space-x-6 text-xs font-semibold tracking-wider text-on-surface-variant uppercase">
<span><span class="text-on-surface">18</span> Nodes Impacted</span>
<span><span class="text-on-surface">6</span> Pools</span>
<div class="flex items-center gap-2 bg-surface-container-highest px-3 py-1 rounded text-primary">
<span class="material-symbols-outlined text-[14px]">smart_toy</span>
<span>Mode: AUTO</span>
</div>
</div>
</header>
<!-- Scrollable Dashboard Content -->
<div class="flex-1 overflow-y-auto p-8">
<div class="max-w-7xl mx-auto space-y-6">
<!-- Top Row: Cost & Utilization -->
<div class="grid grid-cols-12 gap-6">
<!-- Cost Summary & Graph (Span 8) -->
<div class="col-span-8 bg-surface-container-lowest rounded p-6 shadow-sm">
<div class="flex justify-between items-start mb-8">
<div>
<h2 class="text-[17px] font-bold tracking-tight text-on-surface mb-2">Cost Impact Projection</h2>
<div class="flex items-baseline gap-4">
<span class="text-3xl font-bold tracking-tight text-on-surface-variant line-through opacity-60">$4,820</span>
<span class="text-4xl font-bold tracking-tight text-on-surface">$3,580</span>
<div class="ml-4 bg-primary-container text-on-primary-container px-3 py-1 rounded-full text-xs font-bold tracking-wide flex items-center gap-1">
<span class="material-symbols-outlined text-[14px]">trending_down</span>
                                        Savings: $1,240 / 25.7%
                                    </div>
</div>
</div>
<button class="bg-primary text-on-primary px-4 py-2 rounded text-sm font-semibold flex items-center gap-2 hover:bg-primary-dim transition-colors">
                                Apply All 21 Recommendations
                                <span class="material-symbols-outlined text-[18px]">arrow_forward</span>
</button>
</div>
<!-- Graph Area (Simulated) -->
<div class="relative h-48 w-full mt-4 bg-surface-container/30 rounded p-4">
<!-- Y-Axis Labels -->
<div class="absolute left-4 top-4 bottom-8 flex flex-col justify-between text-xs font-semibold text-on-surface-variant/60">
<span>$5k</span><span>$4k</span><span>$3k</span>
</div>
<!-- Graph Lines SVG -->
<svg class="w-full h-full pl-8 pb-4" preserveaspectratio="none" viewbox="0 0 100 100">
<!-- Current Spend (Gray Dashed) -->
<path class="text-outline-variant/60" d="M0,20 L20,25 L40,22 L60,15 L80,18 L100,10" fill="none" stroke="currentColor" stroke-dasharray="4" stroke-width="1.5"></path>
<!-- Recommended Spend (Primary Solid) -->
<path class="text-primary" d="M0,20 L20,25 L40,22 L60,45 L80,55 L100,60" fill="none" stroke="currentColor" stroke-width="2"></path>
<!-- Markers -->
<polygon class="text-primary" fill="currentColor" points="60,45 58,48 62,48"></polygon>
<polygon class="text-primary" fill="currentColor" points="80,55 78,58 82,58"></polygon>
</svg>
<!-- Data Tooltip (Positioned at 10:30 marker roughly) -->
<div class="absolute left-[55%] top-[15%] bg-inverse-surface/90 backdrop-blur-md rounded p-3 text-on-primary shadow-xl border border-white/10 w-48 z-10 pointer-events-none">
<div class="text-xs font-bold text-inverse-on-surface mb-2">10:30 AM</div>
<div class="flex justify-between text-sm mb-1">
<span class="text-outline-variant">Current</span>
<span>$210</span>
</div>
<div class="flex justify-between text-sm mb-1 font-semibold text-primary-fixed-dim">
<span>Optimized</span>
<span>$160</span>
</div>
<div class="h-px bg-white/20 my-2"></div>
<div class="flex justify-between text-xs font-bold text-error-container">
<span>Save</span>
<span>$50</span>
</div>
</div>
</div>
</div>
<!-- Utilization Insights (Span 4) -->
<div class="col-span-4 bg-surface-container-lowest rounded p-6 shadow-sm flex flex-col">
<h2 class="text-[17px] font-bold tracking-tight text-on-surface mb-6">Resource Allocation</h2>
<div class="space-y-6 flex-1">
<!-- CPU -->
<div>
<div class="flex justify-between text-xs font-semibold tracking-wide uppercase text-on-surface-variant mb-2">
<span>CPU Core Usage</span>
<span class="text-error font-bold">+65% Over</span>
</div>
<div class="relative h-2 bg-surface-container-high rounded-full overflow-hidden">
<!-- Actual -->
<div class="absolute top-0 left-0 h-full bg-primary rounded-full w-[35%] z-10"></div>
<!-- Requested -->
<div class="absolute top-0 left-0 h-full bg-error-container/50 rounded-full w-[100%]"></div>
</div>
<div class="flex justify-between mt-1 text-xs text-on-surface-variant/80">
<span>Actual: 142vCPU</span>
<span>Req: 405vCPU</span>
</div>
</div>
<!-- Memory -->
<div>
<div class="flex justify-between text-xs font-semibold tracking-wide uppercase text-on-surface-variant mb-2">
<span>Memory Usage</span>
<span class="text-error font-bold">+40% Over</span>
</div>
<div class="relative h-2 bg-surface-container-high rounded-full overflow-hidden">
<div class="absolute top-0 left-0 h-full bg-primary rounded-full w-[60%] z-10"></div>
<div class="absolute top-0 left-0 h-full bg-error-container/50 rounded-full w-[100%]"></div>
</div>
<div class="flex justify-between mt-1 text-xs text-on-surface-variant/80">
<span>Actual: 820Gi</span>
<span>Req: 1,150Gi</span>
</div>
</div>
</div>
<div class="mt-4 bg-surface-container-low p-3 rounded flex items-start gap-3">
<span class="material-symbols-outlined text-primary text-[20px] mt-0.5">lightbulb</span>
<p class="text-sm text-on-surface-variant leading-relaxed">System-wide rightsizing will reclaim idle resources, primarily correcting severe CPU over-provisioning across worker nodes.</p>
</div>
</div>
</div> <!-- End Top Row -->
<!-- Node Rightsizing Table -->
<div class="bg-surface-container-lowest rounded shadow-sm">
<div class="px-6 py-5 border-b border-outline-variant/15 flex justify-between items-center">
<h2 class="text-[17px] font-bold tracking-tight text-on-surface">Node Pool Optimization</h2>
<button class="text-sm font-semibold text-primary hover:text-primary-dim transition-colors">View All Pools</button>
</div>
<div class="overflow-x-auto">
<table class="w-full text-left border-collapse">
<thead>
<tr class="text-xs font-semibold tracking-wider text-on-surface-variant uppercase bg-surface">
<th class="px-6 py-4 font-semibold">Pool / Instance</th>
<th class="px-6 py-4 font-semibold">Node Count (Cur → Rec)</th>
<th class="px-6 py-4 font-semibold">Proj. CPU</th>
<th class="px-6 py-4 font-semibold">Proj. Mem</th>
<th class="px-6 py-4 font-semibold">Fragmentation</th>
<th class="px-6 py-4 font-semibold">Risk Level</th>
<th class="px-6 py-4 font-semibold text-right">Actions</th>
</tr>
</thead>
<tbody class="text-sm divide-y divide-outline-variant/10">
<tr class="hover:bg-surface-container-low/50 transition-colors">
<td class="px-6 py-4">
<div class="font-bold text-on-surface">c6a.large</div>
<div class="text-xs text-on-surface-variant">Spot Fleet • us-east-1</div>
</td>
<td class="px-6 py-4 font-medium">
<span class="text-on-surface-variant line-through mr-2">12</span>
<span class="text-primary font-bold">9 nodes</span>
</td>
<td class="px-6 py-4">72%</td>
<td class="px-6 py-4">58%</td>
<td class="px-6 py-4"><span class="bg-error-container text-on-error-container px-2 py-1 rounded-full text-xs font-bold">HIGH</span></td>
<td class="px-6 py-4"><span class="bg-surface-container-high text-on-surface px-2 py-1 rounded-full text-xs font-bold">LOW</span></td>
<td class="px-6 py-4 text-right">
<div class="flex justify-end gap-2">
<button class="px-3 py-1.5 text-xs font-semibold text-primary hover:bg-surface-variant rounded transition-colors">Simulate</button>
<button class="px-3 py-1.5 text-xs font-semibold bg-primary text-on-primary rounded hover:bg-primary-dim transition-colors">Apply</button>
</div>
</td>
</tr>
<tr class="hover:bg-surface-container-low/50 transition-colors">
<td class="px-6 py-4">
<div class="font-bold text-on-surface">m5.large</div>
<div class="text-xs text-on-surface-variant">On-Demand • us-east-1</div>
</td>
<td class="px-6 py-4 font-medium">
<span class="text-on-surface-variant line-through mr-2">8</span>
<span class="text-primary font-bold">6 nodes</span>
</td>
<td class="px-6 py-4">65%</td>
<td class="px-6 py-4">80%</td>
<td class="px-6 py-4"><span class="bg-surface-container-high text-on-surface px-2 py-1 rounded-full text-xs font-bold">MED</span></td>
<td class="px-6 py-4"><span class="bg-surface-container-high text-on-surface px-2 py-1 rounded-full text-xs font-bold">LOW</span></td>
<td class="px-6 py-4 text-right">
<div class="flex justify-end gap-2">
<button class="px-3 py-1.5 text-xs font-semibold text-primary hover:bg-surface-variant rounded transition-colors">Simulate</button>
<button class="px-3 py-1.5 text-xs font-semibold bg-primary text-on-primary rounded hover:bg-primary-dim transition-colors">Apply</button>
</div>
</td>
</tr>
</tbody>
</table>
</div>
</div>
<!-- Bottom Row: Pod Table & Drilldown -->
<div class="grid grid-cols-12 gap-6">
<!-- Pod Rightsizing Table (Span 7) -->
<div class="col-span-7 bg-surface-container-lowest rounded shadow-sm flex flex-col">
<div class="px-6 py-5 border-b border-outline-variant/15">
<h2 class="text-[17px] font-bold tracking-tight text-on-surface">Workload Recommendations</h2>
</div>
<div class="overflow-y-auto flex-1">
<table class="w-full text-left border-collapse">
<thead>
<tr class="text-xs font-semibold tracking-wider text-on-surface-variant uppercase bg-surface">
<th class="px-4 py-3">Workload</th>
<th class="px-4 py-3">CPU (Cur→Rec)</th>
<th class="px-4 py-3">Mem (Cur→Rec)</th>
<th class="px-4 py-3 text-right">Save/mo</th>
</tr>
</thead>
<tbody class="text-sm divide-y divide-outline-variant/10">
<!-- Selected Row -->
<tr class="bg-surface-container-high cursor-pointer relative">
<td class="absolute left-0 top-0 bottom-0 w-1 bg-primary"></td>
<td class="px-4 py-4 pl-5 font-bold text-primary">api-service</td>
<td class="px-4 py-4"><span class="text-on-surface-variant line-through text-xs mr-1">500m</span>300m</td>
<td class="px-4 py-4"><span class="text-on-surface-variant line-through text-xs mr-1">1Gi</span>700Mi</td>
<td class="px-4 py-4 text-right font-bold text-on-surface">$120</td>
</tr>
<tr class="hover:bg-surface-container-low/50 cursor-pointer transition-colors">
<td class="px-4 py-4 pl-5 font-bold text-on-surface">worker-queue</td>
<td class="px-4 py-4"><span class="text-on-surface-variant line-through text-xs mr-1">1000m</span>600m</td>
<td class="px-4 py-4"><span class="text-on-surface-variant line-through text-xs mr-1">2Gi</span>1.5Gi</td>
<td class="px-4 py-4 text-right font-bold text-on-surface">$280</td>
</tr>
<tr class="hover:bg-surface-container-low/50 cursor-pointer transition-colors">
<td class="px-4 py-4 pl-5 font-bold text-on-surface">redis-cache</td>
<td class="px-4 py-4"><span class="text-on-surface-variant line-through text-xs mr-1">200m</span>200m</td>
<td class="px-4 py-4"><span class="text-on-surface-variant line-through text-xs mr-1">4Gi</span>2Gi</td>
<td class="px-4 py-4 text-right font-bold text-on-surface">$85</td>
</tr>
</tbody>
</table>
</div>
</div>
<!-- Drilldown Panel (Span 5) -->
<div class="col-span-5 bg-surface-container-lowest rounded shadow-sm p-6 border border-outline-variant/10">
<div class="flex items-center gap-3 mb-6">
<span class="material-symbols-outlined text-primary text-[24px]">apps</span>
<div>
<h3 class="text-[17px] font-bold tracking-tight text-on-surface">api-service</h3>
<p class="text-xs font-semibold tracking-wider text-on-surface-variant uppercase">Deployment • namespace: core</p>
</div>
</div>
<div class="space-y-6">
<!-- Telemetry -->
<div class="grid grid-cols-2 gap-4">
<div class="bg-surface p-3 rounded">
<div class="text-xs font-semibold tracking-wide text-on-surface-variant uppercase mb-1">CPU Profiling</div>
<div class="text-sm font-medium text-on-surface">Avg: 120m</div>
<div class="text-sm font-medium text-on-surface">P95: 260m</div>
<div class="text-sm font-bold text-primary mt-1">Peak: 300m</div>
</div>
<div class="bg-surface p-3 rounded">
<div class="text-xs font-semibold tracking-wide text-on-surface-variant uppercase mb-1">Mem Profiling</div>
<div class="text-sm font-medium text-on-surface">Avg: 450Mi</div>
<div class="text-sm font-medium text-on-surface">P95: 620Mi</div>
<div class="text-sm font-bold text-primary mt-1">Peak: 680Mi</div>
</div>
</div>
<!-- Rationale -->
<div>
<h4 class="text-sm font-bold text-on-surface mb-2">Recommendation Rationale</h4>
<p class="text-sm text-on-surface-variant leading-relaxed">
                                    Historical analysis over 14 days indicates requested limits are 40% higher than peak utilization during maximum load events. Shrinking limits to Peak + 5% buffer guarantees stability while recovering resources.
                                </p>
</div>
<!-- Safety Checks -->
<div>
<h4 class="text-sm font-bold text-on-surface mb-2">Safety Verification</h4>
<ul class="space-y-2">
<li class="flex items-center gap-2 text-sm text-on-surface-variant">
<span class="material-symbols-outlined text-[16px] text-primary">check_circle</span>
                                        Multi-replica deployment (3/3 ready)
                                    </li>
<li class="flex items-center gap-2 text-sm text-on-surface-variant">
<span class="material-symbols-outlined text-[16px] text-primary">check_circle</span>
                                        PodDisruptionBudget active
                                    </li>
<li class="flex items-center gap-2 text-sm text-on-surface-variant">
<span class="material-symbols-outlined text-[16px] text-primary">check_circle</span>
                                        No OOMKills in 30 days
                                    </li>
</ul>
</div>
<!-- Actions -->
<div class="pt-4 border-t border-outline-variant/15 flex gap-3">
<button class="flex-1 bg-surface-container-high text-on-surface py-2 rounded text-sm font-semibold hover:bg-surface-variant transition-colors">Decline</button>
<button class="flex-1 bg-primary text-on-primary py-2 rounded text-sm font-semibold shadow-sm hover:bg-primary-dim transition-colors">Apply 300m / 700Mi</button>
</div>
</div>
</div>
</div> <!-- End Bottom Row -->
</div>
</div>
</main>
</body></html>
]







