"""
Template Routes - Serves CloudFormation templates for client onboarding
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
import os

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get(
    "/aws-onboarding",
    summary="Download AWS CloudFormation template",
    description="Get the CloudFormation template for creating cross-account IAM role"
)
def get_aws_onboarding_template():
    """
    Returns the CloudFormation YAML template for AWS onboarding.
    Clients deploy this in their AWS account to create the cross-account role.
    """
    template_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "templates",
        "aws",
        "read-only-role.yaml"
    )
    
    if os.path.exists(template_path):
        return FileResponse(
            template_path,
            media_type="application/x-yaml",
            filename="spot-optimizer-role.yaml",
            headers={
                "Content-Disposition": "attachment; filename=spot-optimizer-role.yaml"
            }
        )
    else:
        # Return inline template if file doesn't exist
        template_content = """AWSTemplateFormatVersion: '2010-09-09'
Description: 'Creates a cross-account IAM Role for the Spot Optimization Platform.'

Parameters:
  ExternalId:
    Type: String
    Description: 'Unique Security Token provided by the dashboard'
  PlatformPrincipal:
    Type: String
    Description: 'The AWS Account ID of the Optimization Platform'

Resources:
  OptimizationRole:
    Type: 'AWS::IAM::Role'
    Properties:
      RoleName: !Sub 'SpotOptimizer-Role-${ExternalId}'
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS: !Ref PlatformPrincipal
            Action: 'sts:AssumeRole'
            Condition:
              StringEquals:
                'sts:ExternalId': !Ref ExternalId
      ManagedPolicyArns:
        - 'arn:aws:iam::aws:policy/SecurityAudit'
        - 'arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess'
        - 'arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess'

Outputs:
  RoleArn:
    Description: 'The ARN of the created role to paste in the dashboard'
    Value: !GetAtt OptimizationRole.Arn
"""
        return Response(
            content=template_content,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": "attachment; filename=spot-optimizer-role.yaml"
            }
        )

@router.get(
    "/",
    summary="List available templates",
    description="Get a list of all available CloudFormation templates"
)
def list_templates():
    return {
        "items": [
            {
                "id": "aws-onboarding",
                "name": "AWS Cross-Account Role",
                "description": "CloudFormation template to create the necessary IAM role for Spot Optimizer.",
                "url": "/api/v1/templates/aws-onboarding",
                "type": "cloudformation"
            }
        ]
    }
