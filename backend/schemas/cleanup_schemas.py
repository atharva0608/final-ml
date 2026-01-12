"""
Cleanup Module Schemas

Pydantic models for Resource Hygiene & Cleanup operations
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from decimal import Decimal
from datetime import datetime


class ResourceType(str, Enum):
    """Types of AWS resources that can be scanned and cleaned"""
    INSTANCE = "instance"
    VOLUME = "volume"
    SNAPSHOT = "snapshot"
    ELASTIC_IP = "elastic_ip"


class CleanupStatus(str, Enum):
    """Status of a resource in the cleanup process"""
    ACTIVE = "active"
    ORPHANED = "orphaned"
    TERMINATING = "terminating"
    DELETED = "deleted"
    STOPPED = "stopped"
    AVAILABLE = "available"
    UNATTACHED = "unattached"


class ActionType(str, Enum):
    """Types of cleanup actions that can be performed"""
    AUTHORIZE = "authorize"
    UNAUTHORIZE = "unauthorize"
    TERMINATE = "terminate"
    DELETE = "delete"
    RELEASE = "release"


class ResourceItem(BaseModel):
    """Individual resource item in cleanup scan results"""
    id: str = Field(..., description="AWS Resource ID (instance-id, volume-id, etc.)")
    name: Optional[str] = Field(None, description="Resource name tag or identifier")
    type: ResourceType = Field(..., description="Type of AWS resource")
    status: CleanupStatus = Field(..., description="Current status of the resource")
    cost_per_month: Decimal = Field(..., description="Estimated monthly cost in USD")
    region: str = Field(..., description="AWS region where resource is located")
    is_authorized: bool = Field(False, description="Whether resource is marked as authorized")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional resource metadata")
    discovered_at: Optional[datetime] = Field(None, description="When the resource was discovered")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat() if v else None
        }


class CleanupSummary(BaseModel):
    """Summary of cleanup scan results for an AWS account"""
    account_id: str = Field(..., description="AWS Account UUID")
    account_name: Optional[str] = Field(None, description="AWS Account name")
    total_savings_potential: Decimal = Field(..., description="Total monthly savings if all resources cleaned")
    unauthorized_instances_count: int = Field(0, description="Count of instances not in managed clusters")
    orphaned_volumes_count: int = Field(0, description="Count of unattached EBS volumes")
    zombie_snapshots_count: int = Field(0, description="Count of snapshots with deleted source volumes")
    unused_ips_count: int = Field(0, description="Count of unassociated Elastic IPs")
    scanned_regions: List[str] = Field(default_factory=list, description="AWS regions that were scanned")
    instances: List[ResourceItem] = Field(default_factory=list, description="Unauthorized instance details")
    volumes: List[ResourceItem] = Field(default_factory=list, description="Orphaned volume details")
    snapshots: List[ResourceItem] = Field(default_factory=list, description="Zombie snapshot details")
    elastic_ips: List[ResourceItem] = Field(default_factory=list, description="Unused Elastic IP details")
    scanned_at: datetime = Field(default_factory=datetime.utcnow, description="When the scan was performed")

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat() if v else None
        }


class CleanupAction(BaseModel):
    """Request to perform cleanup action on resources"""
    resource_ids: List[str] = Field(..., min_items=1, description="List of AWS Resource IDs to act upon")
    action_type: ActionType = Field(..., description="Type of action to perform")
    resource_type: ResourceType = Field(..., description="Type of resources being acted upon")
    reason: Optional[str] = Field(None, description="Optional reason for the action")

    class Config:
        schema_extra = {
            "example": {
                "resource_ids": ["i-1234567890abcdef0", "i-0987654321fedcba0"],
                "action_type": "terminate",
                "resource_type": "instance",
                "reason": "Orphaned test instances from previous sprint"
            }
        }


class CleanupActionResponse(BaseModel):
    """Response after executing cleanup action"""
    success: bool = Field(..., description="Whether the action completed successfully")
    affected_resources: List[str] = Field(default_factory=list, description="Resource IDs that were successfully affected")
    failed_resources: List[str] = Field(default_factory=list, description="Resource IDs that failed to process")
    errors: List[str] = Field(default_factory=list, description="Error messages for failed resources")
    executed_at: datetime = Field(default_factory=datetime.utcnow, description="When the action was executed")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class RegionScanProgress(BaseModel):
    """Progress tracking for multi-region scanning"""
    region: str = Field(..., description="AWS region being scanned")
    status: str = Field(..., description="Scan status: pending, scanning, completed, failed")
    resources_found: int = Field(0, description="Number of resources found in this region")
    error: Optional[str] = Field(None, description="Error message if scan failed")

    class Config:
        schema_extra = {
            "example": {
                "region": "us-east-1",
                "status": "completed",
                "resources_found": 15,
                "error": None
            }
        }
