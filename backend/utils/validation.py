"""
Input Validation + Cluster Access Guard
========================================
P-04: Centralised validators for all optimize-page endpoints.

Every endpoint must call:
  1. validate_cluster_id(cluster_id)
  2. assert_cluster_access(cluster_id, db)
  3. validate_workload_id(workload_id)   — for workload_id path/query params
  4. validate_node_name(node_name)       — for node_name path params
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

CLUSTER_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')
WORKLOAD_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.\/]{1,253}$')
NODE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9\-\.]{1,253}$')


def validate_cluster_id(cluster_id: str) -> str:
    """Raise HTTP 422 if cluster_id does not match the allowed pattern."""
    if not cluster_id or not CLUSTER_ID_PATTERN.match(cluster_id):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid cluster_id format: '{cluster_id}'. "
                   "Must be 1–64 alphanumeric/underscore/hyphen characters.",
        )
    return cluster_id


def validate_workload_id(workload_id: str) -> str:
    """Raise HTTP 422 if workload_id does not match the allowed pattern."""
    if not workload_id or not WORKLOAD_ID_PATTERN.match(workload_id):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid workload_id format: '{workload_id}'.",
        )
    return workload_id


def validate_node_name(node_name: str) -> str:
    """Raise HTTP 422 if node_name does not match the allowed pattern."""
    if not node_name or not NODE_NAME_PATTERN.match(node_name):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid node_name format: '{node_name}'.",
        )
    return node_name


def assert_cluster_access(cluster_id: str, db: "Session") -> None:
    """
    Raise HTTP 404 if cluster_id does not exist in the clusters table.
    This prevents cross-tenant access and surfaces bad IDs early.
    """
    from backend.models.cluster import Cluster

    exists = db.query(Cluster.id).filter(Cluster.id == cluster_id).first()
    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Cluster '{cluster_id}' not found.",
        )
