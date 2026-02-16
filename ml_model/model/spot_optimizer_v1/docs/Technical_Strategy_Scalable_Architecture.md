
Technical Strategy: Scalable Architecture for Spot Optimization


**Project:** Intelligent Spot Instance Optimization

**Version:** 3.0 (Production Roadmap)

**Status:** Validated (ONNX Opset 14 Verified)

**Author:** Nisha Chothe

1. Executive Summary

This document outlines the architectural roadmap for scaling the Spot Optimization platform from a single-region pilot to a global, multi-region production system. The strategy addresses the dual challenges of adapting to evolving market data (**Vertical Scaling**) and expanding coverage to new AWS geographies (**Horizontal Scaling**).

Our core recommendation is to adopt a **Sliding Window Retraining** strategy for model stability and a **Clustered Unified Model** for global expansion, supported by a **Dual Artifact** pipeline (Native + ONNX) to ensure both learnability and high-performance inference.

**2. Vertical Scaling: Model Evolution (Depth)**

Vertical scaling refers to increasing the "intelligence depth" of the system by continuously ingesting new data streams. The primary engineering challenge is managing **Concept Drift** (changing market behavior) without suffering from **Catastrophic Forgetting**.

**2.1 The Failure of Incremental Learning**

We evaluated "Incremental (Online) Learning" (updating weights with only new data) and rejected it for this use case.

| **Feature** | **Incremental Learning** | **Why it Fails for Spot Pricing** |
| :---: | :---: | :--- |
| **Memory** | Overwrites old weights | **Catastrophic Forgetting:** The model optimizes for Q1 2026 prices and "forgets" the safety rules for Q4 2025 spikes. |
| **Stability** | High Plasticity | **Drift Confusion:** The model cannot distinguish between a temporary price blip (Concept Drift) and a permanent AWS hardware change (Hardware Drift). |
| **Result** | Erratic Predictions | Risk of regression where previously safe instances are flagged as risky. |

**2.2 The Solution: Sliding Window Retraining**

We will implement a **Quarterly Retraining Cycle** using a **36-Month Sliding Window**.

**The Protocol:**

1.  **Trigger:** Every 3 Months (Jan, Apr, Jul, Oct).
2.  **Window Logic:**
    *   **Ingest:** Newest 3 Months.
    *   **Prune:** Oldest 3 Months.
    *   **Total:** Constant 36 Months.
3.  **Benefit:** This solves **Hardware Drift** automatically. As AWS retires older instances (e.g., r4), their data naturally slides out of the training window, "sunsetting" the knowledge without manual intervention.

**2.3 Drift Monitoring Pipeline**

To ensure safety between retraining cycles, we deploy a **Daily Drift Monitor**:

*   **Metric:** Kullback-Leibler (KL) Divergence between *Training Data Distribution* and *Live Inference Data*.
*   **Trigger:** If Model Accuracy (AUC) drops below **85% for 3 consecutive days**, an emergency out-of-cycle retraining job is triggered.

**3. Horizontal Scaling: Global Expansion (Breadth)**

Horizontal scaling involves deploying the solution to new geographic regions (e.g., N. Virginia, Frankfurt). The challenge is balancing model performance against the operational overhead of managing multiple pipelines.

3.1 Architectural Pattern Selection

| **Strategy** | **Description** | **Verdict** | **Rationale** |
| :---: | :---: | :---: | :--- |
| **Independent Models** | Train a separate, dedicated model for each target AWS region (e.g., Model A for Mumbai, Model B for Ohio, for all 15 regions). | Rejected | High Operational overhead for maintenance, retraining, and deployment (15 pipelines). Critically, this approach misses correlation patterns related to global hardware failures or supply chain issues that affect multiple regions simultaneously. |
| **Transfer Learning** | Train the foundational model on a large, primary region's data (Region A), then fine-tune its weights using the new, smaller dataset of the target region (Region B). | Rejected | While efficient for *small* target datasets, if the dataset size of Region A and Region B are comparable (which is expected in a global setup), the fine-tuning step causes **Catastrophic Forgetting** of Region A's patterns, leading to suboptimal performance. |
| **Unified (Pooled) Model** | Combine the historical data from all operational AWS regions into a single, massive training dataset. A single model is trained on this pooled data. | Recommended | Offers the best performance by allowing the model to learn universal physical and economic patterns across the entire AWS infrastructure. It results in the lowest Operational overhead, as only one training and deployment pipeline needs to be managed globally. |

**3.2 Recommendation: The "Clustered Unified" Approach**

To balance data richness with timezone-specific load patterns, we will cluster regions into **3 Macro-Models**:

*   **Cluster 1 (AMER):** N. Virginia, Ohio, Oregon, Canada.
*   **Cluster 2 (EMEA):** Ireland, Frankfurt, London, Bahrain.
*   **Cluster 3 (APAC):** Mumbai, Singapore, Tokyo, Sydney.

**Midpoint Benefit:** Reduces pipeline complexity from 15 jobs to 3, while ensuring "Day/Night" cycles are consistent within the training data.

**4. Operational Excellence: The SageMaker Pipeline**

To support this scale, we must move from ad-hoc scripts to managed SageMaker Pipelines.

**4.1 The "Dual Artifact" Protocol**

To resolve the conflict between **Inference Speed** (ONNX) and **Retrainability** (Native LightGBM), the pipeline enforces a strict Dual Artifact standard.

| **Artifact** | **Format** | **Purpose** | **Storage Path** |
| :---: | :---: | :---: | :---: |
| **Source** | Native (.txt, .model) | **Learning.** Used for retraining, debugging, and transfer learning. Supports .refit(). | `s3://.../models/source/` |
| **Deploy** | ONNX (.onnx) | **Speed.** Used for Batch Transform. Optimized for CPU/GPU. **Immutable.** | `s3://.../models/deploy/` |
| **Decoder** | JSON (.json) | **Translation.** The category_mapping.json file maps strings ("us-east-1") to Integers (0) for ONNX. | `s3://.../models/meta/` |

**4.2 Batch Processing Architecture**

Real-time endpoints (HTTP APIs) are expensive and unnecessary for Spot Pricing, which updates slowly (minutes/hours). We utilize **SageMaker Batch Transform**:

*   **Input:** Hourly snapshot of 1700+ pools (S3).
*   **Compute:** Ephemeral Cluster (e.g., c5.2xlarge).
*   **Process:** Downloads `.onnx` model + `.json` decoder.
    1.  **Step A:** Maps categorical strings using the JSON decoder.
    2.  **Step B:** Runs high-speed inference via ONNX Runtime.
*   **Output:** Uploads risk scores to S3/DynamoDB.

**5. Execution Roadmap**

**Phase 1: Vertical Stabilization (Month 1-3)**

*   **Goal:** Solidify the Mumbai Pilot.
*   **Action:**
    *   Deploy **Sliding Window Retraining** pipeline (Automated).
    *   Implement **Drift Monitor** (CloudWatch Alarms).
    *   **Milestone:** Complete first automated retraining cycle without manual intervention.

**Phase 2: Horizontal Expansion (Month 4-6)**

*   **Goal:** Expand to AMER (North America).
*   **Action:**
    *   **Data Aggregation:** Pool data from N. Virginia (us-east-1) and Ohio (us-east-2).
    *   **Unified Training:** Train the "AMER Cluster Model" using the Pooled strategy.
    *   **Validation:** Compare AMER Model accuracy vs. Independent Models.
    *   **Batch Pipeline:** Deploy the hourly SageMaker Batch Transform job for the AMER cluster.

**Phase 3: Global Optimization (Month 7+)**

*   **Goal:** Cost & Performance efficiency.
*   **Action:**
    *   **ONNX Conversion:** Convert all models to ONNX format for faster inference and portability. (Already in place, but this is the formal step).
    *   **Quantization:** Convert ONNX models to **INT8** (8-bit integer) to reduce memory by 4x.
    *   **Global Rollout:** Replicate the pipeline for EMEA and APAC clusters.
    *   **Edge Deployment:** Test deploying ONNX models directly to Kubernetes Autoscalers (Karpenter) for zero-latency decisions.
