import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.models.account import Account
from backend.schemas.account_schemas import AccountCreate

class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def verify_connection(self, role_arn: str, external_id: str):
        try:
            sts = boto3.client('sts')
            sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName="Verify",
                ExternalId=external_id
            )
            return True
        except ClientError as e:
            raise HTTPException(400, f"AWS Connection Failed: {str(e)}")

    def link_account(self, user_id: int, data: AccountCreate) -> Account:
        self.verify_connection(data.role_arn, data.external_id)
        
        account = Account(
            name=data.name,
            account_id=data.account_id,
            role_arn=data.role_arn,
            external_id=data.external_id,
            status="active"
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account
