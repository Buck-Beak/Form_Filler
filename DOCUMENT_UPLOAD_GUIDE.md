# Document Upload & Parsing Guide

## 🎯 Overview

Your Form Filler bot now supports automatic document parsing! Users can upload documents (PDFs, images, text files) and the bot will extract personal information using Google Gemini AI.

## 📋 Supported Document Types

### ✅ **Fully Supported:**
- **PDF files** (.pdf) - Text extraction from PDF documents
- **Image files** (.jpg, .jpeg, .png, .gif, .bmp) - OCR using Gemini Vision
- **Text files** (.txt, .doc, .docx) - Direct text processing

### 📄 **Best Results With:**
- Aadhaar cards (front/back)
- PAN cards
- Passport pages
- Driver's license
- Resume/CV documents
- ID cards
- Any document with clear text

## 🔧 How It Works

### 1. **Document Upload**
Users simply send any supported document to your Telegram bot.

### 2. **Automatic Processing**
- **PDFs**: Text extracted using PyPDF2
- **Images**: Processed using Gemini Vision API
- **Text files**: Direct text analysis

### 3. **AI Extraction**
Gemini AI extracts the following information:
- Name
- Email
- Phone/Mobile number
- Date of Birth
- Address
- Father's Name
- Mother's Name
- Aadhaar Number
- PAN Number
- Assessment Year
- Gender
- Nationality
- Marital Status

### 4. **Data Storage**
Extracted information is automatically saved to `users.json` with the user's Telegram ID.

## 🚀 Usage Examples

### User Experience:
1. User sends document to bot
2. Bot processes and extracts information
3. Bot confirms extracted data
4. User can now use form filling commands

### Example Bot Responses:
```
📄 Processing your document... Please wait!

✅ Document processed successfully!

📋 Extracted Information:
• Name: Rajesh Kumar Sharma
• Mobile: 9876543210
• Dob: 15-03-1990
• Address: 123, MG Road, Bangalore, Karnataka - 560001
• Father Name: Suresh Kumar Sharma
• Mother Name: Kamla Devi
• Aadhaar Number: 1234-5678-9012

🎉 Your information has been saved! You can now use form filling commands.
```

## 🔧 Technical Implementation

### Key Functions Added:

1. **`extract_text_from_document()`**
   - Handles different file types
   - PDF text extraction
   - Image preparation for vision API

2. **`parse_document_with_gemini()`**
   - Enhanced prompt for information extraction
   - Support for both text and image processing
   - JSON response parsing

3. **`save_user_data()`**
   - Updates existing users or creates new ones
   - Maintains data integrity in users.json

4. **`handle_document()`**
   - Telegram document handler
   - File download and processing
   - User feedback and error handling

## 📁 File Structure

```
Form_Filler/
├── selenium_test.py          # Main bot with document processing
├── users.json               # User database (auto-updated)
├── requirements.txt         # Updated with new dependencies
├── test_document_parsing.py # Test script
└── DOCUMENT_UPLOAD_GUIDE.md # This guide
```

## 🧪 Testing

Run the test script to verify functionality:
```bash
python test_document_parsing.py
```

## ⚙️ Configuration

### Environment Variables (.env):
```env
GEMINI_API_KEY=your_gemini_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
```

### Dependencies:
```bash
pip install -r requirements.txt
```

## 🎯 Bot Commands

### For Users:
1. **Upload Document**: Send any supported document file
2. **Form Filling**: "I want to fill [form name]"
3. **Start**: `/start` - Shows usage instructions

### Bot Responses:
- Processing status updates
- Extracted information confirmation
- Error messages with helpful guidance

## 🔒 Privacy & Security

- Documents are processed temporarily and not stored
- Only extracted information is saved to users.json
- Users can update their information by uploading new documents

## 🚀 Running the Bot

```bash
python selenium_test.py
```

The bot will:
1. Accept document uploads
2. Process them with Gemini AI
3. Extract and save user information
4. Enable form filling functionality

## 📊 Benefits

- **Automated Data Entry**: No manual form filling
- **Multi-format Support**: PDFs, images, text files
- **AI-powered Extraction**: High accuracy with Gemini
- **Seamless Integration**: Works with existing form filling system
- **User-friendly**: Simple document upload process
