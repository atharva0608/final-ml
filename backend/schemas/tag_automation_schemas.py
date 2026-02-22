"""
Tag Automation Rule Pydantic Schemas
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import re


class AutomationRuleCreate(BaseModel):
    """Schema for creating an automation rule"""
    name: str = Field(..., min_length=1, max_length=255, description="Rule name")
    trigger_expr: str = Field(..., max_length=100, description="Trigger expression e.g. 'score < 20'")
    resource_types: List[str] = Field(..., min_items=1, description="Resource types: ['EC2','RDS']")
    grace_days: int = Field(30, ge=0, le=90, description="Grace period in days")
    action: str = Field(..., description="Action: notify|flag|stop|auto_tag|delete")
    notification_channels: List[str] = Field(default_factory=list, description="Channels: email,slack,pagerduty,webhook,jira")
    safety_conditions: List[str] = Field(default_factory=list, description="Safety conditions (AND logic)")

    @validator('action')
    def validate_action(cls, v):
        allowed = ['notify', 'flag', 'stop', 'auto_tag', 'delete']
        if v not in allowed:
            raise ValueError(f'action must be one of: {allowed}')
        return v

    @validator('trigger_expr')
    def validate_trigger(cls, v):
        # Must match: 'score < N' | 'score == N' | 'score > N' | 'missing:KEY' | 'unauthorized'
        score_pattern = r'^score\s*(==|<|>)\s*\d+$'
        missing_pattern = r'^missing:\w+$'
        if re.match(score_pattern, v) or re.match(missing_pattern, v) or v == 'unauthorized':
            return v
        raise ValueError("trigger_expr must be 'score <|==|> N', 'missing:KEY', or 'unauthorized'")

    @validator('safety_conditions', each_item=True)
    def validate_safety(cls, v):
        allowed = ['not_system_managed', 'older_than_30d', 'has_cost', 'not_prod', 'has_iam_profile', 'no_recent_activity']
        if v not in allowed:
            raise ValueError(f'safety_condition must be one of: {allowed}')
        return v

    @validator('notification_channels', each_item=True)
    def validate_channels(cls, v):
        allowed = ['email', 'slack', 'pagerduty', 'webhook', 'jira']
        if v not in allowed:
            raise ValueError(f'notification_channel must be one of: {allowed}')
        return v


class AutomationRuleUpdate(BaseModel):
    """Schema for updating an automation rule"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    trigger_expr: Optional[str] = None
    resource_types: Optional[List[str]] = None
    grace_days: Optional[int] = Field(None, ge=0, le=90)
    action: Optional[str] = None
    notification_channels: Optional[List[str]] = None
    safety_conditions: Optional[List[str]] = None


class AutomationRuleResponse(BaseModel):
    """Schema for automation rule response"""
    id: str
    name: str
    trigger_expr: str
    resource_types: List[str]
    grace_days: int
    action: str
    notification_channels: List[str]
    safety_conditions: List[str]
    enabled: bool
    last_run_at: Optional[datetime] = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AutomationSummary(BaseModel):
    """Summary stats for automation rules"""
    next_cycle_at: Optional[datetime] = None
    resources_in_grace_period: int = 0
    pending_deletion: int = 0


class AutomationRulesListResponse(BaseModel):
    """Response for listing automation rules with summary"""
    rules: List[AutomationRuleResponse]
    summary: AutomationSummary


class AutomationLogEntry(BaseModel):
    """Single automation log entry"""
    id: str
    resource_id: str
    resource_type: str
    action_taken: str
    reason: str
    monthly_cost: Optional[float] = None
    outcome: str
    error_message: Optional[str] = None
    executed_at: datetime

    class Config:
        from_attributes = True


class AutomationLogResponse(BaseModel):
    """Paginated automation log"""
    entries: List[AutomationLogEntry]
    total: int
    page: int
    per_page: int
