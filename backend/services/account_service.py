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
        
        # Check if account already exists
        existing = self.db.query(Account).filter(Account.aws_account_id == data.account_id).first()
        if existing:
            raise HTTPException(400, "Account already linked")

        account = Account(
            name=data.name,
            aws_account_id=data.account_id,
            role_arn=data.role_arn,
            external_id=data.external_id,
            status="active"
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

def get_account_service(db: Session) -> AccountService:
    return AccountService(db)
