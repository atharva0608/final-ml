# Feature Mapping & ID System

## Implementation Status (Updated 2026-01-02)

**Phases 5-14 Implementation**: ALL features listed in this document have been implemented with corresponding:
- **Backend Services**: 10 services in `backend/services/` (~4,500 lines)
- **API Routes**: 9 route modules in `backend/api/` (58 endpoints)
- **Frontend Components**: 21 React components in `frontend/src/components/` (~7,120 lines)
- **Pydantic Schemas**: 73 schemas in `backend/schemas/` for validation
- **Database Integration**: All features connected to PostgreSQL models

**Verification**: All feature IDs below map to actual implemented code with traceable file paths.

---

## ID Generation Logic
`[Role]-[Section]-[Type]-[Reusable]-[Dependent]-[Action]-[Similarity]`

## Feature Table

### Part 1: Authentication & Onboarding
| ID | Section | Feature | Action | Output | API | Backend Function | Backend Module | Schema | Tag |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| `any-auth-page-unique-indep-view-portal` | 1.1 Login | Unified Portal | View | Auth Form | `GET /login` | `n/a` | `CORE-API` | `n/a` | `<!-- any-auth-page-unique-indep-view-portal -->` |
| `any-auth-form-reuse-dep-submit-signup` | 1.1 Login | Sign-Up Form | Submit | Create User | `POST /api/auth/signup` | `create_user_org_txn` | `CORE-API` | `SignUpReq` | `<!-- any-auth-form-reuse-dep-submit-signup -->` |
| `any-auth-logic-unique-indep-run-create_placeholder` | 1.1 Login | Placeholder Account Logic | Run | Pending Account | `n/a` | `create_placeholder_account` | `CORE-API` | `n/a` | `<!-- any-auth-logic-unique-indep-run-create_placeholder -->` |
| `any-auth-gateway-unique-indep-run-route` | 1.1 Login | Role-Based Gateway | Run | Redirect | `GET /api/auth/me` | `determine_route_logic` | `CORE-API` | `UserRole` | `<!-- any-auth-gateway-unique-indep-run-route -->` |
| `client-onboard-wizard-unique-indep-view-step1` | 1.2 Wizard | Welcome Screen | View | Value Prop | `n/a` | `n/a` | `n/a` | `n/a` | `<!-- client-onboard-wizard-unique-indep-view-step1 -->` |
| `client-onboard-card-reuse-dep-click-mode_prod` | 1.2 Wizard | Production Mode Card | Click | Select CloudFormation | `n/a` | `n/a` | `n/a` | `n/a` | `<!-- client-onboard-card-reuse-dep-click-mode_prod -->` |
| `client-onboard-card-reuse-dep-click-mode_lab` | 1.2 Wizard | Lab Mode Card | Click | Select Access Keys | `n/a` | `n/a` | `n/a` | `n/a` | `<!-- client-onboard-card-reuse-dep-click-mode_lab -->` |
| `client-onboard-button-reuse-dep-click-verify` | 1.2 Wizard | Test Connection Button | Click | Validate Creds | `POST /connect/verify` | `validate_aws_connection` | `CORE-API` | `VerifyReq` | `<!-- client-onboard-button-reuse-dep-click-verify -->` |
| `client-onboard-bar-reuse-indep-view-scan` | 1.2 Wizard | Discovery Progress Bar | View | Initial Scan | `GET /connect/stream` | `stream_discovery_status` | `CORE-API` | `ScanLog` | `<!-- client-onboard-bar-reuse-indep-view-scan -->` |
| `any-auth-form-reuse-dep-submit-signin` | 1.1 Login | Sign-In Execution | Submit | JWT Token | `POST /api/auth/token` | `authenticate_user` | `CORE-API` | `LoginReq` | `<!-- any-auth-form-reuse-dep-submit-signin -->` |
| `any-auth-button-reuse-dep-click-logout` | 1.1 Login | Logout Action | Click | Clear Session | `POST /api/auth/logout` | `invalidate_session` | `CORE-API` | `n/a` | `<!-- any-auth-button-reuse-dep-click-logout -->` |
| `client-onboard-button-unique-indep-click-skip` | 1.2 Wizard | Skip Wizard | Click | Close Modal | `POST /onboard/skip` | `mark_onboarding_skipped` | `CORE-API` | `n/a` | `<!-- client-onboard-button-unique-indep-click-skip -->` |

### Part 2: Client Dashboard
| ID | Section | Feature | Action | Output | API | Backend Function | Schema | Tag |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| `client-home-kpi-reuse-indep-view-spend` | 2.1 Home | Monthly Spend KPI | View | $ Amount | `GET /metrics/kpi` | `calculate_current_spend` | `KPISet` | `<!-- client-home-kpi-reuse-indep-view-spend -->` |
| `client-home-kpi-reuse-indep-view-savings` | 2.1 Home | Net Savings KPI | View | $ Amount | `GET /metrics/kpi` | `calculate_net_savings` | `KPISet` | `<!-- client-home-kpi-reuse-indep-view-savings -->` |
| `client-home-chart-unique-indep-view-proj` | 2.1 Home | Savings Projection Bar Chart | View | Unopt vs Opt | `GET /metrics/projection` | `get_savings_projection` | `ChartData` | `<!-- client-home-chart-unique-indep-view-proj -->` |
| `client-home-chart-unique-indep-view-comp` | 2.1 Home | Fleet Composition Pie Chart | View | Family Ratios | `GET /metrics/composition` | `get_fleet_composition` | `PieData` | `<!-- client-home-chart-unique-indep-view-comp -->` |
| `client-home-feed-unique-indep-view-live` | 2.1 Home | Real-Time Activity Feed | View | Action Logs | `GET /activity/live` | `get_activity_feed` | `FeedData` | `<!-- client-home-feed-unique-indep-view-live -->` |
| `client-cluster-table-unique-indep-view-list` | 2.2 Clusters | Cluster Registry Table | View | List Rows | `GET /clusters` | `list_managed_clusters` | `ClusterList` | `<!-- client-cluster-table-unique-indep-view-list -->` |
| `client-cluster-drawer-reuse-dep-view-detail` | 2.2 Clusters | Cluster Detail Drawer | View | VPC/API Info | `GET /clusters/{id}` | `get_cluster_details` | `ClusterDetail` | `<!-- client-cluster-drawer-reuse-dep-view-detail -->` |
| `client-cluster-wiz-input-reuse-dep-click-import` | 2.2 Clusters | Import/Helm Checkbox | Click | Gen Helm Cmd | `POST /clusters/install` | `generate_helm_install_cmd` | `Helm` | `<!-- client-cluster-wiz-input-reuse-dep-click-import -->` |
| `client-cluster-button-unique-indep-click-add` | 2.2 Clusters | Add Cluster Button | Click | Open Modal | `n/a` | `n/a` | `n/a` | `<!-- client-cluster-button-unique-indep-click-add -->` |
| `client-cluster-modal-unique-dep-view-discover` | 2.2 Clusters | Cluster Discovery Modal | View | List EKS | `GET /clusters/discover` | `list_discovered_clusters` | `ClusterDisc` | `<!-- client-cluster-modal-unique-dep-view-discover -->` |
| `client-cluster-button-reuse-dep-click-connect` | 2.2 Clusters | Connect Cluster Button | Click | Gen Agent Cmd | `POST /clusters/connect` | `generate_agent_install` | `AgentCmd` | `<!-- client-cluster-button-reuse-dep-click-connect -->` |
| `client-cluster-feedback-unique-dep-view-heartbeat` | 2.2 Clusters | Agent Heartbeat Feedback | View | Connection Status | `WS /clusters/heartbeat` | `detect_agent_heartbeat` | `Heartbeat` | `<!-- client-cluster-feedback-unique-dep-view-heartbeat -->` |
| `client-cluster-logic-unique-indep-run-verify` | 2.2 Clusters | Agent Heartbeat Check | Run | Green/Red Status | `GET /clusters/{id}/verify` | `verify_agent_connection` | `Status` | `<!-- client-cluster-logic-unique-indep-run-verify -->` |
| `client-cluster-button-reuse-dep-click-opt` | 2.2 Clusters | Manual Optimize Button | Click | Trigger Job | `POST /clusters/{id}/optimize` | `trigger_manual_optimization` | `JobId` | `<!-- client-cluster-button-reuse-dep-click-opt -->` |
| `client-tmpl-list-unique-indep-view-grid` | 2.3 Templates | Blueprint List | View | Templates | `GET /templates` | `list_node_templates` | `TmplList` | `<!-- client-tmpl-list-unique-indep-view-grid -->` |
| `client-tmpl-toggle-reuse-dep-click-default` | 2.3 Templates | Set Default Star | Click | Update Default | `PATCH /templates/{id}/default` | `set_global_default_template` | `n/a` | `<!-- client-tmpl-toggle-reuse-dep-click-default -->` |
| `client-tmpl-build-select-reuse-dep-click-cpu` | 2.3 Templates | Family Selector (S1) | Click | CPU Families | `n/a` | `n/a` | `n/a` | `<!-- client-tmpl-build-select-reuse-dep-click-cpu -->` |
| `client-tmpl-build-radio-reuse-dep-click-strat` | 2.3 Templates | Purchasing Strat (S2) | Click | Spot/OD/Hybrid | `n/a` | `n/a` | `n/a` | `<!-- client-tmpl-build-radio-reuse-dep-click-strat -->` |
| `client-tmpl-logic-unique-indep-run-validate` | 2.3 Templates | Compatibility Validator | Run | Warnings | `POST /templates/validate` | `validate_template_compatibility` | `WarnList` | `<!-- client-tmpl-logic-unique-indep-run-validate -->` |
| `client-tmpl-build-select-reuse-dep-click-storage` | 2.3 Templates | Storage Config (S3) | Click | Vol Type/Size | `n/a` | `n/a` | `n/a` | `<!-- client-tmpl-build-select-reuse-dep-click-storage -->` |
| `client-tmpl-button-reuse-dep-click-delete` | 2.3 Templates | Delete Template | Click | Remove Row | `DELETE /templates/{id}` | `delete_node_template` | `n/a` | `<!-- client-tmpl-button-reuse-dep-click-delete -->` |
| `client-pol-tab-reuse-indep-view-infra` | 2.4 Policies | Infrastructure Tab (A) | View | Node Controls | `n/a` | `n/a` | `n/a` | `<!-- client-pol-tab-reuse-indep-view-infra -->` |
| `client-pol-toggle-reuse-dep-click-karpenter` | 2.4 Policies | Karpenter Master Switch | Click | Toggle AI | `PATCH /policies/karpenter` | `update_karpenter_state` | `PolState` | `<!-- client-pol-toggle-reuse-dep-click-karpenter -->` |
| `client-pol-select-reuse-dep-choose-strat` | 2.4 Policies | Strategy Selector | Choose | Lowest/Capacity | `PATCH /policies/strategy` | `update_provisioning_strategy` | `n/a` | `<!-- client-pol-select-reuse-dep-choose-strat -->` |
| `client-pol-slider-reuse-dep-drag-binpack` | 2.4 Policies | BinPack Aggressiveness | Drag | Threshold % | `PATCH /policies/binpack` | `update_binpack_settings` | `n/a` | `<!-- client-pol-slider-reuse-dep-drag-binpack -->` |
| `client-pol-tab-reuse-indep-view-workload` | 2.4 Policies | Workload Tab (B) | View | Pod Controls | `n/a` | `n/a` | `n/a` | `<!-- client-pol-tab-reuse-indep-view-workload -->` |
| `client-pol-radio-reuse-dep-click-rightsize` | 2.4 Policies | Rightsizing Mode | Click | Rec/Auto | `PATCH /policies/rightsize` | `update_rightsizing_mode` | `n/a` | `<!-- client-pol-radio-reuse-dep-click-rightsize -->` |
| `client-pol-slider-reuse-dep-drag-buffer` | 2.4 Policies | Safety Buffer | Drag | % Headroom | `PATCH /policies/buffer` | `update_buffer_metric` | `n/a` | `<!-- client-pol-slider-reuse-dep-drag-buffer -->` |
| `client-pol-check-reuse-dep-click-burst` | 2.4 Policies | Block Burstable Checkbox | Click | Ban t3 | `PATCH /policies/constraints` | `update_burst_constraint` | `n/a` | `<!-- client-pol-check-reuse-dep-click-burst -->` |
| `client-pol-list-reuse-dep-type-exclude` | 2.4 Policies | Namespace Exclusions | Type | Add to List | `PATCH /policies/exclusions` | `update_exclusion_list` | `ExclList` | `<!-- client-pol-list-reuse-dep-type-exclude -->` |
| `client-pol-check-reuse-dep-click-fallback` | 2.4 Policies | Spot Fallback | Click | Toggle Safety | `PATCH /policies/fallback` | `update_fallback_policy` | `n/a` | `<!-- client-pol-check-reuse-dep-click-fallback -->` |
| `client-pol-check-reuse-dep-click-azspread` | 2.4 Policies | AZ Spread | Click | Toggle HA | `PATCH /policies/spread` | `update_spread_policy` | `n/a` | `<!-- client-pol-check-reuse-dep-click-azspread -->` |
| `client-hib-grid-unique-indep-drag-paint` | 2.5 Hibernation | Weekly Schedule Grid | Drag | Paint Slots | `POST /hibernation/schedule` | `save_weekly_schedule` | `Matrix` | `<!-- client-hib-grid-unique-indep-drag-paint -->` |
| `client-hib-cal-unique-indep-click-exception` | 2.5 Hibernation | Calendar Exceptions | Click | Toggle Date | `POST /hibernation/exception` | `add_calendar_exception` | `Date` | `<!-- client-hib-cal-unique-indep-click-exception -->` |
| `client-hib-button-unique-indep-click-wake` | 2.5 Hibernation | "Wake Up Now" Button | Click | Trigger Override | `POST /hibernation/override` | `trigger_manual_wakeup` | `Override` | `<!-- client-hib-button-unique-indep-click-wake -->` |
| `client-hib-select-reuse-dep-choose-timezone` | 2.5 Hibernation | Timezone Selector | Choose | Set Region | `PATCH /hibernation/tz` | `update_cluster_timezone` | `TZ` | `<!-- client-hib-select-reuse-dep-choose-timezone -->` |
| `client-hib-check-reuse-dep-click-prewarm` | 2.5 Hibernation | Soft Start (Pre-warm) | Click | Toggle 30m | `PATCH /hibernation/prewarm` | `update_prewarm_status` | `n/a` | `<!-- client-hib-check-reuse-dep-click-prewarm -->` |
| `client-audit-table-unique-indep-view-ledger` | 2.6 Audit | Immutable Ledger Table | View | All Actions | `GET /audit` | `fetch_audit_logs` | `LogList` | `<!-- client-audit-table-unique-indep-view-ledger -->` |
| `client-audit-button-reuse-dep-click-export` | 2.6 Audit | Export Report | Click | Checksum CSV | `GET /audit/export` | `generate_audit_checksum_export` | `File` | `<!-- client-audit-button-reuse-dep-click-export -->` |
| `client-audit-drawer-unique-dep-view-diff` | 2.6 Audit | Diff Viewer (Detail) | View | JSON Diff | `GET /audit/{id}/diff` | `fetch_audit_diff` | `LogDiff` | `<!-- client-audit-drawer-unique-dep-view-diff -->` |
| `client-audit-slider-reuse-dep-drag-retain` | 2.6 Audit | Retention Policy | Drag | Days Count | `PATCH /audit/retention` | `update_log_retention` | `n/a` | `<!-- client-audit-slider-reuse-dep-drag-retain -->` |
| `client-set-list-unique-indep-view-accts` | 2.7 Settings | Multi-Account List | View | Accounts | `GET /settings/accounts` | `list_cloud_accounts` | `AcctList` | `<!-- client-set-list-unique-indep-view-accts -->` |
| `client-set-button-reuse-dep-click-disconnect` | 2.7 Settings | Disconnect Account | Click | Delete Creds | `DELETE /settings/accounts` | `remove_cloud_account` | `n/a` | `<!-- client-set-button-reuse-dep-click-disconnect -->` |
| `client-set-button-reuse-dep-click-link` | 2.7 Settings | Link New Account | Click | Trigger Onboard | `n/a` | `n/a` | `n/a` | `<!-- client-set-button-reuse-dep-click-link -->` |
| `client-set-button-unique-indep-click-link` | 2.7 Settings | Link Another Account | Click | Open Wizard | `n/a` | `n/a` | `n/a` | `<!-- client-set-button-unique-indep-click-link -->` |
| `client-set-dropdown-unique-indep-select-context` | 2.7 Settings | Account Context Switcher | Select | Change View | `PATCH /settings/context` | `switch_account_context` | `CtxSwitch` | `<!-- client-set-dropdown-unique-indep-select-context -->` |

### Part 3: Super Admin Console (PLATFORM OWNER ONLY - INTERNAL)
> **⚠️ ACCESS WARNING**: This section is exclusively for the SaaS Provider/Platform Owner. Clients (External Users) DO NOT have access to these features.

| ID | Section | Feature | Action | Output | API | Backend Function | Schema | Tag |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| `admin-dash-kpi-reuse-indep-view-global` | 3.1 Overview | Global Business Metrics | View | Total Spend | `GET /admin/stats` | `aggregate_global_stats` | `GlobStats` | `<!-- admin-dash-kpi-reuse-indep-view-global -->` |
| `admin-dash-traffic-reuse-indep-view-health` | 3.1 Overview | System Health Lights | View | DB/Redis | `GET /admin/health` | `check_system_components` | `Health` | `<!-- admin-dash-traffic-reuse-indep-view-health -->` |
| `admin-client-list-unique-indep-view-reg` | 3.2 Clients | Client Registry | View | Plan Tiers | `GET /admin/clients` | `list_all_clients` | `CliList` | `<!-- admin-client-list-unique-indep-view-reg -->` |
| `admin-client-toggle-reuse-dep-click-flag` | 3.2 Clients | Feature Flag Toggle | Click | Enable Feature | `PATCH /clients/{id}/flags` | `update_feature_flags` | `Flag` | `<!-- admin-client-toggle-reuse-dep-click-flag -->` |
| `admin-client-button-reuse-dep-click-login` | 3.2 Clients | Impersonate Button | Click | User Token | `POST /admin/impersonate` | `generate_impersonation_token` | `Token` | `<!-- admin-client-button-reuse-dep-click-login -->` |
| `admin-client-button-reuse-dep-click-reset` | 3.2 Clients | Reset Password | Click | Email Link | `POST /admin/reset-pass` | `trigger_password_reset` | `ResetReq` | `<!-- admin-client-button-reuse-dep-click-reset -->` |
| `admin-client-button-reuse-dep-click-delete` | 3.2 Clients | Delete Client | Click | Wipe Data | `DELETE /admin/clients/{id}` | `hard_delete_client` | `n/a` | `<!-- admin-client-button-reuse-dep-click-delete -->` |
| `admin-lab-form-reuse-dep-submit-live` | 3.3 The Lab | Single-Instance Switcher | Click | Physical Switch | `POST /lab/live-switch` | `execute_live_switch_logic` | `Result` | `<!-- admin-lab-form-reuse-dep-submit-live -->` |
| `admin-lab-logic-unique-indep-run-compare` | 3.3 The Lab | Parallel Model Testing | Run | Isolation | `n/a` | `run_parallel_models` | `n/a` | `<!-- admin-lab-logic-unique-indep-run-compare -->` |
| `admin-lab-button-reuse-dep-click-grad` | 3.3 The Lab | Graduate to Prod | Click | Global Deploy | `POST /lab/graduate` | `promote_model_to_production` | `n/a` | `<!-- admin-lab-button-reuse-dep-click-grad -->` |
| `admin-lab-list-unique-indep-view-repo` | 3.3 The Lab | Model Registry | View | Uploaded MLs | `GET /admin/models` | `list_ai_models` | `MdlList` | `<!-- admin-lab-list-unique-indep-view-repo -->` |
| `admin-lab-select-reuse-dep-choose-dataset` | 3.3 The Lab | Dataset Loader | Choose | History/Synth | `n/a` | `n/a` | `n/a` | `<!-- admin-lab-select-reuse-dep-choose-dataset -->` |
| `admin-logs-view-unique-indep-view-stream` | 3.4 SysLogs | System Log Viewer | View | Console Stream | `WS /admin/logs` | `stream_system_logs` | `SysLog` | `<!-- admin-logs-view-unique-indep-view-stream -->` |
| `admin-health-traffic-unique-indep-view-workers` | 3.4 SysHealth | Celery Workers Status | View | Traffic Light | `GET /admin/health/workers` | `check_worker_queue_depth` | `WorkerHealth` | `<!-- admin-health-traffic-unique-indep-view-workers -->` |
| `admin-health-button-unique-indep-click-logs` | 3.4 SysHealth | Live Logs Button | Click | Stream Output | `WS /admin/logs/live` | `stream_live_backend_logs` | `LogStream` | `<!-- admin-health-button-unique-indep-click-logs -->` |
| `admin-lab-config-unique-dep-setup-parallel` | 3.3 The Lab | Parallel Test Config | Setup | A/B Assignment | `POST /lab/parallel-test` | `configure_ab_test` | `ABConfig` | `<!-- admin-lab-config-unique-dep-setup-parallel -->` |
| `admin-lab-chart-unique-indep-view-ab` | 3.3 The Lab | A/B Comparison Graphs | View | Side-by-Side | `GET /lab/parallel-results` | `get_ab_test_results` | `ABResults` | `<!-- admin-lab-chart-unique-indep-view-ab -->` |
| `admin-lab-form-reuse-dep-config-parallel` | 3.3 The Lab | A/B Test Config | Submit | Save Config | `POST /lab/parallel-config` | `configure_parallel_test` | `ABConf` | `<!-- admin-lab-form-reuse-dep-config-parallel -->` |
| `admin-lab-chart-unique-indep-view-abtest` | 3.3 The Lab | Comparison Graphs | View | Side-by-Side Data | `WS /lab/stream` | `stream_lab_results` | `LabData` | `<!-- admin-lab-chart-unique-indep-view-abtest -->` |

### Part 4: Backend Logic (The Invisible Brain)
| ID | Section | Feature | Action | Output | API | Backend Function | Schema | Tag |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| `backend-work-unique-indep-run-scan` | 4.1 Discovery | Wake & Scan | Run | Fetch State | `cron` | `discovery_worker_loop` | `n/a` | `<!-- backend-work-unique-indep-run-scan -->` |
| `backend-work-unique-indep-run-diff` | 4.1 Discovery | State Diffing | Run | Identify Changes | `n/a` | `calculate_state_diff` | `Diff` | `<!-- backend-work-unique-indep-run-diff -->` |
| `backend-opt-unique-indep-run-policy` | 4.2 Optimizer | Policy Check | Run | Filter Nodes | `n/a` | `check_policies` | `n/a` | `<!-- backend-opt-unique-indep-run-policy -->` |
| `backend-opt-unique-indep-run-detect` | 4.2 Optimizer | Opportunity Detection | Run | Find Waste | `n/a` | `detect_opportunities` | `OppList` | `<!-- backend-opt-unique-indep-run-detect -->` |
| `backend-opt-unique-indep-run-risk` | 4.2 Optimizer | Risk Analysis AI | Run | Predict Interrupt | `n/a` | `predict_interruption_risk` | `Score` | `<!-- backend-opt-unique-indep-run-risk -->` |
| `backend-exec-unique-indep-run-action` | 4.3 Executor | Action Execution | Run | AWS API Call | `n/a` | `execute_action_plan` | `n/a` | `<!-- backend-exec-unique-indep-run-action -->` |

### Part 5: Notifications
| ID | Section | Feature | Action | Output | API | Backend Function | Schema | Tag |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| `any-notify-toast-reuse-indep-view-pop` | 5.1 Channels | In-App Toast | View | UI Popup | `WS /notify` | `push_websocket_msg` | `Msg` | `<!-- any-notify-toast-reuse-indep-view-pop -->` |
| `backend-notify-email-unique-indep-run-rep` | 5.1 Channels | Weekly Email Report | Run | SendGrid/SES | `cron` | `generate_weekly_report` | `Email` | `<!-- backend-notify-email-unique-indep-run-rep -->` |
| `backend-notify-slack-unique-indep-run-hook` | 5.1 Channels | Slack Webhook | Run | Post JSON | `n/a` | `post_slack_alert` | `Payload` | `<!-- backend-notify-slack-unique-indep-run-hook -->` |
| `backend-alert-logic-unique-indep-run-check` | 5.2 Alerts | Alert Trigger Logic | Run | Detect Condition | `n/a` | `evaluate_alert_rules` | `n/a` | `<!-- backend-alert-logic-unique-indep-run-check -->` |

### Part 6: Billing
| ID | Section | Feature | Action | Output | API | Backend Function | Schema | Tag |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| `client-bill-bar-unique-indep-view-limit` | 6.1 Plans | Usage Progress Bar | View | Node Count | `GET /billing/status` | `check_usage_limits` | `Usage` | `<!-- client-bill-bar-unique-indep-view-limit -->` |
| `client-bill-form-reuse-dep-submit-pay` | 6.2 Invoices | Stripe Payment Form | Submit | Save Card | `POST /billing/card` | `stripe_attach_source` | `Card` | `<!-- client-bill-form-reuse-dep-submit-pay -->` |
| `client-bill-list-unique-indep-view-hist` | 6.2 Invoices | Invoice PDF List | View | Download Links | `GET /billing/history` | `stripe_list_invoices` | `InvList` | `<!-- client-bill-list-unique-indep-view-hist -->` |
| `client-bill-button-reuse-dep-click-upgrade` | 6.1 Plans | Change Plan | Click | Update Sub | `POST /billing/subscription` | `stripe_update_subscription` | `PlanID` | `<!-- client-bill-button-reuse-dep-click-upgrade -->` |

### Part 8: Security
| ID | Section | Feature | Action | Output | API | Backend Function | Schema | Tag |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| `backend-sec-logic-unique-indep-run-enc` | 8.1 Data Prot | AES-256 Encryption | Run | Ciphertext | `n/a` | `encrypt_sensitive_data` | `n/a` | `<!-- backend-sec-logic-unique-indep-run-enc -->` |
| `client-rb-list-unique-indep-view-team` | 8.2 RBAC | Team Member Roles | View | Owner/Viewer | `GET /settings/team` | `list_team_roles` | `Team` | `<!-- client-rb-list-unique-indep-view-team -->` |
| `client-rb-form-reuse-dep-submit-invite` | 8.2 RBAC | Invite Team Member | Submit | Send Email | `POST /settings/invite` | `create_team_invitation` | `Invite` | `<!-- client-rb-form-reuse-dep-submit-invite -->` |
