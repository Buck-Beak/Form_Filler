#!/usr/bin/env python3
"""
Test script for document processing functionality
This script tests the DocumentProcessor class with sample data
"""

import json
import os
import tempfile
from document_processor import DocumentProcessor
import google.generativeai as genai
from config import GEMINI_API_KEY

def create_sample_text_file():
    """Create a sample text file with user information"""
    sample_text = """
    PERSONAL INFORMATION
    
    Name: John Doe
    Email: john.doe@example.com
    Mobile: 9876543210
    Date of Birth: 1990-05-15
    PAN Number: ABCDE1234F
    Address: 123 Main Street, City, State, 12345
    
    EDUCATION
    
    Qualification: Bachelor of Technology
    Institution: ABC University
    Passing Year: 2012
    Percentage: 85.5%
    
    WORK EXPERIENCE
    
    Occupation: Software Engineer
    Work Experience: 10 years
    Annual Income: 800000
    
    ADDITIONAL DETAILS
    
    Father's Name: Robert Doe
    Mother's Name: Mary Doe
    Blood Group: O+
    Marital Status: Married
    Skills: Python, JavaScript, React, Node.js
    Languages: English, Hindi, Spanish
    """
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_text)
        return f.name

def test_document_processing():
    """Test the document processing functionality"""
    print("🧪 Testing Document Processing Functionality")
    print("=" * 50)
    
    # Initialize Gemini
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-2.5-flash')
        print("✅ Gemini AI initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Gemini AI: {e}")
        return False
    
    # Initialize document processor
    try:
        processor = DocumentProcessor(gemini_model)
        print("✅ Document processor initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize document processor: {e}")
        return False
    
    # Create sample text file
    try:
        sample_file = create_sample_text_file()
        print(f"✅ Sample text file created: {sample_file}")
    except Exception as e:
        print(f"❌ Failed to create sample file: {e}")
        return False
    
    try:
        # Test document processing
        print("\n🔄 Processing sample document...")
        result = processor.process_document(sample_file, '.txt')
        
        if "error" in result:
            print(f"❌ Document processing failed: {result['error']}")
            return False
        
        if not result.get("success"):
            print("❌ Document processing failed - no success flag")
            return False
        
        user_details = result["user_details"]
        extracted_count = result["extracted_fields_count"]
        
        print(f"✅ Document processed successfully!")
        print(f"📊 Extracted {extracted_count} fields")
        print(f"📄 Raw text length: {result['raw_text_length']} characters")
        
        print("\n📋 Extracted User Details:")
        print("-" * 30)
        for key, value in user_details.items():
            if value is not None:
                print(f"• {key}: {value}")
        
        # Test validation
        print(f"\n🔍 Validation Results:")
        print(f"• Total fields processed: {len(user_details)}")
        print(f"• Valid fields extracted: {extracted_count}")
        print(f"• Success rate: {(extracted_count/len(user_details)*100):.1f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during document processing: {e}")
        return False
    
    finally:
        # Clean up
        try:
            os.unlink(sample_file)
            print(f"🧹 Cleaned up sample file")
        except Exception:
            pass

def test_users_json_update():
    """Test updating users.json with extracted data"""
    print("\n🧪 Testing Users JSON Update")
    print("=" * 50)
    
    try:
        # Load current users
        with open("users.json", "r") as f:
            users = json.load(f)
        
        print(f"✅ Loaded {len(users)} existing users")
        
        # Create test user data
        test_user = {
            "telegram_id": 999999999,
            "name": "Test User",
            "email": "test@example.com",
            "mobile": "9999999999",
            "dob": "1990-01-01"
        }
        
        # Add test user
        users.append(test_user)
        
        # Save back to file
        with open("users.json", "w") as f:
            json.dump(users, f, indent=4)
        
        print("✅ Test user added to users.json")
        
        # Remove test user
        users = [u for u in users if u.get("telegram_id") != 999999999]
        
        with open("users.json", "w") as f:
            json.dump(users, f, indent=4)
        
        print("✅ Test user removed from users.json")
        return True
        
    except Exception as e:
        print(f"❌ Error testing users.json update: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Document Processing Tests")
    print("=" * 60)
    
    # Test document processing
    doc_test_passed = test_document_processing()
    
    # Test users.json update
    json_test_passed = test_users_json_update()
    
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    print(f"• Document Processing: {'✅ PASSED' if doc_test_passed else '❌ FAILED'}")
    print(f"• Users JSON Update: {'✅ PASSED' if json_test_passed else '❌ FAILED'}")
    
    if doc_test_passed and json_test_passed:
        print("\n🎉 All tests passed! Document processing is ready to use.")
    else:
        print("\n⚠️ Some tests failed. Please check the errors above.")
    
    print("\n📝 Next steps:")
    print("1. Install required dependencies: pip install -r requirements.txt")
    print("2. Set up your .env file with GEMINI_API_KEY and TELEGRAM_BOT_TOKEN")
    print("3. Run the bot: python main.py")
    print("4. Upload documents to your Telegram bot to test!")
