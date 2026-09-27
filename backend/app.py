#import hashlib_md4_patch  # Enable MD4 support for LDAP/NTLM
from fastapi import FastAPI, HTTPException, Depends, Request, Response, File, UploadFile, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uvicorn
import jwt  # PyJWT package
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
from urllib.parse import unquote, quote
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
# backend/app.py - Add after line 27
import aiofiles
from collections import defaultdict
import time
import requests

# Import Ruben's RAG dependencies
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'Ruben_AI_Chatbot-main'))
from dependency.services.iliad_service import IliadService
from dependency.services.embedding_service import EmbeddingService
from langchain_text_splitters import RecursiveCharacterTextSplitter
# Legacy Ruben imports - commented out as we use Phase 4+ services now
# from dependency.processors.text_processor import TextProcessor
# from dependency.agents.hybrid_search import HybridSearch
# from dependency.agents.question_rephraser import QuestionRephraser
# from dependency.agents.information_retriever import InformationRetriever

# Import Phase 3 - Layout-aware chunking services
from services.textract_parser import TextractParser
from services.chunk_transformer import chunk_textract_blocks, get_chunk_statistics
from services.weaviate_indexer import WeaviateIndexer, index_document_chunks

# Import Phase 4 - Multi-Agent RAG Orchestration
from services.rag_orchestrator import get_rag_orchestrator, process_rag_query_sync

# Import Phase 6 - Neo4j Structural Integration
from services.neo4j_ingestion import index_document_to_neo4j, get_neo4j_ingestion_service

# Configure logging early so it's available for all functions
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("ocr-chatbot")

# Initialize Ruben's services
ILIAD_URL = "https://api-epic.ir-gateway.abbvienet.com/iliad"
ILIAD_API_KEY = REDACTED
# Default user token for authentication - will be updated dynamically

# Get auth token from the correct auth service
def get_auth_token():
    """Fetch authentication token from the auth service"""
    try:
        # Use the correct auth service endpoint
        auth_url = "http://gprd-auth:8010/auth.service/auth/token"

        # Make request to get token - try with Windows auth
        response = requests.get(auth_url, timeout=10, auth=requests.auth.HTTPBasicAuth('', ''))

        if response.status_code == 200:
            # Parse the JSON response to get the token
            data = response.json()
            token = REDACTED
            if token:
                logger.info(f"[AUTH] Successfully obtained token from auth service (length: {len(token)})")
                return token
            else:
                logger.warning(f"[AUTH] No token in response")
                # Use the hardcoded token as fallback
                fallback_token = REDACTED
                logger.info("[AUTH] Using fallback token")
                return fallback_token
        else:
            logger.warning(f"[AUTH] Auth service returned status {response.status_code}")
            # Use the hardcoded token as fallback
            fallback_token = REDACTED
            logger.info("[AUTH] Using fallback token due to auth service error")
            return fallback_token
    except Exception as e:
        logger.warning(f"[AUTH] Failed to get token from auth service: {e}")
        # Use the hardcoded token as fallback
        fallback_token = REDACTED
        logger.info("[AUTH] Using fallback token due to exception")
        return fallback_token

# Get initial token for service startup
USER_TOKEN = REDACTED

iliad_service = IliadService(iliad_url=ILIAD_URL, iliad_api_key=ILIAD_API_KEY, user_token=USER_TOKEN)
# Use text-embedding-3-large for Iliad embedding service (for indexing)
# Note: Embeddings don't need user token
embedding_service = EmbeddingService(
    iliad_url=ILIAD_URL,
    iliad_api_key=REDACTED
    user_token=REDACTED
    model="text-embedding-3-large"  # Use 3-large for embeddings
)
# Legacy Ruben services - commented out as we use Phase 4+ services now
# text_processor = TextProcessor(anthropic_api_url=ILIAD_URL, anthropic_api_key=ILIAD_API_KEY)
# hybrid_search = HybridSearch(
#     base_url=ILIAD_URL,
#     api_key=ILIAD_API_KEY,
#     user_token=USER_TOKEN,
#     embedding_model="text-embedding-3-large"
# )
# question_rephraser = QuestionRephraser(api_key=ILIAD_API_KEY, api_url=ILIAD_URL)
# information_retriever = InformationRetriever(
#     api_key=ILIAD_API_KEY,
#     api_url=ILIAD_URL,
#     iliad_url=ILIAD_URL,
#     iliad_api_key=ILIAD_API_KEY,
#     user_token=USER_TOKEN
# )

# Text splitter for chunking (same as Ruben's)
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    length_function=len,
    separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
)

# Add progress tracking store
progress_store: Dict[str, Dict[str, Any]] = {}

# Helper functions for document processing (like Ruben's)
def generate_summary(text: str, max_length: int = 2000) -> str:
    """Generate summary using LLM"""
    try:
        if len(text) > max_length:
            text = text[:max_length] + "..."

        prompt = f"Provide a one line summary of the following document:\n\n{text}"
        response = requests.post(
            url=f"{ILIAD_URL}/api/v1/chat/gpt-4o-mini-global",
            json={"messages": [{"role": "user", "content": prompt}]},
            headers={"x-api-key": ILIAD_API_KEY}
        )

        if response.status_code == 200:
            return response.json()['completion']['content']
        return "Certificate of Analysis document"
    except Exception as e:
        logger.error(f"Summary generation error: {e}")
        return "Document summary unavailable"

def extract_keywords(text: str, max_length: int = 2000) -> str:
    """Extract keywords using LLM"""
    try:
        if len(text) > max_length:
            text = text[:max_length] + "..."

        prompt = f"Extract important keywords for the following text. Not more than 20 keywords:\n\n{text}"
        response = requests.post(
            url=f"{ILIAD_URL}/api/v1/chat/gpt-4o-mini-global",
            json={"messages": [{"role": "user", "content": prompt}]},
            headers={"x-api-key": ILIAD_API_KEY}
        )

        if response.status_code == 200:
            return response.json()['completion']['content']
        return "COA, certificate, analysis, quality, test"
    except Exception as e:
        logger.error(f"Keyword extraction error: {e}")
        return "COA, analysis, certificate"

#to handle special characters
def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent encoding issues with special characters
    """
    import re
    
    # Get file extension
    name, ext = os.path.splitext(filename)
    
    # Replace problematic characters
    safe_name = re.sub(r'\s+', '_', name)  # Spaces to underscores
    safe_name = re.sub(r'[()]', '', safe_name)  # Remove parentheses
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', safe_name)  # Other special chars to _
    safe_name = re.sub(r'_+', '_', safe_name)  # Multiple underscores to single
    
    return f"{safe_name}{ext}"
# Cancellation token system
cancellation_tokens: Dict[str, bool] = {}
active_processes: Dict[str, Dict[str, Any]] = {}
process_files: Dict[str, List[str]] = {}  # Track files created by each process

def is_process_cancelled(process_id: str) -> bool:
    """Check if a process has been cancelled"""
    return cancellation_tokens.get(process_id, False)

def cancel_process_token(process_id: str):
    """Mark a process as cancelled"""
    cancellation_tokens[process_id] = True
    update_progress(process_id, "cancelled", 0, "Process cancelled by user")
    logger.info(f"🛑 Process {process_id} marked as cancelled")

def register_process(process_id: str, process_type: str):
    """Register a new active process"""
    active_processes[process_id] = {
        "type": process_type,
        "start_time": time.time(),
        "stage": "starting",
        "cancellable": True
    }
    process_files[process_id] = []

def add_process_file(process_id: str, file_path: str):
    """Track a file created by a process"""
    if process_id in process_files:
        process_files[process_id].append(file_path)

def cleanup_process_files(process_id: str):
    """Clean up all files created by a process with retry logic for locked files"""
    import gc

    if process_id in process_files:
        for file_path in reversed(process_files[process_id]):
            if not os.path.exists(file_path):
                continue

            # Try to delete with retry logic (for Windows file locking issues)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Force garbage collection to close any open file handles
                    gc.collect()

                    # Try to remove the file
                    os.remove(file_path)
                    logger.info(f"🗑️ Cleaned up file: {file_path}")
                    break  # Success, exit retry loop

                except PermissionError as e:
                    if attempt < max_retries - 1:
                        # File is locked, wait and retry
                        logger.debug(f"⏳ File locked, retrying cleanup ({attempt + 1}/{max_retries}): {file_path}")
                        time.sleep(0.5)  # Wait 500ms before retry
                    else:
                        # Final attempt failed, log warning
                        logger.warning(f"⚠️ Failed to cleanup file after {max_retries} attempts (file may be in use): {file_path}")
                        logger.info(f"💡 File will be overwritten on next upload: {os.path.basename(file_path)}")

                except Exception as e:
                    # Other errors (not locking issues)
                    logger.warning(f"⚠️ Failed to cleanup file {file_path}: {e}")
                    break  # Don't retry for non-locking errors

        del process_files[process_id]

def check_cancellation(process_id: str):
    """Raise exception if process is cancelled"""
    if is_process_cancelled(process_id):
        logger.info(f"⏹️ Process {process_id} stopping due to cancellation - cleanup starting")
        cleanup_process_files(process_id)
        logger.info(f"⏹️ Process {process_id} cleanup complete - raising cancellation exception")
        raise Exception(f"Process {process_id} cancelled by user")

def complete_process(process_id: str):
    """Mark process as completed and cleanup"""
    if process_id in active_processes:
        del active_processes[process_id]
    if process_id in cancellation_tokens:
        del cancellation_tokens[process_id]
    # Don't cleanup files on successful completion
    if process_id in process_files:
        del process_files[process_id]

def update_progress(process_id: str, stage: str, progress: int, message: str = ""):
    """Update progress for a given process ID"""
    if process_id not in progress_store:
        progress_store[process_id] = {}

    # Update fields instead of replacing entire dict (preserves iliad_source, etc.)
    progress_store[process_id].update({
        "stage": stage,
        "progress": progress,
        "message": message,
        "timestamp": time.time()
    })
    logger.info(f"Progress update - {process_id}: {stage} {progress}% - {message}")

def get_progress(process_id: str) -> Optional[Dict[str, Any]]:
    """Get progress for a given process ID"""
    return progress_store.get(process_id)

def cleanup_old_progress():
    """Clean up progress entries older than 1 hour"""
    current_time = time.time()
    to_remove = []
    for process_id, data in progress_store.items():
        if current_time - data.get("timestamp", 0) > 3600:  # 1 hour
            to_remove.append(process_id)
    for process_id in to_remove:
        del progress_store[process_id]

# Load environment variables
load_dotenv()

# Create thread pool for CPU-intensive tasks
executor = ThreadPoolExecutor(max_workers=2)

# Create async wrapper for CPU-intensive tasks
async def run_cpu_intensive_task(func, *args, **kwargs):
    """Run CPU-intensive tasks in thread pool to avoid blocking"""
    loop = asyncio.get_event_loop()
    # Note: run_in_executor doesn't support kwargs, only positional args
    # If kwargs are provided, we need to create a wrapper
    if kwargs:
        # Create a wrapper function that calls func with both args and kwargs
        def wrapper():
            return func(*args, **kwargs)
        return await loop.run_in_executor(executor, wrapper)
    else:
        # No kwargs, can call directly with positional args
        return await loop.run_in_executor(executor, func, *args)

# Create FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up OCR Chatbot API")
    yield
    # Shutdown
    logger.info("Shutting down OCR Chatbot API") 
    executor.shutdown(wait=True)
    logger.info("Thread pool executor shut down")

# Create FastAPI app with lifespan
app = FastAPI(title="OCR Chatbot API", lifespan=lifespan)

# Configure multipart form parsing for large file uploads
from starlette.formparsers import MultiPartParser
MultiPartParser.max_file_size = 100 * 1024 * 1024  # 100MB limit

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
    session_cookie="session",
    path="/",
    same_site="lax",  # Important for cross-origin requests
    https_only=False,  # Set to True if using HTTPS
)

# JWT settings
JWT_SECRET_KEY = REDACTED
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = REDACTED

# Import and include chat routes for Phase 2 Chat History Persistence
try:
    from services.chat_routes import router as chat_router
    from services.database import test_connection as test_db_connection, close_pool as close_db_pool
    app.include_router(chat_router)
    logger.info("Chat history routes registered successfully")

    # Test database connection on startup
    if test_db_connection():
        logger.info("PostgreSQL database connection verified")
    else:
        logger.warning("PostgreSQL database connection failed - chat history features may not work")
except ImportError as e:
    logger.warning(f"Chat routes not available: {e}")

# Import and include schema routes for extraction schemas
try:
    from services.schema_routes import router as schema_router
    app.include_router(schema_router)
    logger.info("Extraction schema routes registered successfully")
except ImportError as e:
    logger.warning(f"Schema routes not available: {e}")
except Exception as e:
    logger.error(f"Error initializing chat routes: {e}")

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
            return {
                "authenticated": True, 
                "username": user["username"],
                "email": user.get("email", "")
            }
        
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
        update_progress(process_id, "uploading", 0, "Starting upload...")
        # Save the original filename without extension for output naming
        #original_filename = os.path.splitext(file.filename)[0]
        sanitized_filename = sanitize_filename(file.filename)
        original_filename = os.path.splitext(sanitized_filename)[0]
        # Create temp directory if it doesn't exist
        base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        # Save the uploaded file with original filename
        pdf_file_path = os.path.join(base_path, f"{original_filename}.pdf")
        
        async with aiofiles.open(pdf_file_path, "wb") as buffer:
            await buffer.write(await file.read())
        
        logger.info(f"Processing PDF file: {file.filename}")
        
        # Step 1: Process with Textract to get Excel file
        from textractservices.textract_single import process_direct_file
        excel_file_path = process_direct_file(pdf_file_path, base_path)
        
        if not excel_file_path:
            raise Exception("Failed to process the PDF file with Textract")
        
        logger.info(f"Textract processing complete. Excel file created at: {excel_file_path}")
        
        # Define only the unified Excel output file
        unified_excel_path = os.path.join(base_path, f"{original_filename}_unified.xlsx")
        
        # Step 2 & 3: Process Excel with GPT AND Advanced Validation IN PARALLEL
        from textractservices.gpt_excel_extractor import GPTCoAExtractor
        from textractservices.final_with_endotoxins import process_coa_optimized
        
        llm_url = "https://api-epic.ir-gateway.abbvienet.com/iliad/api/v1/chat/claude-3.7-sonnet"
        llm_api_key = REDACTED
        
        logger.info("Starting parallel processing: GPT analysis + Advanced validation")
        
        # Create tasks that can run in parallel
        extractor = GPTCoAExtractor(api_key=llm_api_key, api_url=llm_url)
        
        # Set up cancellation callback for the extractor
        extractor.set_cancellation_callback(lambda: check_cancellation(process_id))
        
        # Set up progress callback for the extractor
        extractor.set_progress_callback(lambda progress, message: update_progress(process_id, "analyzing", progress, message))
        
        # Define functions for parallel execution
        def run_gpt_processing():
            check_cancellation(process_id)
            # Direct call - the extractor now has cancellation support and progress callbacks
            df, product_info = extractor.process_excel_with_llm_metadata(excel_file_path, pdf_file_path)
            
            check_cancellation(process_id)
            update_progress(process_id, "analyzing", 59, "Creating unified Excel report...")
            extractor.create_unified_excel(df, product_info, unified_excel_path)
            return df, product_info
        
        # Run both processes in parallel
        try:
            # Checkpoint 5: Before GPT processing
            check_cancellation(process_id)
            
            # First run GPT processing to get enhanced metadata with progress simulation
            gpt_task = asyncio.create_task(
                run_cpu_intensive_task(run_gpt_processing)
            )
            gpt_progress_task = asyncio.create_task(
                simulate_progress(process_id, 40, 60, 25, "analyzing", "AI processing with GPT-4")
            )
            
            gpt_result = await gpt_task
            gpt_progress_task.cancel()  # Stop simulation when done
            df, product_info = gpt_result
            
            # Checkpoint 6: After GPT processing
            check_cancellation(process_id)
            update_progress(process_id, "analyzing", 60, "GPT processing complete")
            logger.info(f"GPT processing complete. Created unified Excel file: {unified_excel_path}")
            
            # Checkpoint 7: Before validation
            check_cancellation(process_id)
            
            # Now run advanced validation with enhanced metadata
            def run_advanced_validation_with_metadata():
                check_cancellation(process_id)
                # Validation function uses its own progress callbacks (60-80% range)
                
                blocks_json_path = os.path.join(base_path, f"{original_filename}_blocks.json")
                if os.path.exists(blocks_json_path):
                    add_process_file(process_id, blocks_json_path)
                    
                    check_cancellation(process_id)
                    # Validation handles its own progress (60-80% range)
                    
                    # Direct call - we'll add cancellation support to this function later
                    result = process_coa_optimized(
                        pdf_file_path, blocks_json_path, unified_excel_path, base_path, product_info,
                        progress_callback=lambda progress, message: update_progress(process_id, "analyzing", progress, message)
                    )
                    
                    check_cancellation(process_id)
                    # Validation already completed to 80%
                    return result
                return None
            
            # Checkpoint 8: Run validation
            validation_result = await run_cpu_intensive_task(run_advanced_validation_with_metadata)
            
            # Checkpoint 9: After validation
            check_cancellation(process_id)
            update_progress(process_id, "analyzing", 90, "Validation complete, finalizing report...")
            
            # Handle advanced validation results
            if validation_result:
                enhanced_excel_path = validation_result.get('enhanced_excel_path')
                enhanced_json_path = validation_result.get('enhanced_json_path')
                validation_status = validation_result.get('validation_status')
                
                logger.info(f"Advanced validation completed with status: {validation_status}")
                
                # Use enhanced file as the primary output if available
                if validation_status == 'enhanced' and enhanced_excel_path and os.path.exists(enhanced_excel_path):
                    primary_excel_path = enhanced_excel_path
                    logger.info(f"Using enhanced Excel file: {enhanced_excel_path}")
                else:
                    primary_excel_path = unified_excel_path
                    logger.info(f"Using original unified Excel file: {unified_excel_path}")
            else:
                logger.warning("Advanced validation skipped - blocks JSON not found")
                primary_excel_path = unified_excel_path
                
        except Exception as e:
            logger.error(f"Error during parallel processing: {str(e)}")
            # Fallback to sequential processing
            logger.info("Falling back to sequential processing...")
            extractor = GPTCoAExtractor(api_key=llm_api_key, api_url=llm_url)
            df, product_info = extractor.process_excel_with_llm_metadata(excel_file_path, pdf_file_path)
            extractor.create_unified_excel(df, product_info, unified_excel_path)
            
            # Try advanced validation with enhanced metadata in fallback
            try:
                blocks_json_path = os.path.join(base_path, f"{original_filename}_blocks.json")
                if os.path.exists(blocks_json_path):
                    validation_result = process_coa_optimized(
                        pdf_file_path, blocks_json_path, unified_excel_path, base_path, product_info
                    )
                    if validation_result and validation_result.get('validation_status') == 'enhanced':
                        enhanced_excel_path = validation_result.get('enhanced_excel_path')
                        if enhanced_excel_path and os.path.exists(enhanced_excel_path):
                            primary_excel_path = enhanced_excel_path
                        else:
                            primary_excel_path = unified_excel_path
                    else:
                        primary_excel_path = unified_excel_path
                else:
                    primary_excel_path = unified_excel_path
            except Exception as fallback_error:
                logger.warning(f"Advanced validation failed in fallback: {fallback_error}")
                primary_excel_path = unified_excel_path
        
        # Clean up the intermediate Excel file created by Textract
        if os.path.exists(excel_file_path) and excel_file_path != unified_excel_path:
            try:
                os.remove(excel_file_path)
                logger.info(f"Cleaned up intermediate Excel file: {excel_file_path}")
            except Exception as e:
                logger.warning(f"Could not remove intermediate Excel file: {e}")
        
        # Clean up any accidentally created files with old naming patterns (but preserve enhanced files)
        patterns_to_clean = [
            f"{original_filename}_data.csv",
            f"{original_filename}_info.json",
            f"{original_filename}_results.json",
            f"{original_filename}.csv",
            f"{original_filename}.xlsx",
            f"{original_filename}_temp.csv"
        ]
        
        for pattern in patterns_to_clean:
            file_to_clean = os.path.join(base_path, pattern)
            if os.path.exists(file_to_clean):
                try:
                    os.remove(file_to_clean)
                    logger.info(f"Cleaned up extra file: {file_to_clean}")
                except Exception as e:
                    logger.warning(f"Could not remove extra file {file_to_clean}: {e}")
        
        # Download link is now embedded in the message directly
        
        # Create a summary message with extracted information
        summary_message = f"""## Certificate of Analysis Processing Complete

**Product Information:**
- Product Name: {product_info.get('product_name', 'Not found')}
- Batch/Lot Number: {product_info.get('batch_number', 'Not found')}
- Manufacturer: {product_info.get('manufacturer', 'Not found')}

The document has been processed with advanced validation and parameter variation detection.

📥 [Download Enhanced CoA Report](/download/{quote(os.path.basename(primary_excel_path), safe='')})
        """
        
        # S3 cleanup code removed - no longer using S3 for storage
        
        # Combine results to return to frontend
        result = {
                "process_id": process_id,
                "file_name": file.filename,
                "original_filename": original_filename,
                "product_info": product_info,
                "test_data": df.to_dict('records'),
                "unified_excel_path": unified_excel_path,
            "enhanced_excel_path": primary_excel_path,
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

@app.get("/upload-progress/{process_id}")
async def get_upload_progress(process_id: str):
    """Get the current progress of a file upload/processing operation"""
    progress = get_progress(process_id)
    if progress:
        return progress
    else:
        return {"stage": "unknown", "progress": 0, "message": "Process not found"}

from fastapi.responses import StreamingResponse
import json
import asyncio

# Import RAG components from Ruben chatbot
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'Ruben_AI_Chatbot-main'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'Ruben_AI_Chatbot-main', 'dependency'))

from dependency.agents.hybrid_search import HybridSearch
from dependency.services.iliad_service import IliadService
from dependency.services.embedding_service import EmbeddingService

# COA RAG session storage
coa_rag_sessions: Dict[str, Dict[str, Any]] = {}

@app.get("/upload-progress-stream/{process_id}")
async def progress_stream(process_id: str):
    """Stream progress updates using Server-Sent Events"""
    async def event_generator():
        last_progress = None
        consecutive_checks = 0
        max_checks = 12000  # 20 minutes max
        heartbeat_counter = 0
        
        while True:
            progress = get_progress(process_id)
            
            if progress:
                # Only send if progress changed
                current_state = f"{progress.get('stage')}:{progress.get('progress')}:{progress.get('message')}"
                if current_state != last_progress:
                    yield f"data: {json.dumps(progress)}\n\n"
                    last_progress = current_state
                    consecutive_checks = 0  # Reset counter when we have progress
                    heartbeat_counter = 0
                # Stop if completed, error, or cancelled
                if progress.get("stage") in ["completed", "error", "cancelled"]:
                    break
            else:
                # Send initial waiting message
                if consecutive_checks == 0:
                    yield f"data: {json.dumps({'stage': 'waiting', 'progress': 0, 'message': 'Waiting for process to start...'})}\n\n"
            heartbeat_counter += 1
            if heartbeat_counter >= 60:  # 60 * 0.5s = 30s
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
                heartbeat_counter = 0
            
            consecutive_checks += 1
            await asyncio.sleep(0.5)
        
        if consecutive_checks >= max_checks:
            yield f"data: {json.dumps({'stage': 'timeout', 'progress': 0, 'message': 'Process is still running in background'})}\n\n"
            consecutive_checks += 1
            await asyncio.sleep(0.5)  # Check every 500ms
        
        # Send timeout message if we exit the loop

    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable Nginx buffering
        }
    )

# Store for processing results
results_store = {}

@app.get("/coa-result/{process_id}")
async def get_coa_result(process_id: str):
    """Get the final results of COA processing"""
    result = results_store.get(process_id)
    if result:
        return result
    else:
        return JSONResponse(
            status_code=404,
            content={"error": "Results not found or still processing"}
        )

@app.get("/hbr-result/{process_id}")
async def get_hbr_result(process_id: str):
    """Get the final results of HBR processing"""
    result = results_store.get(process_id)
    if result:
        return result
    else:
        return JSONResponse(
            status_code=404,
            content={"error": "HBR results not found or still processing"}
        )

@app.post("/cancel-process/{process_id}")
async def cancel_process_endpoint(process_id: str):
    """Cancel a running process"""
    logger.info(f"🛑 Cancel request received for process: {process_id}")
    
    if process_id not in active_processes:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Process not found or already completed"}
        )
    
    try:
        cancel_process_token(process_id)
        return JSONResponse(
            content={
                "success": True,
                "message": "Process cancellation requested",
                "process_id": process_id
            }
        )
    except Exception as e:
        logger.error(f"❌ Error cancelling process {process_id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to cancel: {str(e)}"}
        )

@app.get("/active-processes")
async def get_active_processes():
    """Get list of all active processes"""
    return {
        "active_processes": {
            pid: {
                **info,
                "duration": time.time() - info["start_time"],
                "current_progress": progress_store.get(pid, {})
            }
            for pid, info in active_processes.items()
        }
    }

@app.get("/process-status/{process_id}")
async def get_process_status(process_id: str):
    """Get status of a specific process"""
    if process_id in active_processes:
        info = active_processes[process_id]
        return {
            "status": "active",
            "process_info": info,
            "progress": progress_store.get(process_id, {}),
            "duration": time.time() - info["start_time"],
            "cancellable": info.get("cancellable", True)
        }
    elif process_id in results_store:
        return {
            "status": "completed",
            "results": results_store[process_id]
        }
    else:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "error": "Process not found"}
        )

@app.post("/upload-coa")
async def upload_coa_simple(background_tasks: BackgroundTasks, file: UploadFile = File(...), request: Request = None):
    """
    Simple RAG-only COA processing: Textract → Parse → Chunk → Weaviate
    NO GPT extraction, NO validation - just OCR and indexing for chat.
    For full extraction with Excel report, use /upload-coa-full instead.
    """
    try:
        # Get username from session if available
        username = None
        if request and hasattr(request, 'session'):
            username = request.session.get("username")
        username = username or "anonymous"

        logger.info(f"[COA-Simple] Starting RAG-only upload for user: {username}")

        # Generate unique IDs
        process_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())[:8]

        # Initialize progress
        update_progress(process_id, "uploading", 0, "Starting document upload...")

        # Sanitize and save file
        sanitized_filename = sanitize_filename(file.filename)
        original_filename = os.path.splitext(sanitized_filename)[0]

        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)

        pdf_file_path = os.path.join(base_path, f"{original_filename}.pdf")

        update_progress(process_id, "uploading", 30, "Saving uploaded file...")

        file_content = await file.read()
        with open(pdf_file_path, "wb") as f:
            f.write(file_content)

        update_progress(process_id, "uploading", 50, "File saved successfully")
        logger.info(f"[COA-Simple] File saved: {pdf_file_path}")

        # Start background processing (RAG-only)
        background_tasks.add_task(
            process_coa_rag_only,
            pdf_file_path,
            base_path,
            process_id,
            document_id,
            original_filename,
            username
        )

        return JSONResponse(
            content={
                "message": "Document upload started (RAG-only mode)",
                "process_id": process_id,
                "document_id": document_id,
                "status": "processing"
            },
            status_code=202
        )

    except Exception as e:
        logger.error(f"[COA-Simple] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Upload failed: {str(e)}"}
        )
    finally:
        file.file.close()


async def process_coa_rag_only(
    pdf_file_path: str,
    base_path: str,
    process_id: str,
    document_id: str,
    original_filename: str,
    username: str
):
    """
    RAG-only background processing: Textract → Parse → Chunk → Weaviate
    No GPT extraction, no validation - fast path for chat-only use.
    """
    try:
        # Register process for tracking
        register_process(process_id, "coa_rag_only")
        add_process_file(process_id, pdf_file_path)

        # =========================================
        # Step 1: Run Textract (with LAYOUT)
        # =========================================
        check_cancellation(process_id)
        update_progress(process_id, "extracting", 0, "Starting OCR extraction...")

        from textractservices.textract_single import process_direct_file

        # Run Textract with progress simulation
        textract_task = asyncio.create_task(
            run_cpu_intensive_task(process_direct_file, pdf_file_path, base_path)
        )
        progress_task = asyncio.create_task(
            simulate_progress(process_id, 0, 40, 30, "extracting", "Processing document with OCR")
        )

        excel_file_path = await textract_task
        progress_task.cancel()

        if not excel_file_path:
            raise Exception("Textract processing failed")

        add_process_file(process_id, excel_file_path)

        check_cancellation(process_id)
        update_progress(process_id, "extracting", 40, "OCR extraction complete")

        # =========================================
        # Step 2: Parse Textract blocks
        # =========================================
        blocks_json_path = os.path.join(base_path, f"{original_filename}_blocks.json")

        if not os.path.exists(blocks_json_path):
            raise Exception(f"Blocks file not found: {blocks_json_path}")

        logger.info(f"[COA-RAG-Only] Parsing blocks from: {blocks_json_path}")

        from services.textract_parser import TextractParser
        from services.chunk_transformer import chunk_textract_blocks, get_chunk_statistics
        from services.weaviate_indexer import WeaviateIndexer

        parser = TextractParser(blocks_json_path=blocks_json_path)
        stats = parser.get_statistics()
        logger.info(f"[COA-RAG-Only] Parsed: {stats['tables']} tables, {stats['layouts']} layouts")

        tables = parser.get_all_tables()
        layouts = parser.get_all_layouts()

        update_progress(process_id, "analyzing", 50, f"Found {len(tables)} tables, {len(layouts)} text blocks")

        # =========================================
        # Step 3: Create chunks with grounding
        # =========================================
        check_cancellation(process_id)
        update_progress(process_id, "analyzing", 55, "Creating grounded chunks...")

        # Quick summary generation (optional, can be empty)
        summary = f"Certificate of Analysis: {original_filename}"
        keywords = "COA, certificate, analysis, test, specification, result"

        chunks = chunk_textract_blocks(
            tables=tables,
            layouts=layouts,
            document_id=document_id,
            process_id=process_id,
            filename=f"{original_filename}.pdf",
            document_summary=summary,
            keywords=keywords
        )

        chunk_stats = get_chunk_statistics(chunks)
        logger.info(f"[COA-RAG-Only] Created {len(chunks)} chunks")

        update_progress(process_id, "analyzing", 65, f"Created {len(chunks)} chunks with grounding")

        # =========================================
        # Step 4: Index to Weaviate
        # =========================================
        check_cancellation(process_id)
        update_progress(process_id, "indexing", 70, "Indexing to Weaviate...")

        indexer = WeaviateIndexer()

        if not indexer.check_connection():
            raise Exception("Cannot connect to Weaviate")

        result = indexer.index_chunks_batch(
            chunks=chunks,
            username=username,
            document_type="COA",
            source=f"coa_{username.lower()}" if username else "coa_upload"
        )

        logger.info(f"[COA-RAG-Only] Indexed {result['success']}/{len(chunks)} chunks to Weaviate")

        # =========================================
        # Step 5: Index to Neo4j (Phase 6)
        # =========================================
        check_cancellation(process_id)
        update_progress(process_id, "indexing", 90, "Indexing to Neo4j for structural queries...")

        try:
            neo4j_result = await index_document_to_neo4j(
                process_id=process_id,
                blocks_json_path=blocks_json_path,
                filename=original_filename,
                document_type="COA",
                username=username
            )
            if neo4j_result.get("success"):
                logger.info(f"[COA-RAG-Only] Neo4j indexed: {neo4j_result.get('stats', {})}")
            else:
                logger.warning(f"[COA-RAG-Only] Neo4j indexing skipped: {neo4j_result.get('error', 'Unknown')}")
        except Exception as neo4j_err:
            logger.warning(f"[COA-RAG-Only] Neo4j indexing failed (non-critical): {neo4j_err}")
            # Non-critical - continue without Neo4j

        # =========================================
        # Complete
        # =========================================
        update_progress(process_id, "completed", 100, "Document ready for chat!")

        # Store results
        results_store[process_id] = {
            "success": True,
            "process_id": process_id,
            "document_id": document_id,
            "filename": f"{original_filename}.pdf",
            "original_filename": original_filename,
            "chunks_indexed": result['success'],
            "chunks_failed": result['failed'],
            "weaviate_process_id": process_id,
            "weaviate_chunks": result['success'],
            "statistics": chunk_stats,
            "message": f"## Document Indexed for Chat\n\n**{original_filename}.pdf** has been processed and indexed.\n\n- Tables: {len(tables)}\n- Text blocks: {len(layouts)}\n- Total chunks: {len(chunks)}\n\nYou can now ask questions about this document!"
        }

        # Also store in progress_store for RAG chat lookup
        progress_store[process_id]["weaviate_process_id"] = process_id
        progress_store[process_id]["weaviate_chunks"] = result['success']
        progress_store[process_id]["original_filename"] = f"{original_filename}.pdf"

        logger.info(f"[COA-RAG-Only] Complete. Process ID: {process_id}")
        complete_process(process_id)

    except Exception as e:
        error_msg = str(e)
        if "cancelled by user" in error_msg.lower():
            logger.info(f"[COA-RAG-Only] Process cancelled: {process_id}")
            update_progress(process_id, "cancelled", 0, "Processing cancelled by user")
        else:
            logger.error(f"[COA-RAG-Only] Error: {error_msg}")
            import traceback
            traceback.print_exc()
            update_progress(process_id, "error", 0, f"Error: {error_msg}")

        cleanup_process_files(process_id)
        complete_process(process_id)


@app.post("/upload-coa-full")
async def public_upload_coa_file_full(background_tasks: BackgroundTasks, file: UploadFile = File(...), request: Request = None):
    """
    FULL COA processing: Textract → GPT extraction → Validation → Excel report → Weaviate indexing
    Use this when you need the enhanced Excel report with all GPT/validation processing.
    For RAG-only (faster), use /upload-coa instead.
    """
    try:
        # Try to get username from session if available
        username = None
        if request and hasattr(request, 'session'):
            username = request.session.get("username")
            if username:
                logger.info(f"[Upload] Processing COA for authenticated user: {username}")
            else:
                logger.info("[Upload] No authenticated user in session")
        else:
            logger.info("[Upload] No session available")

        # Generate a unique process ID for tracking
        process_id = str(uuid.uuid4())
        
        # Initialize progress
        update_progress(process_id, "uploading", 0, "Starting upload...")
        
        # Save the original filename without extension for output naming
        #original_filename = os.path.splitext(file.filename)[0]
        sanitized_filename = sanitize_filename(file.filename)
        original_filename = os.path.splitext(sanitized_filename)[0]
        # Create temp directory if it doesn't exist
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        # Save the uploaded file with original filename
        pdf_file_path = os.path.join(base_path, f"{original_filename}.pdf")
        
        update_progress(process_id, "uploading", 30, "Processing file...")
        
        # Read entire file into memory at once (much faster for typical PDF sizes)
        file_content = await file.read()
        
        # Write to disk in one operation (faster than chunked writing)
        with open(pdf_file_path, "wb") as f:
            f.write(file_content)
        
        update_progress(process_id, "uploading", 50, "File uploaded successfully")
        logger.info(f"Processing PDF file: {file.filename}")
        
        # Start background processing
        # Note: The background task will fetch its own auth token from the service
        background_tasks.add_task(
            process_coa_in_background,
            pdf_file_path,
            base_path,
            process_id,
            original_filename,
            None,  # No need to pass token, will fetch fresh one
            username  # Pass username for user-specific source naming
        )
        
        # Return immediately with process_id
        return JSONResponse(
            content={
                "message": "Document upload started successfully",
                "process_id": process_id,
                "status": "processing"
            },
            status_code=202
        )
        
    except Exception as e:
        logger.error(f"Error during upload: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error during upload: {str(e)}"}
        )
    finally:
        file.file.close()


async def simulate_progress(process_id: str, start: int, end: int, duration: int, stage: str, base_message: str):
    """Enhanced progress simulation with varied messages"""
    
    # Different messages for different stages
    extracting_messages = [
        "Initializing document analysis",
        "Detecting tables and forms", 
        "Extracting text regions",
        "Processing document layout",
        "Analyzing page content",
        "Finalizing extraction"
    ]
    
    analyzing_messages = [
        "Identifying test parameters",
        "Extracting specifications",
        "Processing test hierarchies", 
        "Validating results",
        "Cross-referencing data",
        "Creating final report"
    ]
    
    # Pick message list based on stage
    messages = extracting_messages if stage == "extracting" else analyzing_messages
    
    steps = 20
    step_duration = duration / steps
    step_increment = (end - start) / steps
    
    for i in range(steps):
        if is_process_cancelled(process_id):
            return
            
        current_progress = start + (step_increment * i)
        
        # Pick message based on progress through this stage
        msg_index = min(int(i * len(messages) / steps), len(messages) - 1)
        message = f"{base_message} - {messages[msg_index]}"
        
        update_progress(process_id, stage, int(current_progress), message)
        await asyncio.sleep(step_duration)


async def process_coa_in_background(pdf_file_path: str, base_path: str, process_id: str, original_filename: str, user_token: str = None, username: str = None):
    """Background task to process COA document with cancellation support"""
    try:
        # Register this process
        register_process(process_id, "coa_processing")
        add_process_file(process_id, pdf_file_path)
        
        # Checkpoint 1: Before Textract
        check_cancellation(process_id)
        update_progress(process_id, "extracting", 0, "Starting OCR extraction with AWS Textract...")
        
        from textractservices.textract_single import process_direct_file
        
        update_progress(process_id, "extracting", 5, "Initializing Textract processor...")
        check_cancellation(process_id)
        
        # Checkpoint 2: Before Textract processing
        update_progress(process_id, "extracting", 10, "Starting document processing...")
        
        # Run Textract and progress simulation in parallel
        textract_task = asyncio.create_task(
            run_cpu_intensive_task(process_direct_file, pdf_file_path, base_path)
        )
        progress_task = asyncio.create_task(
            simulate_progress(process_id, 10, 40, 30, "extracting", "Processing document with OCR")
        )
        
        # Wait for Textract to complete
        excel_file_path = await textract_task
        progress_task.cancel()  # Stop simulation when done
        
        if not excel_file_path:
            raise Exception("Failed to process the PDF file with Textract")
        
        add_process_file(process_id, excel_file_path)
        
        # Checkpoint 3: After Textract
        check_cancellation(process_id)
        update_progress(process_id, "extracting", 40, "OCR extraction complete")
        logger.info(f"Textract processing complete. Excel file created at: {excel_file_path}")
        
        # Define output files
        unified_excel_path = os.path.join(base_path, f"{original_filename}_unified.xlsx")
        add_process_file(process_id, unified_excel_path)
        
        # Checkpoint 4: Before GPT processing
        check_cancellation(process_id)
        
        # Step 2 & 3: Process Excel with GPT AND Advanced Validation IN PARALLEL
        from textractservices.gpt_excel_extractor import GPTCoAExtractor
        from textractservices.final_with_endotoxins import process_coa_optimized
        
        llm_url = "https://api-epic.ir-gateway.abbvienet.com/iliad/api/v1/chat/claude-3.7-sonnet"
        llm_api_key = REDACTED
        
        logger.info("Starting parallel processing: GPT analysis + Advanced validation")
        update_progress(process_id, "analyzing", 0, "Starting AI analysis...")
        
        # Create tasks that can run in parallel
        extractor = GPTCoAExtractor(api_key=llm_api_key, api_url=llm_url)
        
        # Set up cancellation callback for the extractor
        extractor.set_cancellation_callback(lambda: check_cancellation(process_id))
        
        # Set up progress callback for the extractor
        extractor.set_progress_callback(lambda progress, message: update_progress(process_id, "analyzing", progress, message))
        
        # Define functions for parallel execution
        def run_gpt_processing():
            check_cancellation(process_id)
            # Direct call - the extractor now has cancellation support and progress callbacks
            df, product_info = extractor.process_excel_with_llm_metadata(excel_file_path, pdf_file_path)
            
            check_cancellation(process_id)
            update_progress(process_id, "analyzing", 59, "Creating unified Excel report...")
            extractor.create_unified_excel(df, product_info, unified_excel_path)
            return df, product_info
        
        # Run both processes in parallel
        try:
            # Checkpoint 5: Before GPT processing
            check_cancellation(process_id)
            
            # First run GPT processing to get enhanced metadata with progress simulation
            gpt_task = asyncio.create_task(
                run_cpu_intensive_task(run_gpt_processing)
            )
            gpt_progress_task = asyncio.create_task(
                simulate_progress(process_id, 40, 60, 25, "analyzing", "AI processing with GPT-4")
            )
            
            gpt_result = await gpt_task
            gpt_progress_task.cancel()  # Stop simulation when done
            df, product_info = gpt_result
            
            # Checkpoint 6: After GPT processing
            check_cancellation(process_id)
            update_progress(process_id, "analyzing", 60, "GPT processing complete")
            logger.info(f"GPT processing complete. Created unified Excel file: {unified_excel_path}")
            
            # Checkpoint 7: Before validation
            check_cancellation(process_id)
            
            # Now run advanced validation with enhanced metadata
            def run_advanced_validation_with_metadata():
                check_cancellation(process_id)
                # Validation function uses its own progress callbacks (60-80% range)
                
                blocks_json_path = os.path.join(base_path, f"{original_filename}_blocks.json")
                if os.path.exists(blocks_json_path):
                    add_process_file(process_id, blocks_json_path)
                    
                    check_cancellation(process_id)
                    # Validation handles its own progress (60-80% range)
                    
                    # Direct call - we'll add cancellation support to this function later
                    result = process_coa_optimized(
                        pdf_file_path, blocks_json_path, unified_excel_path, base_path, product_info,
                        progress_callback=lambda progress, message: update_progress(process_id, "analyzing", progress, message)
                    )
                    
                    check_cancellation(process_id)
                    # Validation already completed to 80%
                    return result
                return None
            
            # Run validation without simulation (uses its own progress callbacks)
            validation_result = await run_cpu_intensive_task(run_advanced_validation_with_metadata)
            
            # Validation is complete (already updated to 80% by the function)
            
            # Handle advanced validation results
            if validation_result:
                enhanced_excel_path = validation_result.get('enhanced_excel_path')
                enhanced_json_path = validation_result.get('enhanced_json_path')
                validation_status = validation_result.get('validation_status')
                
                logger.info(f"Advanced validation completed with status: {validation_status}")
                
                # Use enhanced file as the primary output if available
                if validation_status == 'enhanced' and enhanced_excel_path and os.path.exists(enhanced_excel_path):
                    primary_excel_path = enhanced_excel_path
                    logger.info(f"Using enhanced Excel file: {enhanced_excel_path}")
                else:
                    primary_excel_path = unified_excel_path
                    logger.info(f"Using original unified Excel file: {unified_excel_path}")
            else:
                logger.warning("Advanced validation skipped - blocks JSON not found")
                primary_excel_path = unified_excel_path
                
        except Exception as e:
            logger.error(f"Error during parallel processing: {str(e)}")
            # Fallback to sequential processing
            logger.info("Falling back to sequential processing...")
            primary_excel_path = unified_excel_path
        
        # Clean up the intermediate Excel file created by Textract
            if os.path.exists(excel_file_path) and excel_file_path != unified_excel_path:
                try:
                    os.remove(excel_file_path)
                    logger.info(f"Cleaned up intermediate Excel file: {excel_file_path}")
                except Exception as e:
                    logger.warning(f"Could not remove intermediate Excel file: {e}")
            
            # Clean up any accidentally created files with old naming patterns (but preserve enhanced files)
            patterns_to_clean = [
                f"{original_filename}_data.csv",
                f"{original_filename}_info.json",
                f"{original_filename}_results.json",
                f"{original_filename}.csv",
                f"{original_filename}.xlsx",
                f"{original_filename}_temp.csv"
            ]
            
            for pattern in patterns_to_clean:
                file_to_clean = os.path.join(base_path, pattern)
                if os.path.exists(file_to_clean):
                    try:
                        os.remove(file_to_clean)
                        logger.info(f"Cleaned up extra file: {file_to_clean}")
                    except Exception as e:
                        logger.warning(f"Could not remove extra file {file_to_clean}: {e}")
            

            
        # Store the results for later retrieval
        if 'primary_excel_path' in locals():
            # Final checkpoint before completion
            check_cancellation(process_id)
            
            # Create download links with proper URL encoding
            filename = os.path.basename(primary_excel_path)
            encoded_filename = quote(filename, safe='')
            download_links = {
                "Download Enhanced CoA Report": f"/download/{encoded_filename}"
            }

            # Prepare results data (will be stored after all processing completes)
            results_data = {
                "process_id": process_id,
                "file_name": f"{original_filename}.pdf",
                "original_filename": original_filename,
                "message": f"## Certificate of Analysis Processing Complete\n\nThe document has been processed successfully.\n\n📥 [Download Enhanced Results]({list(download_links.values())[0]})",
                "success": True
            }

            # ========== COA WEAVIATE INDEXING FOR RAG (Phase 3) ==========
            # Index the COA document in Weaviate using layout-aware chunking
            # This replaces the old Iliad/RecursiveCharacterTextSplitter approach
            # Old Iliad code commented out below for reference

            blocks_json_path = os.path.join(base_path, f"{original_filename}_blocks.json")
            if os.path.exists(blocks_json_path):
                logger.info(f"[COA-RAG-WEAVIATE] Found blocks.json, starting Weaviate indexing with layout-aware chunking")

                # Store process info
                if process_id not in progress_store:
                    progress_store[process_id] = {}

                # Start background task for Weaviate indexing
                async def index_coa_in_weaviate():
                    try:
                        # Check cancellation at the start of RAG indexing
                        check_cancellation(process_id)

                        # Import Phase 3 services
                        from services.textract_parser import TextractParser
                        from services.chunk_transformer import chunk_textract_blocks
                        from services.weaviate_indexer import WeaviateIndexer

                        logger.info(f"[COA-RAG-WEAVIATE] Parsing blocks.json with layout-aware parser")

                        # Parse blocks.json with layout-aware parser
                        parser = TextractParser(blocks_json_path=blocks_json_path)
                        tables = parser.get_all_tables()
                        layouts = parser.get_all_layouts()

                        stats = parser.get_statistics()
                        logger.info(f"[COA-RAG-WEAVIATE] Parsed: {stats['tables']} tables, {stats['layouts']} layouts")

                        # Check cancellation after parsing
                        check_cancellation(process_id)

                        # Generate document_id for this document
                        import uuid as uuid_module
                        document_id = str(uuid_module.uuid4())[:8]

                        # Create layout-aware chunks with grounding
                        logger.info(f"[COA-RAG-WEAVIATE] Creating layout-aware chunks with cell_grounding and line_grounding")
                        chunks = chunk_textract_blocks(
                            tables=tables,
                            layouts=layouts,
                            document_id=document_id,
                            process_id=process_id,
                            filename=f"{original_filename}.pdf",
                            document_summary="",  # Will be added later if available
                            keywords=""
                        )

                        logger.info(f"[COA-RAG-WEAVIATE] Created {len(chunks)} chunks (tables + layouts)")

                        # Check cancellation before indexing
                        check_cancellation(process_id)

                        # Index chunks to Weaviate
                        logger.info(f"[COA-RAG-WEAVIATE] Indexing chunks to Weaviate with embeddings")
                        indexer = WeaviateIndexer()

                        # Verify Weaviate connection
                        if not indexer.check_connection():
                            logger.error(f"[COA-RAG-WEAVIATE] Cannot connect to Weaviate")
                            return

                        result = indexer.index_chunks_batch(
                            chunks=chunks,
                            username=username or "unknown",
                            document_type="COA",
                            source=f"coa_{username.lower()}" if username else "coa_upload"
                        )

                        logger.info(f"[COA-RAG-WEAVIATE] ✅ Indexed {result['success']}/{len(chunks)} chunks to Weaviate")
                        if result['failed'] > 0:
                            logger.warning(f"[COA-RAG-WEAVIATE] {result['failed']} chunks failed to index")

                        # Store Weaviate info for this process (for RAG chat)
                        progress_store[process_id]["weaviate_process_id"] = process_id
                        progress_store[process_id]["weaviate_chunks"] = result['success']
                        progress_store[process_id]["original_filename"] = f"{original_filename}.pdf"

                        # ALSO store in results_store for persistence
                        if process_id in results_store:
                            results_store[process_id]["weaviate_process_id"] = process_id
                            results_store[process_id]["weaviate_chunks"] = result['success']

                        # ========== PHASE 6: NEO4J INDEXING ==========
                        # Index to Neo4j for structural queries (non-blocking, non-critical)
                        try:
                            check_cancellation(process_id)
                            logger.info(f"[COA-RAG-NEO4J] Starting Neo4j indexing for structural queries...")

                            neo4j_result = await index_document_to_neo4j(
                                process_id=process_id,
                                blocks_json_path=blocks_json_path,
                                filename=original_filename,
                                document_type="COA",
                                username=username or "unknown"
                            )

                            if neo4j_result.get("success"):
                                neo4j_stats = neo4j_result.get("stats", {})
                                logger.info(f"[COA-RAG-NEO4J] ✅ Neo4j indexed: {neo4j_stats.get('tables_created', 0)} tables, "
                                           f"{neo4j_stats.get('cells_created', 0)} cells")
                                # Store Neo4j status
                                if process_id in progress_store:
                                    progress_store[process_id]["neo4j_indexed"] = True
                                    progress_store[process_id]["neo4j_stats"] = neo4j_stats
                                if process_id in results_store:
                                    results_store[process_id]["neo4j_indexed"] = True
                            else:
                                logger.warning(f"[COA-RAG-NEO4J] Neo4j indexing skipped: {neo4j_result.get('error', 'Unknown')}")
                        except Exception as neo4j_err:
                            # Neo4j is non-critical - log warning but continue
                            if "cancelled by user" not in str(neo4j_err).lower():
                                logger.warning(f"[COA-RAG-NEO4J] Neo4j indexing failed (non-critical): {neo4j_err}")
                        # ========== END PHASE 6: NEO4J INDEXING ==========

                    except Exception as e:
                        # Check if this was a cancellation
                        if "cancelled by user" in str(e).lower():
                            logger.info(f"[COA-RAG-WEAVIATE] ⏹️ Indexing stopped for process {process_id} - user cancelled")
                        else:
                            logger.error(f"[COA-RAG-WEAVIATE] Indexing error: {str(e)}")
                            import traceback
                            traceback.print_exc()

                # Run indexing in background (non-blocking)
                asyncio.create_task(index_coa_in_weaviate())
                logger.info("[COA-RAG-WEAVIATE] Background Weaviate indexing task started")
            else:
                logger.warning(f"[COA-RAG-WEAVIATE] blocks.json not found, skipping indexing")
            # ========== END OF COA WEAVIATE INDEXING ==========

            # ========== OLD ILIAD INDEXING CODE (COMMENTED OUT - Feb 5, 2026) ==========
            # Replaced with Weaviate layout-aware chunking above (Phase 3)
            # Keeping for reference - this used RecursiveCharacterTextSplitter which loses structure
            #
            # blocks_json_path = os.path.join(base_path, f"{original_filename}_blocks.json")
            # if os.path.exists(blocks_json_path):
            #     logger.info(f"[COA-RAG] Found blocks.json, starting Iliad indexing")
            #     # ... (old Iliad indexing code removed for brevity)
            #     # Key differences from new approach:
            #     # - Used RecursiveCharacterTextSplitter (loses table structure)
            #     # - No cell_grounding or line_grounding (can't highlight specific cells)
            #     # - Indexed to Iliad/Elasticsearch instead of Weaviate
            # ========== END OF OLD ILIAD CODE ==========

        # Check cancellation before final progress simulation
        check_cancellation(process_id)

        # Final progress simulation to 100%
        final_progress_task = asyncio.create_task(
            simulate_progress(process_id, 81, 100, 3, "analyzing", "Finalizing results")
        )
        await final_progress_task

        # Check cancellation after final progress simulation
        check_cancellation(process_id)

        # Store results ONLY if we made it this far without cancellation
        if 'results_data' in locals():
            results_store[process_id] = results_data

        # Mark as completed
        update_progress(process_id, "completed", 100, "Processing complete!")
        complete_process(process_id)
        
        logger.info(f"Background processing complete for: {original_filename}")
        
    except Exception as e:
        # Check if this was a cancellation
        if "cancelled by user" in str(e).lower():
            logger.info(f"⏹️ Process {process_id} was cancelled by user")
            update_progress(process_id, "cancelled", 0, "Process cancelled by user")
        else:
            logger.error(f"❌ Error in background processing: {str(e)}")
            update_progress(process_id, "error", 0, f"Processing failed: {str(e)}")
            # Cleanup files on error
            cleanup_process_files(process_id)
        
        # Store error result (only if not cancelled)
        if "cancelled by user" not in str(e).lower():
            results_store[process_id] = {
                "process_id": process_id,
                "success": False,
                "error": str(e),
                "message": f"Processing failed: {str(e)}"
            }
        
        # Always complete the process record
        complete_process(process_id)

async def process_hbr_in_background(pdf_file_path: str, excel_file_path: str, hbr_results_path: str, process_id: str, original_filename: str, pdf_path_file: str):
    """Background task to process HBR document with multi-agent system"""
    try:
        # Register this process
        register_process(process_id, "hbr_processing")
        add_process_file(process_id, pdf_file_path)
        add_process_file(process_id, excel_file_path)
        
        # Check cancellation
        check_cancellation(process_id)
        
        from textractservices.hbr_multiagent_api import hbr_multiagent_api
        
        logger.info("Initializing HBR multi-agent processing")
        
        # Continue processing smoothly from uploading (no jarring reset to 0%)
        update_progress(process_id, "processing", 5, "Starting multi-agent HBR extraction...")
        
        # Create a session for multi-agent processing
        session_id = hbr_multiagent_api.create_session(pdf_file_path, excel_file_path)
        session = hbr_multiagent_api.get_session(session_id)
        
        # Set progress callback
        session.set_progress_callback(lambda progress, message: update_progress(process_id, "processing", progress, message))
        
        # Process the documents - pass hbr_results_path as output_dir
        logger.info(f"Processing HBR documents with multi-agent system: {pdf_file_path}, {excel_file_path}")
        results = await hbr_multiagent_api.process_documents(session_id, hbr_results_path)
        
        if not results["success"]:
            raise Exception(results.get("error", "Multi-agent processing failed"))
        
        # Generate download link
        excel_filename = os.path.basename(results["excel_file_path"])
        
        # Check if the file exists in the expected location
        if not os.path.exists(results["excel_file_path"]):
            logger.error(f"Excel file not found at expected path: {results['excel_file_path']}")
            
            # Try to find the file in the hbr_results directory
            for root, dirs, files in os.walk(hbr_results_path):
                for file in files:
                    if file.endswith(".xlsx"):
                        logger.info(f"Found alternative Excel file: {file}")
                        excel_filename = file
                        results["excel_file_path"] = os.path.join(root, file)
                        break
        
        # Download link is now embedded in the message directly
        
        # Log the download link for debugging
        logger.info(f"Created download link: /download/{excel_filename}")
        
        # Create a simple summary message
        summary = results["processing_summary"]
        summary_message = f"## HBR Results\n\nPlease find the HBR extraction result file.\n\n📥 [Download Results Excel](/download/{excel_filename})"
        
        # Clean up the temporary file
        if os.path.exists(pdf_path_file):
            os.remove(pdf_path_file)
        
        # Store results for later retrieval
        response_data = {
            "success": True,
            "process_id": process_id,
            "session_id": session_id,
            "message": summary_message,
            "results": results["results"],
            "missing_parameters": results["missing_parameters"],
            "processing_summary": summary,
            "feedback_available": len(results["missing_parameters"]) > 0
        }
        
        # Store in results_store for /hbr-result endpoint
        results_store[process_id] = response_data
        
        # Mark process as completed
        update_progress(process_id, "completed", 100, "HBR processing complete!")
        
    except Exception as e:
        logger.error(f"Error during HBR processing: {str(e)}")
        # Store error result
        error_data = {
            "success": False,
            "process_id": process_id,
            "error": f"Error processing HBR files: {str(e)}"
        }
        results_store[process_id] = error_data
        update_progress(process_id, "error", 0, f"Processing failed: {str(e)}")
    finally:
        # Always complete the process record
        complete_process(process_id)

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
        
        # Initial progress
        update_progress(process_id, "uploading", 0, "Starting HBR PDF upload...")
        
        # Save the original filename without extension for output naming
        #original_filename = os.path.splitext(file.filename)[0]
        sanitized_filename = sanitize_filename(file.filename)
        original_filename = os.path.splitext(sanitized_filename)[0]
        # Create temp directory if it doesn't exist
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        update_progress(process_id, "uploading", 20, "Processing PDF file...")
        
        # Read entire file into memory at once (faster)
        file_content = await file.read()
        
        # Write to disk in one operation
        pdf_file_path = os.path.join(base_path, f"{original_filename}.pdf")
        with open(pdf_file_path, "wb") as f:
            f.write(file_content)
        
        update_progress(process_id, "uploading", 80, "PDF file saved successfully")
        logger.info(f"Saved HBR PDF file: {file.filename}")
        
        # Store the PDF path in a session variable for later processing with Excel config
        # We'll use a simple file-based storage for this
        storage_path = os.path.join(base_path, f"{process_id}_pdf_path.txt")
        with open(storage_path, "w") as f:
            f.write(pdf_file_path)
        
        update_progress(process_id, "completed", 100, "PDF upload complete")
        
        # Create a simple message with download link
        detailed_message = f"""📄 PDF uploaded: {file.filename}

Now upload your Target List Excel file with two columns: Parameter and Page.

📋 Need the template? [Download HBR Target List Template](/api/download-sample-template)

<hbr_process_id>{process_id}</hbr_process_id>"""

        return {
            "success": True,
            "message": detailed_message,
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
        #original_filename = os.path.splitext(file.filename)[0]
        sanitized_filename = sanitize_filename(file.filename)
        original_filename = os.path.splitext(sanitized_filename)[0]
        # Create temp directory if it doesn't exist
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        # Read entire file into memory at once (faster)
        file_content = await file.read()
        
        # Write Excel file in one operation
        excel_file_path = os.path.join(base_path, f"{original_filename}.xlsx")
        with open(excel_file_path, "wb") as f:
            f.write(file_content)
        
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
                
            # Download link is now embedded in the message directly
            
            # Log the download link for debugging
            logger.info(f"Created download link: /download/{results_filename}")
            
            # Create a simple summary message
            summary_message = f"## HBR Results\n\nPlease find the HBR extraction result file.\n\n📥 [Download Results Excel](/download/{results_filename})"
            
            # Clean up the temporary file
            if os.path.exists(pdf_path_file):
                os.remove(pdf_path_file)
            
            return {
                "success": True,
                "process_id": process_id,
                "message": summary_message,
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
        
        # If not found directly, check the exports directory (for query exports)
        if not os.path.exists(file_path):
            exports_path = os.path.join(os.path.dirname(base_path), 'exports')
            exports_file_path = os.path.join(exports_path, decoded_file_name)
            logger.info(f"Checking exports directory: {exports_file_path}")

            if os.path.exists(exports_file_path):
                file_path = exports_file_path
                logger.info(f"Found file in exports directory: {file_path}")

        # If not found, check the hbr_results directory (most likely location)
        if not os.path.exists(file_path):
            hbr_results_path = os.path.join(base_path, 'hbr_results')
            hbr_file_path = os.path.join(hbr_results_path, decoded_file_name)
            logger.info(f"Checking HBR results directory: {hbr_file_path}")

            if os.path.exists(hbr_file_path):
                file_path = hbr_file_path
                logger.info(f"Found file in HBR results directory: {file_path}")
        
        # If still not found, search all subdirectories
        if not os.path.exists(file_path):
            logger.info(f"File not found at {file_path}, searching in all subdirectories...")
            found = False
            for root, dirs, files in os.walk(base_path):
                for file in files:
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
                if file.endswith('.xlsx'):  # Only log Excel files to reduce noise
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

@app.get("/api/download-sample-template")
async def download_sample_template():
    """
    Endpoint to download a sample HBR target list template
    """
    logger.info("HBR template download requested - using UPDATED version with reference image")
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.drawing.image import Image as XLImage
        from datetime import datetime
        
        # Create a temporary file in the temp directory
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        # Create timestamp for unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        template_path = os.path.join(base_path, f"hbr_target_list_template_{timestamp}.xlsx")
        

        
        # Create a new Excel workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "HBR Target List"
        
        # Define styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        center_alignment = Alignment(horizontal="center", vertical="center")
        
        # Add headers - back to original 3 columns
        headers = ["Parameter", "Search_Pages", "Comments"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_alignment
        
        # Add sample data with example parameters based on your image
        sample_data = [
            ["Bulk Density by USP <616> Method 3", "2,3", "Look in 'Additional Information' section"],
            ["Tapped Density by USP <616> Method 3", "2,3", "Check specification criteria table"], 
            ["Carr Index", "2,3", "Calculate from bulk and tapped density"],
            ["Hausner Ratio", "2,3", "Found in specification column"],
            ["Loss on Drying", "2,3", "Look for moisture content value"],
            ["Date of Analysis", "2,3", "Check document header or footer"],
            ["Date of Bottling", "2,3", "Manufacturing information section"]
        ]
        
        # Add sample data to worksheet
        for row, data in enumerate(sample_data, 2):
            for col, value in enumerate(data, 1):
                ws.cell(row=row, column=col, value=value)
        
        # Add your reference image to the right of the data
        try:
            # Path to your reference image
            assets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
            reference_image_path = os.path.join(assets_path, 'image.png')
            
            if os.path.exists(reference_image_path):
                logger.info(f"Reference image found at: {reference_image_path}")
                # Insert the reference image
                xl_image = XLImage(reference_image_path)
                
                # Resize image to be much larger and very prominent
                xl_image.width = 800   # Width in pixels (increased from 600)
                xl_image.height = 600  # Height in pixels (increased from 450)
                
                # Position image starting at column E (5th column), row 2
                xl_image.anchor = "E2"
                ws.add_image(xl_image)
                logger.info("Reference image successfully added to Excel template")
                
                # Add a title above the image
                ws.cell(row=1, column=5, value="Document Reference Example").font = header_font
                ws.cell(row=1, column=5).fill = header_fill
                ws.cell(row=1, column=5).alignment = center_alignment
                
                # Extend column widths for much larger image
                ws.column_dimensions['E'].width = 100  # Much wider for large image
                ws.column_dimensions['F'].width = 100  # Extra space for image overflow
                ws.column_dimensions['G'].width = 100  # Additional space for image
                ws.column_dimensions['H'].width = 20   # Buffer space
                
            else:
                logger.error(f"Reference image NOT found at: {reference_image_path}")
                # If image doesn't exist, add a note
                ws.cell(row=1, column=5, value="Reference Image Not Found")
                
        except Exception as e:
            logger.warning(f"Could not add reference image: {e}")
            # Add fallback text
            ws.cell(row=1, column=5, value="Reference Image")
        
        # Add instructions in separate rows
        instructions_start_row = len(sample_data) + 4
        instructions = [
            "",
            "INSTRUCTIONS:",
            "1. Replace the sample data above with your actual parameters from your document.",
            "2. Update the Search_Pages column with page numbers where each parameter appears.",
            "3. Add helpful comments to guide the extraction process.",
            "4. Use the reference image on the right to understand document structure.",
            "5. You can add more rows as needed for additional parameters."
        ]
        
        for i, instruction in enumerate(instructions):
            ws.cell(row=instructions_start_row + i, column=1, value=instruction)
        
        # Adjust column widths for clean layout
        ws.column_dimensions['A'].width = 35  # Parameter name
        ws.column_dimensions['B'].width = 15  # Search pages
        ws.column_dimensions['C'].width = 40  # Comments
        
        # Save the workbook
        wb.save(template_path)
        
        # Create a custom response that cleans up temporary files
        async def cleanup_files():
            """Clean up temporary files after serving"""
            try:
                # Clean up template file after a delay
                import asyncio
                await asyncio.sleep(5)  # Wait 5 seconds before cleanup
                if os.path.exists(template_path):
                    os.remove(template_path)
            except Exception as cleanup_error:
                logger.warning(f"Cleanup warning: {cleanup_error}")
        
        # Schedule cleanup task
        import asyncio
        asyncio.create_task(cleanup_files())
        
        # Return the file with appropriate headers
        return FileResponse(
            path=template_path,
            filename="hbr_target_list_template.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=hbr_target_list_template.xlsx",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as e:
        logger.error(f"Error generating sample template: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate sample template: {str(e)}"}
        )

# Multi-Agent HBR endpoints
@app.post("/upload-hbr-multiagent")
async def upload_hbr_multiagent(background_tasks: BackgroundTasks, file: UploadFile = File(...), hbr_pdf_process_id: str = Form(...)):
    """
    Process HBR files using the advanced multi-agent system with Claude
    """
    # Generate a new process ID for the Excel processing
    process_id = str(uuid.uuid4())
    try:
        # Save the original filename without extension for output naming
        #original_filename = os.path.splitext(file.filename)[0]
        sanitized_filename = sanitize_filename(file.filename)
        original_filename = os.path.splitext(sanitized_filename)[0]
        # Create temp directory if it doesn't exist
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)
        
        # Create HBR results directory if it doesn't exist
        hbr_results_path = os.path.join(base_path, 'hbr_results')
        os.makedirs(hbr_results_path, exist_ok=True)
        
        # Read entire file into memory at once (faster)
        file_content = await file.read()
        
        # Write Excel file in one operation
        excel_file_path = os.path.join(base_path, f"{original_filename}.xlsx")
        with open(excel_file_path, "wb") as f:
            f.write(file_content)
        
        logger.info(f"Saved HBR Excel file for multi-agent processing: {file.filename}")
        
        # Get the PDF path from the stored file using the PDF process ID
        pdf_path_file = os.path.join(base_path, f"{hbr_pdf_process_id}_pdf_path.txt")
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
                content={"success": False, "error": "PDF file not found on server. Please upload the PDF file again."}
            )
        
        # Initial progress update
        update_progress(process_id, "uploading", 0, "Starting HBR Excel upload...")
        update_progress(process_id, "uploading", 30, "Excel file uploaded successfully")
        update_progress(process_id, "uploading", 50, "Preparing for processing...")
        update_progress(process_id, "uploading", 70, "Initializing multi-agent system...")
        update_progress(process_id, "uploading", 90, "Ready to start processing...")
        
        # Start background processing
        background_tasks.add_task(
            process_hbr_in_background,
            pdf_file_path,
            excel_file_path,
            hbr_results_path,
            process_id,
            original_filename,
            pdf_path_file
        )
        
        # Return immediately with process_id
        return JSONResponse(
            content={
                "message": "HBR Excel upload started successfully",
                "process_id": process_id,
                "success": True,
                "status": "processing_started"
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing HBR Excel file: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error processing file: {str(e)}"}
        )
    finally:
        file.file.close()

@app.post("/hbr-feedback")
async def hbr_feedback(request: Request):
    """
    Handle user feedback for missing HBR parameters
    """
    try:
        data = await request.json()
        
        # Extract required fields
        session_id = data.get("session_id")
        missing_parameter = data.get("missing_parameter")
        user_message = data.get("user_message")
        pages_already_checked = data.get("pages_already_checked", [])
        
        if not session_id or not missing_parameter or not user_message:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Missing required fields: session_id, missing_parameter, user_message"}
            )
        
        logger.info(f"Processing feedback for session {session_id}, parameter: {missing_parameter}")
        
        # Process feedback using multi-agent API
        from textractservices.hbr_multiagent_api import hbr_multiagent_api
        
        feedback_result = await hbr_multiagent_api.handle_feedback(
            session_id=session_id,
            missing_parameter=missing_parameter,
            user_message=user_message,
            pages_already_checked=pages_already_checked
        )
        
        if not feedback_result["success"]:
            return JSONResponse(
                status_code=400,
                content=feedback_result
            )
        
        # Format the response for the frontend
        assistant_response = feedback_result["assistant_response"]
        
        response_message = f"""🤖 **Assistant Recommendation:**

{assistant_response.get('assistant_message', 'I can help you find that parameter.')}

**Recommended Pages to Check:** {', '.join(map(str, assistant_response.get('recommended_pages', [])))}

**Search Strategy:** {assistant_response.get('reasoning', 'Check the recommended pages carefully.')}

**Search Hints:**
{chr(10).join(f'• {hint}' for hint in assistant_response.get('search_hints', []))}

{f'**Questions to Consider:**{chr(10)}{chr(10).join(f"• {q}" for q in assistant_response.get("clarifying_questions", []))}' if assistant_response.get('clarifying_questions') else ''}

Would you like me to search the recommended pages now, or do you have a specific hint about where to look?"""
        
        return {
            "success": True,
            "session_id": session_id,
            "parameter": missing_parameter,
            "message": response_message,
            "assistant_response": assistant_response,
            "recommended_pages": assistant_response.get("recommended_pages", [])
        }
        
    except Exception as e:
        logger.error(f"Error processing HBR feedback: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error processing feedback: {str(e)}"}
        )

@app.post("/hbr-reprocess")
async def hbr_reprocess(request: Request):
    """
    Reprocess a parameter with user's specific hint
    """
    try:
        data = await request.json()
        
        # Extract required fields
        session_id = data.get("session_id")
        parameter = data.get("parameter")
        user_hint = data.get("user_hint")
        recommended_pages = data.get("recommended_pages", [])
        
        if not session_id or not parameter or not user_hint:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Missing required fields: session_id, parameter, user_hint"}
            )
        
        logger.info(f"Reprocessing parameter {parameter} for session {session_id} with hint: {user_hint}")
        
        # Reprocess using multi-agent API
        from textractservices.hbr_multiagent_api import hbr_multiagent_api
        
        reprocess_result = await hbr_multiagent_api.reprocess_with_hint(
            session_id=session_id,
            parameter=parameter,
            user_hint=user_hint,
            recommended_pages=recommended_pages
        )
        
        if not reprocess_result["success"]:
            return JSONResponse(
                status_code=400,
                content=reprocess_result
            )
        
        # Format the response
        if reprocess_result["found"]:
            result_data = reprocess_result["results"][0]
            response_message = f"""✅ **Parameter Found!**

**{parameter}**: {result_data['value']} {result_data.get('unit', '')}
**Page**: {result_data['page']}
**Confidence**: {result_data.get('confidence', 'Unknown')}
**Location**: {result_data.get('location_found', 'Found on page')}

The parameter has been successfully extracted and added to your results!"""
        else:
            response_message = f"""❌ **Parameter Not Found**

The parameter **{parameter}** was not found on the recommended pages even with your hint.

You might try:
• Checking if the parameter has a different name in the document
• Looking for abbreviations or alternative terms
• Verifying the page numbers are correct
• Providing more specific location hints (e.g., "in the table header", "bottom right corner")"""
        
        return {
            "success": True,
            "session_id": session_id,
            "parameter": parameter,
            "found": reprocess_result["found"],
            "message": response_message,
            "results": reprocess_result.get("results", [])
        }
        
    except Exception as e:
        logger.error(f"Error reprocessing HBR parameter: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error reprocessing parameter: {str(e)}"}
        )

@app.post("/hbr-parameter-feedback")
async def hbr_parameter_feedback(request: Request):
    """
    Handle user feedback about specific parameter extraction results
    """
    try:
        data = await request.json()
        
        # Extract required fields
        session_id = data.get("session_id")
        parameter = data.get("parameter")
        issue_type = data.get("issue_type")  # 'missing' or 'incorrect'
        expected_page = data.get("expected_page")
        current_value = data.get("current_value")
        hint = data.get("hint")
        
        if not session_id or not parameter or not issue_type or not expected_page:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Missing required fields: session_id, parameter, issue_type, expected_page"}
            )
        
        logger.info(f"Processing parameter feedback for session {session_id}, parameter: {parameter}")
        
        # Get session info from multi-agent API
        from textractservices.hbr_multiagent_api import hbr_multiagent_api
        from textractservices.hbr_multiagent import process_user_feedback
        
        session = hbr_multiagent_api.get_session(session_id)
        if not session:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"Session {session_id} not found"}
            )
        
        # Process the feedback using the new function
        feedback_result = await run_cpu_intensive_task(
            process_user_feedback,
            session.pdf_path,
            session.excel_path,
            parameter,
            issue_type,
            expected_page,
            current_value,
            hint,
            session.state  # Pass the previous state
        )
        
        if feedback_result["status"] == "success" and feedback_result.get("updated_excel_path"):
            # Get the updated filename
            updated_filename = os.path.basename(feedback_result["updated_excel_path"])
            
            response_message = f"""✅ **Parameter Updated Successfully!**

**Parameter**: {parameter}
**Page**: {expected_page}
**Issue Type**: {issue_type}
**Result**: The parameter has been re-extracted based on your feedback.

You can download the updated results below."""
            
            return {
                "success": True,
                "session_id": session_id,
                "parameter": parameter,
                "message": response_message,
                "download_links": {
                    "Updated Results Excel": f"/download/{updated_filename}"
                },
                "feedback_result": feedback_result["feedback_processed"]
            }
        else:
            response_message = f"""❌ **Parameter Not Found**

Even with your hint, the parameter **{parameter}** could not be found on page {expected_page}.

Please verify:
• The page number is correct
• The parameter name matches exactly
• Try providing more specific hints about the location"""
            
            return {
                "success": False,
                "session_id": session_id,
                "parameter": parameter,
                "message": response_message,
                "feedback_result": feedback_result.get("feedback_processed", {})
            }
        
    except Exception as e:
        logger.error(f"Error processing parameter feedback: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error processing feedback: {str(e)}"}
        )

@app.get("/hbr-session/{session_id}")
async def get_hbr_session(session_id: str):
    """
    Get information about an HBR multi-agent session
    """
    try:
        from textractservices.hbr_multiagent_api import hbr_multiagent_api
        
        session_info = hbr_multiagent_api.get_session_info(session_id)
        
        if not session_info:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"Session {session_id} not found"}
            )
        
        return {
            "success": True,
            "session_info": session_info
        }
        
    except Exception as e:
        logger.error(f"Error getting HBR session info: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error getting session info: {str(e)}"}
        )

@app.post("/hbr-chat-feedback")
async def hbr_chat_feedback(request: Request):
    """
    Process natural language feedback from chat about parameter extraction
    """
    try:
        data = await request.json()
        
        # Extract required fields
        session_id = data.get("session_id")
        user_message = data.get("message")
        
        if not session_id or not user_message:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Missing required fields: session_id, message"}
            )
        
        logger.info(f"Processing chat feedback for session {session_id}: {user_message}")
        
        # Import the required functions here
        from textractservices.hbr_multiagent import call_claude_agent, safe_json_parse, process_user_feedback
        
        # Use Claude to extract structured information from the natural language message
        extraction_task = f"""Extract parameter feedback information from this user message:

User message: "{user_message}"

Analyze the message and extract:
1. Parameter name (what parameter they're talking about)
2. Page number (where it should be found)
3. Issue type (is it missing or incorrect?)
4. Current value (if they mention what was extracted incorrectly)
5. Hint/location (any guidance about where to find it)

Return ONLY valid JSON:
{{
    "parameter": "extracted parameter name",
    "page": <page number as integer>,
    "issue_type": "missing" or "incorrect",
    "current_value": "current value if mentioned, else null",
    "hint": "any location hints or guidance provided"
}}

If you can't extract certain information, use reasonable defaults:
- If no page mentioned, use null
- If issue type unclear, assume "missing"
- If no hint, extract any location-related information"""
        
        # Call Claude to parse the message
        response = call_claude_agent(
            "Feedback Parser",
            extraction_task,
            {"user_message": user_message}
        )
        
        # Parse Claude's response using safe_json_parse
        feedback_info = safe_json_parse(response, {
            "parameter": "Unknown",
            "page": None,
            "issue_type": "missing",
            "current_value": None,
            "hint": user_message
        })
        
        # Validate we have minimum required info
        if not feedback_info.get("parameter") or feedback_info["parameter"] == "Unknown":
            return {
                "success": False,
                "message": "I couldn't understand which parameter you're referring to. Please mention the specific parameter name.",
                "needs_clarification": True
            }
        
        if not feedback_info.get("page"):
            return {
                "success": False,
                "message": f"I understand you're having an issue with '{feedback_info['parameter']}', but I need to know which page to check. What page should it be on?",
                "needs_clarification": True,
                "partial_info": feedback_info
            }
        
        # Get session info
        from textractservices.hbr_multiagent_api import hbr_multiagent_api
        
        session = hbr_multiagent_api.get_session(session_id)
        if not session:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"Session {session_id} not found"}
            )
        
        logger.info(f"Processing feedback for parameter: {feedback_info['parameter']}, page: {feedback_info['page']}")
        
        # Step 1: Process the feedback to get recommendations
        feedback_result = await run_cpu_intensive_task(
            process_user_feedback,
            session.pdf_path,
            session.excel_path,
            feedback_info["parameter"],
            feedback_info["issue_type"],
            int(feedback_info["page"]),
            feedback_info.get("current_value"),
            feedback_info.get("hint", ""),
            session.state if hasattr(session, 'state') else None
        )
        
        # Check if feedback analysis was successful
        if feedback_result["status"] != "success":
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Failed to process feedback"}
            )
        
        # Step 2: AUTOMATICALLY TRIGGER REPROCESSING
        feedback_data = feedback_result["feedback_processed"]
        recommendations = feedback_data.get("recommendations", {})
        pages_to_check = recommendations.get("pages_to_check", [int(feedback_info["page"])])
        
        logger.info(f"Automatically triggering reprocessing for '{feedback_info['parameter']}' on pages {pages_to_check}")
        
        # Call the reprocessing function
        reprocess_result = await hbr_multiagent_api.reprocess_with_hint(
            session_id=session_id,
            parameter=feedback_info["parameter"],
            user_hint=feedback_info.get("hint", ""),
            recommended_pages=pages_to_check
        )
        
        # Check reprocessing results
        if reprocess_result["success"] and reprocess_result["found"]:
            # Parameter was found!
            result_data = reprocess_result["results"][0]
            
            response_message = f"""✅ **Found it!** I successfully extracted the parameter from page {result_data['page']}:

**{feedback_info['parameter']}**: {result_data['value']} {result_data.get('unit', '')}

{f"**Location**: {result_data.get('location_found', '')}" if result_data.get('location_found') else ""}
{f"**Confidence**: {result_data.get('confidence', 'High')}" if result_data.get('confidence') else ""}

The parameter has been added to your results."""
            
            return {
                "success": True,
                "message": response_message,
                "extracted_info": feedback_info,
                "found": True,
                "extracted_value": {
                    "parameter": result_data.get("parameter"),
                    "value": result_data.get("value"),
                    "unit": result_data.get("unit", ""),
                    "page": result_data.get("page"),
                    "location": result_data.get("location_found", "")
                }
            }
        else:
            # Parameter still not found
            response_message = f"""❌ I searched pages {', '.join(map(str, pages_to_check))} for **{feedback_info['parameter']}** but couldn't find it.

{feedback_data.get('assistant_message', '')}

Could you provide more specific details about:
- The exact location on the page (e.g., "in the table at the bottom")
- Any nearby text or headers
- The format of the value you're expecting

Or try telling me exactly what the value should be if you can see it."""
            
            return {
                "success": False,
                "message": response_message,
                "extracted_info": feedback_info,
                "found": False,
                "pages_checked": pages_to_check
            }
        
    except Exception as e:
        logger.error(f"Error processing chat feedback: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Error processing feedback: {str(e)}"}
        )


# =============================================================================
# Phase 4: Weaviate-based RAG Endpoint (NEW - Multi-Agent Orchestration)
# =============================================================================
# This endpoint uses the new Phase 4 RAG orchestrator with:
# - Semantic Cache
# - Intent Classification
# - Question Rephrasing
# - Parallel Weaviate Hybrid Search
# - Answer Synthesis with cell references
# - Reference extraction for PDF highlighting

@app.post("/api/chat/coa-rag-v2/{process_id}")
async def coa_rag_chat_v2(process_id: str, request: Request):
    """
    Phase 4: Multi-Agent RAG Chat with Weaviate (NEW)

    This endpoint uses the new RAG orchestrator with:
    - Semantic caching for repeated queries
    - Intent classification (vector_only, structural, extraction)
    - Query variations for better recall
    - Parallel Weaviate hybrid search
    - Cell-level references for PDF highlighting

    Args:
        process_id: Document UUID (used as Weaviate filter)

    Request body:
        {
            "message": "What is the batch number?",  // or "question"
            "recent_messages": [  // Optional: last 3 messages for context
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }

    Response:
        {
            "success": true,
            "answer": "The batch number is 12345 [cell:1-5]",
            "references": [{
                "page": 1,
                "bbox": {"left": 0.1, "top": 0.2, "width": 0.1, "height": 0.03},
                "cell_id": "1-5",
                "text": "12345"
            }],
            "confidence": 0.95,
            "query_type": "vector_only",
            "process_id": "uuid"
        }
    """
    try:
        data = await request.json()
        user_message = data.get("message") or data.get("question", "")
        recent_messages = data.get("recent_messages", [])

        logger.info(f"[COA-RAG-V2] Query: '{user_message[:50]}...' for process_id={process_id[:8]}...")

        if not user_message:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "No message provided"}
            )

        # Get document filename - check request body first, then stores
        filename = data.get("filename") or data.get("file_name") or "document.pdf"
        if filename == "document.pdf":
            # Fallback to stores if not in request
            if process_id in progress_store:
                filename = progress_store[process_id].get("original_filename", filename)
            elif process_id in results_store:
                filename = results_store[process_id].get("original_filename",
                           results_store[process_id].get("file_name", filename))

        logger.info(f"[COA-RAG-V2] Using filename: {filename}")

        # Use the RAG orchestrator
        response = process_rag_query_sync(
            query=user_message,
            process_id=process_id,
            filename=filename,
            recent_messages=recent_messages
        )

        # Add metadata
        response["success"] = not response.get("error", False)
        response["process_id"] = process_id
        response["document"] = filename

        logger.info(f"[COA-RAG-V2] Response: confidence={response.get('confidence', 0):.2f}, "
                   f"refs={len(response.get('references', []))}")

        return JSONResponse(
            status_code=200,
            content=response
        )

    except Exception as e:
        logger.error(f"[COA-RAG-V2] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"RAG processing failed: {str(e)}",
                "answer": "I encountered an error processing your question. Please try again."
            }
        )


# =============================================================================
# Streaming COA RAG v2 with Visual Audit Progress
# =============================================================================
@app.post("/api/chat/coa-rag-v2-stream/{process_id}")
async def coa_rag_chat_v2_stream(process_id: str, request: Request):
    """
    Phase 8: Streaming RAG Chat with Visual Audit Progress

    Returns SSE stream with real-time progress for Visual Audit queries.
    For non-visual-audit queries, returns single complete event.

    SSE Event Types:
    - visual_audit_start: Visual audit processing started
    - stage: Stage change (searching, analyzing, extracting, complete)
    - log: Progress log message
    - complete: Final response with full data
    - error: Error occurred
    """
    import queue
    import threading
    import time

    try:
        data = await request.json()
        user_message = data.get("message") or data.get("question", "")
        recent_messages = data.get("recent_messages", [])

        if not user_message:
            async def error_stream():
                yield f"data: {json.dumps({'type': 'error', 'error': 'No message provided'})}\n\n"
            return StreamingResponse(error_stream(), media_type="text/event-stream")

        # Get filename
        filename = data.get("filename") or "document.pdf"
        if filename == "document.pdf":
            if process_id in progress_store:
                filename = progress_store[process_id].get("original_filename", filename)
            elif process_id in results_store:
                filename = results_store[process_id].get("original_filename", filename)

        logger.info(f"[COA-RAG-V2-STREAM] Query: '{user_message[:50]}...' for process_id={process_id[:8]}...")

        # Classify intent to check if Visual Audit
        from services.intent_classifier import classify_with_plan, QueryIntent
        plan = classify_with_plan(user_message)
        is_visual_audit = plan.intent == QueryIntent.VISUAL_AUDIT

        logger.info(f"[COA-RAG-V2-STREAM] Intent: {plan.intent.value}, is_visual_audit={is_visual_audit}")

        async def generate_stream():
            if is_visual_audit:
                # Visual Audit with progress streaming
                # Quick discovery to find target pages for frontend PDF panel
                target_pages = []
                discovery_result = None  # Store for reuse in orchestrator
                try:
                    from services.visual_audit_service import get_visual_audit_service, analyze_conversation_context
                    # Check conversation context first (for follow-up queries)
                    ctx = analyze_conversation_context(user_message, recent_messages)
                    if ctx.get('pages'):
                        target_pages = ctx['pages'][:5]
                        # Create a minimal discovery result for context-based queries
                        discovery_result = {
                            'success': True,
                            'pages_found': target_pages,
                            'auto_analyze': len(target_pages) == 1,
                            'auto_analyze_page': target_pages[0] if len(target_pages) == 1 else None
                        }
                    else:
                        # Do discovery to find pages - store result for orchestrator reuse
                        visual_audit = get_visual_audit_service()
                        discovery_result = visual_audit.discover_audit_targets(
                            query=user_message,
                            process_id=process_id,
                            filename=filename
                        )
                        if discovery_result.get('success'):
                            if discovery_result.get('auto_analyze_page'):
                                target_pages = [discovery_result['auto_analyze_page']]
                            elif discovery_result.get('pages_found'):
                                target_pages = discovery_result['pages_found'][:5]
                    logger.info(f"[COA-RAG-V2-STREAM] Visual Audit target pages: {target_pages}")
                except Exception as e:
                    logger.warning(f"[COA-RAG-V2-STREAM] Quick discovery failed: {e}")

                yield f"data: {json.dumps({'type': 'visual_audit_start', 'query': user_message, 'pages': target_pages})}\n\n"
                yield f"data: {json.dumps({'type': 'stage', 'stage': 'searching'})}\n\n"
                yield f"data: {json.dumps({'type': 'log', 'log': '[SEARCH] Scanning document for relevant data...'})}\n\n"

                # Use queue for progress events from background thread
                progress_queue = queue.Queue()
                result_container = [None]
                error_container = [None]

                def progress_callback(event_type: str, message: str = None, stage: str = None):
                    """Callback for orchestrator to report progress"""
                    if event_type == 'log' and message:
                        progress_queue.put({'type': 'log', 'log': message})
                    elif event_type == 'stage' and stage:
                        progress_queue.put({'type': 'stage', 'stage': stage})

                def process_query():
                    try:
                        orchestrator = get_rag_orchestrator()
                        # Pass precomputed plan and discovery to avoid duplicate LLM calls
                        # This saves ~8-10 seconds by reusing the classification and discovery
                        result = orchestrator.process_query_sync(
                            query=user_message,
                            process_id=process_id,
                            filename=filename,
                            recent_messages=recent_messages,
                            precomputed_plan=plan,
                            precomputed_discovery=discovery_result
                        )
                        result_container[0] = result
                    except Exception as e:
                        logger.error(f"[COA-RAG-V2-STREAM] Processing error: {e}")
                        error_container[0] = str(e)
                    finally:
                        progress_queue.put(None)  # Signal completion

                # Start processing in background thread
                thread = threading.Thread(target=process_query)
                thread.start()

                # Stream progress events with simulated logs for Visual Audit
                # 5 stages for smoother progression: searching -> analyzing -> extracting -> verifying -> complete
                start_time = time.time()
                stage_times = {
                    'analyzing': 1.5,      # Switch to analyzing at 1.5s
                    'extracting': 3.5,     # Switch to extracting at 3.5s
                    'verifying': 6.0       # Switch to verifying at 6.0s
                }
                current_stage = 'searching'
                stages_sent = set(['searching'])  # Track which stages have been sent

                while True:
                    try:
                        event = progress_queue.get(timeout=0.4)
                        if event is None:
                            break
                        yield f"data: {json.dumps(event)}\n\n"
                    except queue.Empty:
                        # Send stage updates based on elapsed time - each stage sent only once
                        elapsed = time.time() - start_time

                        if elapsed > stage_times['verifying'] and 'verifying' not in stages_sent:
                            current_stage = 'verifying'
                            stages_sent.add('verifying')
                            yield f"data: {json.dumps({'type': 'stage', 'stage': 'verifying'})}\n\n"
                            yield f"data: {json.dumps({'type': 'log', 'log': '[VERIFY] Validating results...'})}\n\n"
                        elif elapsed > stage_times['extracting'] and 'extracting' not in stages_sent:
                            current_stage = 'extracting'
                            stages_sent.add('extracting')
                            yield f"data: {json.dumps({'type': 'stage', 'stage': 'extracting'})}\n\n"
                            yield f"data: {json.dumps({'type': 'log', 'log': '[EXTRACT] Locating cell references...'})}\n\n"
                        elif elapsed > stage_times['analyzing'] and 'analyzing' not in stages_sent:
                            current_stage = 'analyzing'
                            stages_sent.add('analyzing')
                            yield f"data: {json.dumps({'type': 'stage', 'stage': 'analyzing'})}\n\n"
                            yield f"data: {json.dumps({'type': 'log', 'log': '[ANALYZE] Processing with AI...'})}\n\n"
                        continue

                thread.join()

                # Send final result
                if error_container[0]:
                    yield f"data: {json.dumps({'type': 'error', 'error': error_container[0]})}\n\n"
                else:
                    response = result_container[0]
                    if response:
                        response["success"] = not response.get("error", False)
                        response["process_id"] = process_id
                        yield f"data: {json.dumps({'type': 'stage', 'stage': 'complete'})}\n\n"
                        yield f"data: {json.dumps({'type': 'log', 'log': '[SUCCESS] Analysis complete'})}\n\n"
                        yield f"data: {json.dumps({'type': 'complete', 'data': response})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'error', 'error': 'No response generated'})}\n\n"

            else:
                # Non-visual-audit: Process normally, return as single complete event
                # Pass precomputed_plan to avoid duplicate LLM classification call (~3s savings)
                orchestrator = get_rag_orchestrator()
                response = orchestrator.process_query_sync(
                    query=user_message,
                    process_id=process_id,
                    filename=filename,
                    recent_messages=recent_messages,
                    precomputed_plan=plan  # Reuse plan from line 3009
                )
                response["success"] = not response.get("error", False)
                response["process_id"] = process_id
                yield f"data: {json.dumps({'type': 'complete', 'data': response})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        logger.error(f"[COA-RAG-V2-STREAM] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")


@app.get("/api/rag/cache-stats")
async def get_rag_cache_stats():
    """Get RAG semantic cache statistics."""
    try:
        orchestrator = get_rag_orchestrator()
        stats = orchestrator.get_cache_stats()
        return JSONResponse(status_code=200, content={"success": True, "stats": stats})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.delete("/api/rag/cache/{process_id}")
async def invalidate_rag_cache(process_id: str):
    """Invalidate RAG cache for a specific document."""
    try:
        orchestrator = get_rag_orchestrator()
        removed = orchestrator.invalidate_cache(process_id)
        return JSONResponse(
            status_code=200,
            content={"success": True, "entries_removed": removed}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =============================================================================
# Legacy Iliad-based RAG Endpoint (kept for backwards compatibility)
# =============================================================================

@app.post("/api/chat/coa-rag/{process_id}")
async def coa_rag_chat(process_id: str, request: Request):
    """
    LEGACY: Handle chat requests for COA documents using Ruben's hybrid search.
    Uses Iliad indexed data for RAG.
    """
    try:
        data = await request.json()
        # Support both 'message' and 'question' fields
        user_message = data.get("message") or data.get("question", "")

        logger.info(f"[COA-Chat] Received request for process {process_id} with message: {user_message[:100] if user_message else 'None'}")

        if not user_message:
            logger.warning(f"[COA-Chat] No message/question provided in request body: {data}")
            return JSONResponse(
                status_code=400,
                content={"error": "No message provided"}
            )

        # Check if we have indexed this document (check both stores)
        source_name = None
        original_filename = None

        # First check progress_store (recent uploads)
        if process_id in progress_store and "iliad_source" in progress_store[process_id]:
            source_name = progress_store[process_id]["iliad_source"]
            original_filename = progress_store[process_id].get("original_filename", "unknown.pdf")

        # Then check results_store (persistent storage)
        elif process_id in results_store and "iliad_source" in results_store[process_id]:
            source_name = results_store[process_id]["iliad_source"]
            original_filename = results_store[process_id].get("original_filename", results_store[process_id].get("file_name", "unknown.pdf"))

        if not source_name:
            logger.warning(f"[COA-Chat] No Iliad source found for process {process_id}")
            return JSONResponse(
                status_code=404,
                content={"error": "COA data not indexed yet. Please wait for extraction to complete."}
            )
        logger.info(f"[COA-Chat] Using source: {source_name} with process_id: {process_id} for file: {original_filename}")

        # Step 1: Use Question Rephraser to generate query variations (like Ruben)
        rephrased_questions = []
        try:
            rephrased_questions = await question_rephraser.rephrase(user_message)
            logger.info(f"[COA-Chat] Generated {len(rephrased_questions)} query variations: {rephrased_questions}")
        except Exception as e:
            logger.warning(f"[COA-Chat] Question rephrasing failed, using original: {e}")
            rephrased_questions = [user_message]

        # Step 2: Use direct hybrid search with process_id filtering
        # The Information Retriever doesn't support custom field filtering easily
        try:
            all_results = []
            seen_chunks = set()

            # Get auth token and headers for all searches
            effective_token = REDACTED
            search_headers = {
                "x-api-key": ILIAD_API_KEY,
                "x-user-token": effective_token  # REQUIRED for search
            }

            # Search with each rephrased question, filtering by process_id
            for question in rephrased_questions:
                # Build search query with process_id filter
                search_query = {
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "match": {
                                        "process_id": process_id  # Filter by process_id
                                    }
                                },
                                {
                                    "multi_match": {
                                        "query": question,
                                        "fields": ["chunk_text", "keywords", "document_summary"]
                                    }
                                }
                            ]
                        }
                    },
                    "size": 5
                }

                # Perform search via Iliad
                search_response = requests.post(
                    url=f"{ILIAD_URL}/api/v1/sources/{source_name}/search",
                    headers=search_headers,  # Use headers WITH user token
                    json={"search": search_query}  # WRAP in "search" field
                )

                if search_response.status_code == 200:
                    results = search_response.json().get("hits", {}).get("hits", [])
                    for hit in results:
                        chunk_text = hit.get("_source", {}).get("chunk_text", "")
                        if chunk_text and chunk_text not in seen_chunks:
                            seen_chunks.add(chunk_text)
                            all_results.append({
                                "text": chunk_text,
                                "score": hit.get("_score", 0)
                            })

            # Sort by score and take top 5
            all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            top_results = all_results[:5]

            # Build context from results
            context_chunks = []
            for result in top_results:
                chunk_text = result.get("text", "")
                score = result.get("score", 0)
                context_chunks.append(f"[Score: {score:.2f}]\n{chunk_text}")

            combined_context = "\n\n---\n\n".join(context_chunks)
            logger.info(f"[COA-Chat] Found {len(context_chunks)} relevant chunks for process {process_id}")


        except Exception as e:
            logger.error(f"[COA-Chat] Hybrid search failed, falling back to direct Iliad query: {e}")
            # Fallback to simpler search if hybrid search fails
            try:
                # Retry with simpler match query
                logger.info(f"[COA-Chat] Attempting fallback search for process {process_id}")

                # Get auth token for fallback search
                effective_token = REDACTED
                if not effective_token:
                    logger.error("[COA-Chat] No auth token available for fallback search")
                    combined_context = ""
                else:
                    search_headers = {
                        "x-api-key": ILIAD_API_KEY,
                        "x-user-token": effective_token  # REQUIRED for search
                    }

                    # Simple match query
                    fallback_query = {
                        "query": {
                            "match": {
                                "chunk_text": user_message
                            }
                        },
                        "size": 5
                    }

                    fallback_response = requests.post(
                        url=f"{ILIAD_URL}/api/v1/sources/{source_name}/search",
                        headers=search_headers,
                        json={"search": fallback_query}  # WRAP in "search" field
                    )

                    if fallback_response.status_code == 200:
                        fallback_results = fallback_response.json()
                        hits = fallback_results.get("hits", {}).get("hits", [])

                        context_chunks = []
                        for hit in hits:
                            chunk_text = hit.get("_source", {}).get("chunk_text", "")
                            score = hit.get("_score", 0)
                            context_chunks.append(f"[Score: {score:.2f}]\n{chunk_text}")

                        combined_context = "\n\n---\n\n".join(context_chunks)
                        logger.info(f"[COA-Chat] Fallback search found {len(context_chunks)} chunks")
                    else:
                        logger.error(f"[COA-Chat] Fallback search failed: {fallback_response.status_code}")
                        combined_context = ""
            except Exception as fallback_e:
                logger.error(f"[COA-Chat] Fallback search error: {fallback_e}")
                combined_context = ""

        # Build prompt for Claude with retrieved context
        prompt = f"""You are analyzing a Certificate of Analysis (COA) document.

Document: {original_filename}

Context from the document (retrieved via hybrid search):
{combined_context}

User Question: {user_message}

Please provide a helpful, accurate answer based on the context above. If the information is not available in the provided context, say so clearly."""

        # Call Claude API for response
        claude_url = ILIAD_URL
        claude_api_key = REDACTED

        response = requests.post(
            f"{claude_url}/api/v1/chat/claude-3.7-sonnet",
            headers={"x-api-key": claude_api_key},
            json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 1500
            }
        )

        if response.status_code == 200:
            claude_response = response.json()
            answer = claude_response.get("completion", {}).get("content", "I couldn't generate a response.")

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "answer": answer,
                    "document": original_filename,
                    "process_id": process_id,
                    "source": source_name
                }
            )
        else:
            logger.error(f"[COA-Chat] Claude API error: {response.status_code} - {response.text}")
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to generate response from AI"}
            )

    except Exception as e:
        logger.error(f"[COA-Chat] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": f"Chat processing failed: {str(e)}"}
        )


# =============================================================================
# Streaming COA RAG Chat Endpoint
# =============================================================================
# This endpoint streams Claude's response token by token for a typing effect

@app.post("/api/chat/coa-rag-stream/{process_id}")
async def coa_rag_chat_stream(process_id: str, request: Request):
    """
    Handle chat requests for COA documents with STREAMING response.
    Returns Server-Sent Events (SSE) for real-time typing effect.
    """
    import json as json_module

    try:
        data = await request.json()
        user_message = data.get("message") or data.get("question", "")

        logger.info(f"[COA-Chat-Stream] Received request for process {process_id}")

        if not user_message:
            return JSONResponse(status_code=400, content={"error": "No message provided"})

        # Check if we have indexed this document (check both stores)
        source_name = None
        original_filename = None

        if process_id in progress_store and "iliad_source" in progress_store[process_id]:
            source_name = progress_store[process_id]["iliad_source"]
            original_filename = progress_store[process_id].get("original_filename", "unknown.pdf")
        elif process_id in results_store and "iliad_source" in results_store[process_id]:
            source_name = results_store[process_id]["iliad_source"]
            original_filename = results_store[process_id].get("original_filename", results_store[process_id].get("file_name", "unknown.pdf"))

        if not source_name:
            return JSONResponse(status_code=404, content={"error": "COA data not indexed yet."})

        logger.info(f"[COA-Chat-Stream] Using source: {source_name}")

        # Step 1: Question Rephrasing
        rephrased_questions = [user_message]
        try:
            rephrased_questions = await question_rephraser.rephrase(user_message)
            logger.info(f"[COA-Chat-Stream] Generated {len(rephrased_questions)} variations")
        except Exception as e:
            logger.warning(f"[COA-Chat-Stream] Rephrasing failed: {e}")

        # Step 2: Hybrid Search
        all_results = []
        seen_chunks = set()
        effective_token = REDACTED
        search_headers = {
            "x-api-key": ILIAD_API_KEY,
            "x-user-token": effective_token
        }

        for question in rephrased_questions:
            search_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"process_id": process_id}},
                            {"multi_match": {"query": question, "fields": ["chunk_text", "keywords", "document_summary"]}}
                        ]
                    }
                },
                "size": 5
            }

            search_response = requests.post(
                url=f"{ILIAD_URL}/api/v1/sources/{source_name}/search",
                headers=search_headers,
                json={"search": search_query}
            )

            if search_response.status_code == 200:
                results = search_response.json().get("hits", {}).get("hits", [])
                for hit in results:
                    chunk_text = hit.get("_source", {}).get("chunk_text", "")
                    if chunk_text and chunk_text not in seen_chunks:
                        seen_chunks.add(chunk_text)
                        all_results.append({"text": chunk_text, "score": hit.get("_score", 0)})

        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_results = all_results[:5]

        context_chunks = [f"[Score: {r['score']:.2f}]\n{r['text']}" for r in top_results]
        combined_context = "\n\n---\n\n".join(context_chunks)
        logger.info(f"[COA-Chat-Stream] Found {len(context_chunks)} relevant chunks")

        # Build prompt
        prompt = f"""You are analyzing a Certificate of Analysis (COA) document.

Document: {original_filename}

Context from the document (retrieved via hybrid search):
{combined_context}

User Question: {user_message}

Please provide a helpful, accurate answer based on the context above. If the information is not available in the provided context, say so clearly."""

        # Step 3: Stream Claude Response
        def generate_stream():
            """Generator that yields SSE events from Claude streaming response"""
            try:
                response = requests.post(
                    f"{ILIAD_URL}/api/v1/chat/claude-3.7-sonnet",
                    headers={"x-api-key": ILIAD_API_KEY},
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 1500,
                        "stream": True
                    },
                    stream=True,
                    timeout=60
                )

                if response.status_code != 200:
                    error_msg = f"Claude API error: {response.status_code}"
                    yield f"data: {json_module.dumps({'error': error_msg})}\n\n"
                    return

                # Stream chunks from Iliad
                for chunk in response.iter_content(chunk_size=None):
                    if chunk:
                        try:
                            # Iliad returns JSON-encoded strings: "Hello,"\n
                            chunk_text = chunk.decode('utf-8').strip()
                            if chunk_text:
                                # Parse the JSON string to get actual text
                                parsed_text = json_module.loads(chunk_text)
                                if parsed_text:
                                    yield f"data: {json_module.dumps({'text': parsed_text})}\n\n"
                        except json_module.JSONDecodeError:
                            # If not valid JSON, send raw text
                            clean_text = chunk_text.strip('"')
                            if clean_text:
                                yield f"data: {json_module.dumps({'text': clean_text})}\n\n"
                        except Exception as e:
                            logger.warning(f"[COA-Chat-Stream] Chunk parse error: {e}")

                # Signal completion
                yield f"data: {json_module.dumps({'done': True, 'document': original_filename, 'process_id': process_id})}\n\n"

            except Exception as e:
                logger.error(f"[COA-Chat-Stream] Stream error: {e}")
                yield f"data: {json_module.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except Exception as e:
        logger.error(f"[COA-Chat-Stream] Error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Chat streaming failed: {str(e)}"})


# =============================================================================
# Phase 3: RAG-Only Document Upload Endpoint
# =============================================================================
# This endpoint processes documents for RAG search WITHOUT GPT extraction/validation
# Flow: Upload PDF -> Textract (with LAYOUT) -> Parse blocks -> Chunk -> Index to Weaviate

@app.post("/upload-rag-doc")
async def upload_rag_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    request: Request = None
):
    """
    Upload a document for RAG-only processing (no GPT extraction).

    This endpoint:
    1. Runs Textract with LAYOUT feature
    2. Parses TABLE and LAYOUT blocks with grounding
    3. Creates chunks with cell_grounding and line_grounding
    4. Indexes to Weaviate for hybrid search

    Returns process_id for progress tracking.
    """
    try:
        # Get username from session if available
        username = None
        if request and hasattr(request, 'session'):
            username = request.session.get("username")
        username = username or "anonymous"

        logger.info(f"[RAG-Upload] Starting RAG-only upload for user: {username}")

        # Generate unique IDs
        process_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())

        # Initialize progress
        update_progress(process_id, "uploading", 0, "Starting RAG document upload...")

        # Sanitize and save file
        sanitized_filename = sanitize_filename(file.filename)
        original_filename = os.path.splitext(sanitized_filename)[0]

        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
        os.makedirs(base_path, exist_ok=True)

        pdf_file_path = os.path.join(base_path, f"{original_filename}.pdf")

        update_progress(process_id, "uploading", 20, "Saving uploaded file...")

        file_content = await file.read()
        with open(pdf_file_path, "wb") as f:
            f.write(file_content)

        update_progress(process_id, "uploading", 40, "File saved successfully")
        logger.info(f"[RAG-Upload] File saved: {pdf_file_path}")

        # Start background processing
        background_tasks.add_task(
            process_rag_document_in_background,
            pdf_file_path,
            base_path,
            process_id,
            document_id,
            original_filename,
            username
        )

        return JSONResponse(
            content={
                "message": "RAG document upload started",
                "process_id": process_id,
                "document_id": document_id,
                "status": "processing"
            },
            status_code=202
        )

    except Exception as e:
        logger.error(f"[RAG-Upload] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Upload failed: {str(e)}"}
        )
    finally:
        file.file.close()


async def process_rag_document_in_background(
    pdf_file_path: str,
    base_path: str,
    process_id: str,
    document_id: str,
    original_filename: str,
    username: str
):
    """
    Background task to process document for RAG indexing.

    Steps:
    1. Run Textract with LAYOUT feature
    2. Parse blocks using TextractParser
    3. Transform to chunks using chunk_transformer
    4. Index to Weaviate
    """
    try:
        # Register process for tracking
        register_process(process_id, "rag_processing")
        add_process_file(process_id, pdf_file_path)

        # =========================================
        # Step 1: Run Textract (with LAYOUT)
        # =========================================
        check_cancellation(process_id)
        update_progress(process_id, "extracting", 0, "Starting Textract OCR with LAYOUT...")

        from textractservices.textract_single import process_direct_file

        # Progress callback for Textract
        def textract_progress(progress, message):
            # Map Textract progress (0-100) to our range (0-40)
            mapped_progress = int(progress * 0.4)
            update_progress(process_id, "extracting", mapped_progress, message)

        # Run Textract (this now uses LAYOUT feature)
        excel_file_path = await run_cpu_intensive_task(
            process_direct_file,
            pdf_file_path,
            base_path,
            textract_progress
        )

        if not excel_file_path:
            raise Exception("Textract processing failed")

        add_process_file(process_id, excel_file_path)

        check_cancellation(process_id)
        update_progress(process_id, "extracting", 40, "Textract complete, parsing blocks...")

        # =========================================
        # Step 2: Parse Textract blocks
        # =========================================
        blocks_json_path = os.path.join(base_path, f"{original_filename}_blocks.json")

        if not os.path.exists(blocks_json_path):
            raise Exception(f"Blocks file not found: {blocks_json_path}")

        logger.info(f"[RAG-Upload] Parsing blocks from: {blocks_json_path}")

        parser = TextractParser(blocks_json_path=blocks_json_path)
        stats = parser.get_statistics()

        logger.info(f"[RAG-Upload] Parsed blocks: {stats}")

        tables = parser.get_all_tables()
        layouts = parser.get_all_layouts()

        update_progress(process_id, "analyzing", 50, f"Found {len(tables)} tables, {len(layouts)} text blocks")

        # =========================================
        # Step 3: Transform to chunks
        # =========================================
        check_cancellation(process_id)
        update_progress(process_id, "analyzing", 55, "Creating grounded chunks...")

        # Generate summary and keywords (quick GPT call)
        summary, keywords = await generate_document_metadata(blocks_json_path, original_filename)

        chunks = chunk_textract_blocks(
            tables=tables,
            layouts=layouts,
            document_id=document_id,
            process_id=process_id,
            filename=original_filename,
            document_summary=summary,
            keywords=keywords
        )

        chunk_stats = get_chunk_statistics(chunks)
        logger.info(f"[RAG-Upload] Created chunks: {chunk_stats}")

        update_progress(process_id, "analyzing", 65, f"Created {len(chunks)} chunks with grounding")

        # =========================================
        # Step 4: Index to Weaviate
        # =========================================
        check_cancellation(process_id)
        update_progress(process_id, "indexing", 70, "Indexing to Weaviate...")

        source_name = f"coa_{username}"

        def indexing_progress(progress, message):
            # Map indexing progress (0-100) to our range (70-95)
            mapped_progress = 70 + int(progress * 0.25)
            update_progress(process_id, "indexing", mapped_progress, message)

        indexer = WeaviateIndexer()
        result = indexer.index_chunks_batch(
            chunks=chunks,
            username=username,
            document_type="COA",
            source=source_name,
            progress_callback=indexing_progress
        )

        logger.info(f"[RAG-Upload] Indexing result: {result['success']} success, {result['failed']} failed")

        # =========================================
        # Complete
        # =========================================
        update_progress(process_id, "completed", 100, "RAG indexing complete")

        # Store results for retrieval
        results_store[process_id] = {
            "status": "completed",
            "document_id": document_id,
            "filename": original_filename,
            "chunks_indexed": result['success'],
            "chunks_failed": result['failed'],
            "source": source_name,
            "statistics": chunk_stats,
            "completed_at": datetime.utcnow().isoformat()
        }

        logger.info(f"[RAG-Upload] Complete. Process ID: {process_id}")

    except ProcessCancelledException:
        logger.info(f"[RAG-Upload] Process cancelled: {process_id}")
        update_progress(process_id, "cancelled", 0, "Processing cancelled by user")
        cleanup_process_files(process_id)

    except Exception as e:
        logger.error(f"[RAG-Upload] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        update_progress(process_id, "error", 0, f"Error: {str(e)}")

    finally:
        unregister_process(process_id)


async def generate_document_metadata(blocks_json_path: str, filename: str) -> tuple:
    """
    Generate summary and keywords for a document using GPT-4o-mini.

    Returns:
        Tuple of (summary, keywords)
    """
    try:
        # Read first portion of text from blocks
        with open(blocks_json_path, 'r', encoding='utf-8') as f:
            pages = json.load(f)

        # Extract LINE block text (first 2000 chars)
        text_content = []
        for page in pages:
            for block in page.get('Blocks', []):
                if block.get('BlockType') == 'LINE':
                    text_content.append(block.get('Text', ''))
                    if len(' '.join(text_content)) > 2000:
                        break
            if len(' '.join(text_content)) > 2000:
                break

        sample_text = ' '.join(text_content)[:2000]

        # Call GPT-4o-mini for quick metadata generation
        response = requests.post(
            f"{ILIAD_URL}/api/v1/chat/gpt-4o-mini-global",
            headers={"x-api-key": ILIAD_API_KEY},
            json={
                "messages": [{
                    "role": "user",
                    "content": f"""Analyze this Certificate of Analysis document text and provide:
1. A one-sentence summary (max 100 chars)
2. 5-10 relevant keywords separated by commas

Document: {filename}
Text sample:
{sample_text}

Respond in this exact format:
SUMMARY: <your summary>
KEYWORDS: <comma-separated keywords>"""
                }],
                "temperature": 0.3,
                "max_tokens": 200
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            content = result.get("completion", {}).get("content", "")

            # Parse response
            summary = ""
            keywords = ""

            for line in content.split('\n'):
                if line.startswith("SUMMARY:"):
                    summary = line.replace("SUMMARY:", "").strip()
                elif line.startswith("KEYWORDS:"):
                    keywords = line.replace("KEYWORDS:", "").strip()

            return summary or f"Certificate of Analysis: {filename}", keywords or "COA, certificate, analysis"
        else:
            logger.warning(f"[RAG-Upload] Metadata generation failed: {response.status_code}")
            return f"Certificate of Analysis: {filename}", "COA, certificate, analysis"

    except Exception as e:
        logger.error(f"[RAG-Upload] Metadata generation error: {e}")
        return f"Certificate of Analysis: {filename}", "COA, certificate, analysis"


@app.get("/rag-result/{process_id}")
async def get_rag_result(process_id: str):
    """Get the result of a RAG document processing job."""
    # Check progress store first (for active processes)
    if process_id in progress_store:
        progress = progress_store[process_id]
        return JSONResponse(
            content={
                "status": progress.get("status", "unknown"),
                "progress": progress.get("progress", 0),
                "message": progress.get("message", ""),
                "process_id": process_id
            }
        )

    # Check results store (for completed processes)
    if process_id in results_store:
        result = results_store[process_id]
        return JSONResponse(content=result)

    return JSONResponse(
        status_code=404,
        content={"error": "Process not found", "process_id": process_id}
    )


# ============================================================================
# PHASE 5: PDF Page Image Endpoints for PDF Viewer with Highlighting
# ============================================================================

from fastapi.staticfiles import StaticFiles

# Mount static files for PDF page images
static_pdf_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "pdf_pages")
os.makedirs(static_pdf_dir, exist_ok=True)
app.mount("/static/pdf_pages", StaticFiles(directory=static_pdf_dir), name="pdf_pages")

# Mount temp folder to serve PDFs directly for react-pdf-viewer
temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
os.makedirs(temp_dir, exist_ok=True)

# Custom endpoint for PDF files with caching headers (faster loading)
@app.get("/temp/{filename:path}")
async def serve_temp_file(filename: str):
    """Serve temp files (PDFs) with cache headers for faster loading."""
    file_path = os.path.join(temp_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type
    content_type = "application/octet-stream"
    if filename.lower().endswith(".pdf"):
        content_type = "application/pdf"
    elif filename.lower().endswith(".xlsx"):
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename.lower().endswith(".json"):
        content_type = "application/json"

    return FileResponse(
        path=file_path,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            "Accept-Ranges": "bytes",  # Enable range requests for PDF.js
        }
    )


@app.get("/api/pdf/{process_id}/page/{page_num}")
async def get_pdf_page_image(process_id: str, page_num: int):
    """
    Get a PDF page as an image (WebP format).

    This endpoint converts PDF pages to images on-demand with caching.
    Used by the frontend PDF viewer for highlighting bbox regions.

    Args:
        process_id: The document process_id (Weaviate filter key)
        page_num: Page number (1-indexed)

    Returns:
        JSON with imageUrl, width, height, cached
    """
    try:
        from services.pdf_image_service import get_pdf_image_service

        service = get_pdf_image_service()
        result = service.get_page_image(process_id, page_num)

        return JSONResponse(content=result)

    except FileNotFoundError as e:
        logger.warning(f"[PDF-Image] Document not found: {process_id}")
        return JSONResponse(
            status_code=404,
            content={"error": "Document not found", "process_id": process_id}
        )

    except ValueError as e:
        logger.warning(f"[PDF-Image] Invalid page: {e}")
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )

    except Exception as e:
        logger.error(f"[PDF-Image] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get page image: {str(e)}"}
        )


@app.get("/api/pdf/{process_id}/metadata")
async def get_pdf_metadata(process_id: str):
    """
    Get PDF document metadata including page count.

    Args:
        process_id: The document process_id

    Returns:
        JSON with documentId, documentName, pageCount, processId
    """
    try:
        from services.pdf_image_service import get_pdf_image_service

        service = get_pdf_image_service()
        result = service.get_document_metadata(process_id)

        return JSONResponse(content=result)

    except FileNotFoundError as e:
        logger.warning(f"[PDF-Metadata] Document not found: {process_id}")
        return JSONResponse(
            status_code=404,
            content={"error": "Document not found", "process_id": process_id}
        )

    except Exception as e:
        logger.error(f"[PDF-Metadata] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get metadata: {str(e)}"}
        )


@app.post("/api/pdf/{process_id}/preload")
async def preload_pdf_pages(process_id: str, request: Request):
    """
    Preload multiple PDF pages in background.

    Request body: { "pages": [1, 2, 3, ...] }

    Returns:
        JSON with preloaded count
    """
    try:
        from services.pdf_image_service import get_pdf_image_service

        body = await request.json()
        pages = body.get("pages", [])

        if not pages:
            return JSONResponse(
                status_code=400,
                content={"error": "No pages specified"}
            )

        service = get_pdf_image_service()
        preloaded = service.preload_pages(process_id, pages)

        return JSONResponse(content={
            "success": True,
            "preloaded": preloaded,
            "requested": len(pages)
        })

    except Exception as e:
        logger.error(f"[PDF-Preload] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to preload pages: {str(e)}"}
        )


@app.delete("/api/pdf/{process_id}/cache")
async def clear_pdf_cache(process_id: str):
    """
    Clear cached PDF page images for a document.

    Args:
        process_id: The document process_id

    Returns:
        JSON with deleted count
    """
    try:
        from services.pdf_image_service import get_pdf_image_service

        service = get_pdf_image_service()
        deleted = service.clear_cache(process_id)

        return JSONResponse(content={
            "success": True,
            "deleted": deleted,
            "process_id": process_id
        })

    except Exception as e:
        logger.error(f"[PDF-ClearCache] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to clear cache: {str(e)}"}
        )


if __name__ == "__main__":
    # Get server config from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("DEBUG", "False").lower() == "true"

    # Increase timeouts for long-running requests
    uvicorn.run("app:app", host=host, port=port, reload=debug, timeout_keep_alive=300, timeout_graceful_shutdown=300) 
