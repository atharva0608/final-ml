import boto3

def check_ec2_tags():
    # Assuming us-east-1 based on previous checks, but let's check ap-south-1 as well.
    # The cluster 'spot-demo-3' was shown with 'ap-south-1' Region in the screenshot.
    ec2 = boto3.client('ec2', region_name='ap-south-1')
    response = ec2.describe_instances()
    
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            tags = instance.get('Tags', [])
            print(f"Instance: {instance_id}")
            for tag in tags:
                print(f"  {tag['Key']}: {tag['Value']}")

check_ec2_tags()
