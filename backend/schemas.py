"""
AWS Spot Optimizer - Validation Schemas
========================================
Marshmallow schemas for input validation
"""

from marshmallow import Schema, fields, validate


class AgentRegistrationSchema(Schema):
    """Validation schema for agent registration"""
    client_token = fields.Str(required=True)
    hostname = fields.Str(required=False, validate=validate.Length(max=255))
    logical_agent_id = fields.Str(required=True, validate=validate.Length(max=255))
    instance_id = fields.Str(required=True)
    instance_type = fields.Str(required=True, validate=validate.Length(max=64))
    region = fields.Str(required=True)
    az = fields.Str(required=True)
    ami_id = fields.Str(required=False)
    mode = fields.Str(required=False, missing='unknown', validate=validate.OneOf(['spot', 'ondemand', 'unknown']))
    agent_version = fields.Str(required=False, validate=validate.Length(max=32))
    private_ip = fields.Str(required=False, validate=validate.Length(max=45))
    public_ip = fields.Str(required=False, validate=validate.Length(max=45))


class HeartbeatSchema(Schema):
    """Validation schema for heartbeat"""
    status = fields.Str(required=True, validate=validate.OneOf(['online', 'offline', 'disabled', 'switching', 'error', 'deleted']))
    instance_id = fields.Str(required=False)
    instance_type = fields.Str(required=False)
    mode = fields.Str(required=False)
    az = fields.Str(required=False)


class PricingReportSchema(Schema):
    """Validation schema for pricing report"""
    instance = fields.Dict(required=True)
    pricing = fields.Dict(required=True)


class SwitchReportSchema(Schema):
    """Validation schema for switch report"""
    old_instance = fields.Dict(required=True)
    new_instance = fields.Dict(required=True)
    timing = fields.Dict(required=True)
    pricing = fields.Dict(required=True)
    trigger = fields.Str(required=True)
    command_id = fields.Str(required=False)


class ForceSwitchSchema(Schema):
    """Validation schema for force switch"""
    target = fields.Str(required=True, validate=validate.OneOf(['ondemand', 'pool', 'spot']))
    pool_id = fields.Str(required=False, validate=validate.Length(max=128))
    new_instance_type = fields.Str(required=False, validate=validate.Length(max=50))
