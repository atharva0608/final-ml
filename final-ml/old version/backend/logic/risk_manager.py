"""
Risk Manager - Global Spot Pool Intelligence

This module implements "Herd Immunity" for Spot instance optimization:
1. Signal Capture: Listen for interruption events
2. Context Check: Verify event is from Production environment
3. Quarantine: Mark pool as poisoned for 15 days
4. Shield: Block all clients from using poisoned pools

The key insight: One client's failure protects everyone else.
"""

from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from database.models import SpotPoolRisk, Account, GlobalRiskEvent
from sqlalchemy import and_


class RiskManager:
    """
    Global risk intelligence for Spot pool management

    Implements a 15-day cooldown quarantine for Spot pools that experience
    interruptions in Production environments. This creates herd immunity
    by preventing ALL clients from using recently-failed pools.
    """

    POISON_DURATION_DAYS = 15  # 15-day cooldown as specified

    def __init__(self, db: Session):
        """
        Initialize risk manager

        Args:
            db: Database session
        """
        self.db = db

    def is_pool_poisoned(
        self,
        region: str,
        availability_zone: str,
        instance_type: str
    ) -> bool:
        """
        Check if a Spot pool is currently flagged as risky

        This is THE GATEKEEPER that all pipelines must consult before
        launching a Spot instance. If this returns True, the pool must
        be skipped entirely.

        Args:
            region: AWS region (e.g., 'us-east-1')
            availability_zone: AZ (e.g., 'us-east-1a')
            instance_type: Instance type (e.g., 'c5.large')

        Returns:
            True if pool is poisoned and should be avoided, False if safe
        """
        # Query for matching risk record
        risk = self.db.query(SpotPoolRisk).filter(
            SpotPoolRisk.region == region,
            SpotPoolRisk.availability_zone == availability_zone,
            SpotPoolRisk.instance_type == instance_type
        ).first()

        if not risk:
            return False  # No risk record = pool is safe

        if not risk.is_poisoned:
            return False  # Risk record exists but pool isn't poisoned

        # Check if poison has expired
        now = datetime.utcnow()
        if risk.poison_expires_at and now > risk.poison_expires_at:
            # Poison has expired - unpoison the pool
            risk.is_poisoned = False
            risk.poisoned_at = None
            risk.poison_expires_at = None
            self.db.commit()
            return False

        # Pool is currently poisoned and poison hasn't expired
        return True

    def mark_pool_as_poisoned(
        self,
        region: str,
        availability_zone: str,
        instance_type: str,
        triggering_customer_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> SpotPoolRisk:
        """
        Mark a Spot pool as poisoned due to an interruption event

        This should be called when a Spot interruption occurs in a
        PRODUCTION environment (Lab failures are ignored).

        Args:
            region: AWS region
            availability_zone: AZ
            instance_type: Instance type
            triggering_customer_id: UUID of account that experienced interruption
            metadata: Additional context (rebalance event, price spike, etc.)

        Returns:
            SpotPoolRisk record (created or updated)
        """
        # Check if risk record already exists
        risk = self.db.query(SpotPoolRisk).filter(
            SpotPoolRisk.region == region,
            SpotPoolRisk.availability_zone == availability_zone,
            SpotPoolRisk.instance_type == instance_type
        ).first()

        now = datetime.utcnow()
        expires_at = now + timedelta(days=self.POISON_DURATION_DAYS)

        if risk:
            # Update existing record
            risk.is_poisoned = True
            risk.interruption_count += 1
            risk.last_interruption = now
            risk.poisoned_at = now
            risk.poison_expires_at = expires_at
            if triggering_customer_id:
                risk.triggering_customer_id = triggering_customer_id
            if metadata:
                risk.metadata = metadata
            risk.updated_at = now
        else:
            # Create new risk record
            risk = SpotPoolRisk(
                region=region,
                availability_zone=availability_zone,
                instance_type=instance_type,
                is_poisoned=True,
                interruption_count=1,
                last_interruption=now,
                poisoned_at=now,
                poison_expires_at=expires_at,
                triggering_customer_id=triggering_customer_id,
                metadata=metadata or {}
            )
            self.db.add(risk)

        self.db.commit()

        print(f"⚠️  Pool {region}/{availability_zone}/{instance_type} marked as POISONED until {expires_at}")
        return risk

    def handle_interruption_signal(
        self,
        region: str,
        availability_zone: str,
        instance_type: str,
        account_id: str,
        event_type: str = "SPOT_INTERRUPTION"
    ) -> Optional[SpotPoolRisk]:
        """
        Handle a Spot interruption signal from AWS EventBridge

        This is the entry point for interruption events. It performs the
        Production check and only poisons the pool if the event came from
        a Production environment.

        Args:
            region: AWS region
            availability_zone: AZ
            instance_type: Instance type
            account_id: AWS account ID (12 digits)
            event_type: Type of event (SPOT_INTERRUPTION, REBALANCE_RECOMMENDATION)

        Returns:
            SpotPoolRisk if pool was poisoned, None if event was ignored
        """
        # Look up account in database
        account = self.db.query(Account).filter(
            Account.account_id == account_id
        ).first()

        if not account:
            print(f"⚠️  Unknown account {account_id} - ignoring interruption signal")
            return None

        # CRITICAL CHECK: Only poison pools for Production interruptions
        if account.environment_type != 'PROD':
            print(f"ℹ️  Lab Mode interruption in {account_id} - NOT poisoning pool (Lab failures don't affect global risk)")
            return None

        # This is a Production interruption - POISON THE POOL
        print(f"🚨 PRODUCTION INTERRUPTION detected in {region}/{availability_zone}/{instance_type}")

        metadata = {
            "event_type": event_type,
            "account_id": account_id,
            "timestamp": datetime.utcnow().isoformat()
        }

        risk = self.mark_pool_as_poisoned(
            region=region,
            availability_zone=availability_zone,
            instance_type=instance_type,
            triggering_customer_id=str(account.id),
            metadata=metadata
        )

        return risk

    def get_poisoned_pools(self, region: Optional[str] = None) -> list:
        """
        Get list of currently poisoned pools

        Args:
            region: Optional region filter

        Returns:
            List of SpotPoolRisk records that are currently poisoned
        """
        query = self.db.query(SpotPoolRisk).filter(
            SpotPoolRisk.is_poisoned == True
        )

        if region:
            query = query.filter(SpotPoolRisk.region == region)

        # Filter out expired poisons
        now = datetime.utcnow()
        active_risks = []

        for risk in query.all():
            if risk.poison_expires_at and now <= risk.poison_expires_at:
                active_risks.append(risk)
            else:
                # Auto-cleanup expired poison
                risk.is_poisoned = False
                risk.poisoned_at = None
                risk.poison_expires_at = None

        self.db.commit()
        return active_risks

    def cleanup_expired_poisons(self) -> int:
        """
        Cleanup expired poison flags

        This should be run periodically (e.g., daily) to clean up old
        poison flags that have exceeded the 15-day cooldown.

        Returns:
            Number of pools cleaned up
        """
        now = datetime.utcnow()

        expired_risks = self.db.query(SpotPoolRisk).filter(
            SpotPoolRisk.is_poisoned == True,
            SpotPoolRisk.poison_expires_at < now
        ).all()

        count = 0
        for risk in expired_risks:
            risk.is_poisoned = False
            risk.poisoned_at = None
            risk.poison_expires_at = None
            count += 1

        self.db.commit()

        if count > 0:
            print(f"🧹 Cleaned up {count} expired poison flags")

        return count

    # ========================================================================
    # New Global Risk Event System (Append-Only Log Pattern)
    # ========================================================================

    @staticmethod
    def register_risk_event(
        db: Session,
        pool_id: str,
        event_type: str,
        client_id: str = None,
        metadata: dict = None
    ) -> GlobalRiskEvent:
        """
        Register a spot disruption event (write-only fast path)

        This is the new append-only log pattern. Each disruption creates a new
        event record that expires after 15 days. Never updates existing records.

        Args:
            db: Database session
            pool_id: Pool identifier (format: 'us-east-1a:c5.large')
            event_type: 'rebalance_notice' or 'termination_notice'
            client_id: UUID of client who experienced the disruption
            metadata: Additional context

        Returns:
            Created GlobalRiskEvent record

        Performance: No queries, just INSERT (~1ms)
        """
        # Parse pool_id
        parts = pool_id.split(':')
        if len(parts) != 2:
            raise ValueError(f"Invalid pool_id format: {pool_id}. Expected 'az:type' (e.g., 'us-east-1a:c5.large')")

        availability_zone = parts[0]
        instance_type = parts[1]

        # Extract region from AZ (e.g., 'us-east-1a' -> 'us-east-1')
        region = availability_zone[:-1] if len(availability_zone) > 1 else availability_zone

        # Calculate expiry (15 days from now)
        reported_at = datetime.utcnow()
        expires_at = reported_at + timedelta(days=15)

        # Create event record
        event = GlobalRiskEvent(
            pool_id=pool_id,
            region=region,
            availability_zone=availability_zone,
            instance_type=instance_type,
            event_type=event_type,
            reported_at=reported_at,
            expires_at=expires_at,
            source_client_id=client_id,
            event_metadata=metadata or {}
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        return event

    @staticmethod
    def is_pool_safe(db: Session, pool_id: str) -> tuple:
        """
        Check if a spot pool is safe to use (read-only fast path)

        Args:
            db: Database session
            pool_id: Pool identifier (format: 'us-east-1a:c5.large')

        Returns:
            Tuple of (is_safe, active_events)
            - is_safe: False if any active events exist, True otherwise
            - active_events: List of active GlobalRiskEvent records

        Performance:
            - Query with indexed columns (pool_id, expires_at)
            - Typical: <5ms for millions of events

        Usage:
            is_safe, events = RiskManager.is_pool_safe(db, 'us-east-1a:c5.large')
            if not is_safe:
                # Skip this pool, choose different candidate
                print(f"Pool poisoned: {len(events)} active disruptions")
        """
        # Query for active events (not expired)
        now = datetime.utcnow()
        active_events = db.query(GlobalRiskEvent).filter(
            and_(
                GlobalRiskEvent.pool_id == pool_id,
                GlobalRiskEvent.expires_at > now
            )
        ).all()

        is_safe = len(active_events) == 0

        return is_safe, active_events


# For testing
if __name__ == '__main__':
    print("="*80)
    print("RISK MANAGER - Global Spot Pool Intelligence")
    print("="*80)
    print("\nImplements Herd Immunity for Spot optimization:")
    print("  1. Signal Capture: Listen for interruption events")
    print("  2. Context Check: Verify event is from Production")
    print("  3. Quarantine: Mark pool as poisoned for 15 days")
    print("  4. Shield: Block ALL clients from using poisoned pools")
    print("\nKey Insight: One client's failure protects everyone else")
    print("\nPOISON DURATION: 15 days")
    print("="*80)
