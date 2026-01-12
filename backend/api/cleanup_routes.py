"""
Cleanup API Routes

HTTP endpoints for Resource Hygiene & Cleanup operations with multi-region support
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.core.database import get_db
from backend.core.dependencies import get_current_user_context, UserContext
from backend.services.cleanup_service import get_cleanup_service, CleanupService
from backend.schemas.cleanup_schemas import (
    CleanupSummary,
    CleanupAction,
    CleanupActionResponse
)
from backend.core.exceptions import ResourceNotFoundError, ValidationError
from backend.core.logger import StructuredLogger

router = APIRouter(prefix="/cleanup", tags=["cleanup"])
logger = StructuredLogger(__name__)


@router.get("/scan/{account_id}", response_model=CleanupSummary, summary="Scan account for orphaned resources across all regions")
def scan_account_resources(
    account_id: str,
    user_context: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
) -> CleanupSummary:
    """
    Scan AWS account for orphaned/zombie resources across ALL enabled regions

    This endpoint analyzes the AWS account in all enabled regions and identifies:
    - **Instances**: EC2 instances not part of managed clusters
    - **Orphaned EBS volumes**: Unattached volumes (status=available)
    - **Zombie snapshots**: Snapshots whose source volume no longer exists
    - **Unused Elastic IPs**: IPs not associated with any instance

    **Multi-Region Scanning**: The service automatically discovers all enabled
    regions in your AWS account and scans each one, providing comprehensive
    visibility across your entire AWS infrastructure.

    Args:
        account_id: AWS Account UUID to scan
        user_context: Current authenticated user (from JWT token)
        db: Database session (injected)

    Returns:
        CleanupSummary with:
        - All orphaned resources grouped by type
        - Total potential monthly savings
        - List of scanned regions
        - Resource counts and details

    Raises:
        404: Account not found or user doesn't have access
        400: Invalid account credentials or permissions
        500: Scan operation failed
    """
    try:
        cleanup_service = get_cleanup_service(db)
        summary = cleanup_service.scan_resources(account_id, user_context.user_id)

        logger.info(
            "Cleanup scan completed",
            user_id=user_context.user_id,
            account_id=account_id,
            total_savings=float(summary.total_savings_potential),
            regions_scanned=len(summary.scanned_regions),
            total_resources=sum([
                summary.unauthorized_instances_count,
                summary.orphaned_volumes_count,
                summary.zombie_snapshots_count,
                summary.unused_ips_count
            ])
        )

        return summary

    except ResourceNotFoundError as e:
        logger.warning(f"Resource not found during cleanup scan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        logger.warning(f"Validation error during cleanup scan: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Cleanup scan failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cleanup scan failed: {str(e)}"
        )


@router.post("/action/{account_id}", response_model=CleanupActionResponse, summary="Execute cleanup action on resources")
def execute_cleanup_action(
    account_id: str,
    action: CleanupAction,
    user_context: UserContext = Depends(get_current_user_context),
    db: Session = Depends(get_db)
) -> CleanupActionResponse:
    """
    Execute cleanup action on selected orphaned resources across regions

    This endpoint performs the requested action on resources identified during scanning.
    The service automatically searches across all regions to find and act on the specified
    resource IDs.

    **Supported Actions:**
    - **AUTHORIZE**: Mark resources as authorized (whitelist them from future scans)
    - **UNAUTHORIZE**: Remove authorization (return to orphaned state)
    - **TERMINATE**: Terminate EC2 instances
    - **DELETE**: Delete EBS volumes or snapshots
    - **RELEASE**: Release Elastic IPs

    **Multi-Region Support**: Actions are executed across all regions automatically.
    You don't need to specify the region - the service will locate each resource
    and execute the action in the correct region.

    Args:
        account_id: AWS Account UUID
        action: CleanupAction with:
            - resource_ids: List of AWS resource IDs
            - action_type: Action to perform (authorize/terminate/delete/release)
            - resource_type: Type of resources (instance/volume/snapshot/elastic_ip)
            - reason: Optional reason for the action
        user_context: Current authenticated user
        db: Database session

    Returns:
        CleanupActionResponse with:
        - success: True if all resources processed successfully
        - affected_resources: List of successfully processed resource IDs
        - failed_resources: List of resource IDs that failed
        - errors: Error messages for failures

    Raises:
        400: Invalid action, parameters, or action not allowed for resource type
        404: Account not found or user doesn't have access
        500: Action execution failed

    Example:
        ```json
        {
            "resource_ids": ["i-1234567890abcdef0", "i-0987654321fedcba0"],
            "action_type": "terminate",
            "resource_type": "instance",
            "reason": "Orphaned test instances from previous sprint"
        }
        ```
    """
    try:
        cleanup_service = get_cleanup_service(db)
        response = cleanup_service.execute_action(action, account_id, user_context.user_id)

        logger.info(
            "Cleanup action executed",
            user_id=user_context.user_id,
            account_id=account_id,
            action_type=action.action_type,
            resource_type=action.resource_type,
            affected_count=len(response.affected_resources),
            failed_count=len(response.failed_resources),
            success=response.success
        )

        return response

    except ResourceNotFoundError as e:
        logger.warning(f"Resource not found during cleanup action: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        logger.warning(f"Validation error during cleanup action: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Cleanup action failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cleanup action failed: {str(e)}"
        )
