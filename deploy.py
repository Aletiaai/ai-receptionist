"""
Deployment script for AI Receptionist Lambda function.
Packages code and dependencies, then uploads to AWS Lambda.
"""

import os
import shutil
import subprocess
import zipfile
import boto3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
LAMBDA_FUNCTION_NAME = "ai-receptionist-chat-handler"
AWS_REGION = os.getenv("AWS_REGION", "us-east-2")

# Directories
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
PACKAGE_DIR = os.path.join(BUILD_DIR, "package")
ZIP_FILE = os.path.join(BUILD_DIR, "lambda_deployment.zip")


def clean_build():
    """Remove previous build artifacts."""
    print("🧹 Cleaning previous build...")
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(PACKAGE_DIR)
    print("   ✅ Build directory cleaned")


def install_dependencies():
    """Install production dependencies using Docker for Lambda compatibility."""
    print("📦 Installing dependencies for Lambda (Linux)...")
    
    # Production dependencies (excludes testing packages)
    prod_requirements = [
        # AWS SDK
        "boto3==1.35.0",
        # OpenAI
        "openai>=1.50.0",
        # Environment variables
        "python-dotenv==1.0.1",
        # HTTP requests
        "requests==2.32.0",
        # Twilio (SMS + SendGrid Email)
        "twilio==9.3.0",
        # Google Calendar API
        "google-auth==2.35.0",
        "google-auth-oauthlib==1.2.1",
        "google-api-python-client==2.149.0",
        # Microsoft Graph API (Outlook)
        "msal==1.31.0",
    ]
    
    prod_req_file = os.path.join(BUILD_DIR, "requirements_prod.txt")
    with open(prod_req_file, "w") as f:
        f.write("\n".join(prod_requirements))
    
    # Check if Docker is available
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        use_docker = True
        print("   🐳 Using Docker for Linux-compatible packages")
    except (subprocess.CalledProcessError, FileNotFoundError):
        use_docker = False
        print("   ⚠️  Docker not available, using local pip (may cause issues)")
    
    if use_docker:
        # Use Docker to install dependencies for Lambda's Amazon Linux environment
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{BUILD_DIR}:/var/task",
            "public.ecr.aws/sam/build-python3.12:latest",
            "/bin/bash", "-c",
            "pip install -r /var/task/requirements_prod.txt -t /var/task/package --quiet --upgrade"
        ]
        
        try:
            subprocess.run(docker_cmd, check=True)
            print("   ✅ Dependencies installed (Linux-compatible)")
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Docker build failed: {e}")
            print("   Falling back to local pip...")
            use_docker = False
    
    if not use_docker:
        # Fallback: local pip install
        subprocess.run(
            [
                "pip", "install",
                "-r", prod_req_file,
                "-t", PACKAGE_DIR,
                "--quiet",
                "--upgrade"
            ],
            check=True
        )
        print("   ✅ Dependencies installed (local)")


def copy_source_code():
    """Copy source code to package directory."""
    print("📄 Copying source code...")
    
    # Copy src directory
    src_dest = os.path.join(PACKAGE_DIR, "src")
    shutil.copytree(
        os.path.join(PROJECT_ROOT, "src"),
        src_dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    
    # Create lambda entry point (lambda_function.py)
    entry_point = '''"""
Lambda entry point.
This file is the handler configured in AWS Lambda.
"""

from src.handlers.router import route_request

# Re-export the handler
handler = route_request
'''
    
    with open(os.path.join(PACKAGE_DIR, "lambda_function.py"), "w") as f:
        f.write(entry_point)
    
    print("   ✅ Source code copied")


def create_zip():
    """Create deployment ZIP file."""
    print("🗜️  Creating deployment package...")
    
    if os.path.exists(ZIP_FILE):
        os.remove(ZIP_FILE)
    
    with zipfile.ZipFile(ZIP_FILE, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PACKAGE_DIR):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            
            for file in files:
                if file.endswith(".pyc"):
                    continue
                
                file_path = os.path.join(root, file)
                arc_name = os.path.relpath(file_path, PACKAGE_DIR)
                zf.write(file_path, arc_name)
    
    # Get file size
    size_mb = os.path.getsize(ZIP_FILE) / (1024 * 1024)
    print(f"   ✅ Package created: {size_mb:.2f} MB")
    
    if size_mb > 50:
        print("   ⚠️  Warning: Package is large. Consider using Lambda Layers for dependencies.")
    
    return ZIP_FILE


def upload_to_lambda():
    """Upload ZIP file to AWS Lambda."""
    print("🚀 Uploading to AWS Lambda...")
    
    lambda_client = boto3.client(
        "lambda",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    
    # Read ZIP file
    with open(ZIP_FILE, "rb") as f:
        zip_content = f.read()
    
    try:
        # Update function code
        response = lambda_client.update_function_code(
            FunctionName=LAMBDA_FUNCTION_NAME,
            ZipFile=zip_content
        )
        
        print(f"   ✅ Uploaded to Lambda: {LAMBDA_FUNCTION_NAME}")
        print(f"   📍 ARN: {response['FunctionArn']}")
        print(f"   📊 Code Size: {response['CodeSize'] / (1024*1024):.2f} MB")
        
        return True
        
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"   ❌ Lambda function '{LAMBDA_FUNCTION_NAME}' not found!")
        print("   Please create the function in AWS Console first.")
        return False
        
    except Exception as e:
        print(f"   ❌ Upload failed: {str(e)}")
        return False


def update_lambda_config():
    """Update Lambda configuration (environment variables, timeout, memory)."""
    print("⚙️  Updating Lambda configuration...")
    
    lambda_client = boto3.client(
        "lambda",
        region_name=AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    
    # Environment variables to set in Lambda
    env_vars = {
        "AWS_REGION_NAME": AWS_REGION,
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "OPENAI_EXTRACTION_MODEL": os.getenv("OPENAI_EXTRACTION_MODEL", "gpt-4.1-mini"),
        "DYNAMODB_TENANTS_TABLE": os.getenv("DYNAMODB_TENANTS_TABLE", "ai-receptionist-tenants"),
        "DYNAMODB_CONVERSATIONS_TABLE": os.getenv("DYNAMODB_CONVERSATIONS_TABLE", "ai-receptionist-conversations"),
        "DYNAMODB_APPOINTMENTS_TABLE": os.getenv("DYNAMODB_APPOINTMENTS_TABLE", "ai-receptionist-appointments"),
        "AZURE_CLIENT_ID": os.getenv("AZURE_CLIENT_ID", ""),
        "AZURE_TENANT_ID": os.getenv("AZURE_TENANT_ID", ""),
        "AZURE_CLIENT_SECRET": os.getenv("AZURE_CLIENT_SECRET", ""),
        "TIMEZONE": os.getenv("TIMEZONE", "America/Mexico_City"),
        "LOG_LEVEL": "INFO",
    }
    
    # Debug: Show which env vars are being set (hide secrets)
    print(f"   📋 Environment variables being set:")
    for key, value in env_vars.items():
        if "SECRET" in key or "KEY" in key:
            display_value = f"{value[:8]}..." if value else "NOT SET"
        else:
            display_value = value if value else "NOT SET"
        print(f"      {key}: {display_value}")

    try:
        response = lambda_client.update_function_configuration(
            FunctionName=LAMBDA_FUNCTION_NAME,
            Timeout=30,  # 30 seconds (OpenAI calls can take time)
            MemorySize=512,  # 512 MB
            Environment={"Variables": env_vars},
            Handler="lambda_function.handler"
        )
        
        print(f"   ✅ Configuration updated")
        print(f"   ⏱️  Timeout: {response['Timeout']}s")
        print(f"   💾 Memory: {response['MemorySize']} MB")
        print(f"   🔧 Handler: {response['Handler']}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Configuration update failed: {str(e)}")
        return False


def main():
    """Run the deployment process."""
    print("\n" + "="*60)
    print("🤖 AI RECEPTIONIST - LAMBDA DEPLOYMENT")
    print("="*60 + "\n")
    
    # Step 1: Clean
    clean_build()
    
    # Step 2: Install dependencies
    install_dependencies()
    
    # Step 3: Copy source code
    copy_source_code()
    
    # Step 4: Create ZIP
    create_zip()
    
    # Step 5: Upload to Lambda
    if not upload_to_lambda():
        print("\n❌ Deployment failed at upload step")
        return False
    
    # Step 6: Update configuration
    # Wait a moment for the code update to complete
    print("⏳ Waiting for code update to complete...")
    import time
    time.sleep(5)
    
    if not update_lambda_config():
        print("\n❌ Deployment failed at configuration step")
        return False
    
    print("\n" + "="*60)
    print("✅ DEPLOYMENT COMPLETE!")
    print("="*60)
    print(f"\n📍 Function: {LAMBDA_FUNCTION_NAME}")
    print(f"🌎 Region: {AWS_REGION}")
    print(f"\n🔗 API Endpoint:")
    print(f"   POST {os.getenv('API_GATEWAY_URL', 'https://your-api-gateway-url')}/chat/{{tenant_id}}")
    print("\n")
    
    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)