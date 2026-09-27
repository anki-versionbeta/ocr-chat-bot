import boto3
import os
import pandas as pd
from PIL import Image
import fitz  # PyMuPDF
import io
import tempfile
from typing import Dict, List, Any, Tuple, Optional
import json
import urllib3
from pathlib import Path
import re
import botocore.config
import time
import sys
import traceback
from datetime import datetime
from botocore.exceptions import ClientError, NoCredentialsError, TokenRetrievalError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Check environment for boto3 configuration
textract_env = os.getenv('TEXTRACT_ENV')
print(f"TEXTRACT_ENV: {textract_env}")

# Configure boto3 session based on environment
if textract_env == 'local':
    # Use session with explicit credentials for local development
    boto3_session = boto3.Session(
        aws_access_key_id=REDACTED
        aws_secret_access_key=REDACTED
        aws_session_token=REDACTED
    )
    print("Using local session with explicit AWS credentials")
    use_session = True
else:
    # Clear any existing AWS credential environment variables to force IAM role usage
    aws_env_vars = [
        'AWS_ACCESS_KEY_ID', 
        'AWS_SECRET_ACCESS_KEY', 
        'AWS_SESSION_TOKEN',
        'AWS_SECURITY_TOKEN'
    ]
    for var in aws_env_vars:
        if var in os.environ:
            print(f"Clearing {var} environment variable")
            del os.environ[var]
    
    # Use default boto3 (will use IAM role/instance profile when on AWS)  
    boto3_session = None
    print(f"Using default boto3 for environment: {textract_env}")
    use_session = False

class TextractProcessor:
    def __init__(self):
        """Initialize AWS clients"""        
        import urllib3
        import os
        import botocore.config
        
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        os.environ['AWS_CA_BUNDLE'] = ''
        
        # Set configuration with very aggressive timeouts
        config = botocore.config.Config(
            connect_timeout=3,    # 3 seconds to establish connection
            read_timeout=7,       # 7 seconds to read response
            retries={'max_attempts': 3},  # Retry up to 3 times with exponential backoff
            signature_version='v4'
        )
        
        # Configure AWS session based on environment
        print("Initializing AWS clients...")
        try:            # Create AWS clients using the configured session
            if use_session and boto3_session:
                self.s3_client = boto3_session.client('s3', region_name='us-east-1', verify=False, config=config)
                self.textract_client = boto3_session.client('textract', region_name='us-east-1', verify=False, config=config)
                print("AWS clients created using session")
            else:
                self.s3_client = boto3.client('s3', region_name='us-east-1', verify=False, config=config)
                self.textract_client = boto3.client('textract', region_name='us-east-1', verify=False, config=config)
                print("AWS clients created using default boto3 (IAM role)")
            
            # Test connection with a simple API call
            try:
                print("Testing S3 connection...")
                self.s3_client.list_buckets()
                print("S3 connection successful!")
            except Exception as e:
                print(f"WARNING: S3 connection test failed: {str(e)}")
            
            # Test Textract client
            try:
                print("Testing Textract connection...")
                self.textract_client.list_document_classifiers()
                print("Textract connection successful!")
            except Exception as e:
                print(f"WARNING: Textract connection test failed: {str(e)}")
                
            self.bucket_name = "ost-intelligent-parsing-test"
            self.temp_folder = "temp_hbr"
            
        except NoCredentialsError:
            print("ERROR: AWS credentials not found or invalid")
            sys.exit(1)
        except TokenRetrievalError:
            print("ERROR: AWS session token is invalid or expired")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to initialize AWS clients: {str(e)}")
            sys.exit(1)

    def upload_to_s3(self, file_path: str) -> str:
        """Upload PDF to S3 and return S3 path"""
        file_name = os.path.basename(file_path)
        s3_path = f"{self.temp_folder}/{file_name}"
        
        try:
            print(f"Uploading {file_path} to S3 bucket {self.bucket_name}/{s3_path}...")
            start_time = time.time()
            with open(file_path, 'rb') as file:
                self.s3_client.upload_fileobj(file, self.bucket_name, s3_path)
            print(f"Upload completed in {time.time() - start_time:.2f} seconds")
            return s3_path
        except Exception as e:
            print(f"ERROR uploading to S3: {str(e)}")
            raise

    def parse_page_numbers(self, search_pages: str) -> List[int]:
        """Convert search_pages string to list of page numbers"""
        if not search_pages or pd.isna(search_pages) or search_pages == 'nan' or search_pages == '':
            return []
        try:
            return [int(page.strip()) for page in search_pages.split(',') if page.strip()]
        except ValueError:
            print(f"Warning: Could not parse page numbers from '{search_pages}'. Using empty list.")
            return []

    def optimize_image(self, image: Image.Image, max_size: int = 1000) -> Image.Image:
        """Resize and optimize image for Textract if needed"""
        # Check if resizing is needed
        if max(image.width, image.height) > max_size:
            print(f"Resizing image from {image.width}x{image.height}", end="")
            # Maintain aspect ratio
            if image.width > image.height:
                new_width = max_size
                new_height = int(image.height * (max_size / image.width))
            else:
                new_height = max_size
                new_width = int(image.width * (max_size / image.height))
                
            # Resize the image
            image = image.resize((new_width, new_height), Image.LANCZOS)
            print(f" to {image.width}x{image.height}")
        
        # Enhance contrast for better OCR if needed
        # image = ImageOps.autocontrast(image)
        
        return image

    def process_pdf(self, pdf_path: str, config_path: str) -> Dict[str, Any]:
        """Process PDF using configuration from Excel"""
        print(f"\n{'='*80}\nStarting PDF processing at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"PDF File: {pdf_path}")
        
        # Read configuration file
        print(f"Reading configuration from: {config_path}")
        try:
            config_df = self._read_excel_with_preprocessing(config_path)
              # Debug: Print column names with detailed info
            print("Excel columns:", config_df.columns.tolist())
            print("\nFirst row sample data:")
            for col, val in config_df.iloc[0].to_dict().items():
                print(f"  {col}: {val} (type: {type(val).__name__})")
            
            print(f"\nSuccessfully read config with {len(config_df)} entries")
        except Exception as e:
            print(f"ERROR reading configuration file: {str(e)}")
            return {'error': f"Failed to read configuration: {str(e)}"}
        
        # Convert search_pages column to string type and handle NaN values
        config_df['search_pages'] = config_df['search_pages'].fillna('')
        config_df['search_pages'] = config_df['search_pages'].astype(str)
        
        # Clean up empty strings that came from NaN values
        config_df['search_pages'] = config_df['search_pages'].replace('nan', '')

        # Upload PDF to S3
        try:
            print("Uploading PDF to S3...")
            s3_path = self.upload_to_s3(pdf_path)
        except Exception as e:
            print(f"ERROR uploading to S3: {str(e)}")
            return {'error': f"Failed to upload PDF: {str(e)}"}
        
        # Process each page using PyMuPDF instead of pdf2image
        all_results = []
        print("Converting PDF to images using PyMuPDF...")
        try:
            start_time = time.time()
            
            # Open PDF with PyMuPDF
            pdf_document = fitz.open(pdf_path)
            total_pages = len(pdf_document)
            print(f"PDF has {total_pages} pages")
            
            # Process each page
            for page_num in range(1, total_pages + 1):
                print(f"\nProcessing page {page_num}/{total_pages}")
                
                # Get the page (PyMuPDF uses 0-based indexing)
                page = pdf_document[page_num - 1]
                
                # Render page to an image (300 DPI for good quality)
                pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
                
                # Convert to PIL Image
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data))
                
                # Optimize image
                image = self.optimize_image(image)
                
                # Convert image to bytes for Textract
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG', optimize=True, quality=85)
                img_byte_arr = img_byte_arr.getvalue()
                print(f"Image size: {len(img_byte_arr)/1024:.1f} KB")
                
                # Get parameters for current page
                page_queries = []
                for idx, row in config_df.iterrows():
                    page_numbers = self.parse_page_numbers(row['search_pages'])
                    
                    # Try different possible column names for the query (case-insensitive)
                    query = None
                    possible_columns = ['param_query', 'search_query', 'query', 'text', 'search_text', 'question', 
                                        'search query', 'search-query', 'description', 'prompt']
                    
                    # First try exact matches
                    for possible_column in possible_columns:
                        if possible_column in config_df.columns:
                            query = row[possible_column]
                            if idx == 0:  # Only print this for the first row
                                print(f"Using column '{possible_column}' for queries")
                            break
                      # If no exact match, try case-insensitive search
                    if query is None:
                        column_mapping = {col.lower(): col for col in config_df.columns}
                        for possible_column in possible_columns:
                            if possible_column.lower() in column_mapping:
                                actual_column = column_mapping[possible_column.lower()]
                                query = row[actual_column]
                                if idx == 0:  # Only print this for the first row
                                    print(f"Using column '{actual_column}' for queries (case-insensitive match)")
                                break
                                
                    # As a last resort, try fuzzy matching or look for any column containing keywords
                    if query is None:
                        keywords = ['query', 'search', 'text', 'question', 'prompt']
                        for col in config_df.columns:
                            if any(keyword in col.lower() for keyword in keywords):
                                query = row[col]
                                if idx == 0:  # Only print this for the first row
                                    print(f"Using column '{col}' for queries (keyword matching)")
                                break
                    
                    if query is None:
                        print(f"\nERROR: Could not find query column in Excel. Available columns: {config_df.columns.tolist()}")
                        print("Please ensure your Excel file has a column containing queries with one of these names:")
                        print(f"  {', '.join(possible_columns)}")
                        print("Alternatively, rename your query column to 'search_query'")
                        return {'error': "Could not find query column in Excel"}
                    
                    # Check if the page number is in the configured pages and query is not empty
                    if page_num in page_numbers and query and not pd.isna(query) and query != 'nan':
                        page_queries.append(query)
                    elif page_num in page_numbers:
                        print(f"  Warning: Empty query found for page {page_num}, row {idx+1}, skipping")
                
                if not page_queries:
                    print(f"No valid queries configured for page {page_num}, skipping")
                    continue                    
                print(f"Found {len(page_queries)} valid queries for page {page_num}")
                
                # Collect all queries for this page to process in batches
                batch_queries = []
                batch_rows = []
                
                for idx, row in config_df.iterrows():
                    page_numbers = self.parse_page_numbers(row['search_pages'])
                    if page_num in page_numbers:
                        # Find query column
                        query = None
                        for possible_column in ['param_query', 'search_query', 'query', 'text']:
                            if possible_column in config_df.columns:
                                query = row[possible_column]
                                break
                        
                        if not query or pd.isna(query) or query == 'nan':
                            continue
                            
                        batch_queries.append(query)
                        batch_rows.append(row)
                
                # Process queries in batches of 30 (Textract limit)
                batch_size = 30
                for i in range(0, len(batch_queries), batch_size):
                    current_batch_queries = batch_queries[i:i+batch_size]
                    current_batch_rows = batch_rows[i:i+batch_size]
                    
                    print(f"  Processing batch of {len(current_batch_queries)} queries...")
                    batch_results = self._extract_values_batch(img_byte_arr, current_batch_queries)
                    
                    # Process batch results
                    for query_idx, (query, row) in enumerate(zip(current_batch_queries, current_batch_rows)):
                        extracted_value, unit = batch_results.get(query_idx, (None, None))
                        
                        # Get parameter name and mapping from original row
                        parameter_name = row.get('parameter', '')
                        parameter_mapping = row.get('parameter_mapping', '')
                        
                        result = {
                            'parameter': parameter_name,
                            'parameter_mapping': parameter_mapping,
                            'page': page_num,
                            'value': extracted_value,
                            'unit': unit if unit else ''
                        }
                        all_results.append(result)
                        print(f"  Result: {parameter_name}: {extracted_value} {unit if unit else ''}")
            
            # Close the PDF document
            pdf_document.close()
        
        except Exception as e:
            print(f"ERROR processing PDF: {str(e)}")
            print(f"Full traceback: {traceback.format_exc()}")
            return {'error': f"PDF processing failed: {str(e)}"}
        
        # Save results to Excel
        if all_results:
            print("\nSaving results to Excel...")
            self._save_results_to_excel(all_results)
            print("Processing complete!")
        else:
            print("\nNo results extracted!")
            
        return all_results

    def _extract_value_with_textract(self, image_bytes: bytes, query: str) -> Tuple[Optional[float], Optional[str]]:
        """Extract value and unit using Textract"""
        start_time = time.time()
        max_retries = 2
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    print(f"    Retry attempt {attempt}/{max_retries}...")
                    
                print(f"    Sending request to Textract for query '{query}'...")
                response = self.textract_client.analyze_document(
                    Document={'Bytes': image_bytes},
                    FeatureTypes=['QUERIES'],
                    QueriesConfig={'Queries': [{'Text': query}]}
                )
                elapsed = time.time() - start_time
                print(f"    Received response in {elapsed:.2f} seconds")
                
                # Extract answer from response
                if 'Blocks' in response and response['Blocks']:
                    for block in response['Blocks']:
                        if block.get('BlockType') == 'QUERY_RESULT':
                            answer = block.get('Text', '')
                            print(f"    Answer: {answer}")
                            
                            # Try to extract value and unit
                            if not answer:
                                return None, None
                                
                            # Pattern to match numbers with optional units
                            match = re.search(r'([\d.,]+)\s*([a-zA-Z%]+)?', answer)
                            if match:
                                # Handle comma as decimal separator
                                value_str = match.group(1).replace(',', '.')
                                try:
                                    value = float(value_str)
                                    unit = match.group(2) if match.group(2) else None
                                    print(f"    Extracted value: {value}, unit: {unit}")
                                    return value, unit
                                except ValueError:
                                    print(f"    Could not convert '{value_str}' to float")
                                    return None, None
                            else:
                                print(f"    No numeric value found in answer: '{answer}'")
                                return None, None
                else:
                    print("    No blocks found in Textract response")
                    
                print("    No result found in response")
                return None, None
                
            except botocore.exceptions.ConnectTimeoutError:
                elapsed = time.time() - start_time
                print(f"    ERROR: Connection timeout for query '{query}' after {elapsed:.2f} seconds")
                if attempt < max_retries:
                    print(f"    Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    return None, None
                    
            except botocore.exceptions.ReadTimeoutError:
                elapsed = time.time() - start_time
                print(f"    ERROR: Read timeout for query '{query}' after {elapsed:.2f} seconds")
                if attempt < max_retries:
                    print(f"    Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    return None, None
                    
            except ClientError as e:
                error_code = e.response['Error']['Code']
                elapsed = time.time() - start_time
                print(f"    ERROR: AWS client error ({error_code}) for query '{query}' after {elapsed:.2f} seconds: {str(e)}")
                # Check if credential expiration error
                if error_code in ('ExpiredToken', 'InvalidClientTokenId'):
                    print("    AWS credentials have expired. Please refresh your credentials.")
                    return None, None
                elif attempt < max_retries:
                    print(f"    Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    return None, None
                    
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"    ERROR processing query '{query}' after {elapsed:.2f} seconds: {str(e)}")
                if attempt < max_retries:
                    print(f"    Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:                    return None, None
        
        # If we get here, all retries failed
        return None, None

    def _extract_values_batch(self, image_bytes: bytes, queries: List[str]) -> Dict[int, Tuple[Optional[float], Optional[str]]]:
        """Extract values and units using Textract with batch queries (up to 30 at once)"""
        start_time = time.time()
        max_retries = 2
        retry_delay = 1  # seconds
        
        # Prepare queries for Textract
        textract_queries = [{'Text': query} for query in queries]
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    print(f"    Retry attempt {attempt}/{max_retries} for batch...")
                    
                print(f"    Sending batch request to Textract with {len(queries)} queries...")
                response = self.textract_client.analyze_document(
                    Document={'Bytes': image_bytes},
                    FeatureTypes=['QUERIES'],
                    QueriesConfig={'Queries': textract_queries}
                )
                elapsed = time.time() - start_time
                print(f"    Received batch response in {elapsed:.2f} seconds")
                
                # Process batch results
                results = {}
                query_result_blocks = []
                
                # Collect all QUERY_RESULT blocks
                if 'Blocks' in response and response['Blocks']:
                    for block in response['Blocks']:
                        if block.get('BlockType') == 'QUERY_RESULT':
                            query_result_blocks.append(block)
                
                # Map results to query indices (Textract returns results in same order as queries)
                for query_idx, query in enumerate(queries):
                    if query_idx < len(query_result_blocks):
                        block = query_result_blocks[query_idx]
                        answer = block.get('Text', '')
                        
                        print(f"    Query {query_idx}: '{query}' -> Answer: {answer}")
                        
                        if answer:
                            # Extract value and unit using same logic as single query
                            match = re.search(r'([\d.,]+)\s*([a-zA-Z%]+)?', answer)
                            if match:
                                value_str = match.group(1).replace(',', '.')
                                try:
                                    value = float(value_str)
                                    unit = match.group(2) if match.group(2) else None
                                    print(f"    Extracted value: {value}, unit: {unit}")
                                    results[query_idx] = (value, unit)
                                except ValueError:
                                    print(f"    Could not convert '{value_str}' to float")
                                    results[query_idx] = (None, None)
                            else:
                                print(f"    No numeric value found in answer: '{answer}'")
                                results[query_idx] = (None, None)
                        else:
                            results[query_idx] = (None, None)
                    else:
                        print(f"    No result block found for query {query_idx}")
                        results[query_idx] = (None, None)
                
                return results
                
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"    ERROR processing batch queries after {elapsed:.2f} seconds: {str(e)}")
                if attempt < max_retries:
                    print(f"    Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    return {i: (None, None) for i in range(len(queries))}
        
        # If we get here, all retries failed
        return {i: (None, None) for i in range(len(queries))}

    def _save_results_to_excel(self, results: List[Dict], output_dir: str = None) -> str:
        """
        Save results to Excel file
        
        Args:
            results: List of dictionaries containing the results
            output_dir: Directory to save the Excel file (optional)
            
        Returns:
            Path to the saved Excel file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        df = pd.DataFrame(results)
        
        # Use provided output directory or default
        if not output_dir:
            # Create the default output directory if it doesn't exist
            output_dir = r"C:\Users\BAPATAR\Downloads\hbr_results"
            os.makedirs(output_dir, exist_ok=True)
        
        output_path = os.path.join(output_dir, f'textract_results_{timestamp}.xlsx')
        df.to_excel(output_path, index=False)
        print(f"Results saved to: {output_path}")
        
        return output_path

    def _read_excel_with_preprocessing(self, config_path: str) -> pd.DataFrame:
        """Read Excel file with proper preprocessing of data types"""
        try:
            # First try to get a list of all sheets
            xlsx = pd.ExcelFile(config_path)
            sheet_names = xlsx.sheet_names
            
            if len(sheet_names) > 1:
                print(f"Excel file contains multiple sheets: {sheet_names}")
                print(f"Using first sheet: {sheet_names[0]}")
            
            # Read the Excel file
            config_df = pd.read_excel(config_path, sheet_name=0)
            
            # Handle case-sensitive column names for common columns
            for col_name in ['search_pages', 'page', 'pages', 'Search Pages', 'Pages']:
                col_match = next((col for col in config_df.columns if col.lower() == col_name.lower()), None)
                if col_match:
                    config_df['search_pages'] = config_df[col_match]
                    if col_match != 'search_pages':
                        print(f"Renamed column '{col_match}' to 'search_pages'")
                    break
                    
            # Ensure search_pages exists
            if 'search_pages' not in config_df.columns:
                print("Warning: No 'search_pages' column found in Excel, adding empty column")
                config_df['search_pages'] = ''
            
            # Convert search_pages column to string type and handle NaN values
            config_df['search_pages'] = config_df['search_pages'].fillna('')
            config_df['search_pages'] = config_df['search_pages'].astype(str)
            
            # Clean up empty strings that came from NaN values
            config_df['search_pages'] = config_df['search_pages'].replace('nan', '')
            
            return config_df
            
        except Exception as e:
            print(f"Error processing Excel file: {str(e)}")
            raise

def main():
    print(f"Starting script at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Initialize processor with configured session
        processor = TextractProcessor()
        
        # Paths to your files
        pdf_path = Path(r"C:\Users\BAPATAR\Downloads\billes 20072628 lot 1000668819-P461Slot1 Buxton3.pdf")
        config_path = Path(r"C:\Users\BAPATAR\Downloads\Copy of pringy.xlsx")
        
        # Process the document
        results = processor.process_pdf(str(pdf_path), str(config_path))
        print("Processing complete!")
    except Exception as e:
        print(f"FATAL ERROR: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()