#!/usr/bin/env python3
"""
Setup script for Document Processing Feature
This script helps install dependencies and verify the setup
"""

import subprocess
import sys
import os

def install_requirements():
    """Install required packages"""
    print("📦 Installing required packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ All packages installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install packages: {e}")
        return False

def check_env_file():
    """Check if .env file exists and has required variables"""
    print("\n🔍 Checking environment configuration...")
    
    if not os.path.exists(".env"):
        print("⚠️ .env file not found. Creating template...")
        with open(".env", "w") as f:
            f.write("# Telegram Bot Configuration\n")
            f.write("TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here\n")
            f.write("\n# Gemini AI Configuration\n")
            f.write("GEMINI_API_KEY=your_gemini_api_key_here\n")
        print("✅ Created .env template file")
        print("📝 Please edit .env file with your actual API keys")
        return False
    
    # Check if variables are set
    from dotenv import load_dotenv
    load_dotenv()
    
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    if not telegram_token or telegram_token == "your_telegram_bot_token_here":
        print("❌ TELEGRAM_BOT_TOKEN not set in .env file")
        return False
    
    if not gemini_key or gemini_key == "your_gemini_api_key_here":
        print("❌ GEMINI_API_KEY not set in .env file")
        return False
    
    print("✅ Environment variables configured correctly")
    return True

def test_imports():
    """Test if all required modules can be imported"""
    print("\n🧪 Testing module imports...")
    
    required_modules = [
        "telegram",
        "google.generativeai",
        "PIL",
        "fitz",  # PyMuPDF
        "docx",
        "pandas",
        "playwright"
    ]
    
    failed_imports = []
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            failed_imports.append(module)
    
    if failed_imports:
        print(f"\n⚠️ Failed to import: {', '.join(failed_imports)}")
        return False
    
    print("✅ All modules imported successfully!")
    return True

def run_basic_test():
    """Run basic functionality test"""
    print("\n🧪 Running basic functionality test...")
    
    try:
        # Test document processor import
        from document_processor import DocumentProcessor
        print("✅ DocumentProcessor imported successfully")
        
        # Test config import
        from config import GEMINI_API_KEY, TELEGRAM_TOKEN
        print("✅ Config imported successfully")
        
        # Test main module import
        import main
        print("✅ Main module imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic test failed: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 Document Processing Setup")
    print("=" * 40)
    
    # Install requirements
    if not install_requirements():
        print("\n❌ Setup failed at package installation")
        return False
    
    # Check environment
    env_ok = check_env_file()
    
    # Test imports
    if not test_imports():
        print("\n❌ Setup failed at module import test")
        return False
    
    # Run basic test
    if not run_basic_test():
        print("\n❌ Setup failed at basic functionality test")
        return False
    
    print("\n" + "=" * 40)
    if env_ok:
        print("🎉 Setup completed successfully!")
        print("\n📝 Next steps:")
        print("1. Make sure your .env file has valid API keys")
        print("2. Run: python main.py")
        print("3. Test by uploading a document to your Telegram bot")
    else:
        print("⚠️ Setup completed with warnings!")
        print("\n📝 Next steps:")
        print("1. Edit .env file with your actual API keys")
        print("2. Run: python main.py")
        print("3. Test by uploading a document to your Telegram bot")
    
    print("\n📚 Documentation:")
    print("• Read DOCUMENT_PROCESSING_README.md for detailed usage")
    print("• Run python test_document_processing.py for testing")
    
    return True

if __name__ == "__main__":
    main()
