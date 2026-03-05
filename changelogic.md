EC2 Termination Bug Report — Resource Hygiene
Observed Symptom:

User clicks "Cleanup" on an EC2 instance in Resource Hygiene
A toast notification fires: "Action TERMINATE initiated" — but only after a long delay
The EC2 instance is NOT actually terminated on AWS
No confirmation toast ("terminated successfully" / "terminated failed") is shown
Bug #1 — Region is "global" When "All Regions" is Selected (CRITICAL)
File: 
CleanupDashboard.jsx
 Lines: 557, 1606

What happens:
When the user has selected "All Regions (Global)" in the region dropdown, selectedRegion === 'ALL'. The frontend then sends:

js
region: selectedRegion === 'ALL' ? 'global' : selectedRegion
So region = 'global' is sent to the backend. In the backend:

python
# hygiene_service.py line 1604-1607
region = action_data.region
if not region or region.lower() == 'global':
    region = 'us-east-1'
The backend silently maps 'global' → 'us-east-1'. If the EC2 instance the user is cleaning up is NOT in us-east-1, the ec2.terminate_instances() call will fail with InvalidInstanceID.NotFound. The backend then catches this as a "resource already cleaned up" success (see Bug #3), and returns {"status": "success"} — which causes the frontend to show "Action TERMINATE initiated" as if it worked.

Result: The toast fires, but the EC2 is neither terminated nor actually the right region was targeted.

How it could be fixed: Store the exact 
region
 of each resource in the scan result, and pass that region (not the filter dropdown value) when executing actions.

Bug #2 — Frontend Toast is Optimistic, Not Based on Real API Success (UX Issue)
File: 
CleanupDashboard.jsx
 Line: 559

What happens:
js
await hygieneAPI.execute(...);
toast.success(`Action ${actionType} initiated`);  // <-- fires immediately after await
The toast fires the moment the API responds (any 200-level response), which is before the termination is actually confirmed on AWS. The word "initiated" is misleading — it implies AWS accepted the termination, but the code doesn't check the 
status
 field in the API response.

The backend can return {"status": "pending_approval", ...} with a 202 Accepted HTTP code, or a {"status": "success", "skipped": true} when the resource was already deleted. The frontend does not distinguish between these and shows the same generic toast in all cases.

There is NO second toast / confirmation after the action completes, because:

The code does not poll or wait for real AWS termination
The backend's 
execute_action
 is synchronous (blocking) and returns immediately after calling ec2.terminate_instances(), which only initiates the termination. The instance may take up to 60 seconds to fully terminate on AWS.
Result: User sees one toast, never a "Terminated" or "Failed" confirmation.

How it could be fixed:

Inspect the response: check result.status === 'pending_approval' and show a different message
Add a second toast or poll for instance state change
Show human-readable action result based on response body
Bug #3 — InvalidInstanceID.NotFound Silently Treated as Success
File: 
hygiene_service.py
 Lines: 1731–1746

What happens:
python
_not_found = {
    'InvalidInstanceID.NotFound', 'InvalidInstanceID.Malformed', ...
}
if code in _not_found:
    return {
        "status": "success",
        "message": "Resource already cleaned up ...",
        "skipped": True,
    }
If terminate_instances() fails because the wrong region was used (Bug #1), AWS returns InvalidInstanceID.NotFound. The backend catches this as a success and returns {"status": "success", "skipped": True} — the API returns a 200 OK. The frontend sees a 200, shows "Action TERMINATE initiated", and the user has no idea the termination never happened.

How it could be fixed: Log this explicitly, and have the frontend render a warning-level toast for skipped: true responses.

Bug #4 — Notification Delay: The Action Waits for 
_get_account_session
 STS Assume Role (Latency)
File: 
hygiene_service.py
 Lines: 69–89

What happens:
Every time an action is executed, 
execute_action
 calls 
_get_account_session
 which does a live sts.assume_role(...) call across the network. If the platform's AWS credentials are slow or STS is taking long, this adds 2–5 seconds of latency before anything happens. This explains the "long delay" before the notification.

If STS fails (e.g., credentials not configured, expired, role missing ExternalId mismatch), the whole action fails with an exception — but the exception is caught and re-raised to the HTTP layer which returns a 500. However, the frontend only catches generic errors and shows toast.error('Failed to execute TERMINATE').

How it could be fixed:

Cache STS session tokens in Redis (they are valid for 1 hour) to avoid re-assuming the role on every action
Show a spinner/loading state in the UI while the action is in progress
Bug #5 — Approval Gate Can Silently Block Action Without Clear UI Feedback
File: 
hygiene_service.py
 Lines: 1543–1570

What happens:
If org.require_automation_approval == True and the logged-in user is not an admin (ORG_ADMIN or SUPER_ADMIN), the action is not executed. Instead an approval ticket is created and the API returns:

json
HTTP 202 Accepted
{"status": "pending_approval", "message": "Action paused. Approval #X created."}
The frontend does not check for 202 vs 200, nor does it inspect result.status. It just calls toast.success('Action TERMINATE initiated') regardless. So the user sees a success toast — but the action is actually pending approval and was never sent to AWS.

How it could be fixed: Check response.status (HTTP 202) or response.data.status === 'pending_approval' in the frontend and show: "Termination requires approval. Ticket created."

Summary Table
#	Bug	Severity	File	Line(s)
1	Wrong region fallback — 
global
 → us-east-1 silently	🔴 Critical	
CleanupDashboard.jsx
 + 
hygiene_service.py
557, 1606
2	Optimistic toast fires regardless of outcome	🔴 Critical	
CleanupDashboard.jsx
559
3	InvalidInstanceID.NotFound silently becomes status: success	🟠 High	
hygiene_service.py
1731–1746
4	STS Assume Role latency causes long delay	🟡 Medium	
hygiene_service.py
69–89
5	Approval gate blocks action silently — toast shows as success	🟠 High	
hygiene_service.py
 + 
CleanupDashboard.jsx
1557, 559
Most Likely Root Cause
The most probable cause for "long delay then no AWS action" is a combination of:

Bug #4 (STS delay causing the latency)
Bug #1 (wrong region → wrong endpoint → InvalidInstanceID.NotFound)
Bug #3 (the NotFound error is silently swallowed and returned as success)
And the reason for "no confirmation notification after" is:

Bug #2 (the frontend shows only one toast, never checks backend response details or polls for completion)

Comment
⌥⌘M
Console Errors Bug Report
Date: 2026-03-04
Errors Reported:

GET /api/v1/teams/invites 404 (Not Found)
DELETE /api/v1/accounts/{id} blocked by CORS Policy
DELETE /api/v1/accounts/{id} 500 (Internal Server Error) — "AWS account could not be deleted"
Bug #1 — /api/v1/teams/invites Endpoint Does Not Exist (404)
File calling it: 
Dashboard.jsx

Line: 408

What happens:
js
// Dashboard.jsx line 408
const invitesRes = await api.get('/api/v1/teams/invites').catch(() => ({ data: [] }));
The Dashboard calls GET /api/v1/teams/invites to count pending team invitations.

Checking all routes in 
team_routes.py
, the available endpoints under /teams prefix are:

GET / — list teams
POST / — create team
PUT /{team_id}/rename
POST /{team_id}/assign
POST /{team_id}/remove
POST /{team_id}/invite — invite a user to a team
GET /{team_id} — get team details
GET /{team_id}/stats
GET /{team_id}/approvers
GET /my-teams/approvers
GET /invites does not exist anywhere in the backend — neither in 
team_routes.py
 nor any other file.

The frontend silently swallows the error (.catch(() => ({ data: [] }))), so awaitingConsent always shows 0 in the dashboard, and a 404 is logged to the browser console.

Possible Cause:
The /invites endpoint was planned as part of the invite system but never implemented. The POST /{team_id}/invite route creates an invitation, but there is no corresponding GET /invites route to list pending invitations for the current user.

How it could be fixed:
Add a GET /invites route to 
team_routes.py
 that queries the database for pending invitations for the current user's email/id. Requires a corresponding DB model/table for invitations.

Bug #2 — CORS Block on DELETE /api/v1/accounts/{id}
Error message:

Access to XMLHttpRequest at 'http://localhost:8000/api/v1/accounts/...'
from origin 'http://localhost' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present.
CORS config files:

config.py
 — line 52–62
docker/.env
 — line 62
What happens:
The CORS_ORIGINS in 
docker/.env
 is:

CORS_ORIGINS=http://localhost:3000,http://localhost:80,http://localhost,https://geophytic-personably-gale.ngrok-free.dev
http://localhost is present, so for a regular GET this should be allowed. However, CORS preflight (OPTIONS) for non-simple HTTP methods like DELETE requires:

The browser sends a OPTIONS preflight request first
The server must explicitly allow DELETE in Access-Control-Allow-Methods
Root Cause:
The CORS error on a DELETE request typically means:

The preflight OPTIONS request returned a response that did not include Access-Control-Allow-Origin, indicating either:
The backend processed the OPTIONS as a real route and returned a 404, which strips the CORS headers, OR
The exact origin http://localhost (port 80 implied) vs http://localhost:80 mapping is causing a mismatch — some browsers treat these as the same, others don't
The backend running in Docker on http://localhost:8000 may not be returning the CORS preflight response before the 500 error fires on the actual DELETE request, combining both errors in the console
Also important: The backend also returns a 500 on the DELETE call (Bug #3 below). When the request itself fails with a 500 before CORS headers are fully set, browsers can misreport the error as a CORS violation.

How it could be fixed:
Add http://localhost:80 and http://localhost explicitly to CORS origins (both with and without port)
Ensure the FastAPI CORS middleware is declared before all API routers in 
api_gateway.py
Verify allow_methods=["*"] or explicitly ["GET", "POST", "PUT", "DELETE", "OPTIONS"] is set
Bug #3 — DELETE /api/v1/accounts/{id} Returns 500
File: 
account_service.py

Lines: 185–234

What happens:
delete_account()
 cascades deletes manually using raw text() SQL:

python
tables_with_cluster_fk = [
    "pod_metrics", "cluster_metrics", "agent_actions", "api_keys",
    "rightsizing_proposals", "optimizer_states", ...
    "instances",
]
for table in tables_with_cluster_fk:
    try:
        self.db.execute(text(f"DELETE FROM {table} WHERE cluster_id IN (...)"))
    except Exception:
        self.db.rollback()  # ← CRITICAL BUG: rolls back entire transaction
Possible Causes:
Cause A — Rollback in Loop Kills Transaction
If ANY table's delete fails (e.g., table doesn't exist yet from a pending migration), self.db.rollback() is called inside the loop. This kills the entire DB session/transaction. Subsequent SQL commands in the same request (including self.db.delete(account) and self.db.commit()) will then fail with an InvalidRequestError or PendingRollbackError.

Cause B — Missing Tables in the FK Delete List
There may be FK-constrained tables referencing 
clusters
 or 
accounts
 that are not in the tables_with_cluster_fk list. For example:

rebalancing_actions (references cluster_id)
termination_events
node_templates / cluster_template_mappings
Any custom tables added in recent migrations
When the final self.db.delete(account) is executed, Postgres raises a foreign key violation which surfaces as a 500.

Cause C — 
account_id
 vs Internal UUID clash
Cluster.account_id is the internal UUID of the 
Account
 row (not the AWS account ID). But in 
delete_account()
:

python
cluster_ids = [c.id for c in self.db.query(Cluster.id).filter(
    Cluster.account_id == account_id  # This is the internal UUID
).all()]
If somewhere the code accidentally passes the AWS account ID string ("123456789012") instead of the internal UUID, no clusters would be found, but FK constraints from clusters → account would still block deletion.

How it could be fixed:
Wrap all raw SQL deletes in a single outer try/except with a proper session.rollback() only at the outermost level, not inside the loop
Audit all FK tables referencing cluster_id and 
account_id
 via SELECT table_name FROM information_schema.key_column_usage WHERE referenced_table_name = 'clusters'
Consider using SQLAlchemy cascade rules (cascade="all, delete-orphan") on the model relationships instead of manual raw SQL
Or simply use ON DELETE CASCADE at the database level via Alembic migration
Summary Table
#	Error	Severity	Root Cause	File
1	GET /teams/invites 404	🟡 Medium	Endpoint never implemented in backend	
team_routes.py
2	CORS Block on DELETE	🟠 High	DELETE 500 caused browser to strip CORS header, reported as CORS error	
api_gateway.py
, 
docker/.env
3	DELETE /accounts/{id} 500	🔴 Critical	self.db.rollback() in loop kills session, or missing FK table in cascade list	account_service.py:185-234
Note: Bug #2 (CORS) and Bug #3 (500) are very likely related — the 500 happening before CORS response is sent causes the browser to see a CORS error instead of the underlying 500.