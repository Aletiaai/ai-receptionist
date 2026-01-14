#!/usr/bin/env python3
"""
OAuth2 Authorization Script for Microsoft Outlook Calendar.
Run this once to authorize the app and save refresh token to DynamoDB.
"""

import os
import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import msal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import after loading env vars
from src.services.dynamo_service import get_dynamo_service

# Azure AD Configuration
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_TENANT_ID")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Calendars.ReadWrite", "User.Read"]
REDIRECT_URI = "http://localhost:8000/callback"

# Token storage - use 'global' tenant for shared calendar access
TOKEN_TENANT_ID = "global"
TOKEN_PROVIDER = "outlook"


class AuthHandler(BaseHTTPRequestHandler):
    """HTTP handler to capture OAuth callback."""
    
    auth_code = None
    
    def do_GET(self):
        """Handle GET request from OAuth callback."""
        parsed = urlparse(self.path)
        
        if parsed.path == "/callback":
            query_params = parse_qs(parsed.query)
            
            if "code" in query_params:
                AuthHandler.auth_code = query_params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"""
                    <html>
                    <body style="font-family: Arial; text-align: center; padding-top: 50px;">
                        <h1>&#9989; Authorization Successful!</h1>
                        <p>You can close this window and return to the terminal.</p>
                    </body>
                    </html>
                """)
            else:
                error = query_params.get("error", ["Unknown error"])[0]
                error_desc = query_params.get("error_description", ["No description"])[0]
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(f"""
                    <html>
                    <body style="font-family: Arial; text-align: center; padding-top: 50px;">
                        <h1>&#10060; Authorization Failed</h1>
                        <p>Error: {error}</p>
                        <p>{error_desc}</p>
                    </body>
                    </html>
                """.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress HTTP server logs."""
        pass


def get_auth_url(app):
    """Generate the authorization URL."""
    return app.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )


def authorize():
    """Run the OAuth2 authorization flow."""
    print("\n" + "="*60)
    print("🔐 OUTLOOK CALENDAR AUTHORIZATION")
    print("="*60)
    
    # Validate configuration
    if not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID]):
        print("❌ Error: Missing Azure credentials in .env file")
        print("   Required: AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID")
        return False
    
    print(f"\n📋 Configuration:")
    print(f"   Client ID: {CLIENT_ID[:8]}...{CLIENT_ID[-4:]}")
    print(f"   Tenant ID: {TENANT_ID[:8]}...{TENANT_ID[-4:]}")
    print(f"   Redirect URI: {REDIRECT_URI}")
    print(f"   Token Storage: DynamoDB (tenant: {TOKEN_TENANT_ID})")
    
    # Create MSAL app
    app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    
    # Generate authorization URL
    auth_url = get_auth_url(app)
    
    print(f"\n🌐 Opening browser for authorization...")
    print(f"   If browser doesn't open, visit this URL manually:")
    print(f"   {auth_url[:80]}...")
    
    # Open browser
    webbrowser.open(auth_url)
    
    # Start local server to capture callback
    print(f"\n⏳ Waiting for authorization callback on {REDIRECT_URI}...")
    
    server = HTTPServer(("localhost", 8000), AuthHandler)
    
    while AuthHandler.auth_code is None:
        server.handle_request()
    
    auth_code = AuthHandler.auth_code
    print(f"\n✅ Authorization code received!")
    
    # Exchange code for tokens
    print(f"\n🔄 Exchanging code for access token...")
    
    result = app.acquire_token_by_authorization_code(
        code=auth_code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    if "access_token" in result:
        print(f"✅ Access token obtained!")
        
        # Prepare token data for storage
        token_data = {
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token"),
            "token_type": result.get("token_type"),
            "expires_in": result.get("expires_in"),
            "scope": result.get("scope"),
            "client_id": CLIENT_ID,
            "tenant_id": TENANT_ID
        }
        
        # Save to DynamoDB
        print(f"\n💾 Saving token to DynamoDB...")
        
        try:
            dynamo = get_dynamo_service()
            
            # First, ensure 'global' tenant exists
            existing = dynamo.get_tenant(TOKEN_TENANT_ID)
            if not existing:
                print(f"   Creating '{TOKEN_TENANT_ID}' tenant entry...")
                dynamo.tenants_table.put_item(Item={
                    'tenant_id': TOKEN_TENANT_ID,
                    'name': 'Global Configuration',
                    'description': 'Shared configuration and tokens',
                    'active': True
                })
            
            # Save the token
            dynamo.save_oauth_token(TOKEN_TENANT_ID, TOKEN_PROVIDER, token_data)
            print(f"✅ Token saved to DynamoDB!")
            
        except Exception as e:
            print(f"❌ Failed to save token to DynamoDB: {str(e)}")
            print("   Falling back to local file storage...")
            
            # Fallback to local file
            os.makedirs("config", exist_ok=True)
            with open("config/outlook_token.json", "w") as f:
                json.dump(token_data, f, indent=2)
            print(f"   Token saved to: config/outlook_token.json")
        
        # Get user info to confirm
        print(f"\n📧 Authorized account:")
        if "id_token_claims" in result:
            claims = result["id_token_claims"]
            print(f"   Name: {claims.get('name', 'N/A')}")
            print(f"   Email: {claims.get('preferred_username', 'N/A')}")
        
        print("\n" + "="*60)
        print("✅ AUTHORIZATION COMPLETE!")
        print("="*60)
        print("\nYou can now use the Outlook Calendar integration.")
        print("The refresh token is stored securely in DynamoDB.")
        
        return True
        
    else:
        print(f"\n❌ Failed to obtain access token!")
        print(f"   Error: {result.get('error')}")
        print(f"   Description: {result.get('error_description')}")
        return False


def check_existing_token():
    """Check if a valid token already exists in DynamoDB."""
    try:
        dynamo = get_dynamo_service()
        token_data = dynamo.get_oauth_token(TOKEN_TENANT_ID, TOKEN_PROVIDER)
        
        if token_data and token_data.get("refresh_token"):
            print(f"\n📁 Existing token found in DynamoDB")
            print(f"   ✅ Refresh token present")
            response = input("\n   Do you want to re-authorize? (y/N): ").strip().lower()
            if response != "y":
                print("   Using existing token.")
                return True
    except Exception as e:
        print(f"   Note: Could not check existing token: {str(e)}")
    
    return False


if __name__ == "__main__":
    if not check_existing_token():
        success = authorize()
        exit(0 if success else 1)