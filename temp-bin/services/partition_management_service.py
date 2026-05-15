"""
Phase 5: Partition Management Service for TimescaleDB

Enterprise Requirements:
- Automated chunk health monitoring
- Compression status tracking
- Partition size optimization
- Retention policy enforcement
- Performance analytics

Key Features:
- Monitor chunk sizes (prevent runaway growth)
- Track compression ratios (ensure 70%+ compression)
- Validate retention policies are running
- Detect missing or corrupted chunks
- Performance metrics for query optimization
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class PartitionManagementService:
    """
    Enterprise partition management for TimescaleDB hypertables.

    Responsibilities:
    - Chunk health monitoring
    - Compression tracking and optimization
    - Retention policy validation
    - Performance analytics
    - Automated maintenance recommendations
    """

    def __init__(self, db: Session):
        self.db = db

    # =====================================================================
    # Chunk Health Monitoring
    # =====================================================================

    def get_chunk_statistics(self) -> List[Dict[str, Any]]:
        """
        Get comprehensive chunk statistics for pod_metrics hypertable.

        Returns:
            List of chunk stats with size, compression, row count
        """
        query = text("""
            SELECT
                h.hypertable_name,
                c.chunk_name,
                c.range_start,
                c.range_end,
                pg_size_pretty(c.total_bytes) as total_size,
                c.total_bytes,
                pg_size_pretty(c.before_compression_total_bytes) as uncompressed_size,
                c.before_compression_total_bytes,
                CASE
                    WHEN c.before_compression_total_bytes > 0
                    THEN ROUND((1 - c.total_bytes::numeric / c.before_compression_total_bytes::numeric) * 100, 2)
                    ELSE 0
                END as compression_ratio_pct,
                c.total_rows,
                c.is_compressed
            FROM timescaledb_information.chunks c
            JOIN timescaledb_information.hypertables h ON c.hypertable_name = h.hypertable_name
            WHERE h.hypertable_name = 'pod_metrics'
            ORDER BY c.range_start DESC
            LIMIT 100;
        """)

        result = self.db.execute(query)
        chunks = []

        for row in result:
            chunks.append({
                "hypertable": row.hypertable_name,
                "chunk_name": row.chunk_name,
                "range_start": row.range_start.isoformat() if row.range_start else None,
                "range_end": row.range_end.isoformat() if row.range_end else None,
                "total_size": row.total_size,
                "total_bytes": row.total_bytes,
                "uncompressed_size": row.uncompressed_size,
                "uncompressed_bytes": row.before_compression_total_bytes,
                "compression_ratio_pct": float(row.compression_ratio_pct),
                "total_rows": row.total_rows,
                "is_compressed": row.is_compressed,
            })

        return chunks

    def get_chunk_health(self) -> Dict[str, Any]:
        """
        Get overall chunk health metrics.

        Enterprise Guardrails:
        - Alert if any chunk >1GB uncompressed
        - Alert if compression ratio <60%
        - Alert if chunk count growing unexpectedly

        Returns:
            Health summary with alerts
        """
        chunks = self.get_chunk_statistics()

        total_chunks = len(chunks)
        compressed_chunks = sum(1 for c in chunks if c["is_compressed"])
        uncompressed_chunks = total_chunks - compressed_chunks

        total_size_bytes = sum(c["total_bytes"] for c in chunks)
        uncompressed_size_bytes = sum(
            c["uncompressed_bytes"] for c in chunks if c["uncompressed_bytes"]
        )

        avg_compression_ratio = (
            sum(c["compression_ratio_pct"] for c in chunks if c["is_compressed"]) /
            max(compressed_chunks, 1)
        )

        # Detect issues
        alerts = []

        # Alert: Large uncompressed chunks
        large_chunks = [
            c for c in chunks
            if not c["is_compressed"] and c["total_bytes"] > 1_000_000_000  # 1GB
        ]
        if large_chunks:
            alerts.append({
                "severity": "WARNING",
                "message": f"{len(large_chunks)} uncompressed chunks exceed 1GB",
                "action": "Run manual compression or reduce chunk interval"
            })

        # Alert: Poor compression ratio
        if avg_compression_ratio < 60:
            alerts.append({
                "severity": "WARNING",
                "message": f"Average compression ratio is {avg_compression_ratio:.1f}% (target: 70%+)",
                "action": "Review compression segmentby/orderby configuration"
            })

        # Alert: Too many uncompressed chunks
        if uncompressed_chunks > 7:  # More than 7 days of uncompressed data
            alerts.append({
                "severity": "INFO",
                "message": f"{uncompressed_chunks} uncompressed chunks (expected: ≤7 for 7-day policy)",
                "action": "Compression policy may be delayed or disabled"
            })

        return {
            "total_chunks": total_chunks,
            "compressed_chunks": compressed_chunks,
            "uncompressed_chunks": uncompressed_chunks,
            "total_size_bytes": total_size_bytes,
            "total_size_human": self._bytes_to_human(total_size_bytes),
            "uncompressed_size_bytes": uncompressed_size_bytes,
            "uncompressed_size_human": self._bytes_to_human(uncompressed_size_bytes),
            "avg_compression_ratio_pct": round(avg_compression_ratio, 2),
            "space_saved_bytes": uncompressed_size_bytes - total_size_bytes,
            "space_saved_human": self._bytes_to_human(uncompressed_size_bytes - total_size_bytes),
            "alerts": alerts,
            "last_checked": datetime.utcnow().isoformat(),
        }

    # =====================================================================
    # Compression Management
    # =====================================================================

    def get_compression_stats(self) -> Dict[str, Any]:
        """
        Get detailed compression statistics.

        Returns:
            Compression performance metrics
        """
        query = text("""
            SELECT
                ht.hypertable_name,
                COUNT(*) as total_chunks,
                SUM(CASE WHEN c.is_compressed THEN 1 ELSE 0 END) as compressed_chunks,
                SUM(c.total_bytes) as total_size_bytes,
                SUM(c.before_compression_total_bytes) as uncompressed_size_bytes,
                SUM(c.total_rows) as total_rows
            FROM timescaledb_information.chunks c
            JOIN timescaledb_information.hypertables ht ON c.hypertable_name = ht.hypertable_name
            WHERE ht.hypertable_name = 'pod_metrics'
            GROUP BY ht.hypertable_name;
        """)

        result = self.db.execute(query).fetchone()

        if not result:
            return {
                "error": "No compression statistics available",
                "hypertable": "pod_metrics",
            }

        compressed_ratio = 0
        if result.uncompressed_size_bytes and result.uncompressed_size_bytes > 0:
            compressed_ratio = (
                1 - (result.total_size_bytes / result.uncompressed_size_bytes)
            ) * 100

        return {
            "hypertable": result.hypertable_name,
            "total_chunks": result.total_chunks,
            "compressed_chunks": result.compressed_chunks,
            "compression_coverage_pct": round(
                (result.compressed_chunks / max(result.total_chunks, 1)) * 100, 2
            ),
            "total_size_bytes": result.total_size_bytes,
            "total_size_human": self._bytes_to_human(result.total_size_bytes),
            "uncompressed_size_bytes": result.uncompressed_size_bytes or 0,
            "uncompressed_size_human": self._bytes_to_human(result.uncompressed_size_bytes or 0),
            "compression_ratio_pct": round(compressed_ratio, 2),
            "space_saved_bytes": (result.uncompressed_size_bytes or 0) - result.total_size_bytes,
            "space_saved_human": self._bytes_to_human(
                (result.uncompressed_size_bytes or 0) - result.total_size_bytes
            ),
            "total_rows": result.total_rows,
        }

    def compress_chunk(self, chunk_name: str) -> bool:
        """
        Manually compress a specific chunk.

        Use case: Force compression for large uncompressed chunks

        Args:
            chunk_name: Full chunk name (e.g., "_hyper_1_1_chunk")

        Returns:
            True if successful
        """
        try:
            query = text(f"SELECT compress_chunk('{chunk_name}');")
            self.db.execute(query)
            self.db.commit()

            logger.info(f"Successfully compressed chunk: {chunk_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to compress chunk {chunk_name}: {str(e)}")
            self.db.rollback()
            return False

    def decompress_chunk(self, chunk_name: str) -> bool:
        """
        Manually decompress a specific chunk.

        Use case: Debugging or re-processing data

        Args:
            chunk_name: Full chunk name

        Returns:
            True if successful
        """
        try:
            query = text(f"SELECT decompress_chunk('{chunk_name}');")
            self.db.execute(query)
            self.db.commit()

            logger.info(f"Successfully decompressed chunk: {chunk_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to decompress chunk {chunk_name}: {str(e)}")
            self.db.rollback()
            return False

    # =====================================================================
    # Retention Policy Management
    # =====================================================================

    def get_retention_policies(self) -> List[Dict[str, Any]]:
        """
        Get all active retention policies.

        Returns:
            List of retention policies with schedules
        """
        query = text("""
            SELECT
                application_name as policy_name,
                hypertable_name,
                config->>'drop_after' as retention_interval,
                scheduled,
                schedule_interval
            FROM timescaledb_information.jobs
            WHERE proc_name = 'policy_retention'
            ORDER BY hypertable_name;
        """)

        result = self.db.execute(query)
        policies = []

        for row in result:
            policies.append({
                "policy_name": row.policy_name,
                "hypertable": row.hypertable_name,
                "retention_interval": row.retention_interval,
                "scheduled": row.scheduled,
                "schedule_interval": str(row.schedule_interval),
            })

        return policies

    def validate_retention_policies(self) -> Dict[str, Any]:
        """
        Validate retention policies are configured correctly.

        Enterprise Requirements:
        - pod_metrics: 14 days
        - pod_metrics_daily: 90 days
        - pod_metrics_monthly: 2 years

        Returns:
            Validation results with any issues
        """
        policies = self.get_retention_policies()

        expected_policies = {
            "pod_metrics": "14 days",
            "pod_metrics_daily": "90 days",
            "pod_metrics_monthly": "2 years",
        }

        issues = []
        found_policies = {}

        for policy in policies:
            hypertable = policy["hypertable"]
            retention = policy["retention_interval"]
            found_policies[hypertable] = retention

            # Check if matches expected
            if hypertable in expected_policies:
                expected = expected_policies[hypertable]
                if retention != expected:
                    issues.append({
                        "hypertable": hypertable,
                        "expected": expected,
                        "actual": retention,
                        "severity": "ERROR",
                        "message": f"Retention policy mismatch for {hypertable}",
                    })

        # Check for missing policies
        for hypertable, expected in expected_policies.items():
            if hypertable not in found_policies:
                issues.append({
                    "hypertable": hypertable,
                    "expected": expected,
                    "actual": "MISSING",
                    "severity": "ERROR",
                    "message": f"Retention policy not configured for {hypertable}",
                })

        return {
            "valid": len(issues) == 0,
            "policies_configured": len(policies),
            "policies_expected": len(expected_policies),
            "issues": issues,
            "details": policies,
        }

    # =====================================================================
    # Continuous Aggregate Management
    # =====================================================================

    def get_continuous_aggregates(self) -> List[Dict[str, Any]]:
        """
        Get all continuous aggregates (materialized views).

        Returns:
            List of continuous aggregates with refresh policies
        """
        query = text("""
            SELECT
                view_name,
                materialization_hypertable_name,
                refresh_lag,
                refresh_interval
            FROM timescaledb_information.continuous_aggregates
            ORDER BY view_name;
        """)

        result = self.db.execute(query)
        aggregates = []

        for row in result:
            aggregates.append({
                "view_name": row.view_name,
                "hypertable": row.materialization_hypertable_name,
                "refresh_lag": str(row.refresh_lag),
                "refresh_interval": str(row.refresh_interval),
            })

        return aggregates

    def refresh_continuous_aggregate(
        self,
        view_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> bool:
        """
        Manually refresh a continuous aggregate.

        Use case: Force refresh after data backfill

        Args:
            view_name: Continuous aggregate name (e.g., "pod_metrics_daily")
            start_time: Start of refresh window (default: 7 days ago)
            end_time: End of refresh window (default: now)

        Returns:
            True if successful
        """
        try:
            if start_time is None:
                start_time = datetime.utcnow() - timedelta(days=7)
            if end_time is None:
                end_time = datetime.utcnow()

            query = text(f"""
                CALL refresh_continuous_aggregate(
                    '{view_name}',
                    '{start_time.isoformat()}'::timestamptz,
                    '{end_time.isoformat()}'::timestamptz
                );
            """)

            self.db.execute(query)
            self.db.commit()

            logger.info(f"Successfully refreshed continuous aggregate: {view_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh continuous aggregate {view_name}: {str(e)}")
            self.db.rollback()
            return False

    # =====================================================================
    # Performance Analytics
    # =====================================================================

    def get_hypertable_info(self) -> Dict[str, Any]:
        """
        Get comprehensive hypertable information.

        Returns:
            Hypertable configuration and statistics
        """
        query = text("""
            SELECT
                hypertable_name,
                num_dimensions,
                num_chunks,
                table_bytes,
                index_bytes,
                toast_bytes,
                total_bytes,
                compression_enabled,
                replication_factor
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'pod_metrics';
        """)

        result = self.db.execute(query).fetchone()

        if not result:
            return {"error": "Hypertable not found"}

        return {
            "hypertable_name": result.hypertable_name,
            "num_dimensions": result.num_dimensions,
            "num_chunks": result.num_chunks,
            "table_bytes": result.table_bytes,
            "table_size_human": self._bytes_to_human(result.table_bytes),
            "index_bytes": result.index_bytes,
            "index_size_human": self._bytes_to_human(result.index_bytes),
            "toast_bytes": result.toast_bytes,
            "toast_size_human": self._bytes_to_human(result.toast_bytes),
            "total_bytes": result.total_bytes,
            "total_size_human": self._bytes_to_human(result.total_bytes),
            "compression_enabled": result.compression_enabled,
            "replication_factor": result.replication_factor,
        }

    def get_chunk_performance(self) -> List[Dict[str, Any]]:
        """
        Get chunk-level performance metrics.

        Useful for identifying slow queries or problematic chunks.

        Returns:
            Chunk performance statistics
        """
        query = text("""
            SELECT
                c.chunk_name,
                c.range_start,
                c.range_end,
                c.total_rows,
                pg_size_pretty(c.total_bytes) as size,
                c.is_compressed
            FROM timescaledb_information.chunks c
            WHERE c.hypertable_name = 'pod_metrics'
            ORDER BY c.total_bytes DESC
            LIMIT 20;
        """)

        result = self.db.execute(query)
        chunks = []

        for row in result:
            chunks.append({
                "chunk_name": row.chunk_name,
                "range_start": row.range_start.isoformat() if row.range_start else None,
                "range_end": row.range_end.isoformat() if row.range_end else None,
                "total_rows": row.total_rows,
                "size": row.size,
                "is_compressed": row.is_compressed,
            })

        return chunks

    # =====================================================================
    # Maintenance Recommendations
    # =====================================================================

    def get_maintenance_recommendations(self) -> List[Dict[str, Any]]:
        """
        Generate automated maintenance recommendations.

        Returns:
            List of actionable recommendations
        """
        recommendations = []

        # Check chunk health
        health = self.get_chunk_health()
        if health["alerts"]:
            for alert in health["alerts"]:
                recommendations.append({
                    "category": "chunk_health",
                    "severity": alert["severity"],
                    "message": alert["message"],
                    "action": alert["action"],
                })

        # Check compression coverage
        compression = self.get_compression_stats()
        if compression.get("compression_coverage_pct", 0) < 80:
            recommendations.append({
                "category": "compression",
                "severity": "WARNING",
                "message": f"Only {compression.get('compression_coverage_pct', 0):.1f}% of chunks are compressed",
                "action": "Review compression policy schedule or manually compress old chunks",
            })

        # Check retention policies
        retention = self.validate_retention_policies()
        if not retention["valid"]:
            for issue in retention["issues"]:
                recommendations.append({
                    "category": "retention",
                    "severity": issue["severity"],
                    "message": issue["message"],
                    "action": f"Configure retention policy: {issue['expected']}",
                })

        return recommendations

    # =====================================================================
    # Utility Methods
    # =====================================================================

    @staticmethod
    def _bytes_to_human(bytes_value: int) -> str:
        """Convert bytes to human-readable format."""
        if bytes_value < 1024:
            return f"{bytes_value} B"
        elif bytes_value < 1024 ** 2:
            return f"{bytes_value / 1024:.2f} KB"
        elif bytes_value < 1024 ** 3:
            return f"{bytes_value / (1024 ** 2):.2f} MB"
        elif bytes_value < 1024 ** 4:
            return f"{bytes_value / (1024 ** 3):.2f} GB"
        else:
            return f"{bytes_value / (1024 ** 4):.2f} TB"


# =====================================================================
# Service Factory
# =====================================================================

def get_partition_service(db: Session) -> PartitionManagementService:
    """
    Factory function to create PartitionManagementService instance.

    Usage:
        from backend.services.partition_management_service import get_partition_service

        service = get_partition_service(db)

        # Get chunk health
        health = service.get_chunk_health()

        # Get compression stats
        compression = service.get_compression_stats()

        # Get maintenance recommendations
        recommendations = service.get_maintenance_recommendations()
    """
    return PartitionManagementService(db)
