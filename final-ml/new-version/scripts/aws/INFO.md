# AWS Scripts - Component Information

> **Last Updated**: 2026-01-02 16:00:00
> **Maintainer**: LLM Agent

---

## Folder Purpose
AWS boto3 scripts for EC2, ASG, and Spot Fleet management. These scripts are called by CORE-EXEC and workers to execute optimization actions.

---

## Component Table

| File Name | Script ID | AWS APIs | Purpose | Called By | Status |
|-----------|-----------|----------|---------|-----------|--------|
| terminate_instance.py | SCRIPT-TERM-01 | ec2.terminate_instances() | Gracefully terminate EC2 instances with volume preservation | CORE-EXEC | ✅ Complete |
| launch_spot.py | SCRIPT-SPOT-01 | ec2.run_instances() | Launch Spot instances with fallback instance types | CORE-EXEC | ✅ Complete |
| detach_volume.py | SCRIPT-VOL-01 | ec2.detach_volume(), ec2.create_snapshot() | Detach EBS volumes with optional snapshot | CORE-EXEC | ✅ Complete |
| update_asg.py | SCRIPT-ASG-01 | autoscaling.update_auto_scaling_group() | Update ASG capacity and configuration | CORE-EXEC, WORK-HIB-01 | ✅ Complete |

---

## Recent Changes

### [2026-01-02 16:00:00] - Phase 9: AWS Boto3 Scripts Implementation Complete
**Changed By**: LLM Agent
**Reason**: Complete all 4 AWS automation scripts for Phase 9
**Impact**: Full AWS script implementation totaling ~1,200 lines of code
**Files Modified**:
- Created scripts/aws/terminate_instance.py (~280 lines) - Graceful instance termination
- Created scripts/aws/launch_spot.py (~400 lines) - Spot instance launching with fallback
- Created scripts/aws/detach_volume.py (~180 lines) - EBS volume detachment
- Created scripts/aws/update_asg.py (~200 lines) - ASG capacity updates
- Updated scripts/aws/INFO.md (this file)
**Feature IDs Affected**: SCRIPT-TERM-01, SCRIPT-SPOT-01, SCRIPT-VOL-01, SCRIPT-ASG-01
**Breaking Changes**: No
**Key Features Implemented**:
- STS role assumption for cross-account access
- Dry-run mode for all scripts
- Volume preservation before instance termination
- Multiple instance type fallback for Spot launches
- Snapshot creation before volume detachment
- ASG process suspension/resumption
- Comprehensive error handling and logging
- CLI interfaces with argparse

---

## Features

### All Scripts Support:
- **DryRun mode**: Validate operations without executing
- **IAM role assumption**: Cross-account access via STS
- **Error handling**: Comprehensive AWS error handling
- **Logging**: Structured logging with timestamps
- **CLI**: Command-line interface with argparse

### terminate_instance.py:
- Graceful termination with wait option
- Volume preservation (set DeleteOnTermination=False)
- Instance state validation
- Waiter for termination completion

### launch_spot.py:
- Multiple instance type fallback
- Launch template support
- Max Spot price specification
- Tag propagation to instances and volumes
- Interruption behavior configuration

### detach_volume.py:
- Force detachment option
- Snapshot creation before detachment
- Wait for volume availability
- Volume state validation

### update_asg.py:
- Update desired/min/max capacity
- Launch template version updates
- Suspend/resume scaling processes
- Current configuration display

---

## Usage Examples

### Terminate Instance
```bash
# Basic termination
python terminate_instance.py --instance-id i-1234567890abcdef0 --region us-east-1

# Preserve volumes
python terminate_instance.py --instance-id i-1234567890abcdef0 --region us-east-1 --preserve-volumes

# Dry run
python terminate_instance.py --instance-id i-1234567890abcdef0 --region us-east-1 --dry-run

# With role assumption
python terminate_instance.py --instance-id i-1234567890abcdef0 --region us-east-1 \
    --role-arn arn:aws:iam::123456789012:role/SpotOptimizer \
    --external-id abc123
```

### Launch Spot Instance
```bash
# Launch with fallback instance types
python launch_spot.py --instance-types m5.large,m5.xlarge --region us-east-1 \
    --launch-template lt-1234567890abcdef0

# Launch with AMI and networking
python launch_spot.py --instance-types m5.large --region us-east-1 \
    --ami ami-12345678 --subnet subnet-12345678 \
    --security-groups sg-12345678,sg-87654321

# With max price
python launch_spot.py --instance-types m5.large --region us-east-1 \
    --launch-template lt-1234567890abcdef0 --max-price 0.10

# With tags
python launch_spot.py --instance-types m5.large --region us-east-1 \
    --launch-template lt-1234567890abcdef0 \
    --tags '{"Name": "SpotOptimizer", "Env": "prod"}'
```

### Detach Volume
```bash
# Basic detachment
python detach_volume.py --volume-id vol-1234567890abcdef0 --region us-east-1

# Force detachment
python detach_volume.py --volume-id vol-1234567890abcdef0 --region us-east-1 --force

# Create snapshot before detaching
python detach_volume.py --volume-id vol-1234567890abcdef0 --region us-east-1 --snapshot
```

### Update ASG
```bash
# Update capacity
python update_asg.py --asg-name my-cluster-asg --region us-east-1 --desired-capacity 5

# Update min/max/desired
python update_asg.py --asg-name my-cluster-asg --region us-east-1 \
    --min 2 --max 10 --desired 5

# Suspend scaling processes
python update_asg.py --asg-name my-cluster-asg --region us-east-1 \
    --suspend-processes Launch,Terminate

# Resume scaling processes
python update_asg.py --asg-name my-cluster-asg --region us-east-1 \
    --resume-processes Launch,Terminate
```

---

## Dependencies

### External Dependencies
- **boto3**: AWS SDK for Python
- **botocore**: Low-level AWS client

### Internal Dependencies
- Called by `backend/core/action_executor.py` (CORE-EXEC)
- Called by `backend/workers/tasks/hibernation_worker.py` (WORK-HIB-01)

---

## Error Handling

All scripts handle:
- **InvalidInstanceID.NotFound**: Instance doesn't exist
- **InvalidVolume.NotFound**: Volume doesn't exist
- **InsufficientInstanceCapacity**: No Spot capacity available
- **SpotMaxPriceTooLow**: Max price below current Spot price
- **DryRunOperation**: Dry run validation successful
- **UnauthorizedOperation**: IAM permission denied

Scripts return:
```python
{
    "success": bool,
    "error": Optional[str],
    "error_code": Optional[str],
    # ... script-specific fields
}
```

---

## Security

- All scripts support STS role assumption for cross-account access
- External ID support for secure role assumption
- No hard-coded credentials
- Follows AWS IAM best practices

---

## Testing

```bash
# Always test with dry-run first
python terminate_instance.py --instance-id i-xxx --region us-east-1 --dry-run
python launch_spot.py --instance-types m5.large --region us-east-1 --dry-run
python detach_volume.py --volume-id vol-xxx --region us-east-1 --dry-run
python update_asg.py --asg-name my-asg --region us-east-1 --desired-capacity 5 --dry-run
```
