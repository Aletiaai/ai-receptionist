"""
Seed script to populate DynamoDB with initial tenant configurations.
Run this once to set up the tenants.
"""

import json
import boto3
from dotenv import load_dotenv
import os
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

# Initialize DynamoDB client
dynamodb = boto3.resource(
    'dynamodb',
    region_name=os.getenv('AWS_REGION', 'us-east-2'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

def seed_tenants():
    """Load tenant configurations from JSON and insert into DynamoDB."""
    
    table = dynamodb.Table(os.getenv('DYNAMODB_TENANTS_TABLE', 'ai-receptionist-tenants'))
    
    # Load tenant configurations
    with open('config/tenants.json', 'r') as f:
        config = json.load(f)
    
    print("🚀 Seeding tenant configurations...")
    print("-" * 40)
    
    for tenant in config['tenants']:
        # Add metadata
        tenant['created_at'] = datetime.now(timezone.utc).isoformat()
        tenant['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        try:
            table.put_item(Item=tenant)
            print(f"✅ Created tenant: {tenant['tenant_id']} ({tenant['name']})")
        except Exception as e:
            print(f"❌ Error creating tenant {tenant['tenant_id']}: {str(e)}")
    
    print("-" * 40)
    print("🎉 Seeding complete!")

def verify_tenants():
    """Verify that tenants were created successfully."""
    
    table = dynamodb.Table(os.getenv('DYNAMODB_TENANTS_TABLE', 'ai-receptionist-tenants'))
    
    print("\n📋 Verifying tenants in database...")
    print("-" * 40)
    
    response = table.scan()
    tenants = response.get('Items', [])
    
    if not tenants:
        print("⚠️  No tenants found in database!")
        return
    
    for tenant in tenants:
        print(f"  • {tenant['tenant_id']}: {tenant['name']}")
        print(f"    Languages: {', '.join(tenant['supported_languages'])}")
        print(f"    Calendar: {tenant['calendar_type']}")
        print(f"    Active: {tenant['active']}")
        print()
    
    print(f"✅ Total tenants: {len(tenants)}")

if __name__ == "__main__":
    seed_tenants()
    verify_tenants()