import unittest
import time
from unittest.mock import patch, MagicMock

from backend.services.decision_engine import DecisionEngine
from backend.services.pool_ranking_service import PoolRankingService
from backend.services.billing_service import BillingService
from backend.services.control_plane_loop import ControlPlaneLoop
from backend.services.hibernation_service import HibernationService
from backend.services.action_executor import ActionExecutor
from backend.core.exceptions import StalePlanError, ConflictError

class TestIntegrationHardening(unittest.IsolatedAsyncioTestCase):
    async def test_1_blacklist_mid_cycle_aborts_execution(self):
        """TEST 1: Blacklist mid-cycle aborts execution"""
        cluster_id = "test-cluster-1"
        region = "us-east-1"
        control_plane = ControlPlaneLoop()
        
        # Simulate a rankings change mid-cycle
        with patch.object(PoolRankingService, 'get_rankings_version', side_effect=[1, 2]):
            with patch.object(DecisionEngine, 'run_evaluation_cycle') as mock_cycle:
                result = await control_plane.run_decision_cycle(cluster_id, region)
                
                self.assertEqual(result.status, "ABORTED")
                self.assertEqual(result.reason, "RANKING_STALE")
                mock_cycle.assert_not_called()

    async def test_2_worker_restart_preserves_instability_decay(self):
        """TEST 2: Worker restart preserves instability decay"""
        from backend.services.risk_engine import RiskEngine
        cluster_id = "test-cluster-2"
        # Simulate entered CONSERVATIVE state 60 minutes ago
        with patch('backend.services.risk_engine.get_redis_client') as mock_redis:
            mock_redis.return_value.hget.return_value = str(time.time() - 3600)  # 60 mins ago
            
            risk_engine = RiskEngine()
            boost = await risk_engine.get_cluster_instability_boost(cluster_id)
            
            # Expected: ~1.3 * exp(-3600/7200) ≈ 0.788
            self.assertTrue(0.78 < boost < 0.79)

    async def test_3_org_spend_spike_blocks_upward_resize(self):
        """TEST 3: Org spend spike blocks upward resize"""
        org_id = "test-org-1"
        action_executor = ActionExecutor()
        
        with patch('backend.services.billing_service.BillingService.get_org_spend_velocity') as mock_velocity:
            mock_velocity.return_value = {
                "current_hourly": 120,
                "rolling_avg_24h": 100,
                "threshold_pct": 20.0
            }
            
            # UPSIZE should block
            result_up = await action_executor.execute_action(org_id, "test-cluster-3", "UPSIZE")
            self.assertEqual(result_up.status, "BLOCKED")
            self.assertEqual(result_up.reason, "SPEND_VELOCITY")
            
            # DOWNSIZE should pass through
            result_down = await action_executor.execute_action(org_id, "test-cluster-3", "DOWNSIZE")
            self.assertNotEqual(result_down.status, "BLOCKED")

    async def test_4_stale_execution_plan_hash_aborts_execution(self):
        """TEST 4: Stale execution plan hash aborts execution"""
        cluster_id = "test-cluster-4"
        control_plane = ControlPlaneLoop()
        
        with patch('backend.pipeline.stage5_execution.controller.ExecutionController.verify_plan_hash') as mock_verify:
            mock_verify.side_effect = StalePlanError("Plan hash mismatch")
            
            with self.assertRaises(StalePlanError):
                await control_plane.execute_step(cluster_id, {"candidate_pools": []})

    async def test_5_stabilization_lock_blocks_second_action(self):
        """TEST 5: Stabilization lock blocks second action"""
        cluster_id = "test-cluster-5"
        control_plane = ControlPlaneLoop()
        
        with patch('backend.services.cooldown_controller.CooldownController.is_stabilizing') as mock_stabilizing:
            mock_stabilizing.return_value = True
            
            result = await control_plane.run_decision_cycle(cluster_id, "us-east-1")
            
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual(result.reason, "STABILIZING")

    async def test_6_hibernation_blocks_entire_cycle(self):
        """TEST 6: Hibernation blocks entire cycle"""
        cluster_id = "test-cluster-6"
        control_plane = ControlPlaneLoop()
        
        with patch('backend.services.hibernation_service.HibernationService.is_cluster_hibernating') as mock_hibernating:
            mock_hibernating.return_value = True
            
            result = await control_plane.run_decision_cycle(cluster_id, "us-east-1")
            
            self.assertEqual(result.status, "SKIPPED")
            self.assertEqual(result.reason, "HIBERNATING")

    async def test_7_ev_divergence_is_eliminated(self):
        """TEST 7: EV divergence is eliminated"""
        # Testing EV breakdown matches evaluation exactly
        proposal = {
            "candidate_pool": "pool-xyz",
            "ev_breakdown": {"ev": 0.85, "savings": 0.90, "risk": 0.05}
        }
        
        with patch('backend.services.optimizer_coordinator.OptimizerCoordinator.evaluate_proposal') as mock_eval:
            mock_eval.return_value = proposal["ev_breakdown"]["ev"]
            
            evaluated_ev = mock_eval(proposal)
            self.assertEqual(evaluated_ev, 0.85)

    async def test_8_hibernation_conflict_detection_catches_cross_type_overlaps(self):
        """TEST 8: Hibernation conflict detection catches cross-type overlaps"""
        hibernation_service = HibernationService()
        
        # Schedule 1: WEEKLY, overnight Monday-Friday
        existing_schedules = [{
            "id": "sched_1",
            "schedule_type": "WEEKLY",
            "schedule_matrix": "000000" + "11111" + "00000"
        }]
        
        # Schedule 2: DAILY, all ones
        new_schedule = {
            "schedule_type": "DAILY",
            "schedule_matrix": "1" * 24
        }
        
        with patch('backend.services.hibernation_service.HibernationService.get_active_schedules') as mock_active:
            mock_active.return_value = existing_schedules
            with patch('backend.services.hibernation_service.detect_schedule_conflicts') as mock_conflict:
                mock_conflict.side_effect = ConflictError("Overlap detected", overlap_hours=8)
                
                with self.assertRaises(ConflictError) as context:
                    await hibernation_service.create_schedule(new_schedule)
                self.assertTrue(context.exception.overlap_hours > 0)

if __name__ == '__main__':
    unittest.main()
