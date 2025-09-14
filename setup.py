import os
import sys
import subprocess
from pathlib import Path

def print_banner():
    print("=" * 60)
    print("🏛️  CITIZEN VOICE AI - QUICK SETUP")
    print("=" * 60)

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"   Current version: {sys.version}")
        sys.exit(1)
    else:
        print(f"✅ Python version: {sys.version.split()[0]}")

def install_dependencies():
    """Install required Python packages"""
    print("\n📦 Installing Python dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                      check=True, capture_output=True)
        print("✅ Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        print("   Try running: pip install -r requirements.txt")
        return False
    return True

def check_files():
    """Check if required files exist"""
    required_files = ["main.py", "index.html", "requirements.txt"]
    missing_files = []
    
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Missing files: {', '.join(missing_files)}")
        print("   Please ensure all files are in the same directory")
        return False
    else:
        print("✅ All required files found")
    return True

def setup_environment():
    """Setup environment variables"""
    print("\n🔧 Setting up environment variables...")
    
    env_file = Path(".env")
    if not env_file.exists():
        env_content = """# Citizen Voice AI Environment Variables
# IBM Watson Configuration (Optional)
WATSON_REGION_CODE=us-south
WATSON_JWT_TOKEN=your_jwt_token_here
WATSON_INSTANCE_ID=your_instance_id_here

# Database Configuration (Future use)
DATABASE_URL=sqlite:///./citizen_voice.db

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True

# Security
SECRET_KEY=your-secret-key-change-this-in-production
"""
        with open(env_file, "w") as f:
            f.write(env_content)
        print("✅ Created .env file with default settings")
        print("   📝 Edit .env file to add your Watson credentials")
    else:
        print("✅ .env file already exists")

def create_directories():
    """Create necessary directories"""
    dirs = ["logs", "data", "uploads", "backups"]
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
    print("✅ Created necessary directories")

def run_tests():
    """Run basic tests"""
    print("\n🧪 Running basic tests...")
    try:
        # Test import of main modules
        import fastapi
        import uvicorn
        import pydantic
        print("✅ Core modules imported successfully")
        
        # Test main.py syntax
        subprocess.run([sys.executable, "-m", "py_compile", "main.py"], 
                      check=True, capture_output=True)
        print("✅ main.py syntax is valid")
        
        return True
    except Exception as e:
        print(f"❌ Tests failed: {e}")
        return False

def print_usage_instructions():
    """Print usage instructions"""
    print("\n" + "=" * 60)
    print("🚀 SETUP COMPLETE! HERE'S HOW TO USE THE SYSTEM:")
    print("=" * 60)
    print("1. Start the backend server:")
    print("   python main.py")
    print("")
    print("2. Open your browser and visit:")
    print("   http://localhost:8000/chat  (ChatGPT-style interface)")
    print("   http://localhost:8000/docs  (API documentation)")
    print("")
    print("3. For Watson AI integration:")
    print("   - Edit .env file with your Watson credentials")
    print("   - Restart the server")
    print("")
    print("4. API Endpoints:")
    print("   POST /api/chat           - Chat with AI")
    print("   POST /api/complaint      - Submit complaint")
    print("   GET  /api/analytics      - View analytics")
    print("   WS   /ws                 - Real-time updates")
    print("")
    print("🔧 Configuration:")
    print("   - Edit .env for environment settings")
    print("   - Check logs/ directory for application logs")
    print("   - Watson integration is optional (works in mock mode)")
    print("=" * 60)

def main():
    """Main setup function"""
    print_banner()
    
    # Check Python version
    check_python_version()
    
    # Check required files
    if not check_files():
        sys.exit(1)
    
    # Install dependencies
    if not install_dependencies():
        sys.exit(1)
    
    # Setup environment
    setup_environment()
    
    # Create directories
    create_directories()
    
    # Run tests
    if not run_tests():
        print("⚠️  Some tests failed, but you can still try running the system")
    
    # Print usage instructions
    print_usage_instructions()
    
    print("\n🎉 Setup completed successfully!")
    print("💡 Run 'python main.py' to start the server")

if __name__ == "__main__":
    main()