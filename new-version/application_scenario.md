# Application Scenario & Flow Description

## Overview
This document provides a comprehensive, step-by-step narrative of the "Spot Optimizer" platform's user journey. It details the **User Interface Interactions**, the **Backend Logic** triggered at each step, and the expected **System Outcomes**. It covers the complete lifecycle from a new user's first login to advanced enterprise management and Super Admin operations.

---

## 🛣️ Part 7: The End-to-End User Journey ("The Runway")

### Phase 1: The "Aha!" Moment (Day 0)
**Objective**: Convert a new signup into a verified user with data usage visibility in under 5 minutes.

1.  **User Signup**:
    *   **Action**: User visits the landing page and enters "Acme Corp", "admin@acme.com", and a password.
    *   **Backend Logic**: `create_user_org_txn` runs an atomic transaction:
        *   Creates the User record with hashed password.
        *   Creates the Organization ID.
        *   **Crucial Step**: Creates a "Placeholder Account" (Status=`pending`) to prevent null-reference errors in the dashboard.
    *   **Outcome**: User is redirected to the /setup route.

2.  **Onboarding Wizard (The Hand-Holding)**:
    *   **UI Change**: A modal overlay darkens the screen. "Welcome to Spot Optimizer!".
    *   **Action**: User clicks the **"Production Mode (CloudFormation)"** card.
    *   **Step**: System displays a pre-generated CloudFormation URL and a "Verify" button.
    *   **Action**: User deploys the stack in AWS Console, then returns and clicks **[ Verify Connection ]**.
    *   **Backend Logic**: `validate_aws_connection` triggers. It attempts to assume the cross-account IAM Role. If successful, it updates the Placeholder Account to Status=`active`.

3.  **The First Scan (Discovery)**:
    *   **UI Change**: The Dashboard loads. It initially shows an "Empty State" skeleton loader.
    *   **Backend Logic**: The `discovery_worker_loop` kicks off immediately for this new account. It calls `ec2:DescribeInstances` and `eks:ListClusters`.
    *   **UI Change**: After ~30 seconds, the graphs suddenly populate ("Pop!").
    *   **Key Visual**: The **Net Savings KPI** lights up: *"Potential Savings: $1,400/mo"*.
    *   **User Thought**: "Wow, I'm wasting a lot of money." (The Hook).

---

### Phase 1.5: The Agent Installation (The Bridge)
**Objective**: Establish deep visibility into the Kubernetes layer.

1.  **Cluster Discovery**:
    *   **Action**: User clicks **[ + Add Cluster ]** on the Dashboard.
    *   **UI**: A modal lists discovered EKS clusters: `prod-cluster`, `staging-cluster`.
    *   **Action**: User selects `staging-cluster` and clicks **[ Connect ]**.

2.  **Agent Deployment**:
    *   **System**: Generates a unique Helm installation command.
    *   **Action**: User copies the command and runs it in their terminal: `helm install agent spot-optimizer...`
    *   **Feedback**: The Dashboard modal detects the heartbeat: *"🟢 Connection Established! Agent v1.2 active."*

---

## Phase 2: Configuration & Trust (Day 1)
**Objective**: configuring the automation rules and verifying safety before enabling full autopilot.

1.  **Policy Configuration**:
    *   **Navigation**: User goes to sidebar → **Optimization Policies**.
    *   **Infra Layer (Tab A)**:
        *   **Action**: Toggles **Karpenter Autoscaling** to **[ ON ]**.
        *   **Action**: Selects Strategy: **"Capacity Optimized"** (to prioritize stability over lowest absolute price).
        *   **Action**: Toggles **Spot Fallback Protection** to **[ x ]** (ensures uptime during market crunches).
    *   **Backend Logic**: `update_policy` saves these preferences to the `cluster_policies` JSONB column.

2.  **Hibernation Schedule Setup**:
    *   **Navigation**: User goes to sidebar → **Cluster Hibernation**.
    *   **UI Interaction**: User sees the **Weekly Scheduler Grid**. They click-and-drag to paint the blocks for "Saturday" and "Sunday" completely **Grey** (Sleep Mode).
    *   **Action**: Checks **[ x ] Enable 30-minute Pre-warm** so devs can work Monday morning.
    *   **Backend Logic**: `set_schedule` persists this matrix. The scheduler cron will now check this every minute.
    *   **Visual Feedback**: The **Savings Ticker** updates: *"Projected Monthly Savings: +$450"*.

3.  **Safety & Manual Test**:
    *   **Action**: User goes to **Exclusions** and types `kube-system` to ensure core DNS/CNI pods are never touched.
    *   **Action**: User goes to **Clusters Registry**, finds a "Staging" cluster, and clicks the small **[ Optimize Now ]** button.
    *   **Backend Logic**:
        *   `detect_opportunities`: Finds an On-Demand node with low utilization.
        *   `risk_analysis_ai`: Confirms Spot Market is stable.
        *   `execute_action_plan`: Drains the node and replaces it.
    *   **UI Feedback**: The **Real-Time Feed** scrolls: *"Just now: Switched Node i-0x89... to Spot (Saved $0.04/hr)"*.

---

## Phase 3: Automation & Value (Day 7)
**Objective**: The system runs autonomously ("Set & Forget").

1.  **Background Operations**:
    *   **Scenario**: The user is asleep. It is 2:00 AM.
    *   **Backend Logic**:
        *   **Discovery Worker**: Runs every 5 minutes to track inventory.
        *   **Optimizer Engine**: Monitors for waste.
        *   **Alerting**: Checks the "Hibernation Schedule".

2.  **Notification & Engagement**:
    *   **Event**: The "Dev Cluster" enters Sleep Mode.
    *   **Output**: The user receives a **Slack Notification** (via Webhook):
        > *"💤 Hibernation Active: Dev-Cluster-01 is going to sleep. Estimated savings for tonight: $40."*

3.  **Weekly Report**:
    *   **Event**: Monday morning.
    *   **Output**: User receives an email breakdown.
        *   *"Total Savings this week: $350"*
        *   *"Efficiency Score: Improved from 40% (F) to 75% (B)"*
        *   *"Top Saving Action: Spot Replacement on Video-Transcoder node."*

---

## Phase 4: Expansion (Day 30+)
**Objective**: Enterprise scale adoption.

1.  **Billing & Plan Upgrade**:
    *   **Visual Trigger**: The User sees the **Node Usage Bar** in the sidebar is Red: *"Using 48 of 50 Nodes"*.
    *   **Action**: Goes to **Billing**, clicks **[ Upgrade to Enterprise ]**.
    *   **Form**: Enters Credit Card details via **Stripe Elements**.
    *   **Backend Logic**: `stripe_attach_source` verifies the card, charges the pro-rated amount, and unlocks "Unlimited Nodes".

2.  **Advanced Workload Tuning**:
    *   **Action**: User creates a new **Node Template** named "AI-Workloads".
        *   Selects **GPU Families** (g4dn, p3).
        *   Sets **Disk Size** to 500GB (gp3).
    *   **Action**: Goes to **Optimization Policies > Workload Layer**.
    *   **Action**: Sets **Spot Affinity** for their "Training" namespace to **"Force Spot"** (Hard Constraint).
    *   **Outcome**: Machine Learning jobs now run exclusively on cheap Spot instances, saving ~70%.

3.  **Governance & RBAC**:
    *   **Action**: User goes to **Settings > Team Members**.
    *   **Action**: Invites their Security Auditor email.
    *   **Role Selection**: Assigns Role = **"Viewer"**.
    *   **Backend Logic**: `create_invite`. When the Auditor logs in, they can *view* the **Audit Logs** and **Dashboards** but all "Save", "Delete", and "Toggle" buttons are disabled/hidden.

4.  **Multi-Account Federation**:
    *   **Scenario**: The user wants to manage their "Research Lab" AWS account separately from "Production".
    *   **Action**: Navigates to **Settings > Cloud Integrations**.
    *   **Action**: Clicks **[ Link Another Account ]** and repeats the CloudFormation onboarding for the new account ID.
    *   **Outcome**: The Dashboard now shows a global dropdown to switch contexts between **"Acme Prod"** and **"Acme Lab"**.

---

## 🛡️ Part 3: Super Admin Console ("God Mode") - PLATFORM OWNER ONLY

**⚠️ RESTRICTED ACCESS WARNING**: This interface is **exclusively** for the SaaS Platform Owner (Internal Staff). Clients (External Users/Customers) **NEVER** see these screens.

**Scenario**: A Platform Engineer at the SaaS company needs to debug a client issue or test a new AI model.

1.  **Client Support (Impersonation)**:
    *   **User**: Internal Support Engineer.
    *   **Action**: Admin navigates to **Client Registry**. Finds "Acme Corp".
    *   **Action**: Clicks the key icon **[ Impersonate ]**.
    *   **Backend Logic**: `impersonate_client` generates a temporary JWT with Acme's Org ID but the Admin's Audit identity.
    *   **UI Change**: The screen refreshes. The Admin now sees *exactly* what Acme sees (Dashboard, Settings, etc.). A sticky banner warns: *"⚠ Impersonating Acme Corp"*.

2.  **The Lab: Live Single-Instance Switcher ("Canary Test")**:
    *   **User**: Internal Platform Architect.
    *   **Objective**: Verify that `m5.large` -> `c5.large` switching works physically before rolling it out to the Client Base.
    *   **Action**: Admin goes to **The Lab**.
    *   **Input**: Selects a specific running instance `i-0abc...`.
    *   **Input**: Selects Target Model: `Spot-V2-Aggressive`.
    *   **Action**: Clicks **[ ⚡ Execute Live Switch ]**.
    *   **Real-Time Telemetry**:
        *   The UI shows live timers updating:
        *   *Volume Detach Time: 4.2s... Done.*
        *   *Spot Request Time: 1.1s... Done.*
        *   *Boot Time: 45s... Done.*
    *   **Result**: Success. The Admin confirms the new code handles volume attachment correctly.

3.  **Model Graduation**:
    *   **User**: Head of Data Science (Internal).
    *   **Action**: Being satisfied with the Lab test, the Admin clicks **[ 🎓 Graduate to Production ]**.
    *   **Confirmation**: A modal shows a check-list of safety checks (`[x] Boot Time < 60s`).
    *   **Backend Logic**: `promote_model_to_production` broadcasts a Redis event. All client `Optimizer Engines` instantly start using the new V2 model logic for their next run.

4.  **System Health Monitoring**:
    *   **User**: DevOps Lead (Internal).
    *   **Action**: Navigates to **System Status**.
    *   **Visual**: Sees the "Celery Workers" traffic light is **Yellow** (Queue Depth > 500).
    *   **Action**: Clicks **Live Logs** to stream the backend output and identifies a latency spike in `us-west-2`.

5.  **Lab: Parallel Model Testing (A/B Test)**:
    *   **User**: Data Scientist.
    *   **Objective**: Compare "Conservative v1" vs "Aggressive v2" models simultaneously.
    *   **Action**: Configures **Parallel Test** in The Lab.
        *   Assigns `Instance-A` (Tag: `lab-stable`) to **Model v1**.
        *   Assigns `Instance-B` (Tag: `lab-beta`) to **Model v2**.
    *   **Outcome**: Watches live side-by-side graphs. *Result: Model v2 saved 15% more but had 1 extra interruption.*
