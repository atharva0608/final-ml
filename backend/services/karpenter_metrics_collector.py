import time
import json
import logging
from typing import Dict, List
from kubernetes import client
from backend.services.karpenter_service import KarpenterService

logger = logging.getLogger(__name__)

class KarpenterMetricsCollector:
    """
    Tasks 2.3 & 2.4: Collects Karpenter provisioning metrics from cluster.
    """
    def __init__(self, db, redis_client):
        self.db = db
        self.redis = redis_client

    def collect_metrics_for_cluster(self, cluster_id: str):
        """Collects success rates and provision p90s for a cluster."""
        karpenter_svc = KarpenterService(self.db, self.redis)
        from backend.models.cluster import Cluster
        cluster = karpenter_svc.db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return
            
        try:
            api_client = karpenter_svc._get_k8s_client(cluster)
            custom_api = client.CustomObjectsApi(api_client)
            
            # Task 2.3: Success rates collection from NodeClaims
            nodeclaims = custom_api.list_cluster_custom_object(group="karpenter.sh", version="v1", plural="nodeclaims")
            now_ts = time.time()
            
            for nc in nodeclaims.get("items", []):
                uid = nc.get("metadata", {}).get("uid")
                labels = nc.get("metadata", {}).get("labels", {})
                instance_type = labels.get("node.kubernetes.io/instance-type")
                if not instance_type:
                    continue
                    
                status = nc.get("status", {})
                conditions = status.get("conditions", [])
                
                is_ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)
                is_failed = any(
                    (c.get("type") == "Launched" and c.get("status") == "False") or 
                    (c.get("type") == "Ready" and c.get("status") == "False" and "Capacity" in c.get("reason", ""))
                    for c in conditions
                )
                
                outcome = None
                if is_ready: outcome = 1
                elif is_failed: outcome = 0
                else: continue
                
                dedup_key = f"spot:placement:nc_outcome:{uid}:{outcome}"
                if self.redis.setnx(dedup_key, "1"):
                    self.redis.expire(dedup_key, 86400)
                    hist_key = f"spot:placement:success_log:{cluster_id}:{instance_type}"
                    self.redis.lpush(hist_key, f"{now_ts}:{outcome}")

                    # Task 2.6: Track region/AZ level spot availability history
                    # We can use the generic availability logic
                    zone = labels.get("topology.kubernetes.io/zone")
                    region = labels.get("topology.kubernetes.io/region", cluster.region if hasattr(cluster, 'region') else 'us-east-1')
                    
                    if region:
                        r_hist_key = f"spot:placement:avail_hist_log:{cluster_id}:{region}"
                        self.redis.lpush(r_hist_key, f"{now_ts}:{outcome}")
                        if zone:
                            z_hist_key = f"spot:placement:avail_hist_log_az:{cluster_id}:{region}:{zone}"
                            self.redis.lpush(z_hist_key, f"{now_ts}:{outcome}")

                # Task 2.4: Provision time p90
                # Compute duration from creation to Ready 
                if is_ready:
                    ready_cond = next((c for c in conditions if c.get("type") == "Ready" and c.get("status") == "True"), None)
                    creation_time_str = nc.get("metadata", {}).get("creationTimestamp")
                    
                    if ready_cond and creation_time_str:
                        ready_time_str = ready_cond.get("lastTransitionTime")
                        if ready_time_str:
                            dedup_dur_key = f"spot:placement:nc_duration:{uid}"
                            # Only record duration once per NodeClaim
                            if self.redis.setnx(dedup_dur_key, "1"):
                                self.redis.expire(dedup_dur_key, 86400 * 2)
                                try:
                                    from dateutil import parser
                                    created_dt = parser.isoparse(creation_time_str)
                                    ready_dt = parser.isoparse(ready_time_str)
                                    duration = (ready_dt - created_dt).total_seconds()
                                    if duration > 0:
                                        np_class = labels.get("aura.io/nodepool-class", "spot-general")
                                        dur_hist_key = f"spot:placement:duration_log:{cluster_id}:{np_class}"
                                        self.redis.lpush(dur_hist_key, f"{now_ts}:{duration}")
                                except Exception as e:
                                    logger.warning(f"Error computing NodeClaim duration: {e}")
                    
            # Process success log keys 
            cursor = '0'
            hist_keys = []
            while cursor != 0:
                cursor, keys = self.redis.scan(cursor=cursor, match=f"spot:placement:success_log:{cluster_id}:*", count=100)
                hist_keys.extend(keys)
                
            for h_key in hist_keys:
                if isinstance(h_key, bytes):
                    h_key = h_key.decode('utf-8')
                inst_type = h_key.split(':')[-1]
                
                items = self.redis.lrange(h_key, 0, -1)
                cutoff_120m = now_ts - (120 * 60)
                cutoff_15m = now_ts - (15 * 60)
                
                valid_120m, valid_15m = [], []
                
                for item in items:
                    if isinstance(item, bytes): item = item.decode('utf-8')
                    parts = item.split(':')
                    if len(parts) == 2:
                        ts = float(parts[0])
                        out = int(parts[1])
                        if ts >= cutoff_120m:
                            valid_120m.append(out)
                            if ts >= cutoff_15m:
                                valid_15m.append(out)
                                
                self.redis.expire(h_key, 120 * 60)
                
                rate_15m = sum(valid_15m) / len(valid_15m) if valid_15m else 1.0
                rate_120m = sum(valid_120m) / len(valid_120m) if valid_120m else 1.0
                
                self._store_success_rate(inst_type, 15, rate_15m)
                self._store_success_rate(inst_type, 120, rate_120m)
                
            # Process region/AZ log keys for Task 2.6 (Spot Availability Factor)
            # The spec wants 3-window history. Let's just track 15 min rolling success as the current window
            # and `compute_spot_availability_factor` will read the smoothed history
            cursor = '0'
            avail_keys = []
            while cursor != 0:
                cursor, scan_keys = self.redis.scan(cursor=cursor, match=f"spot:placement:avail_hist_log*:{cluster_id}:*", count=100)
                avail_keys.extend(scan_keys)

            region_availability = {}
            az_availability = {}

            for a_key in avail_keys:
                if isinstance(a_key, bytes): a_key = a_key.decode('utf-8')
                
                parts = a_key.split(':')
                obj_type = parts[3] # avail_hist_log or avail_hist_log_az
                
                items = self.redis.lrange(a_key, 0, -1)
                # Compute availability over last 15 minutes window
                cutoff_15m = now_ts - (15 * 60)
                valid = []
                for item in items:
                    if isinstance(item, bytes): item = item.decode('utf-8')
                    tk = item.split(':')
                    if len(tk) == 2 and float(tk[0]) >= cutoff_15m:
                        valid.append(int(tk[1]))
                        
                self.redis.expire(a_key, 120 * 60)
                
                avail_rate = sum(valid) / len(valid) if valid else 1.0
                
                if obj_type == "avail_hist_log":
                    region = parts[5]
                    region_availability[region] = avail_rate
                else:
                    region = parts[5]
                    zone = parts[6]
                    az_availability.setdefault(region, {})[zone] = avail_rate

            # Push current availability into the history array used by PlacementAdvisor
            for region, rate in region_availability.items():
                r_key = f"spot:placement:availability_history:{region}"
                # Append to history array in Redis
                raw = self.redis.get(r_key)
                history = json.loads(raw) if raw else []
                history.append(rate)
                history = history[-3:] # keep 3 windows
                self.redis.setex(r_key, 600, json.dumps(history))

            for region, zones in az_availability.items():
                az_key = f"spot:placement:availability_history_az:{region}"
                raw = self.redis.hgetall(az_key) or {}
                
                for zone, rate in zones.items():
                    val = raw.get(zone.encode('utf-8') if isinstance(zone, str) else zone)
                    if val and isinstance(val, bytes): val = val.decode('utf-8')
                    z_hist = json.loads(val) if val else []
                    z_hist.append(rate)
                    z_hist = z_hist[-3:]
                    self.redis.hset(az_key, zone, json.dumps(z_hist))
                self.redis.expire(az_key, 600)

            # Task 2.4: Provision time p90 collection
            cursor = '0'
            dur_keys = []
            while cursor != 0:
                cursor, keys = self.redis.scan(cursor=cursor, match=f"spot:placement:duration_log:{cluster_id}:*", count=100)
                dur_keys.extend(keys)
                
            for d_key in dur_keys:
                if isinstance(d_key, bytes):
                    d_key = d_key.decode('utf-8')
                np_class = d_key.split(':')[-1]
                
                items = self.redis.lrange(d_key, 0, -1)
                # Keep 24 hours of data
                cutoff_24h = now_ts - (24 * 3600)
                
                valid_durations = []
                for item in items:
                    if isinstance(item, bytes): item = item.decode('utf-8')
                    parts = item.split(':')
                    if len(parts) == 2:
                        ts = float(parts[0])
                        dur = float(parts[1])
                        if ts >= cutoff_24h:
                            valid_durations.append(dur)
                            
                self.redis.expire(d_key, 24 * 3600 + 3600)
                
                if valid_durations:
                    import numpy as np
                    p90 = np.percentile(valid_durations, 90)
                else:
                    # Fallbacks
                    fallbacks = {
                        "spot-general": 45.0,
                        "spot-compute": 60.0,
                        "spot-memory": 120.0,
                        "on-demand-general": 30.0
                    }
                    p90 = fallbacks.get(np_class, 120.0)
                    
                self._store_p90(np_class, p90)
                
            logger.info(f"Collected Karpenter metrics for cluster {cluster_id}")
            
        except Exception as e:
            logger.error(f"Failed to collect Karpenter metrics for cluster {cluster_id}: {e}")

    def _store_success_rate(self, instance_type: str, window_minutes: int, rate: float):
        """Store in Redis `spot:placement:scheduling_success:{instance_type}:{window}m`"""
        key = f"spot:placement:scheduling_success:{instance_type}:{window_minutes}m"
        self.redis.setex(key, 300, str(rate)) # 5 min TTL
        
    def _store_p90(self, nodepool_class: str, p90: float):
        """Store in Redis `spot:placement:provision_p90:{nodepool_class}`"""
        key = f"spot:placement:provision_p90:{nodepool_class}"
        self.redis.setex(key, 600, str(p90)) # 10 min TTL
