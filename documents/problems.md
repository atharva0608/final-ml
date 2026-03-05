Good. Clean separation. Two modes, two completely different philosophies.

---

## Mode 1 — ML + Rightsizing Together

**Philosophy: Risk is the primary variable. Savings is secondary. ±20% cost swing is acceptable if risk justifies it.**

The ML rebalancer already knows which pools are safe. Rightsizing in this mode is a risk-aware resize — you're asking "what size on what pool minimizes interruption risk, and does the cost land within 20% of current?"

```
Gate order (strict):

1. RISK GATE — primary
   Pick the candidate with lowest final_risk first
   Among candidates within 5% risk of each other → treat as equal tier
   Hard reject at 0.85 catastrophic ceiling (unchanged)

2. COST GATE — ±20% band, not savings-first
   candidate_price <= current_price × 1.20 → acceptable
   candidate_price > current_price × 1.20 → reject
   (you will pay up to 20% more for meaningfully lower risk)
   (you won't pay more than 20% more for any reason)

3. EV GATE — tiebreaker within the risk tier
   Among equally risky candidates within the cost band
   pick the one with highest net EV

4. DIVERSITY GATE — last
   Family ratio, AZ spread — enforced but not the primary sort
```

What this means practically: if pool A costs $0.15/hr with risk 0.12, and pool B costs $0.17/hr with risk 0.07, and your current node is $0.15/hr — the ML+Rightsizing mode picks pool B. It costs 13% more. It's within the 20% band. The lower risk justifies it.

The 20% band is not a savings threshold. It is a cost ceiling. You are buying safety with money, up to a defined limit.

```python
# In combined mode evaluation (optimizer_coordinator.py COMBINED_EVALUATION)

COST_BAND_PCT = 0.20  # configurable per org

def evaluate_combined_candidate(candidate, current_node, cluster):

    # Gate 1: Risk — hard gates first
    if final_risk >= 0.85:
        return reject("catastrophic_risk")

    # Gate 2: Cost band — not savings, cost ceiling
    cost_ratio = candidate.spot_price / current_node.cost_per_hour
    if cost_ratio > (1 + COST_BAND_PCT):
        return reject("exceeds_cost_band")
    # Note: no lower bound — savings are welcome but not required

    # Gate 3: EV tiebreaker
    ev = evaluate_candidate_ev(savings, final_risk, ...)
    if not ev["is_eligible"]:
        return reject("ev_not_eligible")

    return approve(
        sort_key=(final_risk, cost_ratio)  # risk first, then cost
    )
```

---

## Mode 2 — Auto Rightsizing Alone

**Philosophy: No downtime. Upscale freely if capacity is growing. Never optimize an overprovisioned node if the alternative costs more. Let it run fat.**

This mode has zero interest in risk arbitrage. It is purely defensive. The cluster is already on whatever pool it's on. Rightsizing here means: make sure pods have enough room, don't thrash the cluster for marginal savings, and if something needs more capacity — give it more capacity immediately.

```
Gate order (completely different):

1. UPSCALE GATE — checked first, always approved if triggered
   P99 > current request → upscale unconditionally
   No savings check. No cost check. Just do it.
   Downtime risk of an OOMKill or CPU throttle > downtime risk of resize.

2. DOWNSCALE GATE — only if candidate is cheaper
   usage < 50% of request (overprovisioned signal)
   AND candidate_price < current_price → consider resize
   AND candidate_price >= current_price → DO NOTHING
   "Let it run overprovisioned" is the correct answer here

3. NO EV GATE in this mode
   EV calculation assumes you care about savings optimization
   In no-downtime mode you don't — you care about stability
   Skip evaluate_candidate_ev() entirely for downscale decisions
   Use only: is_cheaper AND is_safe_to_drain

4. CONFIDENCE GATE — stricter than combined mode
   Only HIGH confidence recommendations execute automatically
   MEDIUM confidence → surface in UI for manual approval
   LOW confidence → suppress entirely
```

What this means practically: a node running at 45% CPU utilization on an r5.xlarge is "overprovisioned." In combined mode you'd resize it. In auto-rightsizing-alone mode you look at whether an alternative exists that is cheaper. If the cheapest alternative is an m5.large that costs $0.04/hr more — you do nothing. The node stays overprovisioned. That is the correct outcome. You do not pay more to use less.

```python
# In rightsizing_service.py — mode-aware evaluation

def should_auto_rightsize(recommendation, current_node, mode):

    if mode == "AUTO_ONLY":

        # Upscale: always approve — capacity > stability
        if recommendation.action == "INCREASE":
            return True, "UPSCALE_APPROVED_NO_CHECK"

        # Downscale: only if cheaper, only if high confidence
        if recommendation.action == "REDUCE":
            if recommendation.confidence != "HIGH":
                return False, "INSUFFICIENT_CONFIDENCE"

            if recommendation.estimated_cost >= current_node.cost_per_hour:
                return False, "NOT_CHEAPER_STAY_OVERPROVISIONED"

            # Check it's actually safe to drain (no PDB blocks etc)
            if not is_safe_to_drain(current_node):
                return False, "DRAIN_UNSAFE"

            return True, "DOWNSCALE_APPROVED"

    elif mode == "COMBINED_ML":
        # Handled by combined evaluator above — risk-first logic
        return evaluate_combined_candidate(...)
```

---

## The Key Difference In One Table

| Decision Point | ML + Rightsizing Together | Auto Rightsizing Alone |
|---|---|---|
| Primary gate | Risk score | Is it an upscale? |
| Cost tolerance | ±20% band | Only cheaper, never more |
| Overprovisioned node | Resize if better risk exists | Leave it — do nothing |
| Savings requirement | Not required within cost band | Required for downscale |
| EV calculation | Yes — tiebreaker | No — skip entirely |
| Confidence threshold | MEDIUM and above auto-execute | HIGH only auto-execute |
| Upscale on capacity growth | Considered with risk weighting | Unconditional — always yes |

---

## Where This Lives in the Codebase

**`optimizer_coordinator.py`** — The phase machine already has `COMBINED_EVALUATION`. Add a mode flag at the cluster or org level: `optimization_mode = "COMBINED_ML" or "AUTO_RIGHTSIZING_ONLY"`. Route to different evaluation functions based on this flag.

**`rightsizing_service.py` `_analyze_controller()`** — Add the mode parameter. In `AUTO_ONLY` mode, skip the cost delta calculation entirely for upscale recommendations. For downscale, add the explicit cheaper-than-current check before returning any recommendation.

**`decision_engine.py`** — In `AUTO_ONLY` mode, remove the EV gate from the rightsizing evaluation path. Keep it for pool switching decisions but not for pure resource request adjustments — those don't involve pool changes, just pod resource specs.

**`DecisionEngineV3Dashboard.jsx`** — The existing mode toggle (`Auto-Rightsizing` and `Auto-Rebalancing` toggles) maps directly to this. When only Auto-Rightsizing is on and Auto-Rebalancing is off, that is `AUTO_ONLY` mode. When both are on, that is `COMBINED_ML` mode. The mode flag is already surfaced in the UI — it just needs to wire through to the evaluation path in the backend.

---

## The Simple Version

**Combined mode:** you are trading cost for safety. Risk wins. 20% cost swing is the price of admission.

**Auto-only mode:** you are protecting stability. Capacity needs are always met. Savings are only taken when they're free — meaning the alternative is genuinely cheaper and safe to switch to. Otherwise the overprovisioned node is a feature, not a bug.