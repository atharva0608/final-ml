import os
import boto3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.account import Account

engine = create_engine("postgresql://user:password@localhost/spot_optimizer")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

account = db.query(Account).first()
print(f"Account: {account.id}, Role: {account.role_arn}, ExtID: {account.external_id}")

sts = boto3.client('sts')
assumed = sts.assume_role(
    RoleArn=account.role_arn,
    RoleSessionName="TestScan",
    ExternalId=account.external_id
)
creds = assumed['Credentials']
eks = boto3.client(
    'eks',
    region_name='us-east-1',
    aws_access_key_id=creds['AccessKeyId'],
    aws_secret_access_key=creds['SecretAccessKey'],
    aws_session_token=creds['SessionToken']
)
print("EKS Clusters:", eks.list_clusters())
