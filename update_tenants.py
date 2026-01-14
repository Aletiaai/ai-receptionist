"""
Script to update tenant configurations in DynamoDB.
"""

from dotenv import load_dotenv
load_dotenv()

from src.services.dynamo_service import get_dynamo_service

# ⚠️ UPDATE THESE with real email addresses
TENANT_UPDATES = {
    "consulate": {
        "admin_email": "bogowild@gmail.com",  # Change this
        "admin_phone": "+1234567890"  # Optional
    },
    "realestate": {
        "admin_email": "bogowild@gmail.com",  # Change this
        "admin_phone": "+1234567890"  # Optional
    }
}


def update_tenants():
    """Update tenant configurations in DynamoDB."""
    print("\n" + "="*60)
    print("📝 UPDATING TENANT CONFIGURATIONS")
    print("="*60)
    
    dynamo = get_dynamo_service()
    
    for tenant_id, updates in TENANT_UPDATES.items():
        print(f"\n🔄 Updating tenant: {tenant_id}")
        
        # Build update expression
        update_parts = []
        expression_values = {}
        
        for key, value in updates.items():
            if value:  # Only update non-empty values
                update_parts.append(f"{key} = :{key}")
                expression_values[f":{key}"] = value
        
        if not update_parts:
            print(f"   ⚠️ No updates for {tenant_id}")
            continue
        
        update_expression = "SET " + ", ".join(update_parts)
        
        try:
            dynamo.tenants_table.update_item(
                Key={'tenant_id': tenant_id},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            print(f"   ✅ Updated: {list(updates.keys())}")
            
        except Exception as e:
            print(f"   ❌ Failed: {str(e)}")
    
    # Verify updates
    print("\n" + "="*60)
    print("📋 VERIFYING UPDATES")
    print("="*60)
    
    for tenant_id in TENANT_UPDATES.keys():
        tenant = dynamo.get_tenant(tenant_id)
        if tenant:
            print(f"\n{tenant_id}:")
            print(f"   admin_email: {tenant.get('admin_email', 'NOT SET')}")
            print(f"   admin_phone: {tenant.get('admin_phone', 'NOT SET')}")


if __name__ == "__main__":
    update_tenants()