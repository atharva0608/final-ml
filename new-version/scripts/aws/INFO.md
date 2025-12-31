# AWS Scripts - Component Information

> **Last Updated**: 2025-12-31 12:36:00
> **Maintainer**: LLM Agent

## Folder Purpose
AWS boto3 scripts for EC2, ASG, and Spot Fleet management.

## Planned Scripts

| File Name | Script ID | AWS APIs | Purpose | Called By | Status |
|-----------|-----------|----------|---------|-----------|--------|
| terminate_instance.py | SCRIPT-TERM-01 | ec2.terminate_instances() | Gracefully drain and terminate node | CORE-EXEC | Pending |
| launch_spot.py | SCRIPT-SPOT-01 | ec2.request_spot_fleet() | Request Spot Fleet | CORE-EXEC | Pending |
| detach_volume.py | SCRIPT-VOL-01 | ec2.detach_volume() | Detach EBS volumes | CORE-EXEC | Pending |
| update_asg.py | SCRIPT-ASG-01 | autoscaling.update_auto_scaling_group() | Update ASG configuration | CORE-EXEC, WORK-HIB-01 | Pending |

## Features
- DryRun mode support
- IAM role assumption via STS
- Comprehensive error handling
- Audit logging integration
- Rollback logic on failure

## Dependencies
- boto3 (AWS SDK)
- SQLAlchemy (for audit logging)
