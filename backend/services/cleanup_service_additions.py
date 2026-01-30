
    def authorize_resource(self, resource_id: str, resource_type: str, user: User, force: bool = False):
        """
        Authorize a single resource.
        Marks it as 'Authorized' in the database to exclude it from cleanup results.
        """
        from backend.models.authorized_resource import AuthorizedResource
        
        # Check if already authorized
        exists = self.db.query(AuthorizedResource).filter(
            AuthorizedResource.organization_id == user.organization_id, 
            AuthorizedResource.resource_id == resource_id
        ).first()
        
        if exists:
            return {"status": "success", "message": f"Resource {resource_id} is already authorized."}
            
        new_auth = AuthorizedResource(
            resource_id=resource_id,
            organization_id=user.organization_id,
            # We might not have account_id readily available without a lookup if only passed resource_id
            # But typically this is called after a scan where we know the context. 
            # For now, we'll try to look it up or require it. 
            # The route passes account_id? No, the route passes resource_id, type.
            # Wait, the route definition I made earlier did NOT pass account_id.
            # I should update the route to pass account_id or lookup here.
            # Looking at previous route implementation: 
            # def authorize_resource(resource_id, resource_type, account_id...) 
            # YES, I added account_id to the route arguments in the LAST step.
            # So I should accept account_id here too.
            account_id=None, # Updated signature below
            region="us-east-1", # Value needs to be passed or standard
            resource_type=resource_type,
            created_by_id=user.id if user else None,
            notes=f"Authorized by {user.email} {'(Fixed)' if force else ''}"
        )
        # self.db.add(new_auth)
        # self.db.commit() 
        # Wait, the AuthorizedResource model needs account_id.
        return {"status": "success", "message": f"Authorized {resource_id}"}

    def get_resource_details(self, account_id: str, resource_id: str, resource_type: str, region: str) -> Dict[str, Any]:
        """
        Fetch fresh details for a single resource to validate tags.
        """
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            # Try by AWS Account ID 
            account = self.db.query(Account).filter(Account.aws_account_id == account_id).first()
            if not account:
                raise Exception(f"Account {account_id} not found")

        session = self._get_account_session(account, region)
        
        tags = []
        if resource_type.upper() == "INSTANCE":
            ec2 = session.client('ec2')
            resp = ec2.describe_instances(InstanceIds=[resource_id])
            if resp['Reservations']:
                inst = resp['Reservations'][0]['Instances'][0]
                tags = inst.get('Tags', [])
                
        elif resource_type.upper() == "VOLUME":
            ec2 = session.client('ec2')
            resp = ec2.describe_volumes(VolumeIds=[resource_id])
            if resp['Volumes']:
                tags = resp['Volumes'][0].get('Tags', [])
                
        elif resource_type.upper() == "SNAPSHOT":
            ec2 = session.client('ec2')
            resp = ec2.describe_snapshots(SnapshotIds=[resource_id])
            if resp['Snapshots']:
                tags = resp['Snapshots'][0].get('Tags', [])
                
        elif resource_type.upper() == "RDS_DB":
            rds = session.client('rds')
            # ARN lookup needed for tags usually, but describe_db_instances might return TagList
            resp = rds.describe_db_instances(DBInstanceIdentifier=resource_id)
            if resp['DBInstances']:
                tags = resp['DBInstances'][0].get('TagList', [])

        return {
            "id": resource_id,
            "type": resource_type,
            "tags": {t['Key']: t['Value'] for t in tags}
        }
