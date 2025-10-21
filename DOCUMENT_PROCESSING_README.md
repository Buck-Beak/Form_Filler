# Document Processing Feature

This feature allows the Telegram bot to extract user details from uploaded documents using Google's Gemini AI and automatically add them to the `users.json` database.

## Features

- **Multi-format Support**: PDF, Word documents, Excel files, images, and text files
- **AI-powered Extraction**: Uses Gemini AI to intelligently extract structured user data
- **Data Validation**: Validates and cleans extracted data before saving
- **Profile Management**: Updates existing profiles or creates new ones
- **Error Handling**: Comprehensive error handling and user feedback

## Supported File Types

| Format | Extensions | Processing Method |
|--------|------------|-------------------|
| PDF | `.pdf` | PyMuPDF text extraction |
| Word | `.docx`, `.doc` | python-docx library |
| Excel | `.xlsx`, `.xls` | pandas + openpyxl |
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp` | Gemini Vision API |
| Text | `.txt` | Direct file reading |

## Extracted Fields

The system can extract the following user details:

### Personal Information
- Name
- Email
- Mobile/Phone number
- Date of Birth
- PAN/Aadhaar ID
- Address
- Gender
- Father's Name
- Mother's Name

### Professional Information
- Occupation
- Annual Income
- Work Experience
- Skills
- Certifications
- Projects

### Educational Information
- Qualification
- Institution
- Passing Year
- Percentage/CGPA

### Additional Details
- Blood Group
- Marital Status
- Languages Known
- Hobbies
- Achievements
- Bank Account
- IFSC Code
- Emergency Contact
- References
- Notes

## Usage

1. **Start the bot**: Send `/start` to begin
2. **Upload document**: Send any supported document file
3. **Wait for processing**: The bot will extract and analyze the document
4. **Review results**: The bot will show extracted fields and update your profile
5. **Use form filling**: Your extracted data can now be used for automatic form filling

## Example Workflow

```
User: /start
Bot: Welcome! Upload any document to extract your details...

User: [Uploads resume.pdf]
Bot: 📄 Processing document: resume.pdf
     🔄 Extracting text and analyzing with AI...
     ⏳ This may take a few moments...

Bot: ✅ Document processed successfully!
     📊 Extracted 15 fields from the document
     🆕 Created new profile for you
     
     📋 Your profile data:
     • name: John Doe
     • email: john.doe@example.com
     • mobile: 9876543210
     • dob: 1990-05-15
     • occupation: Software Engineer
     ...
     
     🎉 Profile created! You can now use form filling features.
```

## Technical Implementation

### DocumentProcessor Class

The `DocumentProcessor` class handles all document processing operations:

```python
from document_processor import DocumentProcessor

# Initialize with Gemini model
processor = DocumentProcessor(gemini_model)

# Process a document
result = processor.process_document(file_path, file_extension)
```

### Key Methods

- `extract_text_from_file()`: Extracts text from various file formats
- `extract_user_details_with_gemini()`: Uses AI to extract structured data
- `validate_user_details()`: Validates and cleans extracted data
- `process_document()`: Main processing pipeline

### Error Handling

The system includes comprehensive error handling for:
- Unsupported file formats
- File size limits (20MB max)
- Corrupted or empty documents
- AI processing failures
- Database update errors

## Configuration

### Required Environment Variables

```bash
GEMINI_API_KEY=your_gemini_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

### Dependencies

The following packages are required for document processing:

```
PyMuPDF>=1.23.0          # PDF processing
python-docx>=0.8.11      # Word documents
pandas>=1.5.0            # Excel files
Pillow>=9.0.0            # Image processing
openpyxl>=3.0.0          # Excel support
google-generativeai      # Gemini AI
```

## Testing

Run the test script to verify functionality:

```bash
python test_document_processing.py
```

This will test:
- Document text extraction
- AI-powered data extraction
- Data validation
- Users.json database updates

## Security & Privacy

- Documents are processed locally and temporarily
- Temporary files are automatically deleted after processing
- User data is stored securely in the local `users.json` file
- No data is sent to external services except Gemini AI for text extraction

## Troubleshooting

### Common Issues

1. **"Unsupported file type"**: Check if the file extension is supported
2. **"File too large"**: Reduce file size to under 20MB
3. **"No text extracted"**: Document might be corrupted or contain only images
4. **"Limited data extracted"**: Document might not contain personal information

### Debug Mode

Enable debug logging by setting the log level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

- Support for more file formats (PowerPoint, RTF, etc.)
- Batch document processing
- Data export/import functionality
- Advanced validation rules
- Custom field mapping
- OCR for scanned documents
