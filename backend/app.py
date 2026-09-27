from fastapi import FastAPI, HTTPException, Depends, Request, Response, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uvicorn
import jwt
from datetime import datetime, timedelta
import os
from starlette.middleware.sessions import SessionMiddleware
from ldap3 import Server, Connection, ALL, NTLM
import logging
from dotenv import load_dotenv
import shutil
from tempfile import NamedTemporaryFile
import uuid
import mimetypes
import pdfplumber
import re
import pandas as pd
from werkzeug.utils import secure_filename
import json
import boto3
from urllib.parse import unquote

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("ocr-chatbot")

# Create FastAPI app
app = FastAPI(title="OCR Chatbot API")

# Add custom middleware to log all requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"Response: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request error: {str(e)}")
        raise

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=REDACTED
    max_age=int(os.getenv("SESSION_MAX_AGE", "1800")),  # 30 minutes by default
)

# JWT settings
JWT_SECRET_KEY = REDACTED
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = REDACTED

# LDAP Configuration
LDAP_SERVER = os.getenv("LDAP_SERVER", "ldaps://ldap-ad.abbvienet.com:636")
LDAP_DOMAIN = os.getenv("LDAP_DOMAIN", "abbvienet.com")
LDAP_SERVICE_USERNAME = os.getenv("LDAP_SERVICE_USERNAME", "SVC-IPLDAP")
LDAP_SERVICE_PASSWORD = REDACTED
LDAP_USERS_CONTAINER = os.getenv("LDAP_USERS_CONTAINER", "OU=People,DC=abbvienet,DC=com")

# Models
class User(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# JWT token functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

# Authentication function
def get_current_user(request: Request):
    if "authenticated" not in request.session or not request.session["authenticated"]:
        logger.warning("Authentication failed - No valid session")
        return None
    return {"username": request.session.get("username"), "email": request.session.get("email")}

# LDAP Authentication
def authenticate_with_ldap(username: str, password: str):
    try:
        # Connect to LDAP server
        server = Server(LDAP_SERVER, get_info=ALL)
        conn = Connection(
            server,
            user=f"{LDAP_DOMAIN}\\{username}",
            password=REDACTED
            authentication=NTLM,
            auto_bind=True
        )

        # Search for the user in the LDAP directory
        search_filter = f"(&(objectclass=user)(sAMAccountName={username}))"
        conn.search(
            search_base=LDAP_USERS_CONTAINER,
            search_filter=search_filter,
            attributes=['givenName', 'mail']
        )

        if conn.entries:
            # User authenticated successfully
            user_data = {
                "username": username,
                "email": conn.entries[0].mail.value if hasattr(conn.entries[0], 'mail') else None
            }
            return user_data
        else:
            # User not found in LDAP
            return None
    except Exception as e:
        logger.error(f"LDAP Authentication error: {str(e)}")
        return None

# Routes
@app.get("/")
def read_root():
    return {"message": "OCR Chatbot API"}

@app.get("/ping")
def ping():
    """Simple endpoint to test if server is running"""
    return {"status": "ok", "message": "Server is running"}

@app.get("/routes")
def list_routes():
    """List all available routes for debugging"""
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "name": route.name,
            "methods": [method for method in route.methods]
        })
    return {"routes": routes}

@app.post("/api/login")
async def login(user: User, request: Request, response: Response):
    try:
        # Authenticate with LDAP
        user_data = authenticate_with_ldap(user.username, user.password)
        
        if not user_data:
            logger.warning(f"Login failed for user: {user.username}")
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Invalid credentials"}
            )
        
        # Create access token
        access_token_expires = REDACTED
        access_token = REDACTED
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        
        # Set session data
        request.session["authenticated"] = True
        request.session["username"] = user.username
        request.session["email"] = user_data.get("email")
        
        logger.info(f"Login successful for user: {user.username}")
        return {"success": True, "username": user.username, "access_token": access_token, "token_type": "bearer"}
    
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"}
        )

@app.get("/api/check-auth")
async def check_auth(request: Request):
    try:
        user = get_current_user(request)
        if user:
            logger.info(f"Valid session found for user: {user['username']}")
            return {"authenticated": True, "username": user["username"]}
        
        logger.info("No valid session found")
        return JSONResponse(
            status_code=401,
            content={"authenticated": False}
        )
    
    except Exception as e:
        logger.error(f"Check auth error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"}
        )

@app.post("/api/logout")
async def logout(request: Request):
    username = request.session.get("username", "unknown")
    request.session.clear()
    logger.info(f"User logged out: {username}")
    return {"success": True}

@app.get("/api/profile")
async def get_profile(request: Request):
    user = get_current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized"}
        )
    
    # Return user profile data from session
    user_data = {
        "username": user["username"],
        "email": user["email"]
    }
    logger.info(f"Profile data returned for user: {user['username']}")
    return user_data

@app.post("/api/chat/upload-coa")
async def upload_coa_file(file: UploadFile = File(...), request: Request = None):
    """
    Handle file upload from chat interaction and process it with textract then GPT
    """
    # Temporarily disabled authentication for testing
    # user = get_current_user(request)
    # if not user:
    #     return JSONResponse(
    #         status_code=401,
    #         content={"error": "Unauthorized"}
    #     )
    
    try:
        # Generate a unique process ID for tracking
        process_id = str(uuid.uuid4())
        
        # Save the original filename without extension for output naming
        original_filename = os.path.splitext(file.filename)[0]
        
        # Create temp directory if it doesn't exist
        base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        # Save the uploaded file with original filename
        pdf_file_path = os.path.join(base_path, f"{original_filename}.pdf")
        
        with open(pdf_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"Processing PDF file: {file.filename}")
        
        # Step 1: Process with Textract to get Excel file
        from textractservices.textract_single import process_direct_file
        excel_file_path = process_direct_file(pdf_file_path, base_path)
        
        if not excel_file_path:
            raise Exception("Failed to process the PDF file with Textract")
        
        logger.info(f"Textract processing complete. Excel file created at: {excel_file_path}")
        
        # Define output files with original filename
        excel_path = os.path.join(base_path, f"{original_filename}.xlsx")
        csv_path = os.path.join(base_path, f"{original_filename}_data.csv")
        json_info_path = os.path.join(base_path, f"{original_filename}_info.json")
        combined_path = os.path.join(base_path, f"{original_filename}_results.json")
        unified_excel_path = os.path.join(base_path, f"{original_filename}_unified.xlsx")
        
        # Ensure the Excel file has the original filename
        if os.path.exists(excel_file_path) and excel_file_path != excel_path:
            shutil.copy2(excel_file_path, excel_path)
        
        # Step 2: Process Excel with GPT
        from textractservices.gpt_excel_extractor import GPTCoAExtractor
        llm_url = "https://api-epic.ir-gateway.abbvienet.com/iliad/api/v1/chat/claude-3.7-sonnet"
        llm_api_key = REDACTED
        
        logger.info("Starting GPT analysis of Excel file")
        extractor = GPTCoAExtractor(api_key=llm_api_key, api_url=llm_url)
        df, product_info = extractor.process_excel(excel_file_path)
        
        # Save output files with original filename
        df.to_csv(csv_path, index=False)
        
        with open(json_info_path, 'w') as f:
            json.dump(product_info, f, indent=2)
            
        with open(combined_path, 'w') as f:
            json.dump({
                'product_info': product_info,
                'test_data': df.to_dict('records')
            }, f, indent=2)
            
        # Create unified Excel file
        extractor.create_unified_excel(df, product_info, unified_excel_path)
            
        logger.info(f"Created output files with original filename")
        
        # Create download links
        download_links = {
            "Excel File": f"/download/{os.path.basename(excel_path)}",
            "Unified Excel Report": f"/download/{os.path.basename(unified_excel_path)}",
            "CSV Data": f"/download/{os.path.basename(csv_path)}",
            "JSON Info": f"/download/{os.path.basename(json_info_path)}",
            "Complete Results": f"/download/{os.path.basename(combined_path)}"
        }
        
        # Create a summary message with extracted information
        summary_message = f"""## Certificate of Analysis Processing Complete

**Product Information:**
- Product Name: {product_info.get('product_name', 'Not found')}
- Batch/Lot Number: {product_info.get('batch_number', 'Not found')}
- Manufacturer: {product_info.get('manufacturer', 'Not found')}

The document has been processed successfully. You can download the results below.
        """
        
        # S3 cleanup code removed - no longer using S3 for storage
        
        # Combine results to return to frontend
        result = {
            "process_id": process_id,
            "file_name": file.filename,
            "original_filename": original_filename,
            "product_info": product_info,
            "test_data": df.to_dict('records'),
            "excel_path": excel_path,
            "csv_path": csv_path,
            "json_info_path": json_info_path,
            "combined_json_path": combined_path,
            "unified_excel_path": unified_excel_path,
            "download_links": download_links,
            "message": summary_message,
            "success": True
        }
        
        logger.info(f"File processing complete: {file.filename}")
        return result
        
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error processing file: {str(e)}"}
        )
    finally:
        file.file.close()

@app.post("/upload-coa")
async def public_upload_coa_file(file: UploadFile = File(...)):
    """
    Public endpoint to handle file upload from chat interaction without requiring authentication
    This simplifies testing and development
    """
    try:
        # Generate a unique process ID for tracking
        process_id = str(uuid.uuid4())
        
        # Save the original filename without extension for output naming
        original_filename = os.path.splitext(file.filename)[0]
        
        # Create temp directory if it doesn't exist
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        # Save the uploaded file with original filename
        pdf_file_path = os.path.join(base_path, f"{original_filename}.pdf")
        
        with open(pdf_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"Processing PDF file: {file.filename}")
        
        # Step 1: Process with Textract to get Excel file
        try:
            from textractservices.textract_single import process_direct_file
            excel_file_path = process_direct_file(pdf_file_path, base_path)
            
            if not excel_file_path:
                raise Exception("Failed to process the PDF file with Textract")
            
            logger.info(f"Textract processing complete. Excel file created at: {excel_file_path}")
            
            # Define output files with original filename
            excel_path = os.path.join(base_path, f"{original_filename}.xlsx")
            csv_path = os.path.join(base_path, f"{original_filename}_data.csv")
            json_info_path = os.path.join(base_path, f"{original_filename}_info.json")
            combined_path = os.path.join(base_path, f"{original_filename}_results.json")
            unified_excel_path = os.path.join(base_path, f"{original_filename}_unified.xlsx")
            
            # Ensure the Excel file has the original filename
            if os.path.exists(excel_file_path) and excel_file_path != excel_path:
                shutil.copy2(excel_file_path, excel_path)
            
            # Step 2: Process Excel with GPT
            from textractservices.gpt_excel_extractor import GPTCoAExtractor
            llm_url = "https://api-epic.ir-gateway.abbvienet.com/iliad/api/v1/chat/claude-3.7-sonnet"
            llm_api_key = REDACTED
            
            logger.info("Starting GPT analysis of Excel file")
            extractor = GPTCoAExtractor(api_key=llm_api_key, api_url=llm_url)
            df, product_info = extractor.process_excel(excel_file_path)
            
            # Save output files with original filename
            df.to_csv(csv_path, index=False)
            
            with open(json_info_path, 'w') as f:
                json.dump(product_info, f, indent=2)
                
            with open(combined_path, 'w') as f:
                json.dump({
                    'product_info': product_info,
                    'test_data': df.to_dict('records')
                }, f, indent=2)
                
            # Create unified Excel file
            extractor.create_unified_excel(df, product_info, unified_excel_path)
                
            logger.info(f"Created output files with original filename")
            
            # Create download links
            download_links = {
                "Excel File": f"/download/{os.path.basename(excel_path)}",
                "Unified Excel Report": f"/download/{os.path.basename(unified_excel_path)}",
                "CSV Data": f"/download/{os.path.basename(csv_path)}",
                "JSON Info": f"/download/{os.path.basename(json_info_path)}",
                "Complete Results": f"/download/{os.path.basename(combined_path)}"
            }
            
            # Create a summary message with extracted information
            summary_message = f"""## Certificate of Analysis Processing Complete

**Product Information:**
- Product Name: {product_info.get('product_name', 'Not found')}
- Batch/Lot Number: {product_info.get('batch_number', 'Not found')}
- Manufacturer: {product_info.get('manufacturer', 'Not found')}

The document has been processed successfully. You can download the results below.
            """
            
            # Combine results to return to frontend
            result = {
                "process_id": process_id,
                "file_name": file.filename,
                "original_filename": original_filename,
                "product_info": product_info,
                "test_data": df.to_dict('records'),
                "excel_path": excel_path,
                "csv_path": csv_path,
                "json_info_path": json_info_path,
                "combined_json_path": combined_path,
                "unified_excel_path": unified_excel_path,
                "download_links": download_links,
                "message": summary_message,
                "success": True
            }
            
            logger.info(f"File processing complete: {file.filename}")
            return result
            
        except Exception as processing_error:
            logger.error(f"Error during processing: {str(processing_error)}")
            # Return a simplified response if processing fails
            result = {
                "process_id": process_id,
                "file_name": file.filename,
                "original_filename": original_filename,
                "product_info": {
                    "product_name": "Could not extract",
                    "batch_number": "Could not extract",
                    "date_of_manufacture": "Could not extract"
                },
                "test_data": [
                    {
                        "test": "Document processing",
                        "specification": "PDF should be processed correctly",
                        "result": "Processing failed - see logs",
                        "unit": "N/A"
                    }
                ],
                "success": False,
                "error": str(processing_error)
            }
        
        logger.info(f"File processing complete: {file.filename}")
        return result
        
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error processing file: {str(e)}"}
        )
    finally:
        file.file.close()

@app.post("/test-upload")
async def test_upload(file: UploadFile = File(...)):
    """
    Simple test endpoint for file uploads with minimal processing
    """
    try:
        # Just return basic file info without processing
        return {
            "success": True,
            "filename": file.filename,
            "content_type": file.content_type,
            "size": file.size,
            "message": "File received successfully"
        }
    except Exception as e:
        logger.error(f"Test upload error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Test upload error: {str(e)}"}
        )

@app.post("/upload-hbr-pdf")
async def upload_hbr_pdf(file: UploadFile = File(...)):
    """
    Public endpoint to handle HBR PDF file upload
    """
    try:
        # Generate a unique process ID for tracking
        process_id = str(uuid.uuid4())
        
        # Save the original filename without extension for output naming
        original_filename = os.path.splitext(file.filename)[0]
        
        # Create temp directory if it doesn't exist
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        # Save the uploaded file with original filename
        pdf_file_path = os.path.join(base_path, f"{original_filename}.pdf")
        
        with open(pdf_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"Saved HBR PDF file: {file.filename}")
        
        # Store the PDF path in a session variable for later processing with Excel config
        # We'll use a simple file-based storage for this
        storage_path = os.path.join(base_path, f"{process_id}_pdf_path.txt")
        with open(storage_path, "w") as f:
            f.write(pdf_file_path)
        
        return {
            "success": True,
            "message": "HBR PDF uploaded successfully. Please upload the Excel configuration file next.",
            "process_id": process_id,
            "pdf_file": original_filename
        }
        
    except Exception as e:
        logger.error(f"Error processing HBR PDF file: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error processing file: {str(e)}"}
        )
    finally:
        file.file.close()

@app.post("/upload-hbr-excel")
async def upload_hbr_excel(file: UploadFile = File(...), process_id: str = Form(...)):
    """
    Public endpoint to handle HBR Excel configuration file upload and process with previously uploaded PDF
    """
    try:
        # Save the original filename without extension for output naming
        original_filename = os.path.splitext(file.filename)[0]
        
        # Create temp directory if it doesn't exist
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        # Save the uploaded Excel file
        excel_file_path = os.path.join(base_path, f"{original_filename}.xlsx")
        
        with open(excel_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"Saved HBR Excel file: {file.filename}")
        
        # Get the PDF path from the stored file
        pdf_path_file = os.path.join(base_path, f"{process_id}_pdf_path.txt")
        if not os.path.exists(pdf_path_file):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "PDF file not found. Please upload the PDF file first."}
            )
        
        with open(pdf_path_file, "r") as f:
            pdf_file_path = f.read().strip()
        
        if not os.path.exists(pdf_file_path):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "PDF file not found on server. Please upload the PDF file again."}            )
        
        # Process the HBR files using the TextractProcessor from hbr_python.py
        try:
            from textractservices.hbr_python import TextractProcessor
            
            # Create the TextractProcessor (it handles session creation internally)
            logger.info("Initializing TextractProcessor for HBR processing")
            processor = TextractProcessor()
            
            # Process the PDF with the Excel configuration
            logger.info(f"Processing HBR PDF with Excel configuration: {pdf_file_path}, {excel_file_path}")
            results = processor.process_pdf(pdf_file_path, excel_file_path)
            
            # Generate output paths for download - use a simple name without spaces
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            results_filename = f"hbr_results_{timestamp}.xlsx"
            results_excel_path = os.path.join(base_path, results_filename)
            
            # Use pandas to save the results directly in the temp directory
            results_df = pd.DataFrame(results)
            results_df.to_excel(results_excel_path, index=False)
            logger.info(f"Saved HBR results to: {results_excel_path}")
            
            # Verify the file exists before creating the download link
            if not os.path.exists(results_excel_path):
                logger.error(f"Results file was not created at expected path: {results_excel_path}")
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": "Failed to create results file"}
                )
                
            # Create download links with the filename that actually exists
            download_links = {
                "Results Excel": f"/download/{results_filename}"
            }
            
            # Log the download link for debugging
            logger.info(f"Created download link: /download/{results_filename}")
            
            # Create a summary message with extracted information
            summary_message = f"""## HBR Document Processing Complete

**Document Information:**
- PDF: {os.path.basename(pdf_file_path)}
- Configuration: {os.path.basename(excel_file_path)}
- Parameters Extracted: {len(results)}

The document has been processed successfully. You can download the results below.
            """
            
            # Clean up the temporary file
            if os.path.exists(pdf_path_file):
                os.remove(pdf_path_file)
            
            return {
                "success": True,
                "process_id": process_id,
                "message": summary_message,
                "download_links": download_links,
                "results": results
            }
            
        except Exception as processing_error:
            logger.error(f"Error during HBR processing: {str(processing_error)}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Error processing HBR files: {str(processing_error)}"}
            )
        
    except Exception as e:
        logger.error(f"Error processing HBR Excel file: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error processing file: {str(e)}"}
        )
    finally:
        file.file.close()

@app.get("/download/{file_name:path}")
async def download_file(file_name: str):
    """
    Endpoint to download files from the temp directory
    """
    try:
        # URL decode the file name
        decoded_file_name = unquote(file_name)
        logger.info(f"Download request for file: {decoded_file_name}")
        
        # Check if file exists in the temp directory
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        file_path = os.path.join(base_path, decoded_file_name)
        logger.info(f"Looking for file at: {file_path}")
        
        # If not found directly, try to find it in subdirectories
        if not os.path.exists(file_path):
            logger.info(f"File not found at {file_path}, searching in subdirectories...")
            found = False
            for root, dirs, files in os.walk(base_path):
                logger.info(f"Searching in directory: {root}")
                for file in files:
                    logger.info(f"Checking file: {file}")
                    if file == decoded_file_name:
                        file_path = os.path.join(root, file)
                        logger.info(f"Found file at: {file_path}")
                        found = True
                        break
                if found:
                    break
        
        # List all files in temp directory for debugging
        logger.info("Files in temp directory:")
        for root, dirs, files in os.walk(base_path):
            for file in files:
                logger.info(f"  {os.path.join(root, file)}")
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            raise HTTPException(status_code=404, detail=f"File not found: {decoded_file_name}")
        
        # Determine content type based on file extension
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            if decoded_file_name.endswith('.xlsx'):
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            elif decoded_file_name.endswith('.csv'):
                content_type = 'text/csv'
            elif decoded_file_name.endswith('.json'):
                content_type = 'application/json'
            else:
                content_type = 'application/octet-stream'
        
        # Return the file with CORS headers
        logger.info(f"Serving file: {file_path} with content type: {content_type}")
        response = FileResponse(
            path=file_path, 
            filename=os.path.basename(decoded_file_name),
            media_type=content_type
        )
        
        # Add CORS headers
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        
        return response
    
    except Exception as e:
        logger.error(f"Error serving file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving file: {str(e)}")

if __name__ == "__main__":
    # Get server config from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    # Increase timeouts for long-running requests
    uvicorn.run("app:app", host=host, port=port, reload=debug, timeout_keep_alive=300, timeout_graceful_shutdown=300) 