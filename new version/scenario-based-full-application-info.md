In client side we have 

1. Dashboard-
Purpose
The Dashboard provides a real-time operational overview of a selected cluster, combining cluster health, capacity, autoscaler status, workload distribution, and hibernation visibility in a single view.
This is the default landing page after selecting a cluster
Dashboard Layout
The dashboard is divided into four logical zones:
Cluster Details (left)
Nodes & Workloads Summary (top center)
Autoscaler & Hibernation Controls (middle)
Resource Utilization (bottom)
1. Cluster Details Panel

Location Top-left section of the dashboard.

Fields Displayed
Cluster Status
Connected / Disconnected / Read-only
Status badge with icon
Kubernetes Provider
Cloud provider + Kubernetes service (e.g., GKE)
Region
Primary cluster region
Kubernetes Version
Connected
Relative time since last successful agent heartbeat
Cluster ID
Copy-to-clipboard action
Behavior
Status updates in near real-time
If disconnected, dashboard becomes read-only
Clicking cluster name navigates back to Cluster List
2. Nodes Summary Panel

Location
Top-right section of the dashboard.
Metrics Displayed
Nodes Overview
Total Nodes
Split by:
On-Demand
Spot
Fallback
Node Ownership Breakdown
Table with:
Managed by
Platform-managed nodes
Cloud-managed (native) nodes
Count
CPU utilization percentage
Behavior
Reflects autoscaler decisions
Shows coexistence of platform and cloud nodes
Helps users understand who controls what

3. Workloads Summary
Location
Below Nodes Summary.
Metrics
Total Pods
Scheduled Pods
Behavior
If scheduled < total pods:
Indicates capacity or scheduling issue
Used as a quick health signal for the cluster
4. Autoscaler Policies Summary
Section Title
Autoscaler Policies
Display
Shows count of enabled autoscaler policies
Example: 2 / 3 enabled
Interaction
Clicking opens Autoscaler Settings
Acts as a status indicator, not configuration panel
5. Hibernation Schedules Summary
Section Title
Hibernation Schedules
Display
Shows number of active schedules
Example: 1
Interaction
Clicking opens Cluster Hibernation page
If no schedules exist:
Shows empty state
Prompts user to create a schedule
Purpose
Makes time-based cost controls visible directly on dashboard
Prevents “hidden automation” surprises
6. Resource Utilization (Visual)
Location
Bottom section of the dashboard.
Resource Donut Charts
CPU
Total CPU provisioned
Used vs unused capacity
Visual indicator of over/under-provisioning
Memory
Total memory provisioned
Used vs unused capacity
Storage (if available)
Allocated vs consumed storage
Behavior
Charts are informational, not interactive
Used to visually confirm optimization impact
Updates dynamically as nodes are added/removed
Dashboard Design Principles (Implicit)
Read-heavy, action-light
No destructive actions directly on dashboard
Operational confidence
Everything needed to answer: “Is my cluster healthy and optimized?”
Fast navigation
Each section links to its detailed configuration page
Safe by default
No hidden automation without visibility
What the Dashboard Does NOT Do (By Design)
No configuration editing
No autoscaler tuning
No workload mutation
No security remediation
Those actions are intentionally routed to their dedicated sections.
Summary
The Dashboard acts as:
A single source of truth for cluster state
A visibility layer for automation
A navigation hub to deeper controls
A trust-building surface for users
2. Cluster List-
Purpose-This section displays all Kubernetes clusters that our read-only agent is monitoring and provides controls to connect, disconnect, or manage clusters.
Cluster Summary Overview:
At the top of the Cluster List page, a summary section displays aggregated metrics across all connected clusters, including total compute cost (monthly), total number of nodes (split by Spot, Fallback, and On-Demand), total CPU, and total memory. This overview provides a quick, organization-level snapshot before drilling down into individual cluster details.
Canonical Cluster States
State
Description
PENDING
Cluster created in platform, agent not yet verified
CONNECTING
Agent install script executed, verification in progress
CONNECTED
Agent verified, cluster fully operational
READ_ONLY
Metrics available, optimization disabled
PARTIALLY_CONNECTED
Agent heartbeat present, incomplete permissions
DISCONNECTED
Agent unreachable or intentionally disconnected
ERROR
Terminal error during onboarding
REMOVING
Cluster removal in progress
REMOVED
Cluster fully deleted

State Definitions & Transitions
1. PENDING
Description
Cluster record exists in backend
Agent has not yet connected
Created immediately after user clicks Connect Cluster
Entry Conditions
User initiates cluster connection
Cluster name & provider registered
Allowed Transitions
PENDING → CONNECTING
PENDING → REMOVED
UI Behavior
Cluster visible in list
Status: Pending
Actions:
Remove cluster
2. CONNECTING
Description
Agent install script executed
Backend awaiting:
Agent registration
Heartbeat
Permission validation
Entry Conditions
User clicks “I ran the script”
Backend Checks
Agent pod exists
Initial heartbeat received
API connectivity validated
Permission scope verified
Allowed Transitions
CONNECTING → CONNECTED
CONNECTING → PARTIALLY_CONNECTED
CONNECTING → ERROR
UI Behavior
Status: Connecting
Spinner indicator
No destructive actions allowed
3. CONNECTED
Description
Agent fully functional
All required permissions validated
Metrics, cost data, and optimization enabled
Entry Conditions
Successful verification of:
Heartbeat
Metrics ingestion
Required RBAC permissions
Allowed Transitions
CONNECTED → READ_ONLY
CONNECTED → DISCONNECTED
CONNECTED → PARTIALLY_CONNECTED
CONNECTED → REMOVING
UI Behavior
Status: Connected
All features enabled
Actions:
Adjust costs
Disconnect cluster
Remove cluster
4. READ_ONLY
Description
Agent connected
Optimization permissions disabled or revoked
Monitoring remains active
Entry Conditions
User disables optimization
Permission downgrade detected
Allowed Transitions
READ_ONLY → CONNECTED
READ_ONLY → DISCONNECTED
READ_ONLY → REMOVING
UI Behavior
Status badge: Read-only
Metrics visible
Optimization actions disabled
Action:
Enable optimization
5. PARTIALLY_CONNECTED (Error-Recoverable State)
Description
Agent heartbeat present
One or more required capabilities missing
Common Causes
Missing cloud permissions
Cost API access denied
Metrics server unreachable
Node-level RBAC missing
Entry Conditions
Partial verification success during CONNECTING or CONNECTED
Allowed Transitions
PARTIALLY_CONNECTED → CONNECTED
PARTIALLY_CONNECTED → READ_ONLY
PARTIALLY_CONNECTED → DISCONNECTED
PARTIALLY_CONNECTED → ERROR
UI Behavior
Status: Degraded / Partial
Warning banner displayed
Feature availability reduced
Action:
View error details
Retry verification
Reconnect cluster
6. ERROR (Terminal Onboarding Failure)
Description
Agent installation or verification failed
Cluster not usable
Common Causes
Script failed to execute
Agent pod crash-looping
Invalid cluster credentials
Network egress blocked
Entry Conditions
Hard failure during CONNECTING
Allowed Transitions
ERROR → CONNECTING (retry)
ERROR → REMOVED
UI Behavior
Status: Error
Error message displayed
Copyable error logs
Actions:
Retry connection
Remove cluster
7. DISCONNECTED
Description
Agent intentionally removed or unreachable
No live data ingestion
Entry Conditions
User disconnects cluster
Heartbeat timeout exceeded
Allowed Transitions
DISCONNECTED → CONNECTING
DISCONNECTED → REMOVED
UI Behavior
Status: Disconnected
Historical data visible
Actions:
Reconnect cluster
Remove cluster
8. REMOVING
Description
Cluster deletion in progress
Platform-managed resources being cleaned up
Entry Conditions
User confirms removal
Disconnect with “delete nodes” selected
Allowed Transitions
REMOVING → REMOVED
UI Behavior
Status: Removing
Actions disabled
Progress indicator
9. REMOVED
Description
Cluster fully deleted
No backend records remain
Entry Conditions
Successful completion of removal process
UI Behavior
Cluster removed from list
No recovery possible
Error Handling & Recovery Model
Retry Logic
Agent heartbeat rechecked periodically
Manual retry available in UI
Automatic recovery for transient failures
Timeouts
CONNECTING timeout → ERROR
Heartbeat timeout → DISCONNECTED
Audit Logging
All transitions generate audit events:
Previous state
New state
Trigger (user / system)
Timestamp
Failure reason (if any)
Why This Model Works
Prevents undefined states
Supports safe retries
Allows partial functionality
Enables clear UI behavior mapping
Scales to multi-provider support
Summary
This lifecycle model ensures:
Clear separation of user intent vs system health
Safe onboarding and offboarding
Graceful degradation instead of hard failures
Predictable UI behavior


Disconnect Cluster Flow (Pop-up Modal)
Popup Title
Disconnect your cluster
Popup Description / Warning Text
This action will remove all platform-managed resources managing your cluster.
The platform-created cloud user cannot be deleted automatically and must be removed manually from the cloud provider IAM.
A “Full list of resources” link is provided for reference.
Confirmation Section
Instruction text:
Please confirm that you want to disconnect from the platform by entering the cluster name below.
Input field:
Cluster name must be typed exactly (text validation required)
Paste support enabled
Optional Destructive Action
Checkbox (enabled by default):
Delete all platform-created nodes
Warning badge displayed inline:
Might cause downtime
Helper text:
All platform-created nodes will be drained and deleted.
Depending on application configuration, this action may cause downtime.
Footer Actions
Cancel (secondary action, closes modal)
Disconnect (primary destructive action, disabled until cluster name matches)



 
3.Optimization
Purpose
The Optimization section is the central place where users define how the platform should optimize costs and resources for a cluster.
It exposes policy-driven controls that determine what optimizations are allowed, how aggressively they are applied, and what savings can be achieved.
This section does not directly change infrastructure on its own; instead, it configures the optimization behavior used by features such as Available Savings, Rebalancer, and Autoscaler.
Workload Optimization Preferences

Workload Rightsizing
Toggle
Enable / Disable workload rightsizing
Description
Automatically applies CPU and memory request recommendations based on actual workload usage.
Uses historical utilization data to prevent over-provisioning while maintaining workload stability.
Metrics Displayed
Current efficiency (%)
Represents how efficiently allocated resources are being used.
Waste
Displays wasted CPU and memory (e.g., unused requests).
$ Saved by rightsizing
Actual cost savings already achieved.
Additional savings (%)
Potential additional savings if remaining recommendations are applied.
View Action
Opens the Workloads Efficiency report for workload-level details.
Behavior
When enabled:
Rightsizing recommendations are applied automatically.
When disabled:
Recommendations remain visible but are not enforced.
Configuration Preferences
Use Spot Instances
Toggle
Enable / Disable Spot instance usage
Description
Enables the platform to recommend and provision Spot instances to reduce compute costs.
Options
All workloads
All workloads are considered eligible for Spot, unless explicitly restricted.
Spot-friendly workloads
Only workloads marked as interruption-tolerant are considered.
Metrics Displayed
Workloads to run on Spot
Shows count and percentage of workloads eligible for Spot (e.g., 12 / 12, 100%).
Additional actions
Indicates how many workloads need configuration changes (e.g., tolerations) to become Spot-friendly.
Available savings (%)
Estimated savings achievable through Spot adoption.
View Action
Opens detailed Spot eligibility and recommendations view.
ARM Support
Toggle
Enable / Disable ARM-based nodes
Description
Allows the platform to include ARM-based instances in the optimized cluster configuration to improve price-performance.
Controls
Slider to define percentage of CPUs to run on ARM
Range: 0% to 100%
Metrics Displayed
Available savings (%)
Estimated savings achievable through ARM migration.
Behavior
Gradually migrates workloads to ARM nodes based on the configured percentage.
Supports mixed-architecture clusters (ARM + x86).
Optimization Behavior (System-Level)
All optimization settings are cluster-scoped.
Changes here affect:
Available Savings calculations
Rebalance decisions
Node replacement strategies
No immediate infrastructure changes occur unless:
Rebalance is triggered
Autoscaler actions are enabled
Design Intent
Shift optimization from manual tuning to policy-based automation
Allow users to:
Start conservatively
Gradually increase optimization scope
Ensure transparency by always showing:
Current impact
Achieved savings
Remaining potential
Summary
The Optimization section acts as:
A policy configuration layer
A safety boundary for automation
A savings potential indicator
It defines what the platform is allowed to optimize, while execution happens through controlled workflows like Available Savings and Rebalancer.

4.Cost Monitoring
Purpose
The Cost Monitoring section provides continuous visibility into infrastructure spend across clusters, nodes, and workloads.
It enables users to understand where money is being spent, detect inefficiencies early, and track the impact of optimization actions over time.
This section is observational and analytical by design—it does not make changes, but it informs decisions taken in Optimization and Available Savings.
Cost Monitoring Dashboard
Overview Metrics
At the top of the page, high-level cost indicators are displayed for the selected scope (organization or cluster):
Total Compute Cost
Monthly aggregated cost
Includes all active nodes and workloads
Cost Trend Indicator
Percentage increase or decrease compared to the previous period
Time Range Selector
Daily / Weekly / Monthly views
Cost Breakdown Views
Cost by Cluster
Displays cost distribution across all connected clusters
Helps identify:
Most expensive clusters
Underutilized clusters
Supports sorting by total cost
Cost by Node / Instance Type
Shows spend per node group or instance type
Includes:
Instance family
Pricing model (On-Demand / Spot / Fallback)
Hourly and monthly cost
Useful for identifying:
Expensive instance types
Inefficient node sizing
Cost by Workload
Attributes infrastructure cost to individual workloads (deployments, services)
Helps teams understand:
Which applications drive cost
Cost per workload over time
Enables accountability at the application level
Resource Utilization vs Cost
CPU & Memory Cost Correlation
Visual comparison between:
Allocated resources
Actual utilization
Associated cost
Highlights:
Over-provisioned workloads
Idle but expensive resources
Filters & Controls
Filters
Cluster
Namespace
Workload
Resource type (CPU / Memory)
Pricing model (Spot / On-Demand)
Time range
Search
Keyword-based search for clusters, workloads, or nodes
Historical Analysis
Time-Series Cost Trends
Line and bar charts showing cost evolution
Supports:
Day-over-day
Month-over-month comparisons
Used to:
Track optimization impact
Detect sudden cost spikes
Integration with Optimization
Cost Monitoring feeds data into:
Available Savings
Workload Rightsizing
Rebalance decisions
Any optimization action taken is later reflected here as:
Reduced spend
Improved cost efficiency
Read-Only by Design
No destructive or mutating actions are available
Ensures:
Safe access for finance and management users
Separation between visibility and control
Design Intent
Provide financial transparency without operational risk
Enable collaboration between:
Engineering
DevOps
Finance (FinOps)
Make cost data:
Actionable
Traceable
Easy to correlate with infrastructure changes
Summary
The Cost Monitoring section acts as:
A single source of truth for spend
A diagnostic tool for inefficiencies
A feedback loop for optimization efforts
It bridges the gap between raw cloud billing data and intelligent optimization workflows.



4.Available Savings

Purpose - The Available Savings section provides a centralized cost-optimization control plane for a selected cluster. It shows current compute spend, optimization progress, actionable savings opportunities, and safe automation controls to move the cluster toward its most cost-efficient configuration.
This section answers one core question for the user:
“How much am I spending today, how much can I save, and what action should I take next?”
Top Summary Panel
Current Compute Cost
Displays the current monthly compute cost for the selected cluster.
This value reflects:
Active nodes
Instance pricing
CPU and memory allocations
Progress to Optimal Setup
A percentage indicator (e.g., 82.9%) showing how close the cluster is to its optimal cost configuration.
Visual progress bar:
Left side = current state
Right side = optimal state
Serves as a continuous optimization score, not a static metric.

Rebalance Recommendation Section
Section Title
Rebalance to reach optimal configuration
Description
Explains that the platform can automatically:
Replace suboptimal nodes
Provision more cost-efficient alternatives
Migrate workloads safely
Primary Action
Rebalance button
Initiates automated infrastructure optimization
Performs node replacement and workload migration
Aims to reach the optimal configuration shown above
This action is guided and reversible, not destructive by default.

Workload Optimization Preferences
This section defines policy-level optimization controls that influence how savings are achieved.

Workload Rightsizing
Toggle
ON / OFF
Description
Automatically adjusts CPU and memory requests based on actual workload usage.
Prevents over-provisioning while maintaining workload stability.
Metrics Displayed
Current efficiency percentage
Wasted CPU and memory
Dollar amount saved by rightsizing
Additional savings potential (percentage)
Behavior
When enabled:
Rightsizing recommendations are automatically applied
When disabled:
Recommendations remain visible but are not enforced
Configuration Comparison
Purpose
Provides a transparent, side-by-side comparison between the current cluster configuration and the optimized configuration.

Current Cluster Configuration
Shows:
Instance type(s)
CPU and memory allocation
Hourly cost
Total monthly compute cost
This represents the existing state of the cluster.

Optimized Cluster Configuration
Shows:
Proposed instance types
Optimized CPU and memory allocation
Reduced hourly cost
Reduced total monthly compute cost (highlighted)
This represents the post-optimization state if recommended actions are applied.

Highlighted Outcome
Optimized monthly compute cost is visually emphasized
Makes savings immediately understandable and confidence-building
Allows users to see exactly what will change before taking action
Navigation & Context
The Available Savings page is:
Accessible from the left navigation
Also reachable via “Adjust costs” from the Cluster List
All data shown is scoped to the selected cluster
Actions taken here are reflected in:
Dashboard
Cost monitoring
Audit log
Design Intent (Implicit)
Focused on outcomes, not configuration complexity
Encourages safe automation over manual tuning
Makes cost optimization:
Measurable
Incremental
Transparent
Summary
The Available Savings section acts as:
A cost health report
An optimization progress tracker
A decision surface for automation
A trust layer that shows impact before execution
It is the primary interface where users move from cost visibility to cost action.

6.Security & Compliance
Overview
The Security & Compliance feature provides automated security assessment, runtime threat detection, and compliance reporting for Kubernetes clusters connected to CAST AI. It continuously evaluates cluster posture against industry standards (e.g., CIS Benchmarks), identifies vulnerabilities, and highlights configuration issues that could increase security risk. 
Primary UI Elements
Security Dashboard: Summary of overall security posture with key metrics such as compliance score, vulnerabilities count, and non-compliant resources.
Compliance Report: Lists security best practice violations with severity levels and remediation guidance. Cast AI
Vulnerabilities Report: Shows container image vulnerabilities across clusters with severity and affected resources. Cast AI
Attack Paths: Visualization of possible exploit vectors through misconfigurations or exposed services. Cast AI
Node OS Update Monitoring: Tracks outdated node OS images and schedules updates to improve security and compliance posture. Cast AI
Agent & Controls
Kvisor Security Agent
Installed in the cluster to enable enhanced security features.
Performs container image scanning, configuration assessment, and runtime anomaly detection.
Status Indicators
Ready to enable
Enabled
Activating
Update needed
These indicators show current security feature state and installation progress. Cast AI
Configuration & Customization
Users can enable or disable specific security controls (e.g., vulnerability scanning, compliance scanning, runtime detection) per cluster. Cast AI
Filtering in reports allows narrowing findings by severity, resource type, cluster, and namespace. Cast AI
7.Autoscaler
Overview
The Autoscaler feature manages cluster capacity automatically to match workload demand and reduce costs by scaling node counts up or down based on actual utilization. Cast AI
Key UI Settings
Unscheduled Pods Policy
Automatically adds nodes when unschedulable pods are detected.
Node Deletion Policy
Removes idle nodes after a configurable TTL.
Evictor Mode
Continuously compacts pods into fewer nodes to maximize utilization and free up empty nodes.
Optional Aggressive Mode considers applications with single replicas.
Scoped Mode (API/Terraform Only)
Limits autoscaling activity to nodes managed by CAST AI (Pods must tolerate specific taints). Cast AI
Behavior & Policies
Policies can be toggled on/off using switches in the Autoscaler settings UI.
Advanced policies include CPU limits, minimum/maximum resource bounds, and selective scaling constraints. Cast AI
8.Node Templates
Overview
Node Templates define how new nodes should be provisioned by the autoscaler — essentially acting as virtual autoscaler profiles separate from cluster default settings. They determine what kind of nodes CAST AI will add for scaling operations. Cast AI
Primary Concepts
Template Name & Status Switch:
Each template has a descriptive name and an enable/disable switch in UI.
Node Selection Properties:
Custom taints and labels can be applied so workloads with matching scheduling constraints land on templated nodes. Cast AI
Linked Node Configuration:
Each template can be associated with a Node Configuration that defines specifics like disk size, image version, network subnets, etc. Cast AI
Resource Offering & Architecture:
Templates can target different instance types (On-Demand, Spot) and CPU architectures (x86, ARM). Cast AI
Generated Templates & Management
UI provides a “Generate Templates” option to auto-create common templates for the cluster based on current utilization.
Templates are added in a disabled state so operators can review before enabling. Cast AI



9.Cluster Hibernation
Purpose
The Cluster Hibernation feature enables organizations to automatically pause and resume Kubernetes clusters based on predefined schedules, helping reduce infrastructure costs during periods of inactivity such as nights, weekends, or non-working hours.
This feature is especially useful for development, testing, staging, and non-production clusters that do not require 24/7 availability.

Cluster Hibernation Overview
When enabled, Cluster Hibernation allows users to:
Schedule when clusters should hibernate (scale down)
Automatically resume clusters at specified times
Reduce cloud spend without manual intervention
Maintain predictable cluster availability aligned with business hours
Hibernation Schedules View
Main Page Elements
Create Schedule Section
Primary CTA:
Add hibernation schedule
Opens the schedule creation flow
Quickstart Option:
Quickstart with workday schedule
Pre-configured weekday (business hours) hibernation template
Schedule List Panel
Displays all configured hibernation schedules for the selected cluster.
Each schedule includes:
Schedule Name
Enable / Disable Toggle
Allows temporarily turning schedules on or off without deleting them
Status Indicator
Active / Disabled

Schedule Configuration (Conceptual)
A hibernation schedule defines:
Active Periods
Time ranges when the cluster should remain running
Hibernate Periods
Time ranges when the cluster should be scaled down
Days of the Week
Weekdays, weekends, or custom day selections
Timezone Awareness
Schedules respect the configured cluster or organization timezone
Cluster Behavior During Hibernation
When a cluster enters hibernation:
Worker nodes are scaled down or removed
Compute resources are released
Cluster control plane remains reachable (depending on provider)
No workloads are scheduled or running
When resuming:
Nodes are re-provisioned automatically
Workloads resume normal scheduling
Autoscaler policies re-apply
Cost Optimization Impact
Visual Cost Insight
The UI highlights:
Total cluster cost (monthly)
Estimated savings percentage
Before vs after cost trend
Clear indication of cost reduction during hibernation periods
This helps users directly correlate hibernation schedules with cost savings.
Safety & Usage Guidelines
Recommended primarily for non-production clusters
Production clusters should use hibernation only if:
Workloads are stateless
Downtime is acceptable
Users should ensure:
No critical jobs are scheduled during hibernation windows
External dependencies tolerate cluster downtime
Integration with Other Features
Cluster Hibernation works in coordination with:
Autoscaler
Autoscaler resumes normal operation after wake-up
Cost Monitoring
Cost reductions are reflected in cost dashboards
Available Savings
Hibernation contributes to overall savings metrics
Audit Log
All hibernation and resume events are recorded
Design Intent
The Cluster Hibernation feature is designed to:
Eliminate manual cluster shutdown/startup workflows
Enforce cost discipline automatically
Align infrastructure availability with real usage patterns
Provide predictable and transparent cost savings
Summary
Cluster Hibernation is a scheduling-based cost optimization feature that:
Automatically pauses clusters during idle periods
Resumes them when needed
Reduces unnecessary cloud spend
Requires minimal ongoing management
It is a key component of a cost-aware Kubernetes operating model, especially for organizations managing multiple environments.

10.Audit Log
Purpose
The Audit Log section provides a centralized, chronological record of all actions and events that occur within a cluster managed by the platform. It is designed to support:
Change tracking
Troubleshooting
Security and compliance auditing
Operational transparency
Audit logging captures both user-initiated actions and automated system behaviors triggered by policies or internal workflows.

Accessing the Audit Log
Navigation
Users can access the Audit Log via:
Left sidebar menu under the selected cluster
Audit log item
Entry point from related sections (e.g., Hibernation events, Rebalance actions)
Once opened, the audit log loads a scrollable table of events for the cluster.
Audit Log Interface
Table Columns
Each entry in the Audit Log displays:
Timestamp
When the action or event occurred. Cast AI
Operation Name
A short description of the action performed (e.g., “Cluster hibernated”, “Node template updated”). Cast AI
Initiated By
Identifies the actor:
User email (for manual actions)
Policy name (for automated actions) Cast AI
Event Details
Expandable Entries
Clicking an audit row expands the entry.
Expanded view shows:
Detailed metadata
Resource IDs
Parameters passed
Before/after values (if applicable) Cast AI
JSON/YAML View
An icon ({}) allows switching the detail view into:
JSON
YAML
This supports programmatic inspection or export. Cast AI
Filtering & Search
Built-in Filters
Text search: Filter by arbitrary keywords (operation name, resource, etc.). Cast AI
Time range: Choose preset ranges or custom windows. Cast AI
Initiated by: Filter events by user identity or policy trigger. Cast AI
Advanced Criteria
Rebalance ID
Node ID
Node status
Policy applied
Node template & version
Configuration version
These criteria help locate precise operational events. Cast AI
Recent Searches
History of recent filters/search queries is retained for ease of reuse. Cast AI
Event Types
Audit log entries include, but are not limited to:
User actions
Cluster disconnect/reconnect
Template creation or removal
Hibernation schedule CRUD
Policy actions
Autoscaler events
Rightsizing applied
Rebalance operations
System events
Cluster hibernated/resumed
Hibernation failures
Autoscaler scale up/down
Hibernation Audit Events
Cluster hibernation operations generate specific audit events, including:
Cluster hibernated
Cluster hibernation failed
Cluster resumed
Cluster resumption failed
These events help correlate automation actions with cost impact and user intentions. 
Retention & Export
Retention Policy
Audit logs are retained directly in the console for 90 days by default.
After 90 days, older log data is archived and not directly visible in the UI.
Users can request archived logs for long-term retention or compliance.
Audit Log Exporter
For organizations with long-term compliance requirements, logs can be exported externally using an Audit Log Exporter:
Built on OpenTelemetry
Streams audit events to external systems (SIEM, ELK, Grafana, Loki, etc.)
Ensures unlimited retention outside the console UI 
Use Cases
Operational Troubleshooting
Determine why an automated action occurred
Understand sequencing of events leading to a failure
Security & Compliance
Track user actions for audit trails
Demonstrate policy enforcement history
Change History
Review infrastructure and policy changes over time
Tie configuration changes to cost optimization outcomes
Design Intent
The Audit Log is built to be:
Readable: Clear timestamped events and actor identification
Queryable: Powerful filtering and search
Integrable: Compatible with external systems for retention and SIEM purposes
Actionable: Helps teams trace behaviors, errors, and policy impacts
Summary
The Audit Log is a critical feature for governance, operational visibility, and compliance. It captures all actions and events (manual and automated), supports rich filtering, and is exportable for long-term retention or integration into enterprise logging systems


