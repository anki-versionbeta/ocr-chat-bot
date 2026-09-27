import os
import requests
import json
import pandas as pd
import argparse
import time
import re 
from typing import Dict, List, Tuple, Any, Optional
import openpyxl
import traceback
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("Warning: aiohttp not available, falling back to synchronous requests")
import fitz  # PyMuPDF
import base64
import io
from PIL import Image
import numpy as np
from fuzzywuzzy import process


class GPTCoAExtractor:
    def __init__(self, api_key: str, api_url: str, model: Optional[str] = None):
        if not api_key:
            raise ValueError("API key is required.")
        if not api_url:
            raise ValueError("API URL is required.")

        self.api_key = api_key
        self.api_url = api_url
        self.model = model or "gpt-4o"
        
        # Cancellation support
        self.cancellation_callback = None
        
        # Progress callback support
        self.progress_callback = None
        
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Configuration for batch processing
        self.BATCH_SIZE = 5  # Process 5 sheets at a time
        self.MAX_CHARS_PER_BATCH = 25000  # Max characters per batch
        self.MAX_PARALLEL_BATCHES = 3  # Maximum parallel batch processing
        
        # Metadata fields to look for with LLM
        self.metadata_fields = [
            'Manufacturing Date', 'Expiry Date', 'Product Name', 'Product Number', 'Product Code',
            'Manufacturer', 'Packaging Site', 'Storage', 'Batch Number', 'Material Number',
            'Product Name', 'DoM', 'Fill Date', 'Date of Manufacture', 'Expiration Date',
            'Lot Number', 'Serial Number'
        ]
        
        # For storing LLM-extracted metadata
        self.llm_metadata = {}
        self.metadata_extraction_complete = False
        self._loop = None
        self._severe_truncation_detected = False

    def set_cancellation_callback(self, callback):
        """Set a callback function to check for cancellation"""
        self.cancellation_callback = callback
    
    def set_progress_callback(self, callback):
        """Set a callback function for progress updates"""
        self.progress_callback = callback
    
    def update_progress(self, progress: int, message: str):
        """Update progress if callback is set"""
        if self.progress_callback:
            self.progress_callback(progress, message)
    
    def check_cancellation(self):
        """Check if the process should be cancelled"""
        if self.cancellation_callback:
            self.cancellation_callback()

    def analyze_excel_structure(self, excel_path: str) -> Dict[str, Any]:
        """
        Analyze Excel file structure to plan processing strategy
        """
        print(f"📊 Analyzing Excel file structure...")
        
        xls = pd.ExcelFile(excel_path)
        sheet_analysis = []
        total_size = 0
        
        for sheet_name in xls.sheet_names:
            try:
                # Read sheet with minimal processing to get size
                df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, dtype=str, nrows=100)
                
                # Estimate full sheet size
                sample_size = len(df.to_string())
                total_rows = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, dtype=str, nrows=0).shape[0]
                estimated_size = (sample_size / min(100, len(df))) * total_rows if len(df) > 0 else 0
                
                sheet_info = {
                    'name': sheet_name,
                    'rows': total_rows,
                    'cols': len(df.columns),
                    'estimated_size': int(estimated_size),
                    'is_empty': df.empty or df.isna().all().all()
                }
                
                sheet_analysis.append(sheet_info)
                total_size += estimated_size
                
                print(f"  📄 Sheet '{sheet_name}': {total_rows} rows x {len(df.columns)} cols (~{int(estimated_size):,} chars)")
                
            except Exception as e:
                print(f"  ⚠️ Error analyzing sheet '{sheet_name}': {e}")
                sheet_analysis.append({
                    'name': sheet_name,
                    'rows': 0,
                    'cols': 0,
                    'estimated_size': 0,
                    'is_empty': True,
                    'error': str(e)
                })
        
        # Create processing plan
        non_empty_sheets = [s for s in sheet_analysis if not s.get('is_empty', True)]
        
        return {
            'total_sheets': len(xls.sheet_names),
            'non_empty_sheets': len(non_empty_sheets),
            'total_estimated_size': int(total_size),
            'sheet_details': sheet_analysis,
            'requires_batching': len(non_empty_sheets) > 10 or total_size > 50000
        }

    def create_sheet_batches(self, sheet_analysis: List[Dict]) -> List[List[Dict]]:
        """
        Create optimal batches of sheets for processing
        """
        non_empty_sheets = [s for s in sheet_analysis if not s.get('is_empty', True)]
        
        if not non_empty_sheets:
            return []
        
        # Keep sheets in original order for better document flow
        sorted_sheets = non_empty_sheets  # Don't sort by size, keep original order
        
        batches = []
        current_batch = []
        current_size = 0
        
        for sheet in sorted_sheets:
            sheet_size = sheet['estimated_size']
            
            # Check if adding this sheet would exceed limits
            if (len(current_batch) >= self.BATCH_SIZE or 
                (current_size + sheet_size > self.MAX_CHARS_PER_BATCH and current_batch)):
                # Start new batch
                batches.append(current_batch)
                current_batch = [sheet]
                current_size = sheet_size
            else:
                current_batch.append(sheet)
                current_size += sheet_size
        
        # Add last batch
        if current_batch:
            batches.append(current_batch)
        
        print(f"\n📦 Created {len(batches)} batches for processing:")
        for i, batch in enumerate(batches):
            batch_size = sum(s['estimated_size'] for s in batch)
            print(f"  Batch {i+1}: {len(batch)} sheets (~{batch_size:,} chars)")
        
        return batches

    def process_sheet_batch(self, excel_path: str, sheets: List[Dict], batch_num: int) -> Tuple[List[Dict], Dict]:
        """
        Process a batch of sheets
        """
        print(f"\n🔄 Processing Batch {batch_num} ({len(sheets)} sheets)...")
        
        # Extract text from all sheets in batch
        combined_text = ""
        sheet_names = []
        
        for sheet_info in sheets:
            sheet_name = sheet_info['name']
            sheet_names.append(sheet_name)
            
            try:
                df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, dtype=str)
                df = df.fillna('')
                
                sheet_text = f"\n\n=== Sheet: {sheet_name} ===\n"
                for _, row in df.iterrows():
                    row_text = " | ".join(map(str, row.tolist()))
                    sheet_text += row_text + "\n"
                
                combined_text += sheet_text
                
            except Exception as e:
                print(f"  ⚠️ Error reading sheet '{sheet_name}': {e}")
        
        if not combined_text.strip():
            print(f"  ⚠️ Batch {batch_num} has no data")
            return [], {}
        
        # Create batch-specific prompt
        prompt = self.create_batch_prompt(combined_text, sheet_names)
        
        # Query GPT
        max_retries = 2  # Fewer retries for batches
        for attempt in range(max_retries):
            try:
                response = self.query_gpt(prompt, max_retries=1)
                
                if "error" not in response:
                    extracted_data = self.extract_json_from_response(response)
                    if extracted_data:
                        test_data = extracted_data.get('test_data', [])
                        product_info = extracted_data.get('product_info', {})
                        print(f"  ✅ Batch {batch_num}: Extracted {len(test_data)} tests")
                        return test_data, product_info
                    
            except Exception as e:
                print(f"  ⚠️ Batch {batch_num} attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        
        print(f"  ❌ Batch {batch_num} failed after {max_retries} attempts")
        return [], {}

    def create_batch_prompt(self, text: str, sheet_names: List[str]) -> str:
        """
        Create a prompt specifically for batch processing
        """
        prompt = f"""
        Analyze this batch of Certificate of Analysis data from sheets: {', '.join(sheet_names)}.
        Extract test parameters and product information.

        Data:
        ```
        {text}
        ```

        Instructions:
        1. Extract product information if found (Product Name, Code, Batch Number, Dates)
        2. Extract ALL test parameters with specifications and results
        3. Preserve hierarchical relationships (Parent - Child format)
        4. Extract units from results
        5. Handle multiple sheets - tests may span across sheets

        Return ONLY JSON:
        ```json
        {{
            "product_info": {{
                "product_name": "...",
                "code": "...",
                "batch_number": "...",
                "date_of_manufacture": "...",
                "expiration_date": "..."
            }},
            "test_data": [
                {{
                    "test": "test name",
                    "specification": "spec",
                    "result": "value",
                    "unit": "unit"
                }}
            ]
        }}
        ```
        """
        return prompt

    def process_excel_with_parallel_batches(self, excel_path: str) -> Tuple[pd.DataFrame, Dict]:
        """
        Process Excel file using sequential batch processing for large files (maintains sheet order)
        """
        print(f"\n🚀 Starting sequential batch processing for: {excel_path}")
        
        # Analyze file structure
        analysis = self.analyze_excel_structure(excel_path)
        
        if not analysis['requires_batching']:
            print("📋 File is small enough for single processing")
            return self.process_excel_single(excel_path)
        
        # Create batches
        batches = self.create_sheet_batches(analysis['sheet_details'])
        
        if not batches:
            print("⚠️ No non-empty sheets found")
            return pd.DataFrame(), {}
        
        # Process batches SEQUENTIALLY to maintain sheet order
        all_test_data = []
        all_product_info = {}
        
        print(f"\n📦 Processing {len(batches)} batches sequentially to maintain order:")
        
        for batch_index, batch in enumerate(batches):
            print(f"\n🔄 Processing Batch {batch_index + 1} of {len(batches)}...")
            
            # Update progress based on batch completion
            batch_progress = 42 + int((batch_index / len(batches)) * 16)  # 42-58% range
            self.update_progress(batch_progress, f"Processing batch {batch_index + 1} of {len(batches)}")
            
            try:
                test_data, product_info = self.process_sheet_batch(excel_path, batch, batch_index + 1)
                
                # Add results in order
                all_test_data.extend(test_data)
                print(f"  ✅ Batch {batch_index + 1}: Added {len(test_data)} tests in order")
                
                # Merge product info (prefer non-empty values)
                for key, value in product_info.items():
                    if value and (key not in all_product_info or not all_product_info[key]):
                        all_product_info[key] = value
                    
            except Exception as e:
                print(f"  ❌ Error processing batch {batch_index + 1}: {e}")
                # Continue with next batch even if one fails
        
        # Create final dataframe
        df = pd.DataFrame(all_test_data)
        
        # Remove duplicates while preserving order
        if not df.empty:
            df = df.drop_duplicates(subset=['test', 'specification'], keep='first')
        
        print(f"\n✅ Sequential processing complete: {len(df)} total tests in correct sheet order")
        
        return df, all_product_info

    def process_excel_single(self, excel_path: str) -> Tuple[pd.DataFrame, Dict]:
        """
        Process Excel file using single request (for smaller files)
        """
        excel_text = self.extract_text_from_excel(excel_path)
        if not excel_text:
            print("Failed to extract text from Excel.")
            return pd.DataFrame(), {}
        
        prompt = self.create_prompt(excel_text)
        response = self.query_gpt(prompt)
        
        extracted_data = self.extract_json_from_response(response)
        if not extracted_data:
            print("Failed to extract valid JSON data from LLM response.")
            return pd.DataFrame(), {}
        
        return self.create_dataframe(extracted_data)

    def process_excel(self, excel_path: str) -> Tuple[pd.DataFrame, Dict]:
        """
        Main entry point - automatically chooses best processing method
        """
        print(f"\n🔍 Analyzing file to determine processing strategy...")
        
        # Quick analysis
        try:
            xls = pd.ExcelFile(excel_path)
            num_sheets = len(xls.sheet_names)
            print(f"📊 File contains {num_sheets} sheets")
            
            # Use parallel batch processing for files with many sheets
            if num_sheets > 15:
                print(f"📦 Using parallel batch processing for {num_sheets} sheets")
                df, product_info = self.process_excel_with_parallel_batches(excel_path)
            else:
                # Try single processing first
                print(f"📄 Attempting single processing for {num_sheets} sheets")
                try:
                    df, product_info = self.process_excel_single(excel_path)
                except Exception as e:
                    print(f"⚠️ Single processing failed: {e}")
                    print("🔄 Switching to batch processing...")
                    df, product_info = self.process_excel_with_parallel_batches(excel_path)
            
            # Auto-save results
            output_dir = os.path.dirname(excel_path)
            base_filename = os.path.splitext(os.path.basename(excel_path))[0]
            print(f"\n💾 Auto-saving results to {output_dir}")
            self.save_results(df, product_info, output_dir, base_filename)
            
            return df, product_info
            
        except Exception as e:
            print(f"❌ Error processing Excel: {e}")
            traceback.print_exc()
            return pd.DataFrame(), {}

    def extract_text_from_excel(self, excel_path: str) -> str:
        """
        Extract text from Excel file - optimized for large files
        """
        try:
            xls = pd.ExcelFile(excel_path)
            text_content = ""
            total_chars = 0
            max_chars = 100000  # Limit total extraction

            for sheet_name in xls.sheet_names:
                if total_chars >= max_chars:
                    print(f"⚠️ Reached character limit ({max_chars}), stopping extraction")
                    break
                
                df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, dtype=str)
                df = df.fillna('') 

                sheet_text = f"Sheet: {sheet_name}\n"
                for _, row in df.iterrows():
                    row_text = " | ".join(map(str, row.tolist()))
                    sheet_text += row_text + "\n"
                    
                    # Check size limit
                    if total_chars + len(sheet_text) > max_chars:
                        break

                text_content += sheet_text + "\n\n"
                total_chars += len(sheet_text)

            return text_content
        except Exception as e:
            print(f"Error extracting text from Excel: {e}")
            return ""

    def create_prompt(self, excel_text: str) -> str:
        """Original prompt creation method"""
        prompt = f"""
        Analyze the following Certificate of Analysis (CoA) data extracted from an Excel file.
        Your task is to structure this information into a specific JSON format with proper hierarchical relationships.

        CoA Data:
        ```
        {excel_text}
        ```

        Instructions:
        1.  Identify the main product information: Product Name, Code/Material Number, Batch Number, Date of Manufacture, Expiration Date. Place this in the `product_info` object. Use null or omit keys if information is not found.
        
        2.  IMPORTANT: Pay careful attention to hierarchical relationships between test parameters:
            - Identify main parent tests (like "MC Powder", "Vehicle", etc.)
            - Identify child tests under each parent (like "Appearance" under "MC Powder")
            - Identify any sub-child tests under children (creating a 3-level hierarchy if present)
        2a. Extract ALL test parameters that appear in the testing section of the CoA. EXCLUDE ONLY these specific administrative sections:
                - Process Information sections (containing process steps, fermentation details, cell culture procedures)
                - Certificate Information sections (document control, revision numbers, filing numbers)
                - QA Review or Production Review sections (approval signatures, review dates)
                - Document metadata (creation dates, document IDs that are not batch numbers)
        
        2b. INCLUDE all legitimate test parameters, even if they have formats like:
            - Simple compliance statements ("Complies", "Pass", "Acceptable")
            - Reference standards or control results
            - Identity tests and confirmatory tests
            - Safety and toxicity parameters
            - Microbiological tests
            - Physical appearance tests
            - Any parameter that evaluates product quality, safety, or identity
            - Tests with results showing "COMP - Complies" when they relate to actual product testing
        
        2c. When in doubt, INCLUDE the parameter if it appears in the main testing section of the document and relates to product evaluation.
        3.  Format test names with proper hierarchical relationships:
            - For child tests: "Parent - Child" (e.g., "MC Powder - Appearance")
            - For sub-child tests: "Parent - Child - SubChild" (e.g., "MC Powder - Related Substances - Individual degradation products")
            - PRESERVE ALL NUMBERS AND PARENTHESES in test names, like "1. Appearance" or "Test (1)" or "(1)Individual"
        
        4.  For each test parameter identified, extract:
            - The complete hierarchical test name (as described above)
            - Specification (keep the complete value INCLUDING any units if present)
            - Result value (extract WITHOUT units)
            - Unit (extract units from the RESULT column only - look for units like %, mg/mL, °C, etc. at the end of result values)
            
            IMPORTANT UNIT EXTRACTION RULES:
            - Extract units ONLY from the result column, NOT from specifications
            - If result is "99.2 %", then result = "99.2" and unit = "%"
            - If result is "< 0.02 EU/mg", then result = "< 0.02" and unit = "EU/mg"
            - Keep specifications complete with their units (do not modify them)
            - Common units to extract from results: %, mg/mL, mg, mL, µg, EU/mg, ppm, °C, g/mol, etc.

        5.  Structure the extracted test data as a list of objects under the `test_data` key. Each object should contain 'test', 'specification', 'result', and 'unit' keys. Use null or omit keys if information is not found for a specific test.
        
        6.  Return ONLY the final JSON object, enclosed in triple backticks (```json ... ```). Do not include any introductory text, explanations, or summaries outside the JSON structure.

        Pay special attention to:
        - Indentation or formatting in the document that indicates hierarchy
        - Numbered items (like "1.", "(1)", etc.) which should be preserved in test names
        - Tests that appear to be grouped under headings
        - Multi-level nesting (parent, child, sub-child relationships)
        7. If the specification and result columns are empty, the test parameter might be a parent to the rows below (but only ~30% chance). However, STOP extracting when you encounter administrative sections like "Process Information", "Certificate Information", "QA Review", or "Production Review" - these are NOT test data even if they have values in specification/result columns.
        7a. CRITICAL: When specification or result columns contain multiple sub-parameters separated by semicolons or similar delimiters, split them into separate test objects with proper hierarchy. Parse the pattern "SubParam1: value1; SubParam2: value2" and create individual test entries as "Parent - SubParam1", "Parent - SubParam2", etc., matching each sub-parameter with its corresponding specification and result values.
        7b - INTELLIGENT MULTI-VALUE CELL HANDLING:**
    
            When a cell contains multiple values (separated by line breaks, semicolons, or other delimiters), use pharmaceutical testing intelligence to decide whether to split or keep together:
            
            SPLIT when the values represent:
            - Different test attributes or properties being measured
            - Different test methods or analytical techniques
            - Different units that measure fundamentally different things
            - Individual components that need separate tracking (like different impurities)
            
            KEEP TOGETHER when the values represent:
            - A single test criterion expressed as a range (min-max)
            - Multiple acceptance criteria for the same property
            - Different ways of expressing the same limit
            
            Apply your understanding of pharmaceutical/chemical testing:
            - Visual properties vs instrumental measurements are usually different tests
            - Different analytical methods are separate tests
            - Individual impurities or substances are tracked separately
            - Use the context and your knowledge of GxP testing to make intelligent decisions
        
        7c. SPECIAL HANDLING FOR IN-PROCESS CONTENT UNIFORMITY TESTS:

            When you encounter IN-PROCESS CONTENT UNIFORMITY tests in the Excel data:

            FORMAT RULES:
            1. Add "Stage 1, Stage 2" between the parameter name and the detail
            2. Combine BOTH stage specifications into one, separated by comma
            3. Extract summary statistics for EACH parameter separately

            STRUCTURE:
            - Test name pattern: "IN-PROCESS CONTENT UNIFORMITY - [PARAMETER] - Stage 1, Stage 2 - [DETAIL]"
            where [PARAMETER] = actual drug name from data (e.g., ETHINYL ESTRADIOL, NORETHINDRONE ACETATE)
            where [DETAIL] = Bag.# X or summary metric name

            - For bags: Use the actual bag numbers from the data
            - For summaries: Look for Avg, RSD, Min, Max rows for EACH parameter

            CRITICAL REQUIREMENTS:
            ✓ Extract the ACTUAL specifications from YOUR data, not from this example
            ✓ Extract the ACTUAL result values from YOUR data
            ✓ Each parameter (ETHINYL ESTRADIOL, NORETHINDRONE ACETATE) has its OWN set of summary statistics
            ✓ Do NOT miss any summary rows - carefully check for all Avg, RSD, Min, Max for EACH drug
            ✓ The specification text appears only in the first row of each parameter - COPY this same specification to ALL rows for that parameter (all bags and summary rows)

            WHAT TO LOOK FOR IN YOUR DATA:
            - Individual bag results (Bag.# 1, Bag.# 2, etc.) - all bags are tested for both stages
            - Summary statistics that appear after the bag results:
            * Avg. (all samples, wt. correct)
            * RSD (all samples, wt. correct)  
            * Min. (all samples, as is)
            * Max. (all samples, as is)
            - These summaries appear for EACH parameter - don't stop after finding one set
            - Continue extracting until you've found all 4 summary rows for EACH drug compound you are always missing one please check ex: ETHINYL ESTRADIOL for this you are missing please add this too 
        8. please check relationships correclty like specified impurites has chemicals not unspecified if there 
        example Specified Impurities - Unspecified (each) there the speciifed impurites is not parent to unspecified unspeciifed in unique
        Specified Impurities - Total (Specified and Unspecified) here too here the total (Specified and Unspecified) is seperate row not child because it is just showing the total so it wont come under 
        Specified Impurities - Arginine Adduct here too so dont add like this
       9. CRITICAL: Only stop extracting when you encounter clear section headers like:
    - "Process Information"
    - "Certificate Information" 
    - "QA Review"
    - "Production Review"
    - "Document Control"
    - Similar administrative section headers
    9. Format specifications: both limits = "X - Y", upper limit only = "≤ Y", lower limit only = "≥ X".
    10. If columns show "ANALYSIS" and "NAME" separately, combine them as "Analysis - Name" in the Test field.
    Do NOT stop extracting for legitimate test parameters just because they have simple results or compliance statements.
        ```json
        {{
            "product_info": {{
                "product_name": "...",
                "code": "...", // or material_number
                "batch_number": "...",
                "date_of_manufacture": "...",
                "expiration_date": "..."
            }},
            "test_data": [
                {{
                    "test": "PARENT - CHILD", // or "PARENT - CHILD - SUBCHILD" for deeper hierarchies
                    "specification": "...",
                    "result": "...",
                    "unit": "..." // or null/omit if not applicable
                }},
                // ... more test objects
            ]
        }}
        ```

        Focus on accurately capturing ALL test items and their complete hierarchical relationships, including proper formatting of numbered items and parentheses.
        When in doubt about whether something is a test parameter, err on the side of inclusion rather than exclusion.
        
        CRITICAL JSON FORMATTING REQUIREMENTS:
        - Return ONLY the JSON object, no explanations or additional text before or after
        - Properly escape any special characters in strings (quotes, backslashes, etc.)
        - Ensure valid JSON syntax even if test names contain special characters
        - Use double quotes for all strings, never single quotes
        - End all objects and arrays with proper comma placement
        - Do not include trailing commas after the last element in arrays or objects
        - If test names contain quotes, escape them as \\"
        - If values span multiple lines, use \\n for line breaks within the JSON string
        - Never break string values across actual line breaks - keep them as single escaped strings
        """
        return prompt

    def query_gpt(self, prompt: str, max_retries: int = 3) -> Dict:
        """Query GPT with optimized token allocation and thinking mode"""
        
        # First, check if prompt is too large
        estimated_tokens = REDACTED
        
        if estimated_tokens > 25000:
            print(f"⚠️ Prompt too large (~{estimated_tokens} tokens). Needs chunking...")
            return {"error": "prompt_too_large", "estimated_tokens": estimated_tokens}

        # Optimized payload with thinking mode parameters
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 64000,  # Maximum for non-thinking mode
            "thinking_budget": 1024,  # Minimum thinking tokens to reduce overhead  
            "model": self.model
        }

        for attempt in range(max_retries):
            try:
                # Check for cancellation before each API attempt
                self.check_cancellation()
                
                print(f"Sending request to LLM API (Attempt {attempt + 1}/{max_retries})...")
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=180 
                )
                response.raise_for_status() 
                print("LLM API request successful.")
                return response.json()
            except requests.exceptions.Timeout:
                print(f"API request timed out (Attempt {attempt + 1}/{max_retries}).")
            except requests.exceptions.RequestException as e:
                print(f"API request failed (Attempt {attempt + 1}/{max_retries}): {e}")
                
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        print(f"Response Status: {e.response.status_code}")
                        print(f"Response Body: {e.response.text[:500]}...") 
                    except Exception:
                        print("Could not read response body.")

            if attempt < max_retries - 1:
                wait_time = 2 ** attempt 
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print("All API request attempts failed.")
                return {"error": "API request failed after multiple attempts"}

        return {"error": "API request failed unexpectedly"}

    def extract_json_from_response(self, response: Dict) -> Optional[Dict]:
        """Extract JSON from LLM response"""
        if "error" in response:
            print(f"Cannot extract JSON, API response contains error: {response['error']}")
            return None

        try:
            if 'choices' in response and response['choices']:
                message = response['choices'][0].get('message', {})
                completion_text = message.get('content')
            elif 'completion' in response:
                completion_text = response['completion']['content']
            else:
                completion_text = json.dumps(response) 
                print("Warning: Unknown response structure.")

            if not completion_text or not isinstance(completion_text, str):
                print(f"Error: Could not find text content in LLM response.")
                return None

            # Extract JSON from markdown if present
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', completion_text, re.IGNORECASE)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                json_match = re.search(r'\{[\s\S]*\}', completion_text)
                if not json_match:
                    print(f"Error: Could not find valid JSON structure in response")
                    return None
                json_str = json_match.group(0)

            # Try parsing
            try:
                extracted_data = json.loads(json_str)
                return extracted_data
            except json.JSONDecodeError as e:
                print(f"JSON parsing failed: {e}")
                # Try fixing common issues
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                try:
                    extracted_data = json.loads(json_str)
                    return extracted_data
                except:
                    return None
                
        except Exception as e:
            print(f"Unexpected error extracting JSON from response: {e}")
            return None

    def create_dataframe(self, extracted_data: Dict) -> Tuple[pd.DataFrame, Dict]:
        """Create DataFrame from extracted data"""
        try:
            product_info = extracted_data.get('product_info', {})
            test_data = extracted_data.get('test_data', [])

            if not isinstance(test_data, list):
                print(f"Warning: 'test_data' is not a list. Found type: {type(test_data)}")
                test_data = []
            if not isinstance(product_info, dict):
                print(f"Warning: 'product_info' is not a dictionary. Found type: {type(product_info)}")
                product_info = {}

            df = pd.DataFrame(test_data)
            
            expected_cols = ['test', 'specification', 'result', 'unit']
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = None 

            df = df[expected_cols]

            return df, product_info
        except Exception as e:
            print(f"Error creating DataFrame: {e}")
            return pd.DataFrame(), {}

    def save_results(self, df: pd.DataFrame, product_info: Dict, output_dir: str, base_filename: str) -> None:
        """Save extracted data to files"""
        try:
            os.makedirs(output_dir, exist_ok=True)

            # Save to CSV
            csv_path = os.path.join(output_dir, f"{base_filename}_data.csv")
            df.to_csv(csv_path, index=False, encoding='utf-8') 
            print(f"Test data saved to {csv_path}")

            # Save product info JSON
            json_path = os.path.join(output_dir, f"{base_filename}_info.json")
            with open(json_path, 'w', encoding='utf-8') as f: 
                json.dump(product_info, f, indent=2, ensure_ascii=False) 
            print(f"Product info saved to {json_path}")
            
            # Save combined JSON
            combined_path = os.path.join(output_dir, f"{base_filename}_results.json")
            combined_data = {
                "product_info": product_info,
                "test_data": df.to_dict(orient='records')
            }
            with open(combined_path, 'w', encoding='utf-8') as f:
                json.dump(combined_data, f, indent=2, ensure_ascii=False)
            print(f"Combined results saved to {combined_path}")
            
            # Create unified Excel file
            unified_excel_path = os.path.join(output_dir, f"{base_filename}_unified.xlsx")
            self.create_unified_excel(df, product_info, unified_excel_path)
            print(f"Unified Excel file created at {unified_excel_path}")
            
        except Exception as e:
            print(f"Error saving results: {e}")

    def create_unified_excel(self, df: pd.DataFrame, product_info: Dict, excel_path: str) -> None:
        """Create a well-formatted Excel file containing both product metadata and test data"""
        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                workbook = writer.book
                sheet_name = "Certificate of Analysis"
                
                # Title
                title_df = pd.DataFrame([["Certificate of Analysis", ""]], columns=["", ""])
                title_df.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=0)
                
                # Metadata section
                metadata_df = pd.DataFrame(columns=["Property", "Value"])
                
                row_idx = 0
                for key, value in product_info.items():
                    if value:
                        display_key = key.replace('_', ' ').title()
                        metadata_df.loc[row_idx] = [display_key, value]
                        row_idx += 1
                
                metadata_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=2)
                
                # Test data
                test_data_start_row = 2 + len(metadata_df) + 1 + 1
                
                if not df.empty:
                    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=test_data_start_row)
                
                # Format worksheet
                worksheet = writer.sheets[sheet_name]
                
                # Title formatting
                title_cell = worksheet["A1"]
                title_cell.font = openpyxl.styles.Font(bold=True, size=16)
                title_cell.alignment = openpyxl.styles.Alignment(horizontal='center', vertical='center')
                worksheet.merge_cells("A1:B1")
                
                # Column widths
                for col in worksheet.columns:
                    max_length = 0
                    if hasattr(col[0], 'column_letter'):
                        column = col[0].column_letter
                        for cell in col:
                            if cell.value:
                                cell_length = len(str(cell.value))
                                if cell_length > max_length:
                                    max_length = cell_length
                        adjusted_width = (max_length + 2) * 1.2
                        worksheet.column_dimensions[column].width = min(adjusted_width, 50)
                
                # Borders
                thin_border = openpyxl.styles.Border(
                    left=openpyxl.styles.Side(style='thin'),
                    right=openpyxl.styles.Side(style='thin'),
                    top=openpyxl.styles.Side(style='thin'),
                    bottom=openpyxl.styles.Side(style='thin')
                )
                
                # Apply formatting
                for row in range(3, 4 + len(metadata_df)):
                    for col in range(1, 3):
                        cell = worksheet.cell(row=row, column=col)
                        cell.border = thin_border
                        if row == 3:  # Header
                            cell.font = openpyxl.styles.Font(bold=True)
                            cell.fill = openpyxl.styles.PatternFill(start_color="E6E6E6", end_color="E6E6E6", fill_type="solid")
                        elif col == 1:  # Keys
                            cell.font = openpyxl.styles.Font(bold=True)
                            cell.fill = openpyxl.styles.PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                
                # Create additional sheets
                if not df.empty:
                    df.to_excel(writer, sheet_name="Test Data Only", index=False)
                
                metadata_only_df = pd.DataFrame(columns=["Metadata", "Value"])
                idx = 0
                for key, value in product_info.items():
                    if value:
                        display_key = key.replace('_', ' ').title()
                        metadata_only_df.loc[idx] = [display_key, value]
                        idx += 1
                
                if not metadata_only_df.empty:
                    metadata_only_df.to_excel(writer, sheet_name="Metadata Only", index=False)
            
            print(f"Created unified Excel file with professional formatting")
            
        except Exception as e:
            print(f"Error creating unified Excel file: {e}")
            traceback.print_exc()
    
    async def get_llm_metadata_async(self, pdf_path: str, existing_metadata: Dict) -> None:
        """
        Extract missing metadata using LLM with high-resolution images
        Runs in parallel, doesn't block main workflow
        
        Args:
            pdf_path: Path to the PDF file
            existing_metadata: Already extracted metadata from traditional methods
        """
        try:
            print(f"🔍 Starting parallel LLM metadata extraction from PDF: {pdf_path}")
            
            # Check for cancellation at the start
            self.check_cancellation()
            
            # Determine missing metadata fields
            missing_keys = []
            for field in self.metadata_fields:
                # Check if field is missing or empty in existing metadata
                field_found = False
                for key, value in existing_metadata.items():
                    if (field.lower() in key.lower() or key.lower() in field.lower()) and value and str(value).strip():
                        field_found = True
                        break
                
                if not field_found:
                    missing_keys.append(field)
            
            # Check for cancellation after analyzing fields
            self.check_cancellation()
            
            if not missing_keys:
                print("   ✅ All metadata fields already extracted, skipping LLM extraction")
                self.metadata_extraction_complete = True
                return
            
            print(f"   🎯 Looking for missing metadata: {missing_keys}")
            
            # Create intelligent prompt for metadata extraction
            prompt_text = f"""
You are analyzing a Certificate of Analysis (CoA) for a chemical/pharmaceutical product.
Extract metadata using STANDARDIZED field names to avoid conflicts with existing data.

EXTRACTION TARGET: {missing_keys}

CRITICAL FIELD STANDARDIZATION:
- Use ONLY these exact field names in your JSON response:
  • "Date Of Manufacture" (not "Manufacturing Date", "DoM", "Mfg Date")
  • "Product Name" (not "Product", "Drug Name")  
  • "Code" (not "Product Code", "Material Number", "Product Number")
  • "Batch Number" (not "Lot Number", "Batch", "Lot")
  • "Manufacturer" (not "Mfg", "Company", "Supplier")
  • "Storage" (for storage conditions)
  • "Material Number" (for internal material codes)
  • "Serial Number" (for serial/tracking numbers)
  • "Expiration Date" (not "Expiry Date", "Exp Date")

INTELLIGENT EXTRACTION RULES:
1. **Manufacturing Dates**: Look for dates near "Manufactured", "DoM", "Mfg Date", "Production Date"
   → Always return as "Date Of Manufacture"

2. **Product Identification**: 
   - Main product name (usually prominent) → "Product Name"  
   - Product codes/part numbers → "Code"
   - Material/internal codes → "Material Number"

3. **Batch/Lot Information**: Look for "Batch", "Lot", "B#", "L#" codes → "Batch Number"

4. **Company Information**: Manufacturer/supplier company → "Manufacturer"

5. **Date Formatting**: Always use mm/dd/yyyy format for dates

6. **Context Intelligence**:
   - Distinguish Manufacturing Date vs Issue Date vs Signature Date
   - Distinguish Batch Number vs Document Number vs Page Number  
   - Prioritize product-related information over document metadata

7. **Value Quality**: Only include values that are clearly identified and meaningful

SMART CONFLICT AVOIDANCE:
- Since you're filling missing metadata, be precise about field naming
- If uncertain about field mapping, prefer the standardized names above
- Don't include fields that might already exist with different names

RESPONSE FORMAT:
Return ONLY a clean JSON object with standardized field names:
{{
  "Date Of Manufacture": "12/01/2019",
  "Code": "0-W01", 
  "Manufacturer": "Gnosis Bioresearch S.r.l.",
  "Storage": "Store at (-20±5)°C"
}}

NO markdown formatting, explanations, or extra text. Just the JSON object.
"""

            # Convert PDF pages to high-resolution images
            message = {
                "role": "user",
                "content": [{"type": "text", "text": prompt_text}]
            }
            
            # Process PDF with high DPI for better accuracy
            pdf_document = fitz.open(pdf_path)
            for page_number in range(min(len(pdf_document), 5)):  # Limit to first 5 pages
                page = pdf_document.load_page(page_number)
                pix = page.get_pixmap(alpha=False, dpi=300)  # High resolution
                img_bytes = pix.pil_tobytes(format="PNG")
                
                # Convert to base64
                image_b64 = base64.b64encode(img_bytes).decode("utf-8")
                message['content'].append({
                    "type": "image",
                    "encoding": "base64",
                    "media_type": "image/png",
                    "data": image_b64
                })
            
            pdf_document.close()
            
            # Send request to LLM
            payload = {
                "messages": [message],
                "max_tokens": 1000,
                "model": self.model
            }
            
            if AIOHTTP_AVAILABLE:
                print(f"   📤 Sending async metadata extraction request to {self.model}")
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.api_url, 
                        json=payload, 
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=120)
                    ) as response:
                        if response.status == 200:
                            response_data = await response.json()
                            
                            # Extract response content
                            if 'choices' in response_data and response_data['choices']:
                                content = response_data['choices'][0]['message']['content']
                            elif 'completion' in response_data:
                                content = response_data['completion']['content']
                            else:
                                content = str(response_data)
                            
                            # Parse JSON response
                            try:
                                # Try to extract JSON from response
                                json_match = re.search(r'\{[\s\S]*\}', content)
                                if json_match:
                                    extracted_metadata = json.loads(json_match.group(0))
                                else:
                                    # Fallback: try to parse entire content as JSON
                                    extracted_metadata = json.loads(content)
                                
                                # Store extracted metadata
                                self.llm_metadata = extracted_metadata
                                print(f"   ✅ LLM extracted {len(extracted_metadata)} metadata fields: {list(extracted_metadata.keys())}")
                                
                            except json.JSONDecodeError as e:
                                print(f"   ⚠️ Failed to parse LLM response as JSON: {e}")
                                print(f"   Raw response: {content[:200]}...")
                                self.llm_metadata = {}
                        
                        else:
                            print(f"   ❌ LLM request failed with status {response.status}")
                            self.llm_metadata = {}
            else:
                # Fallback to synchronous requests if aiohttp is not available
                print(f"   📤 Sending synchronous metadata extraction request to {self.model}")
                response = requests.post(self.api_url, json=payload, headers=self.headers, timeout=120)
                
                if response.status_code == 200:
                    response_data = response.json()
                    
                    # Extract response content
                    if 'choices' in response_data and response_data['choices']:
                        content = response_data['choices'][0]['message']['content']
                    elif 'completion' in response_data:
                        content = response_data['completion']['content']
                    else:
                        content = str(response_data)
                    
                    # Parse JSON response
                    try:
                        # Try to extract JSON from response
                        json_match = re.search(r'\{[\s\S]*\}', content)
                        if json_match:
                            extracted_metadata = json.loads(json_match.group(0))
                        else:
                            # Fallback: try to parse entire content as JSON
                            extracted_metadata = json.loads(content)
                        
                        # Store extracted metadata
                        self.llm_metadata = extracted_metadata
                        print(f"   ✅ LLM extracted {len(extracted_metadata)} metadata fields: {list(extracted_metadata.keys())}")
                        
                    except json.JSONDecodeError as e:
                        print(f"   ⚠️ Failed to parse LLM response as JSON: {e}")
                        print(f"   Raw response: {content[:200]}...")
                        self.llm_metadata = {}
                
                else:
                    print(f"   ❌ LLM request failed with status {response.status_code}")
                    self.llm_metadata = {}
            
        except Exception as e:
            print(f"   ❌ Error in LLM metadata extraction: {str(e)}")
            self.llm_metadata = {}
        
        finally:
            self.metadata_extraction_complete = True
            print("   🏁 Async LLM metadata extraction completed")

    def run_async_in_thread(self, coro):
        """
        Run async coroutine in a separate thread with its own event loop
        """
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(coro)
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_in_thread)
        thread.start()
        return thread

    def merge_metadata(self, original_metadata: Dict, llm_metadata: Dict) -> Dict:
        """
        Intelligently merge original metadata with LLM-extracted metadata using smart deduplication
        
        This function implements:
        1. Field grouping by semantic meaning
        2. Value quality assessment 
        3. Smart replacement of inferior values
        4. Duplicate prevention
        
        Args:
            original_metadata: Metadata from traditional extraction
            llm_metadata: Metadata from LLM extraction
            
        Returns:
            Merged metadata dictionary with no duplicates
        """
        print("   🔄 Starting intelligent metadata merge with deduplication...")
        
        # Define field groups by semantic meaning
        field_groups = {
            'manufacturing_date': [
                'date_of_manufacture', 'Date Of Manufacture', 'manufacturing date', 
                'DoM', 'dom', 'Mfg Date', 'mfg_date', 'Manufacturing Date',
                'Date of Manufacture', 'manufacture_date', 'mfg date'
            ],
            'expiration_date': [
                'expiration_date', 'Expiration Date', 'expiry_date', 'Expiry Date',
                'exp_date', 'Exp Date', 'expiry date', 'expiration date'
            ],
            'batch_number': [
                'batch_number', 'Batch Number', 'lot_number', 'Lot Number',
                'batch', 'Batch', 'lot', 'Lot', 'lot_no', 'batch_no'
            ],
            'product_name': [
                'product_name', 'Product Name', 'product', 'Product',
                'drug_name', 'Drug Name', 'product_title', 'name'
            ],
            'product_code': [
                'code', 'Code', 'product_code', 'Product Code', 'product_number',
                'Product Number', 'material_number', 'Material Number', 'part_number'
            ],
            'manufacturer': [
                'manufacturer', 'Manufacturer', 'mfg', 'Mfg', 'company', 'Company',
                'supplier', 'Supplier', 'vendor', 'Vendor'
            ],
            'storage': [
                'storage', 'Storage', 'storage_conditions', 'Storage Conditions',
                'storage_condition', 'store', 'Store'
            ]
        }
        
        def assess_value_quality(value: str) -> int:
            """
            Assess the quality of a metadata value
            Returns higher scores for better quality values
            """
            if not value or str(value).strip() == '' or str(value).lower() == 'nan':
                return 0
            
            value_str = str(value).strip()
            score = 10  # Base score
            
            # Length bonus (more detailed is usually better)
            score += min(len(value_str) // 5, 10)
            
            # Specificity bonuses
            if re.search(r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}', value_str):  # Date format
                score += 20
            elif re.search(r'\d{4}', value_str):  # Year present
                score += 10
            elif re.search(r'\d{1,2}[\/\-]\d{4}', value_str):  # Month/Year
                score += 15
            
            # Technical detail bonuses
            if '±' in value_str or '°C' in value_str or '°F' in value_str:  # Storage conditions
                score += 15
            if '-' in value_str and len(value_str) > 5:  # Compound codes
                score += 10
            if any(char.isdigit() for char in value_str):  # Contains numbers
                score += 5
            
            # Format penalties
            if value_str.upper() == value_str and len(value_str) > 3:  # ALL CAPS
                score -= 5
            if value_str.lower() in ['unknown', 'n/a', 'na', 'not specified', 'tbd']:
                score -= 20
            
            return score
        
        def find_field_group(field_name: str) -> str:
            """Find which group a field belongs to"""
            field_lower = field_name.lower()
            for group_name, variants in field_groups.items():
                if any(variant.lower() == field_lower for variant in variants):
                    return group_name
            return field_name  # Return original if no group found
        
        def get_best_field_name(group_name: str, available_fields: List[str]) -> str:
            """Get the best field name for a group (prefer standardized names)"""
            if group_name in field_groups:
                # Prefer standardized names (first in list is usually best)
                for preferred in field_groups[group_name][:3]:  # Check first 3 preferred names
                    if preferred in available_fields:
                        return preferred
            return available_fields[0] if available_fields else group_name
        
        # Group all fields by semantic meaning
        field_data = {}  # group_name -> [(field_name, value, quality_score)]
        
        # Process original metadata
        for field_name, value in original_metadata.items():
            if value:
                group = find_field_group(field_name)
                quality = assess_value_quality(value)
                
                if group not in field_data:
                    field_data[group] = []
                field_data[group].append((field_name, value, quality))
        
        # Process LLM metadata
        for field_name, value in llm_metadata.items():
            if value:
                group = find_field_group(field_name)
                quality = assess_value_quality(value)
                
                if group not in field_data:
                    field_data[group] = []
                field_data[group].append((field_name, value, quality))
        
        # Build final merged metadata by selecting best value for each group
        merged = {}
        replacement_count = 0
        addition_count = 0
        
        for group, candidates in field_data.items():
            if not candidates:
                continue
                
            # Sort by quality score (descending)
            candidates.sort(key=lambda x: x[2], reverse=True)
            best_field, best_value, best_quality = candidates[0]
            
            # Use standardized field name if possible
            available_fields = [c[0] for c in candidates]
            final_field_name = get_best_field_name(group, available_fields)
            
            # If we're not using the best quality field name, use the best quality value
            if final_field_name != best_field:
                merged[final_field_name] = best_value
            else:
                merged[best_field] = best_value
            
            # Log the decision
            if len(candidates) > 1:
                print(f"   🔄 Resolved {group} field collision:")
                for field, value, quality in candidates:
                    marker = "✅" if (field == best_field or field == final_field_name) else "❌"
                    print(f"      {marker} {field}: '{value}' (quality: {quality})")
                print(f"      → Kept: {final_field_name} = '{best_value}'")
                replacement_count += 1
            else:
                print(f"   ➕ Added: {final_field_name} = '{best_value}'")
                addition_count += 1
        
        print(f"   ✅ Metadata merge complete: {replacement_count} conflicts resolved, {addition_count} fields added")
        print(f"   📊 Final metadata: {len(merged)} fields (from {len(original_metadata)} + {len(llm_metadata)} original)")
        
        return merged

    def _process_small_chunk(self, chunk_text: str, sheet_name: str, start_row: int, end_row: int, all_test_data: list):
        """Process a small chunk of data safely"""
        try:
            # Create focused prompt for this small chunk
            chunk_prompt = f"""
            Extract test data from this small section of a Certificate of Analysis.
            This is from sheet '{sheet_name}', rows {start_row}-{end_row}.
            
            Data:
            ```
            {chunk_text}
            ```
            
            Instructions:
            1. Extract ONLY valid test parameters with specifications and results
            2. Skip any administrative sections or headers without test data
            3. Preserve hierarchical relationships (Parent - Child format)
            4. Extract units from results (e.g., "99.2 %" → result="99.2", unit="%")
            
            Return ONLY test data as JSON:
            ```json
            {{
                "test_data": [
                    {{
                        "test": "test name",
                        "specification": "spec value",
                        "result": "result value",
                        "unit": "unit or empty"
                    }}
                ]
            }}
            ```
            
            CRITICAL JSON FORMATTING REQUIREMENTS:
            - Return ONLY the JSON object, no explanations or additional text before or after
            - Properly escape any special characters in strings (quotes, backslashes, etc.)
            - Ensure valid JSON syntax even if test names contain special characters
            - Use double quotes for all strings, never single quotes
            - End all objects and arrays with proper comma placement
            - Do not include trailing commas after the last element in arrays or objects
            """
            
            # Use smaller max_tokens for chunks
            chunk_response = self._query_gpt_small(chunk_prompt)
            chunk_data = self.extract_json_from_response(chunk_response)
            
            if chunk_data and 'test_data' in chunk_data:
                tests = chunk_data['test_data']
                print(f"    Found {len(tests)} tests in small chunk")
                all_test_data.extend(tests)
            else:
                print(f"    No tests found in chunk rows {start_row}-{end_row}")
                
        except Exception as e:
            print(f"    Error processing small chunk {start_row}-{end_row}: {e}")

    def _query_gpt_small(self, prompt: str) -> Dict:
        """Query GPT with optimized tokens for chunked requests"""
        
        # Optimized payload for chunks - no thinking mode needed for simple extraction
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 16000,  # Increased from 4000 for better chunk coverage
            "thinking_budget": 512,  # Even smaller thinking budget for chunks
            "model": self.model
        }
        
        try:
            print(f"    Sending optimized chunk request...")
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=120  # Shorter timeout for small requests
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"    Optimized chunk request failed: {e}")
            return {"error": str(e)}

    def process_excel_without_saving(self, excel_path: str) -> Tuple[pd.DataFrame, Dict]:
        """
        Process Excel file without saving intermediate files (CSV, JSON)
        Only returns the DataFrame and product_info
        """
        print(f"Step 1: Extracting text from Excel: {excel_path}")
        excel_text = self.extract_text_from_excel(excel_path)
        if not excel_text:
            print("Failed to extract text from Excel.")
            return pd.DataFrame(), {}
        print(f"Extracted {len(excel_text)} characters.")

        print("Step 2: Creating prompt for LLM.")
        prompt = self.create_prompt(excel_text)

        print("Step 3: Querying LLM API.")
        response = self.query_gpt(prompt)

        print("Step 4: Extracting JSON from LLM response.")
        extracted_data = self.extract_json_from_response(response)
        if not extracted_data:
            print("Failed to extract valid JSON data from LLM response.")
            return pd.DataFrame(), {}

        print("Step 5: Creating DataFrame from extracted data.")
        df, product_info = self.create_dataframe(extracted_data)
        print(f"DataFrame created with {len(df)} rows.")
        
        # Skip auto-saving - just return the data
        return df, product_info

    def _dataframe_to_text(self, df: pd.DataFrame) -> str:
        """Convert DataFrame to text format for prompt"""
        text_lines = []
        for _, row in df.iterrows():
            # Filter out empty cells
            non_empty = [str(cell) for cell in row if str(cell).strip()]
            if non_empty:
                text_lines.append(" | ".join(non_empty))
        return "\n".join(text_lines)

    def process_excel_with_llm_metadata(self, excel_path: str, pdf_path: str = None) -> Tuple[pd.DataFrame, Dict]:
        """
        Process Excel file with parallel LLM metadata extraction
        
        Args:
            excel_path: Path to the Excel file
            pdf_path: Path to the original PDF file for LLM metadata extraction
            
        Returns:
            Tuple of (DataFrame, enhanced_product_info)
        """
        print(f"Processing Excel with LLM metadata: {excel_path}")
        
        # Check for cancellation at the start
        self.check_cancellation()
        self.update_progress(41, "Starting GPT analysis...")
        
        # Start LLM metadata extraction in parallel if PDF is provided
        llm_thread = None
        if pdf_path and os.path.exists(pdf_path):
            # Check for cancellation before starting LLM
            self.check_cancellation()
            self.update_progress(42, "Extracting metadata with GPT-4...")
            
            if AIOHTTP_AVAILABLE:
                print("Starting parallel async LLM metadata extraction...")
                coro = self.get_llm_metadata_async(pdf_path, {})
                llm_thread = self.run_async_in_thread(coro)
            else:
                print("Starting parallel LLM metadata extraction (sync fallback)...")
                def run_sync_extraction():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(self.get_llm_metadata_async(pdf_path, {}))
                    finally:
                        loop.close()
                
                llm_thread = threading.Thread(target=run_sync_extraction)
                llm_thread.start()
        
        # Just use process_excel which already has all the intelligent routing logic!
        df, product_info = self.process_excel(excel_path)
        
        # Check for cancellation before waiting for LLM
        self.check_cancellation()
        
        # Wait for LLM metadata and merge if available
        if llm_thread:
            print("Waiting for async LLM metadata extraction to complete...")
            llm_thread.join(timeout=60)
            
            # Check for cancellation after LLM completes
            self.check_cancellation()
            
            if self.metadata_extraction_complete:
                print("Merging LLM-extracted metadata...")
                enhanced_product_info = self.merge_metadata(product_info, self.llm_metadata)
                print(f"Enhanced metadata: {len(enhanced_product_info)} fields")
                return df, enhanced_product_info
            else:
                print("Async LLM metadata extraction timed out, using original metadata")
        
        return df, product_info

def main():
    parser = argparse.ArgumentParser(description='Extract CoA data from Excel using GPT-based LLM API with batch processing')
    parser.add_argument('excel_path', help='Path to the Excel file')
    parser.add_argument('--api-key', help='LLM API key (or set LLM_API_KEY env var)')
    parser.add_argument('--api-url', help='LLM API endpoint URL (or set LLM_API_URL env var)')
    parser.add_argument('--output-dir', default='', help='Output directory (default: same as Excel file)')
    parser.add_argument('--model', default=None, help='Specific LLM model name to use')

    args = parser.parse_args()

    # Get API credentials
    api_key = REDACTED
    api_url = args.api_url or os.environ.get('LLM_API_URL')

    if not api_key or not api_url:
        print("API Key/URL not found. Trying to load from env.py...")
        try:
            current_env = os.getenv('COA_APP_ENV', 'local') 
            print(f"Using environment config: '{current_env}'")

            from env import env_vars
            
            env_config = env_vars.get(current_env)
            if env_config:
                if not api_key:
                    api_key = REDACTED
                    print("Loaded API Key from env.py")
                if not api_url:
                    api_url = env_config.get('llm_url')
                    print("Loaded API URL from env.py")
            else:
                print(f"Warning: Environment '{current_env}' not found in env.py.")

        except ImportError:
            print("Warning: Could not import env.py.")
        except Exception as e:
            print(f"Warning: Error loading config from env.py: {e}")

    if not api_key:
        print("Error: LLM API key not provided or found.")
        return
    if not api_url:
        print("Error: LLM API URL not provided or found.")
        return

    try:
        print(f"Initializing GPTCoAExtractor with API URL: {api_url}")
        extractor = GPTCoAExtractor(api_key=api_key, api_url=api_url, model=args.model)

        print(f"Processing Excel file: {args.excel_path}")
        start_time = time.time()
        df, product_info = extractor.process_excel(args.excel_path)
        end_time = time.time()
        print(f"\n⏱️ Processing finished in {end_time - start_time:.2f} seconds.")

        if not df.empty or product_info: 
            print("\n📋 Extracted Product Info:")
            print(json.dumps(product_info, indent=2))
            print("\n📊 Extracted Test Data Sample:")
            print(df.head())
            print(f"\n✅ Total test data rows: {len(df)}")
        else:
            print("❌ No data extracted from Excel or extraction failed.")

    except ValueError as ve:
        print(f"Configuration Error: {ve}")
    except Exception as e:
        print(f"An unexpected error occurred during processing: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()