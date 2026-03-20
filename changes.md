<!DOCTYPE html>

<html class="h-full bg-gray-50" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Cloud Management - Cluster Overview</title>
<!-- Tailwind CSS v3 CDN -->
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&amp;display=swap" rel="stylesheet"/>
<style data-purpose="typography">
    body { font-family: 'Inter', sans-serif; }
    .section-title {
        font-size: 17px;
        font-weight: 700;
        margin: 0px;
        letter-spacing: -0.4px;
        color: rgb(17, 19, 24);
        text-transform: none; /* Override uppercase if applied */
    }
  </style>
<style data-purpose="custom-shadows">
    .card-shadow { box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06); }
  </style>
</head>
<body class="h-full overflow-hidden flex">
<!-- BEGIN: Left Sidebar -->
<aside class="w-64 bg-[#0F172A] text-gray-300 flex-shrink-0 hidden md:flex flex-col" data-purpose="sidebar">
<div class="p-6 flex items-center space-x-3">
<div class="w-8 h-8 bg-blue-600 rounded flex items-center justify-center font-bold text-white">S</div>
<div>
<div class="text-sm font-semibold text-white">Spot Optimizer</div>
<div class="text-[10px] uppercase tracking-wider text-gray-500">ORG_ADMIN</div>
</div>
</div>
<div class="px-4 mb-4">
<div class="relative">
<span class="absolute inset-y-0 left-0 pl-3 flex items-center text-gray-500">
<svg class="h-4 w-4" fill="none" stroke="currentColor" viewbox="0 0 24 24"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>
</span>
<input class="block w-full pl-10 pr-3 py-2 border-none rounded-md bg-[#1E293B] text-sm focus:ring-blue-500 placeholder-gray-500" placeholder="Search features..." type="text"/>
</div>
</div>
<nav class="flex-1 px-4 space-y-1 overflow-y-auto">
<div class="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-2 mt-4">Overview</div>
<a class="group flex items-center px-2 py-2 text-sm font-medium rounded-md bg-gray-900 text-white" href="#">
<svg class="mr-3 h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewbox="0 0 24 24"><path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>
        Dashboard
      </a>
<div class="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-2 mt-6">Cost Intelligence</div>
<a class="group flex items-center px-2 py-2 text-sm font-medium rounded-md hover:bg-gray-800 hover:text-white" href="#">
<svg class="mr-3 h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewbox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>
        ASCP.ai <span class="ml-auto bg-blue-600 text-[10px] px-1.5 py-0.5 rounded">ML</span>
</a>
<a class="group flex items-center px-2 py-2 text-sm font-medium rounded-md hover:bg-gray-800 hover:text-white" href="#">
<svg class="mr-3 h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewbox="0 0 24 24"><path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>
        Right-Sizing
      </a>
</nav>
<div class="p-4 border-t border-gray-800">
<div class="flex items-center space-x-3">
<div class="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-xs font-bold text-white">A</div>
<div class="flex-1 min-w-0">
<p class="text-xs font-medium text-white truncate">ath@gmail.com</p>
<p class="text-[10px] text-gray-500 truncate">ORG_ADMIN</p>
</div>
<svg class="h-4 w-4 text-gray-500" fill="none" stroke="currentColor" viewbox="0 0 24 24"><path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>
</div>
</div>
</aside>
<!-- END: Left Sidebar -->
<!-- Main Content Area -->
<main class="flex-1 flex flex-col min-w-0 overflow-hidden bg-gray-50">
<!-- BEGIN: Top Header/Breadcrumb -->
<header class="bg-white border-b border-gray-200 px-8 py-4 flex items-center justify-between">
<div class="flex items-center space-x-4">
<h1 class="section-title">spot-demo-1</h1>
<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
<span class="w-2 h-2 mr-1.5 bg-orange-500 rounded-full"></span>
          Warning
        </span>
<div class="flex space-x-1 ml-4">
<span class="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-medium border border-gray-200 uppercase">AWS</span>
<span class="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-medium border border-gray-200 uppercase">ap-south-1</span>
<span class="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] font-medium border border-gray-200 uppercase">K8s 1.28</span>
</div>
</div>
<div class="flex items-center space-x-3">
<button class="px-4 py-2 border border-blue-600 text-blue-600 rounded-md text-sm font-medium hover:bg-blue-50">Update Agent</button>
<button class="px-4 py-2 border border-gray-300 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-50">Refresh</button>
<button class="px-4 py-2 border border-red-200 text-red-600 rounded-md text-sm font-medium hover:bg-red-50">Remove</button>
</div>
</header>
<!-- END: Top Header/Breadcrumb -->
<!-- Tabs Navigation -->
<div class="bg-white border-b border-gray-200 px-8">
<nav aria-label="Tabs" class="flex space-x-8">
<a class="border-blue-600 text-blue-600 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm" href="#">Overview</a>
<a class="border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm" href="#">Optimization Settings</a>
<a class="border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm" href="#">Node Template</a>
<a class="border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm" href="#">Activity Log</a>
</nav>
</div>
<!-- Scrollable Content -->
<div class="flex-1 overflow-y-auto p-8 space-y-8">
<!-- BEGIN: Agent Status Alert -->
<section data-purpose="status-alert">
<div class="bg-white border border-orange-200 rounded-lg p-4 flex items-center justify-between border-l-4 border-l-orange-400 card-shadow">
<div class="flex items-center">
<div class="flex flex-col">
<div class="flex items-center">
<span class="font-semibold text-gray-900">Agent Degraded</span>
<span class="ml-2 text-[10px] text-gray-400 bg-gray-100 px-1 rounded uppercase">v1.0.0</span>
</div>
<p class="text-sm text-gray-500 mt-0.5">Last heartbeat: Unknown · Metrics collection active</p>
</div>
</div>
<div class="w-2 h-2 bg-orange-500 rounded-full"></div>
</div>
</section>
<!-- END: Agent Status Alert -->
<!-- BEGIN: KPI Row -->
<section class="grid grid-cols-1 lg:grid-cols-3 gap-6" data-purpose="kpi-cards">
<!-- Cost & Savings Card -->
<div class="bg-white p-6 rounded-lg border border-gray-200 card-shadow relative">
<div class="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-4">Cost &amp; Savings</div>
<div class="flex items-center space-x-6">
<div class="relative flex items-center justify-center">
<!-- Circular Savings Potentail -->
<svg class="w-20 h-20">
<circle class="text-gray-100" cx="40" cy="40" fill="transparent" r="32" stroke="currentColor" stroke-width="8"></circle>
<circle class="text-green-500" cx="40" cy="40" fill="transparent" r="32" stroke="currentColor" stroke-dasharray="201" stroke-dashoffset="86" stroke-linecap="round" stroke-width="8"></circle>
</svg>
<span class="absolute text-sm font-bold text-green-600">57.0%</span>
</div>
<div class="grid grid-cols-1 gap-2">
<div>
<p class="text-[11px] text-gray-500">Monthly Cost</p>
<p class="text-2xl font-bold text-gray-900">$90</p>
</div>
<div class="flex space-x-4">
<div>
<p class="text-[11px] text-gray-500">Realized</p>
<p class="text-sm font-semibold text-gray-900">$0</p>
</div>
<div class="border-l border-orange-300 pl-4">
<p class="text-[11px] text-gray-500">Potential</p>
<p class="text-sm font-semibold text-orange-600">$47.59</p>
</div>
</div>
</div>
</div>
</div>
<!-- Node Composition Card -->
<div class="bg-white p-6 rounded-lg border border-gray-200 card-shadow">
<div class="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-4">Node Composition</div>
<div class="flex items-center justify-between">
<div class="text-center">
<div class="inline-flex flex-col items-center justify-center w-20 h-20 rounded-full border-4 border-blue-50">
<span class="text-xl font-bold text-gray-900">0%</span>
<span class="text-[10px] text-gray-400">Spot Ratio</span>
</div>
</div>
<div class="flex-1 ml-8 space-y-3">
<div class="flex items-center justify-between text-sm">
<div class="flex items-center"><span class="w-2 h-2 rounded-full bg-green-500 mr-2"></span>Spot</div>
<span class="font-semibold">0</span>
</div>
<div class="flex items-center justify-between text-sm">
<div class="flex items-center"><span class="w-2 h-2 rounded-full bg-orange-400 mr-2"></span>Fallback</div>
<span class="font-semibold">0</span>
</div>
<div class="flex items-center justify-between text-sm">
<div class="flex items-center"><span class="w-2 h-2 rounded-full bg-blue-600 mr-2"></span>On-Demand</div>
<span class="font-semibold">3</span>
</div>
</div>
</div>
</div>
<!-- Resource Utilization Card -->
<div class="bg-white p-6 rounded-lg border border-gray-200 card-shadow">
<div class="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-4">Pods</div>
<div class="grid grid-cols-2 gap-4 h-full"><div class="flex items-center space-x-8 py-2">
<div class="flex flex-col items-center justify-center border-r border-gray-100 pr-8">
<div class="relative flex items-center justify-center w-20 h-20 rounded-full border-4 border-gray-100">
<span class="text-2xl font-bold text-gray-900">477</span>
</div>
<span class="text-[10px] font-bold text-gray-400 uppercase mt-2">Total Pods</span>
</div>
<div class="flex-1">
<div class="bg-green-50 border border-green-100 rounded-lg p-3 flex items-center">
<div class="w-10 h-10 bg-white rounded-md flex items-center justify-center border border-green-200 mr-3">
<span class="text-lg font-bold text-green-600">53</span>
</div>
<div>
<div class="flex items-center">
<p class="text-xs font-bold text-gray-900">Pods are Spot-friendly</p>
<svg class="w-3 h-3 text-gray-400 ml-1" fill="none" stroke="currentColor" viewbox="0 0 24 24"><path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>
</div>
<p class="text-[10px] text-gray-500">11.1% of all pods</p>
</div>
</div>
</div>
</div></div>
</div>
</section>
<!-- END: KPI Row -->
<!-- BEGIN: Optimization & Status -->
<section class="space-y-6" data-purpose="optimization-status">
<div class="bg-white rounded-lg border border-gray-200 card-shadow overflow-hidden">
<div class="p-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
<h3 class="section-title">Optimization Status</h3>
<button class="text-blue-600 text-xs font-medium hover:underline">Manage Policies →</button>
</div>
<div class="grid grid-cols-1 md:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-gray-100">
<div class="p-6">
<p class="text-xs font-semibold text-gray-900 mb-1">ASCP.ai</p>
<div class="flex items-center text-sm text-gray-500">
<span class="w-2 h-2 rounded-full bg-gray-300 mr-2"></span>
                Inactive
              </div>
<p class="text-[10px] text-blue-500 mt-2 cursor-pointer hover:underline">Install agent to enable</p>
</div>
<div class="p-6 border-l-4 border-l-orange-400">
<p class="text-xs font-semibold text-gray-900 mb-1">Right-Sizing</p>
<div class="flex items-center text-sm text-orange-600">
<span class="w-2 h-2 rounded-full bg-orange-400 mr-2"></span>
                Over-provisioned
              </div>
<div class="mt-2">
<span class="text-xl font-bold">3</span>
<span class="text-[10px] text-gray-400 block">$153/mo potential</span>
</div>
</div>
<div class="p-6">
<p class="text-xs font-semibold text-gray-900 mb-1">Policies</p>
<p class="text-sm text-gray-500"><span class="font-bold text-gray-700">0 active</span> / 5 configured</p>
</div>
<div class="p-6">
<p class="text-xs font-semibold text-gray-900 mb-1">Hibernation</p>
<div class="flex items-center text-sm text-gray-500">
<span class="w-2 h-2 rounded-full bg-gray-300 mr-2"></span>
                No schedules
              </div>
<p class="text-[10px] text-gray-400 mt-2">Configure to save on dev</p>
</div>
</div>
</div>
<!-- Karpenter Management Section -->
<div class="bg-white rounded-lg border border-gray-200 card-shadow overflow-hidden">
<div class="p-4 border-b border-gray-100 bg-gray-50/50">
<h3 class="section-title">Karpenter Management</h3>
</div>
<div class="p-6 flex flex-col md:flex-row md:items-center justify-between space-y-4 md:space-y-0">
<div>
<div class="flex items-center space-x-4 mb-2">
<span class="text-sm font-semibold text-gray-900">Status</span>
<span class="px-2 py-0.5 bg-gray-100 text-gray-500 text-[10px] font-medium rounded uppercase">Not Installed</span>
</div>
<p class="text-sm text-gray-500">Not installed — required to apply right-sizing optimizations</p>
</div>
<button class="bg-green-600 hover:bg-green-700 text-white px-6 py-2.5 rounded-md text-sm font-semibold flex items-center transition-colors">
<svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewbox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>
              Install Karpenter
            </button>
</div>
</div>
</section>
<!-- END: Optimization & Status -->
<!-- BEGIN: Spot Instance Analysis -->
<section data-purpose="spot-instance-analysis">
<div class="bg-white rounded-lg border border-gray-200 card-shadow overflow-hidden">
<div class="p-4 border-b border-gray-200 bg-gray-50/50 flex justify-between items-center">
<h3 class="section-title">Spot Instance Analysis</h3>
<div class="flex items-center text-[10px] text-gray-400 font-bold uppercase tracking-wider space-x-2">
<span>Available Savings:</span>
<span class="text-green-600 text-sm">6.7%</span>
</div>
</div>
<div class="overflow-x-auto">
<table class="min-w-full divide-y divide-gray-200">
<thead class="bg-gray-50">
<tr>
<th class="px-6 py-3 text-left text-[10px] font-bold text-gray-500 uppercase tracking-wider">Workloads</th>
<th class="px-6 py-3 text-center text-[10px] font-bold text-gray-500 uppercase tracking-wider">Replicas</th>
<th class="px-6 py-3 text-center text-[10px] font-bold text-gray-500 uppercase tracking-wider">Current Type</th>
<th class="px-6 py-3 text-right text-[10px] font-bold text-gray-500 uppercase tracking-wider">Recommendation</th>
</tr>
</thead>
<tbody class="bg-white divide-y divide-gray-100">
<tr class="hover:bg-gray-50">
<td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">deployment-five-6789f5648f</td>
<td class="px-6 py-4 whitespace-nowrap text-center text-sm text-gray-600">15</td>
<td class="px-6 py-4 whitespace-nowrap text-center">
<span class="text-[10px] font-bold text-slate-500 px-2 py-0.5 rounded border border-slate-200">ON DEMAND</span>
</td>
<td class="px-6 py-4 whitespace-nowrap text-right">
<span class="bg-blue-600 text-white text-[10px] font-bold px-2 py-1 rounded shadow-sm">SPOT</span>
</td>
</tr>
<tr class="hover:bg-gray-50">
<td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">deployment-four-6789f5648f</td>
<td class="px-6 py-4 whitespace-nowrap text-center text-sm text-gray-600">2</td>
<td class="px-6 py-4 whitespace-nowrap text-center">
<span class="text-[10px] font-bold text-slate-500 px-2 py-0.5 rounded border border-slate-200">ON DEMAND</span>
</td>
<td class="px-6 py-4 whitespace-nowrap text-right">
<span class="bg-blue-600 text-white text-[10px] font-bold px-2 py-1 rounded shadow-sm">SPOT</span>
</td>
</tr>
</tbody>
</table>
</div>
</div>
</section>
<!-- END: Spot Instance Analysis -->
<!-- BEGIN: Cluster configuration -->
<section class="space-y-6" data-purpose="cluster-configuration">
<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
<!-- Current Cluster Configuration -->
<div class="bg-white rounded-lg border border-gray-200 card-shadow overflow-hidden flex flex-col">
<div class="p-4 border-b border-gray-100 bg-gray-50/50">
<h3 class="section-title">Current Cluster Configuration</h3>
</div>
<div class="overflow-x-auto flex-1">
<table class="min-w-full divide-y divide-gray-100">
<thead class="bg-gray-50">
<tr>
<th class="px-4 py-2 text-left text-[10px] font-bold text-gray-400 uppercase">Qty</th>
<th class="px-4 py-2 text-left text-[10px] font-bold text-gray-400 uppercase">Instance</th>
<th class="px-4 py-2 text-right text-[10px] font-bold text-gray-400 uppercase">Hourly</th>
<th class="px-4 py-2 text-right text-[10px] font-bold text-gray-400 uppercase">Total Hourly</th>
<th class="px-4 py-2 text-right text-[10px] font-bold text-gray-400 uppercase">Total Monthly</th>
</tr>
</thead>
<tbody class="divide-y divide-gray-50 text-[11px]">
<tr class="hover:bg-gray-50/50">
<td class="px-4 py-3 font-medium text-gray-900">76 x</td>
<td class="px-4 py-3">
<div class="flex items-center space-x-2">
<svg class="w-4 h-4 text-gray-400" fill="currentColor" viewbox="0 0 24 24"><path d="M19,20H5V20H19V20M19,18H5V4H19V18M17,10H15V8H17V10M17,14H15V12H17V14M13,10H11V8H13V10M13,14H11V12H13V14M9,10H7V8H9V10M9,14H7V12H9V14Z"></path></svg>
<div class="flex flex-col">
<span class="font-bold text-gray-700">c4.4xlarge</span>
<span class="text-[9px] text-gray-400 uppercase">16 CPU, 30 GIB</span>
</div>
</div>
</td>
<td class="px-4 py-3 text-right text-gray-600">$1.00 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right text-gray-600">$76.01 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right font-medium text-gray-900">$54,555.84 <span class="text-[9px] text-gray-400">/ mo</span></td>
</tr>
<tr class="hover:bg-gray-50/50">
<td class="px-4 py-3 font-medium text-gray-900">40 x</td>
<td class="px-4 py-3">
<div class="flex items-center space-x-2">
<svg class="w-4 h-4 text-gray-400" fill="currentColor" viewbox="0 0 24 24"><path d="M19,20H5V20H19V20M19,18H5V4H19V18M17,10H15V8H17V10M17,14H15V12H17V14M13,10H11V8H13V10M13,14H11V12H13V14M9,10H7V8H9V10M9,14H7V12H9V14Z"></path></svg>
<div class="flex flex-col">
<div class="flex items-center space-x-1">
<span class="font-bold text-gray-700">r4.4xlarge</span>
<span class="bg-gray-800 text-white text-[8px] px-1 rounded">SPOT</span>
</div>
<span class="text-[9px] text-gray-400 uppercase">16 CPU, 122 GIB</span>
</div>
</div>
</td>
<td class="px-4 py-3 text-right text-gray-600">$0.55 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right text-gray-600">$24.70 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right font-medium text-gray-900">$15,788.00 <span class="text-[9px] text-gray-400">/ mo</span></td>
</tr>
<tr class="hover:bg-gray-50/50">
<td class="px-4 py-3 font-medium text-gray-900">24 x</td>
<td class="px-4 py-3">
<div class="flex items-center space-x-2">
<svg class="w-4 h-4 text-gray-400" fill="currentColor" viewbox="0 0 24 24"><path d="M19,20H5V20H19V20M19,18H5V4H19V18M17,10H15V8H17V10M17,14H15V12H17V14M13,10H11V8H13V10M13,14H11V12H13V14M9,10H7V8H9V10M9,14H7V12H9V14Z"></path></svg>
<div class="flex flex-col">
<span class="font-bold text-gray-700">m4.16xlarge</span>
<span class="text-[9px] text-gray-400 uppercase">64 CPU, 256 GIB</span>
</div>
</div>
</td>
<td class="px-4 py-3 text-right text-gray-600">$3.74 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right text-gray-600">$89.76 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right font-medium text-gray-900">$64,696.32 <span class="text-[9px] text-gray-400">/ mo</span></td>
</tr>
<tr class="hover:bg-gray-50/50">
<td class="px-4 py-3 font-medium text-gray-900">3 x</td>
<td class="px-4 py-3">
<div class="flex items-center space-x-2">
<svg class="w-4 h-4 text-gray-400" fill="currentColor" viewbox="0 0 24 24"><path d="M19,20H5V20H19V20M19,18H5V4H19V18M17,10H15V8H17V10M17,14H15V12H17V14M13,10H11V8H13V10M13,14H11V12H13V14M9,10H7V8H9V10M9,14H7V12H9V14Z"></path></svg>
<div class="flex flex-col">
<span class="font-bold text-gray-700">m4.2xlarge</span>
<span class="text-[9px] text-gray-400 uppercase">8 CPU, 32 GIB</span>
</div>
</div>
</td>
<td class="px-4 py-3 text-right text-gray-600">$0.55 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right text-gray-600">$1.60 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right font-medium text-gray-900">$1,010.88 <span class="text-[9px] text-gray-400">/ mo</span></td>
</tr>
</tbody>
</table>
</div>
<div class="p-4 bg-blue-50/50 border-t border-blue-100 flex justify-between items-center">
<div>
<p class="section-title text-[10px] uppercase mb-1">Current cluster compute cost:</p>
<div class="flex space-x-3">
<span class="text-[9px] text-gray-500 font-semibold uppercase">233 Instances</span>
<span class="text-[9px] text-gray-500 font-semibold uppercase">8216 CPU</span>
<span class="text-[9px] text-gray-500 font-semibold uppercase">50000 GiB</span>
<span class="text-[9px] text-gray-500 font-semibold uppercase">90 GPU</span>
</div>
</div>
<div class="text-right">
<span class="text-xl font-bold text-slate-800">$1,787,371.20</span>
<span class="text-xs text-gray-400 ml-1">/mo</span>
</div>
</div>
</div>
<!-- Optimized Cluster Configuration -->
<div class="bg-white rounded-lg border border-gray-200 card-shadow overflow-hidden flex flex-col">
<div class="p-4 border-b border-gray-100 bg-gray-50/50">
<h3 class="section-title">Optimized Cluster Configuration</h3>
</div>
<div class="overflow-x-auto flex-1">
<table class="min-w-full divide-y divide-gray-100">
<thead class="bg-gray-50">
<tr>
<th class="px-4 py-2 text-left text-[10px] font-bold text-gray-400 uppercase">Qty</th>
<th class="px-4 py-2 text-left text-[10px] font-bold text-gray-400 uppercase">Instance</th>
<th class="px-4 py-2 text-right text-[10px] font-bold text-gray-400 uppercase">Hourly</th>
<th class="px-4 py-2 text-right text-[10px] font-bold text-gray-400 uppercase">Total Hourly</th>
<th class="px-4 py-2 text-right text-[10px] font-bold text-gray-400 uppercase">Total Monthly</th>
</tr>
</thead>
<tbody class="divide-y divide-gray-50 text-[11px]">
<tr class="hover:bg-gray-50/50">
<td class="px-4 py-3 font-medium text-gray-900">10 x</td>
<td class="px-4 py-3">
<div class="flex items-center space-x-2">
<svg class="w-4 h-4 text-gray-400" fill="currentColor" viewbox="0 0 24 24"><path d="M19,20H5V20H19V20M19,18H5V4H19V18M17,10H15V8H17V10M17,14H15V12H17V14M13,10H11V8H13V10M13,14H11V12H13V14M9,10H7V8H9V10M9,14H7V12H9V14Z"></path></svg>
<div class="flex flex-col">
<span class="font-bold text-gray-700">a1.2xlarge</span>
<span class="text-[9px] text-gray-400 uppercase">32 CPU, 256 GIB</span>
</div>
</div>
</td>
<td class="px-4 py-3 text-right text-gray-600">$2.02 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right text-gray-600">$20.20 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right font-medium text-gray-900">$14,515.20 <span class="text-[9px] text-gray-400">/ mo</span></td>
</tr>
<tr class="hover:bg-gray-50/50">
<td class="px-4 py-3 font-medium text-gray-900">12 x</td>
<td class="px-4 py-3">
<div class="flex items-center space-x-2">
<svg class="w-4 h-4 text-gray-400" fill="currentColor" viewbox="0 0 24 24"><path d="M19,20H5V20H19V20M19,18H5V4H19V18M17,10H15V8H17V10M17,14H15V12H17V14M13,10H11V8H13V10M13,14H11V12H13V14M9,10H7V8H9V10M9,14H7V12H9V14Z"></path></svg>
<div class="flex flex-col">
<span class="font-bold text-gray-700">m5a.8xlarge</span>
<span class="text-[9px] text-gray-400 uppercase">32 CPU, 128 GIB</span>
</div>
</div>
</td>
<td class="px-4 py-3 text-right text-gray-600">$1.62 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right text-gray-600">$19.44 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right font-medium text-gray-900">$13,962.24 <span class="text-[9px] text-gray-400">/ mo</span></td>
</tr>
<tr class="hover:bg-gray-50/50">
<td class="px-4 py-3 font-medium text-gray-900">2 x</td>
<td class="px-4 py-3">
<div class="flex items-center space-x-2">
<svg class="w-4 h-4 text-gray-400" fill="currentColor" viewbox="0 0 24 24"><path d="M19,20H5V20H19V20M19,18H5V4H19V18M17,10H15V8H17V10M17,14H15V12H17V14M13,10H11V8H13V10M13,14H11V12H13V14M9,10H7V8H9V10M9,14H7V12H9V14Z"></path></svg>
<div class="flex flex-col">
<div class="flex items-center space-x-1">
<span class="font-bold text-gray-700">m5a.1xlarge2</span>
<span class="bg-gray-800 text-white text-[8px] px-1 rounded">SPOT</span>
</div>
<span class="text-[9px] text-gray-400 uppercase">48 CPU, 192 GIB</span>
</div>
</div>
</td>
<td class="px-4 py-3 text-right text-gray-600">$0.78 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right text-gray-600">$1.56 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right font-medium text-gray-900">$1,116.72 <span class="text-[9px] text-gray-400">/ mo</span></td>
</tr>
<tr class="hover:bg-gray-50/50">
<td class="px-4 py-3 font-medium text-gray-900">7 x</td>
<td class="px-4 py-3">
<div class="flex items-center space-x-2">
<svg class="w-4 h-4 text-gray-400" fill="currentColor" viewbox="0 0 24 24"><path d="M19,20H5V20H19V20M19,18H5V4H19V18M17,10H15V8H17V10M17,14H15V12H17V14M13,10H11V8H13V10M13,14H11V12H13V14M9,10H7V8H9V10M9,14H7V12H9V14Z"></path></svg>
<div class="flex flex-col">
<div class="flex items-center space-x-1">
<span class="font-bold text-gray-700">r5a.12xlarge</span>
<span class="bg-gray-800 text-white text-[8px] px-1 rounded">SPOT</span>
</div>
<span class="text-[9px] text-gray-400 uppercase">48 CPU, 384 GIB</span>
</div>
</div>
</td>
<td class="px-4 py-3 text-right text-gray-600">$0.81 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right text-gray-600">$5.67 <span class="text-[9px] text-gray-400">/ h</span></td>
<td class="px-4 py-3 text-right font-medium text-gray-900">$4,094.00 <span class="text-[9px] text-gray-400">/ mo</span></td>
</tr>
</tbody>
</table>
</div>
<div class="p-4 bg-green-50/50 border-t border-green-100 flex justify-between items-center">
<div>
<p class="section-title text-[10px] uppercase mb-1">Optimized cluster compute cost:</p>
<div class="flex space-x-3">
<span class="text-[9px] text-gray-500 font-semibold uppercase">115 Instances</span>
<span class="text-[9px] text-gray-500 font-semibold uppercase">6160 CPU</span>
<span class="text-[9px] text-gray-500 font-semibold uppercase">45476 GiB</span>
<span class="text-[9px] text-gray-500 font-semibold uppercase">84 GPU</span>
</div>
</div>
<div class="text-right">
<span class="text-xl font-bold text-green-600">$768,254.26</span>
<span class="text-xs text-gray-400 ml-1">/mo</span>
</div>
</div>
</div>
</div>
</section>
<!-- END: Cluster configuration -->
<!-- BEGIN: Cluster cost trends -->
<section data-purpose="cluster-cost-trends">
<div class="bg-white rounded-lg border border-gray-200 card-shadow p-6">
<div class="flex items-center justify-between mb-8">
<h3 class="section-title">Cluster Cost Trends</h3>
<div class="flex bg-gray-100 rounded-md p-1">
<button class="px-4 py-1.5 bg-white rounded shadow-sm text-xs font-semibold text-blue-600 border border-gray-100">24 hours</button>
<button class="px-4 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-700">7 days</button>
</div>
</div>
<div class="grid grid-cols-1 lg:grid-cols-4 gap-8">
<div class="space-y-8 pr-6 border-r border-gray-50">
<div>
<p class="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1">Current Average Cost</p>
<p class="text-2xl font-bold text-slate-800">$1,787,371.20 <span class="text-xs text-gray-400">/mo</span></p>
<div class="w-full h-1 bg-blue-100 rounded-full mt-2">
<div class="w-full h-full bg-blue-500 rounded-full"></div>
</div>
</div>
<div>
<p class="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1">Optimal Average Cost</p>
<p class="text-2xl font-bold text-green-600">$768,254.26 <span class="text-xs text-gray-400">/mo</span></p>
<div class="w-full h-1 bg-green-100 rounded-full mt-2">
<div class="w-3/5 h-full bg-green-500 rounded-full"></div>
</div>
</div>
<div class="pt-6 border-t border-gray-100">
<p class="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1">Available Savings</p>
<p class="text-4xl font-extrabold text-blue-600 tracking-tight">57.02%</p>
</div>
</div>
<div class="lg:col-span-3 h-80 relative" data-purpose="cost-chart-container">
<!-- Chart SVG Simulation -->
<div class="absolute inset-0 flex flex-col justify-between">
<div class="flex justify-between text-[9px] text-gray-400 border-b border-gray-50 pb-1">
<span>$ 3000</span>
<span class="flex items-center">Hourly cost <svg class="w-3 h-3 ml-1" fill="none" stroke="currentColor" viewbox="0 0 24 24"><path d="M19 9l-7 7-7-7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg></span>
</div>
<div class="flex-1 relative">
<svg class="w-full h-full" preserveaspectratio="none" viewbox="0 0 800 240">
<!-- Area fills -->
<path d="M0,160 C100,80 200,120 300,100 C400,80 500,140 600,120 C700,100 800,140 L800,240 L0,240 Z" fill="rgba(219, 234, 254, 0.4)"></path>
<path d="M0,200 C100,180 200,210 300,190 C400,170 500,220 600,200 C700,180 800,220 L800,240 L0,240 Z" fill="rgba(187, 247, 208, 0.4)"></path>
<!-- Grid lines -->
<line class="stroke-gray-100" stroke-dasharray="4" x1="0" x2="800" y1="60" y2="60"></line>
<line class="stroke-gray-100" stroke-dasharray="4" x1="0" x2="800" y1="120" y2="120"></line>
<line class="stroke-gray-100" stroke-dasharray="4" x1="0" x2="800" y1="180" y2="180"></line>
<!-- Trend lines -->
<path d="M0,160 C100,80 200,120 300,100 C400,80 500,140 600,120 C700,100 800,140" fill="none" stroke="#3b82f6" stroke-width="2"></path>
<path d="M0,200 C100,180 200,210 300,190 C400,170 500,220 600,200 C700,180 800,220" fill="none" stroke="#22c55e" stroke-width="2"></path>
<!-- Vertical Guide -->
<line class="stroke-slate-300" stroke-dasharray="4" x1="450" x2="450" y1="0" y2="240"></line>
</svg>
<!-- Tooltip Overlay -->
<div class="absolute top-2 left-[56%] bg-white rounded-lg shadow-xl border border-gray-100 w-64 p-4 z-20 pointer-events-none">
<div class="flex justify-between items-center border-b border-gray-50 pb-2 mb-3">
<span class="text-[11px] font-bold text-gray-400">AUG 15</span>
<span class="text-[11px] font-medium text-gray-500">2:00-3:00 AM</span>
</div>
<div class="space-y-3">
<div class="flex justify-between items-center">
<div class="flex items-center">
<span class="w-1.5 h-1.5 rounded-full bg-blue-500 mr-2"></span>
<span class="text-[10px] font-bold text-gray-400 uppercase tracking-tight">Current:</span>
</div>
<span class="text-xs font-bold text-slate-700">$2768.02 <span class="text-[9px] font-normal text-gray-400">/ h</span></span>
</div>
<div class="flex justify-between items-center">
<div class="flex items-center">
<span class="w-1.5 h-1.5 rounded-full bg-green-500 mr-2"></span>
<span class="text-[10px] font-bold text-gray-400 uppercase tracking-tight">Optimal:</span>
</div>
<span class="text-xs font-bold text-green-600">$905.77 <span class="text-[9px] font-normal text-gray-400">/ h</span></span>
</div>
<div class="pt-2 border-t border-gray-50 flex justify-between items-center">
<span class="text-[10px] font-bold text-blue-600 uppercase tracking-tight">Available Savings:</span>
<span class="text-xs font-black text-blue-600">67.27%</span>
</div>
</div>
</div>
</div>
<div class="flex justify-between text-[9px] text-gray-400 pt-2 border-t border-gray-50">
<span>5 PM</span><span>6 PM</span><span>7 PM</span><span>8 PM</span><span>9 PM</span><span>10 PM</span><span>11 PM</span><span>12 AM</span><span>1 AM</span><span>2 AM</span><span>3 AM</span>
</div>
</div>
</div>
<div class="mt-8 pt-6 border-t border-gray-50 flex items-center justify-center space-x-12">
<div class="flex items-center text-[10px] font-bold text-gray-500 uppercase tracking-wider">
<span class="w-3 h-1 bg-blue-500 rounded-sm mr-2"></span> Current cluster cost
                </div>
<div class="flex items-center text-[10px] font-bold text-gray-500 uppercase tracking-wider">
<span class="w-3 h-1 bg-green-500 rounded-sm mr-2"></span> Optimal cluster cost
                </div>
<div class="flex items-center text-[10px] font-bold text-gray-500 uppercase tracking-wider">
<span class="w-3 h-1 bg-blue-100 border border-blue-200 rounded-sm mr-2"></span> Total savings potential
                </div>
</div>
</div>
</div></section>
<!-- END: Cluster cost trends -->
</div>
</main>
</body></html>