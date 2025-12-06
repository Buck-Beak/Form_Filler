import json
import os
import tempfile
import logging
from typing import Dict, List, Optional, Any
import google.generativeai as genai
from PIL import Image
import fitz  # PyMuPDF for PDF processing
import docx  # python-docx for Word documents
import pandas as pd  # For Excel files

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self, gemini_model):
        self.gemini_model = gemini_model
        self.supported_formats = {
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'],
            'pdf': ['.pdf'],
            'document': ['.docx', '.doc'],
            'spreadsheet': ['.xlsx', '.xls'],
            'text': ['.txt']
        }
    
    def extract_text_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF file"""
        try:
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return ""
    
    def extract_text_from_docx(self, file_path: str) -> str:
        """Extract text from Word document"""
        try:
            doc = docx.Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            logger.error(f"Error extracting text from DOCX: {e}")
            return ""
    
    def extract_text_from_excel(self, file_path: str) -> str:
        """Extract text from Excel file"""
        try:
            df = pd.read_excel(file_path)
            text = df.to_string()
            return text
        except Exception as e:
            logger.error(f"Error extracting text from Excel: {e}")
            return ""
    
    def extract_text_from_image(self, file_path: str) -> str:
        """Extract text from image using Gemini Vision"""
        try:
            # Open and process the image
            image = Image.open(file_path)
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Use Gemini to extract text from image
            response = self.gemini_model.generate_content([
                "Extract all text content from this image. Return only the text content, no explanations.",
                image
            ])
            
            return response.text if response.text else ""
        except Exception as e:
            logger.error(f"Error extracting text from image: {e}")
            return ""
    
    def extract_text_from_file(self, file_path: str, file_extension: str) -> str:
        """Extract text from various file formats"""
        file_extension = file_extension.lower()
        
        if file_extension in self.supported_formats['pdf']:
            return self.extract_text_from_pdf(file_path)
        elif file_extension in self.supported_formats['document']:
            return self.extract_text_from_docx(file_path)
        elif file_extension in self.supported_formats['spreadsheet']:
            return self.extract_text_from_excel(file_path)
        elif file_extension in self.supported_formats['image']:
            return self.extract_text_from_image(file_path)
        elif file_extension in self.supported_formats['text']:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading text file: {e}")
                return ""
        else:
            logger.warning(f"Unsupported file format: {file_extension}")
            return ""
    
    def extract_user_details_with_gemini(self, extracted_text: str) -> Dict[str, Any]:
        """Use Gemini AI to extract structured user details from text"""
        try:
            prompt = f"""
            Extract user details from the following text and return ONLY a JSON object with the following structure.
            If any field is not found, set it to null.
            
            Required JSON structure:
            {{
                "name": "Full name",
                "email": "Email address",
                "mobile": "Phone number",
                "dob": "Date of birth (YYYY-MM-DD format)",
                "panAdhaarUserId": "PAN or Aadhaar ID",
                "address": "Full address",
                "gender": "Gender",
                "father_name": "Father's name",
                "mother_name": "Mother's name",
                "occupation": "Occupation",
                "annual_income": "Annual income",
                "bank_account": "Bank account number",
                "ifsc_code": "IFSC code",
                "emergency_contact": "Emergency contact number",
                "blood_group": "Blood group",
                "marital_status": "Marital status",
                "qualification": "Educational qualification",
                "institution": "Educational institution",
                "passing_year": "Year of passing",
                "percentage": "Percentage/CGPA",
                "work_experience": "Work experience in years",
                "skills": "Skills (comma-separated)",
                "languages": "Languages known (comma-separated)",
                "hobbies": "Hobbies (comma-separated)",
                "achievements": "Achievements",
                "certifications": "Certifications",
                "projects": "Projects worked on",
                "references": "References",
                "notes": "Additional notes"
            }}
            
            Text to extract from:
            {extracted_text}
            
            Return ONLY the JSON object, no additional text or explanations.
            """
            
            response = self.gemini_model.generate_content(prompt)
            
            # Try to parse the JSON response
            try:
                # Clean the response text
                response_text = response.text.strip()
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                
                user_details = json.loads(response_text)
                logger.info(f"Successfully extracted user details: {list(user_details.keys())}")
                return user_details
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Response text: {response.text}")
                return {}
                
        except Exception as e:
            logger.error(f"Error extracting user details with Gemini: {e}")
            return {}
    
    def validate_user_details(self, user_details: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean extracted user details"""
        validated = {}
        
        # Basic validation rules
        validation_rules = {
            'name': lambda x: x.strip() if x and len(x.strip()) > 1 else None,
            'email': lambda x: x.strip() if x and '@' in x and '.' in x else None,
            'mobile': lambda x: ''.join(filter(str.isdigit, str(x))) if x else None,
            'dob': lambda x: x.strip() if x and len(x.strip()) >= 8 else None,
            'panAdhaarUserId': lambda x: x.strip() if x and len(x.strip()) >= 4 else None,
            'address': lambda x: x.strip() if x and len(x.strip()) > 5 else None,
            'gender': lambda x: x.strip().lower() if x and x.strip().lower() in ['male', 'female', 'other'] else None,
            'father_name': lambda x: x.strip() if x and len(x.strip()) > 1 else None,
            'mother_name': lambda x: x.strip() if x and len(x.strip()) > 1 else None,
            'occupation': lambda x: x.strip() if x and len(x.strip()) > 1 else None,
            'annual_income': lambda x: x.strip() if x else None,
            'bank_account': lambda x: ''.join(filter(str.isdigit, str(x))) if x else None,
            'ifsc_code': lambda x: x.strip().upper() if x and len(x.strip()) >= 4 else None,
            'emergency_contact': lambda x: ''.join(filter(str.isdigit, str(x))) if x else None,
            'blood_group': lambda x: x.strip().upper() if x and x.strip().upper() in ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'] else None,
            'marital_status': lambda x: x.strip().lower() if x and x.strip().lower() in ['single', 'married', 'divorced', 'widowed'] else None,
            'qualification': lambda x: x.strip() if x and len(x.strip()) > 1 else None,
            'institution': lambda x: x.strip() if x and len(x.strip()) > 1 else None,
            'passing_year': lambda x: str(x).strip() if x and str(x).strip().isdigit() and 1950 <= int(str(x).strip()) <= 2030 else None,
            'percentage': lambda x: x.strip() if x else None,
            'work_experience': lambda x: x.strip() if x else None,
            'skills': lambda x: x.strip() if x else None,
            'languages': lambda x: x.strip() if x else None,
            'hobbies': lambda x: x.strip() if x else None,
            'achievements': lambda x: x.strip() if x else None,
            'certifications': lambda x: x.strip() if x else None,
            'projects': lambda x: x.strip() if x else None,
            'references': lambda x: x.strip() if x else None,
            'notes': lambda x: x.strip() if x else None
        }
        
        for field, validator in validation_rules.items():
            try:
                validated[field] = validator(user_details.get(field))
            except Exception as e:
                logger.warning(f"Validation error for field {field}: {e}")
                validated[field] = None
        
        return validated
    
    def process_document(self, file_path: str, file_extension: str) -> Dict[str, Any]:
        """Main method to process a document and extract user details"""
        logger.info(f"Processing document: {file_path}")
        
        # Extract text from document
        extracted_text = self.extract_text_from_file(file_path, file_extension)
        
        if not extracted_text.strip():
            logger.warning("No text extracted from document")
            return {"error": "No text could be extracted from the document"}
        
        logger.info(f"Extracted {len(extracted_text)} characters of text")
        
        # Extract user details using Gemini
        user_details = self.extract_user_details_with_gemini(extracted_text)
        
        if not user_details:
            logger.warning("No user details extracted")
            return {"error": "Could not extract user details from the document"}
        
        # Validate user details
        validated_details = self.validate_user_details(user_details)
        
        # Count non-null fields
        non_null_fields = sum(1 for v in validated_details.values() if v is not None)
        
        logger.info(f"Successfully processed document. Extracted {non_null_fields} valid fields")
        
        return {
            "success": True,
            "user_details": validated_details,
            "extracted_fields_count": non_null_fields,
            "raw_text_length": len(extracted_text)
        }
