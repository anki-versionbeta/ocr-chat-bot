import os
import json
import fitz  # PyMuPDF
import base64
import requests
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import re
import traceback
import time
from typing import Dict, List, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# API Configuration
LLM_URL = "https://api-epic.ir-gateway.abbvienet.com/iliad/api/v1/chat/claude-3.5-sonnet" 
VALIDATION_LLM_URL = "https://api-epic.ir-gateway.abbvienet.com/iliad/api/v1/chat/claude-3.7-sonnet"  # or gpt-4o
LLM_API_KEY = REDACTED

# Global variable to store current PDF path during processing
_current_pdf_path = None

def set_current_pdf_path(pdf_path: str):
    """Set the current PDF path for optimization functions"""
    global _current_pdf_path
    _current_pdf_path = pdf_path

def get_current_pdf_path() -> str:
    """Get the current PDF path"""
    global _current_pdf_path
    return _current_pdf_path

def extract_standard_product_metadata(excel_path: str) -> dict:
    """
    Extract product metadata from the unified Excel file with generic field normalization
    
    Args:
        excel_path: Path to the unified Excel file
        
    Returns:
        Dictionary containing normalized product metadata
    """
    try:
        # Try to extract product info from the Certificate of Analysis sheet
        main_df = pd.read_excel(excel_path, sheet_name='Certificate of Analysis', header=None)
        product_info = {}
        
        # Standard field mappings for normalization
        field_normalizations = {
            # Product name variations
            'product_name': 'Product Name',
            'productname': 'Product Name',
            'product': 'Product Name',
            'name': 'Product Name',
            'drug_name': 'Product Name',
            'drug name': 'Product Name',
            
            # Code/Material variations
            'code': 'Code',
            'product_code': 'Code',
            'product code': 'Code',
            'material_number': 'Material Number',
            'material number': 'Material Number',
            'product_number': 'Product Number',
            'product number': 'Product Number',
            
            # Batch/Lot variations
            'batch_number': 'Batch Number',
            'batch number': 'Batch Number',
            'batch': 'Batch Number',
            'lot_number': 'Lot Number',
            'lot number': 'Lot Number',
            'lot': 'Lot Number',
            
            # Date variations
            'date_of_manufacture': 'Date of Manufacture',
            'date of manufacture': 'Date of Manufacture',
            'manufacturing_date': 'Date of Manufacture',
            'manufacturing date': 'Date of Manufacture',
            'dom': 'Date of Manufacture',
            'mfg_date': 'Date of Manufacture',
            'mfg date': 'Date of Manufacture',
            'manufacture_date': 'Date of Manufacture',
            'manufacture date': 'Date of Manufacture',
            
            # Expiration variations
            'expiration_date': 'Expiration Date',
            'expiration date': 'Expiration Date',
            'expiry_date': 'Expiration Date',
            'expiry date': 'Expiration Date',
            'exp_date': 'Expiration Date',
            'exp date': 'Expiration Date',
            
            # Other common fields
            'manufacturer': 'Manufacturer',
            'mfg': 'Manufacturer',
            'company': 'Manufacturer',
            'storage': 'Storage',
            'storage_conditions': 'Storage',
            'storage conditions': 'Storage',
            'packaging_site': 'Packaging Site',
            'packaging site': 'Packaging Site',
            'fill_date': 'Fill Date',
            'fill date': 'Fill Date',
            'serial_number': 'Serial Number',
            'serial number': 'Serial Number'
        }
        
        # Extract all metadata from the first 15 rows (more flexible)
        for i in range(min(15, len(main_df))):
            if len(main_df.iloc[i]) >= 2:
                key = str(main_df.iloc[i, 0]).strip()
                value = str(main_df.iloc[i, 1]).strip()
                
                # Skip empty or nan values
                if not key or not value or key == 'nan' or value == 'nan':
                    continue
                
                # Skip if it's the title row
                if key.lower() == 'certificate of analysis':
                    continue
                
                # Normalize the key
                key_lower = key.lower()
                normalized_key = field_normalizations.get(key_lower, key)
                
                # If not in our normalization dict, try to make it presentable
                if normalized_key == key and '_' in key:
                    # Convert snake_case to Title Case
                    normalized_key = ' '.join(word.capitalize() for word in key.split('_'))
                elif normalized_key == key and key.islower():
                    # Capitalize single words
                    normalized_key = key.capitalize()
                
                # Store the metadata
                product_info[normalized_key] = value
        
        return product_info
        
    except Exception as e:
        print(f"   ⚠️ Could not extract product info from Excel: {e}")
        return {}

def normalize_product_metadata(product_info: dict) -> dict:
    """
    Normalize product metadata field names to standard format
    This function can be used to normalize metadata from any source (GPT, Excel, etc.)
    
    Args:
        product_info: Dictionary with product metadata (any field names)
        
    Returns:
        Dictionary with normalized field names
    """
    # Standard field mappings for normalization
    field_normalizations = {
        # Product name variations
        'product_name': 'Product Name',
        'productname': 'Product Name',
        'product': 'Product Name',
        'name': 'Product Name',
        'drug_name': 'Product Name',
        'drug name': 'Product Name',
        
        # Code/Material variations
        'code': 'Code',
        'product_code': 'Code',
        'product code': 'Code',
        'material_number': 'Material Number',
        'material number': 'Material Number',
        'product_number': 'Product Number',
        'product number': 'Product Number',
        
        # Batch/Lot variations
        'batch_number': 'Batch Number',
        'batch number': 'Batch Number',
        'batch': 'Batch Number',
        'lot_number': 'Lot Number',
        'lot number': 'Lot Number',
        'lot': 'Lot Number',
        
        # Date variations
        'date_of_manufacture': 'Date of Manufacture',
        'date of manufacture': 'Date of Manufacture',
        'manufacturing_date': 'Date of Manufacture',
        'manufacturing date': 'Date of Manufacture',
        'dom': 'Date of Manufacture',
        'mfg_date': 'Date of Manufacture',
        'mfg date': 'Date of Manufacture',
        'manufacture_date': 'Date of Manufacture',
        'manufacture date': 'Date of Manufacture',
        
        # Expiration variations
        'expiration_date': 'Expiration Date',
        'expiration date': 'Expiration Date',
        'expiry_date': 'Expiration Date',
        'expiry date': 'Expiration Date',
        'exp_date': 'Expiration Date',
        'exp date': 'Expiration Date',
        
        # Other common fields
        'manufacturer': 'Manufacturer',
        'mfg': 'Manufacturer',
        'company': 'Manufacturer',
        'storage': 'Storage',
        'storage_conditions': 'Storage',
        'storage conditions': 'Storage',
        'packaging_site': 'Packaging Site',
        'packaging site': 'Packaging Site',
        'fill_date': 'Fill Date',
        'fill date': 'Fill Date',
        'serial_number': 'Serial Number',
        'serial number': 'Serial Number'
    }
    
    normalized_info = {}
    
    for key, value in product_info.items():
        # Skip empty or nan values
        if not value or str(value).strip() == '' or str(value).lower() == 'nan':
            continue
            
        # Normalize the key
        key_lower = key.lower()
        normalized_key = field_normalizations.get(key_lower, key)
        
        # If not in our normalization dict, try to make it presentable
        if normalized_key == key and '_' in key:
            # Convert snake_case to Title Case
            normalized_key = ' '.join(word.capitalize() for word in key.split('_'))
        elif normalized_key == key and key.islower():
            # Capitalize single words
            normalized_key = key.capitalize()
        
        # Store the normalized metadata
        normalized_info[normalized_key] = value
    
    return normalized_info

def extract_page_as_image(pdf_path: str, page_num: int) -> str:
    """Convert a PDF page to base64 image"""
    pdf = fitz.open(pdf_path)
    page = pdf[page_num - 1]
    pix = page.get_pixmap(alpha=False, dpi=300)
    img_bytes = pix.pil_tobytes(format="PNG")
    pdf.close()
    return base64.b64encode(img_bytes).decode("utf-8")

def detect_content_uniformity_data(test_names: List[str], page_text: str = "") -> bool:
    """
    Detect if the data contains content uniformity tests
    Updated to catch UNIFORMITY OF DOSAGE UNITS patterns
    """
    content_uniformity_indicators = [
        # Primary patterns
        "UNIFORMITY OF DOSAGE UNITS - ETHINYL ESTRADIOL - Content of 10 tablets",
        "IN-PROCESS CONTENT UNIFORMITY",
        "CONTENT UNIFORMITY",
        "UNIFORMITY OF DOSAGE",
        
        # Specific test patterns
        "Content of 10 tablets",
        "Content of 30 tablets",
        
        # Stage patterns
        "Stage 1, Stage 2",
        "stage 1, stage 2",
        
        # Summary statistics patterns that appear in uniformity tests
        "Avg. (all samples, wt. correct)",
        "RSD (all samples, wt. correct)",
        "Min. (all samples, as is)",
        "Max. (all samples, as is)",
        
        # Drug names commonly in uniformity tests
        "ETHINYL ESTRADIOL",
        "NORETHINDRONE ACETATE",
        "DP-43",
        
        # Common summary indicators in uniformity tests
        "Average", "SD", "RSD", "AV", "Min", "Max"
    ]
    
    # Count how many indicators we find
    indicator_count = 0
    uniformity_tests_found = []
    
    # Check in test names
    for test in test_names:
        test_lower = test.lower()
        
        # Direct check for UNIFORMITY patterns
        if "uniformity" in test_lower and ("dosage" in test_lower or "content" in test_lower):
            uniformity_tests_found.append(test)
            indicator_count += 3  # Strong indicator
            
        # Check for other indicators
        for indicator in content_uniformity_indicators:
            if indicator.lower() in test_lower:
                indicator_count += 1
                
                # Special case: if we find drug name + statistics combo
                if ("ethinyl estradiol" in test_lower or "norethindrone" in test_lower) and \
                   any(stat in test_lower for stat in ["average", "sd", "rsd", "av", "min", "max"]):
                    indicator_count += 2  # Extra weight for this combo
    
    # If we found direct uniformity tests, that's definitive
    if uniformity_tests_found:
        print(f"   🎯 Detected {len(uniformity_tests_found)} UNIFORMITY tests")
        print(f"      Examples: {uniformity_tests_found[:3]}")
        return True
    
    # Otherwise, check if we have enough indicators
    if indicator_count >= 5:
        print(f"   🎯 Detected content uniformity data (found {indicator_count} indicators)")
        return True
    
    # Check in page text if provided
    if page_text:
        page_text_lower = page_text.lower()
        page_indicators = 0
        
        for indicator in content_uniformity_indicators:
            if indicator.lower() in page_text_lower:
                page_indicators += 1
        
        if page_indicators >= 3:
            print(f"   🎯 Detected content uniformity data in page text (found {page_indicators} indicators)")
            return True
    
    return False

def find_pages_with_tests(pdf_path: str, folder_path: str, excel_path: str) -> Tuple[list, bool]:
    """
    Find pages that have both 'Test' header AND actual test parameter names
    Also detects if this is content uniformity data
    
    Returns:
        Tuple of (valid_pages, is_content_uniformity)
    """
    
    try:
        # Find the blocks JSON file in the folder
        original_filename = os.path.splitext(os.path.basename(pdf_path))[0]
        json_path = os.path.join(folder_path, f"{original_filename}_blocks.json")
        
        if not os.path.exists(json_path):
            print(f"   ⚠️ Blocks JSON file not found: {json_path}")
            return [], False
        
        print(f"   Finding pages with 'Test' header AND test parameters AND specifications...")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        df = pd.read_excel(excel_path, sheet_name='Test Data Only')
        test_names = df['test'].tolist()
        
        # ========== KEY ADDITION: GET SPECIFICATIONS ==========
        specifications = df['specification'].tolist() if 'specification' in df.columns else []
        
        # Extract key specification patterns (numbers, ranges, limits)
        spec_patterns = []
        for spec in specifications:
            if pd.notna(spec) and spec:
                spec_str = str(spec)
                
                # Extract numeric patterns from specifications
                # These are VERY unlikely to appear in non-test pages
                
                # Pattern 1: Ranges like "4.50-5.50" or "98.0 - 102.0"
                ranges = re.findall(r'\d+\.?\d*\s*[-–]\s*\d+\.?\d*', spec_str)
                spec_patterns.extend(ranges)
                
                # Pattern 2: Limits like "≤ 100", "< 0.5", ">= 98.0"
                limits = re.findall(r'[≤≥<>]\s*\d+\.?\d*', spec_str)
                spec_patterns.extend(limits)
                
                # Pattern 3: Percentages like "99.0%", "0.1%"
                percentages = re.findall(r'\d+\.?\d*\s*%', spec_str)
                spec_patterns.extend(percentages)
                
                # Pattern 4: Units like "cfu/g", "EU/mg", "mg/mL"
                units = re.findall(r'\d+\.?\d*\s*(?:cfu/g|EU/mg|mg/mL|mg/ml)', spec_str)
                spec_patterns.extend(units)
        
        # Remove duplicates and keep unique patterns
        spec_patterns = list(set(spec_patterns))
        print(f"   Found {len(spec_patterns)} unique specification patterns to match")
        if spec_patterns:
            print(f"   Sample patterns: {spec_patterns[:5]}...")
        
        print(f"   Looking for: 'Test'/'Specification' header + any of {len(test_names)} test parameters + specifications")
        
        # Check if this is content uniformity data BASED ON THE ACTUAL TESTS FOUND
        # USE THE PROPER DETECTION FUNCTION INSTEAD OF HARDCODED LIST
        is_content_uniformity = detect_content_uniformity_data(test_names)
        # Define comprehensive test header patterns
        test_header_patterns = [
            r'^test$',                          # Exact: "Test"
            r'^tests$',                         # Exact: "Tests"
            r'^test\s+',                        # "Test " followed by space
            r'^tests\s+',                       # "Tests " followed by space
            r'^test:',                          # "Test:"
            r'^tests:',                         # "Tests:"
            r'^test\s*description',             # "Test Description"
            r'^test\s*parameter',               # "Test Parameter"
            r'^test\s*condition',               # "Test Condition"
            r'^test\s*method',                  # "Test Method"
            r'^test\s*result',                  # "Test Result"
            r'^testing',                        # "Testing..."
            r'^test\s*name',                    # "Test Name"
            r'^laboratory\s*test',              # "Laboratory Test"
            r'^lab\s*test',                     # "Lab Test"
            r'^diagnostic\s*test',              # "Diagnostic Test"
            r'^clinical\s*test',                # "Clinical Test"
            r'^test\s*\/',                      # "Test /"
            r'^test\s*\|',                      # "Test |"
            r'^test\s*\t',                      # "Test" with tab
            r'^\d+\.\s*test',                   # "1. Test"
            r'^test\s*\d+',                     # "Test 1"
            r'^test:',                          # "Test:"
            # ADD SPECIFICATION HEADER PATTERNS
            r'^specification$',                 # Exact: "Specification"
            r'^specifications$',                # Exact: "Specifications"
            r'^specification\s+',               # "Specification " followed by space
            r'^specifications\s+',              # "Specifications " followed by space
            r'^specification:',                 # "Specification:"
            r'^specifications:',                # "Specifications:"
            r'^test\s*specification',           # "Test Specification"
            r'^test\s*specifications',          # "Test Specifications"
        ]
        
        # Compile patterns for efficiency
        compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in test_header_patterns]
        
        # Words that might indicate false positives (not actual test headers)
        false_positive_indicators = [
            'contest', 'protest', 'latest', 'fastest', 'testing the', 'test the',
            'attest', 'detest', 'retest', 'pretest', 'posttest'
        ]
        
        # Find pages that have both Test header AND test parameters
        valid_pages = []
        
        # Get all pages that exist in JSON
        all_pages = set()
        for item in json_data:
            if isinstance(item, dict) and 'Blocks' in item:
                blocks = item['Blocks']
                for block in blocks:
                    if isinstance(block, dict) and 'Page' in block:
                        all_pages.add(block['Page'])
        
        for page_num in sorted(all_pages):
            print(f"   Checking page {page_num}...")
            
            # Get all text blocks from this page
            page_text_blocks = []
            has_test_header = False
            header_found = None
            
            for item in json_data:
                if isinstance(item, dict) and 'Blocks' in item:
                    blocks = item['Blocks']
                    for block in blocks:
                        if (isinstance(block, dict) and 'Text' in block and 
                            'Page' in block and block['Page'] == page_num):
                            text_content = block['Text'].strip()
                            page_text_blocks.append(text_content)
                            
                            # Skip if it's a false positive
                            text_lower = text_content.lower()
                            is_false_positive = any(fp in text_lower for fp in false_positive_indicators)
                            
                            if not is_false_positive:
                                # Check against all patterns
                                for pattern in compiled_patterns:
                                    if pattern.search(text_content):
                                        has_test_header = True
                                        header_found = text_content
                                        print(f"     ✓ Found Test/Specification header: '{text_content}'")
                                        break
            
            if not has_test_header:
                print(f"     ✗ No 'Test'/'Specification' header found on page {page_num}")
                continue
            
            # Now check if this page also contains actual test parameters
            page_text = ' '.join(page_text_blocks).lower()
            tests_found = 0
            found_tests = []
            
            # Enhanced test parameter matching
            for test_name in test_names:
                clean_test = test_name.strip()
                
                if not clean_test:  # Skip empty test names
                    continue
                
                # Try multiple matching strategies
                match_found = False
                
                # 1. Exact match (case-insensitive)
                if clean_test.lower() in page_text:
                    match_found = True
                
                # 2. Remove parentheses and try again
                if not match_found:
                    clean_no_parens = re.sub(r'\([^)]*\)', '', clean_test).strip()
                    if clean_no_parens and clean_no_parens.lower() in page_text:
                        match_found = True
                
                # 3. Try main part after " - "
                if not match_found and " - " in clean_test:
                    main_part = clean_test.split(" - ")[-1].strip()
                    main_no_parens = re.sub(r'\([^)]*\)', '', main_part).strip()
                    if main_no_parens and main_no_parens.lower() in page_text:
                        match_found = True
                
                # 4. Try with word boundaries (to avoid partial matches)
                if not match_found:
                    # Create pattern for word boundary matching
                    test_pattern = r'\b' + re.escape(clean_test.lower()) + r'\b'
                    if re.search(test_pattern, page_text):
                        match_found = True
                
                if match_found:
                    tests_found += 1
                    found_tests.append(clean_test)
            
            # ========== NEW: COUNT SPECIFICATIONS (KEY ADDITION) ==========
            specs_found = 0
            found_specs = []
            
            # Combine page text for specification matching (use original case)
            page_text_original = ' '.join(page_text_blocks)
            
            for spec_pattern in spec_patterns:
                # Check if this specification pattern appears on the page
                # Use exact match for numeric patterns (they're unlikely to be random)
                if spec_pattern in page_text_original:
                    specs_found += 1
                    found_specs.append(spec_pattern)
                    if specs_found >= 10:  # Stop after finding enough
                        break
            
            print(f"     Found {tests_found} test parameters, {specs_found} specifications")
            
            if found_tests:
                print(f"     Test examples: {found_tests[:3]}")
            if found_specs:
                print(f"     Spec examples: {found_specs[:3]}")
            
            # ========== IMPROVED DECISION LOGIC ==========
            # A pharmaceutical test page should have:
            # 1. Test header (already checked)
            # 2. At least 1 test parameter
            # 3. At least 2 specifications (strong indicator of real test data)
            
            # Torque Test pages won't have specifications like "4.50-5.50%" or "≤ 100 cfu/g"
            
            if has_test_header and tests_found >= 1 and specs_found >= 2:
                valid_pages.append(page_num)
                print(f"     ✅ PAGE {page_num} SELECTED! (Tests: {tests_found}, Specs: {specs_found})")
            else:
                reasons = []
                if tests_found < 1:
                    reasons.append("insufficient tests")
                if specs_found < 2:
                    reasons.append("no pharmaceutical specifications")
                print(f"     ✗ Page {page_num} rejected ({', '.join(reasons)})")
        
        # Additional validation: Check for consecutive pages
        # Sometimes test results span multiple pages
        if valid_pages:
            # Check if we should include pages immediately after valid test pages
            extended_pages = set(valid_pages)
            for page in valid_pages:
                # Check if next page has test parameters (even without header)
                next_page = page + 1
                if next_page in all_pages and next_page not in extended_pages:
                    # Check for test parameters on next page
                    page_text_blocks = []
                    for item in json_data:
                        if isinstance(item, dict) and 'Blocks' in item:
                            blocks = item['Blocks']
                            for block in blocks:
                                if (isinstance(block, dict) and 'Text' in block and 
                                    'Page' in block and block['Page'] == next_page):
                                    page_text_blocks.append(block['Text'].strip())
                    
                    next_page_text = ' '.join(page_text_blocks).lower()
                    tests_on_next = sum(1 for test in test_names 
                                      if test.strip() and test.strip().lower() in next_page_text)
                    
                    if tests_on_next >= 3:  # If continuation page has multiple tests
                        extended_pages.add(next_page)
                        print(f"     ➕ Added continuation page {next_page} ({tests_on_next} tests found)")
            
            valid_pages = sorted(list(extended_pages))
        
        # Final determination about content uniformity
        if False:
            print(f"   📦 Content uniformity data detected")
            print(f"   🎯 Recommendation: Use batch processing for optimal extraction")
        
        # ========== FINAL SUMMARY ==========
        print(f"\n   📊 Results:")
        print(f"   - Valid pharmaceutical test pages: {valid_pages}")
        print(f"   - Rejected non-pharmaceutical pages by lack of specifications")
        print(f"   - Used specification patterns to filter out packaging/torque tests")
        
        return valid_pages, is_content_uniformity
        
    except Exception as e:
        print(f"   Error finding test pages: {e}")
        import traceback
        traceback.print_exc()
        return [], False

def ask_specific_question(page_image_b64: str, question: str, is_large_data: bool = False, llm_url: str = None) -> str:
    """Ask a very specific question about the image"""
    
    if page_image_b64:  # If image is provided
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": question
                    },
                    {
                        "type": "image",
                        "encoding": "base64",
                        "media_type": "image/png",
                        "data": page_image_b64
                    }
                ]
            }
        ]
    else:  # Text-only question
        messages = [
            {
                "role": "user",
                "content": question
            }
        ]
    
    headers = {"X-API-Key": LLM_API_KEY}
    
    # Choose the appropriate URL - use provided llm_url or default to standard LLM_URL
    api_url = llm_url if llm_url else LLM_URL
    model_name = "claude-3.5-sonnet" if llm_url == VALIDATION_LLM_URL else "claude-3.5-sonnet"
    
    # Adjust token limits based on data size
    if is_large_data:
        payload = {
            "messages": messages,
            "max_tokens": 64000,
            "temperature": 0.15,
            #"thinking_budget": 2048,  # More thinking for complex merging
        }
        print(f"        🧠 Using {model_name} for validation with extended token limit")
    else:
        payload = {
            "messages": messages,
            "temperature": 0.17  # Add temperature for simple extraction (0.1 = more focused, 0.7 = more creative)
        }
        if llm_url == VALIDATION_LLM_URL:
            print(f"        🧠 Using {model_name} for validation")
        else:
            print(f"        🧠 Using {model_name} for standard extraction with temperature 0.7")
    
    # Add this debug code right before the requests.post line:
    try:
        # Debug the request size and structure
        request_size = len(json.dumps(payload))
        print(f"        📊 Request size: {request_size:,} characters")
        #print(f"        📋 Payload structure: messages={len(payload['messages'])}, max_tokens={payload.get('max_tokens','default')}")
        
        if request_size > 50000:  # If larger than 50KB
            print(f"        ⚠️ Large request detected - might cause 400 error")
        
        response = requests.post(api_url, json=payload, headers=headers, timeout=120)
    except Exception as e:
        print(f"        ❌ Error sending request: {e}")
        return "Error"
    
    if response.status_code == 200:
        data = response.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content']
        elif 'completion' in data:
            return data['completion']['content']
    elif response.status_code == 500:
        print(f"   ⚠️ 500 Server Error - request too large, trying chunked approach...")
        return "REQUEST_TOO_LARGE"
    
    return "Error"

def get_simple_extraction_prompt(page_num: int) -> str:
    """Get a simple, focused extraction prompt without original data comparison"""
    
    return f"""Extract ALL test data from page {page_num} of this pharmaceutical Certificate of Analysis.
    This is a GxP-regulated pharmaceutical CoA - every test parameter and its hierarchy is critical for regulatory compliance.

    **CORE PRINCIPLE**: Every test has three components:
    1. **TEST** = What parameter did we measure?
    2. **SPECIFICATION** = What should it be? (the acceptance criteria)
    3. **RESULT** = What did we actually find?
   **TABLE STRUCTURE RULE**:
    Borders define relationships:
    - Rows with borders BETWEEN them = STANDALONE tests
    - Multiple rows WITHIN same bordered section = Check for parent-child
    - First row in section with just test name = PARENT
    - Following rows in same section = CHILDREN
    - Single row with borders around it = STANDALONE
    Example:
        Total impurities (specified and unspecified, not including chiral impurity PCI-32769) -- STANDALONE not parent

    **HOW TO IDENTIFY EACH:**

    TEST (What we measured):
    - The parameter name: pH, Assay, Dissolution, Defects, etc.
    - The thing being tested: "Critical defects", "Bending Stiffness", "Endotoxins"

    SPECIFICATION (What it should be):
    - Any acceptance criteria, limits, or requirements
    - Words like: "should be", "must be", "limit", "max", "min", "not more than", "not less than"
    - ALL criteria that define pass/fail (AQL values, sample sizes, acceptance numbers)
    - If multiple criteria exist, combine them ALL
    RESULT (What we found):
    - The actual measurement, count, or observation
    - Words like: "found", "observed", "measured", "detected", "actual"
    - The data from THIS specific batch/lot
    - Usually the LAST numeric value in a row

    **VALIDATION CHECK - Am I extracting real test data?**
    Before extracting ANY row, ask yourself:
    - Does this look like other pharmaceutical tests on this page?
    - Is this in the same format/structure as confirmed test data?
    - Would a pharmaceutical scientist care about this for drug quality?
    - Is this measuring something ABOUT THE DRUG itself?

    If you see a pattern like:
    Test Name | Specification/Limit | Result/Value → IT'S A TEST
    Description text without values → NOT A TEST
    Administrative info → NOT A TEST

    PHARMACEUTICAL TEST vs PACKAGING DATA:
    - PHARMACEUTICAL TESTS = Tests on the drug/medicine itself (Assay, pH, Dissolution, Impurities)
    - PACKAGING DATA = Information about the box/carton (colors, dimensions)
    - ONLY EXTRACT PHARMACEUTICAL TESTS
    - Skip ALL packaging specifications like "Frontside colours"
    - If it's about the container/box/carton = NOT A TEST
    - If it's about the medicine/drug = IT'S A TEST
    - This document may contain both - only extract drug quality tests
    **MANUFACTURING PROCESS vs DRUG QUALITY:**
    - SKIP: Equipment parameters (Turbine Speed, Sweep Speed, RPM, Hz settings) → How it's made, NOT what it is
    - SKIP: Process metrics (Batch Yield, Process Yield) → Production efficiency, NOT drug quality
    - EXTRACT: Chemical content (Titanium Dioxide %, Zinc Oxide %, API %) → What's IN the drug
    - Simple rule: If it could be measured WITHOUT the drug present → NOT A TEST
    THINK LIKE A HUMAN READING THE DOCUMENT:
    - If you see a table with multiple descriptive columns, combine them intelligently into the test name
    - Each row with different descriptive information represents a different test protocol
    - dont extract complaince statements always check for the actual test chemical data for the product as gxp data
    - Compliance statements are NOT test data
    - If it's explaining (compliance, manufacturing, approvals) = NOT A TEST

    CONTEXT CHECK: Look at surrounding rows - if you see "Assay", "Impurities", "pH" nearby, you're in the test section. If you see "Carton", "Label", "Signature" nearby, you're NOT in the test section.

    INTELLIGENT HIERARCHY DETECTION FOR PHARMACEUTICAL DATA:
    **GXP HIERARCHY RULE**: In pharmaceutical CoAs, test groupings (Identification, Purity, Microbiology) are regulatory requirements - preserve all parent-child relationships exactly as shown.

    1. **VISUAL HIERARCHY RECOGNITION**:

    **CRITICAL SLASH (/) HANDLING IN PARENT HEADERS**:
    - When you see a line with "/" and EMPTY specification/result columns → This is a PARENT header
    - The "/" is PART OF THE NAME, not a separator - keep the ENTIRE line as the parent name
    - Example: "Identification of Deoxycholic Acid by HPLC-CAD/Deoxycholic Acid Assay" is ONE parent
    - If next lines contain parts of text before/after the "/" → They are CHILDREN of this parent
    - Pattern: If "ABC/XYZ" has no values, and next lines are "ABC" and "XYZ" with values → Parent-child relationship
    - NEVER split the parent name at "/" - always keep it complete
    - Section headers (bold, larger font, or separated): These are PARENTS
    - Tests listed under sections: These are CHILDREN of that section
    - Indented or grouped tests: Part of the parent section above them
    - Tests after a section header remain children until a new section appears

    2. **PHARMACEUTICAL SECTION PATTERNS**:
    Common parent sections in pharmaceutical CoAs:
    - Appearance/Description sections
    - General Tests/Physical Tests
    - Identity/Identification
    - Purity/Impurities/Related Substances
    - Potency/Assay
    - Microbiological Tests/Microbiology
    - Additional Tests/Specific Tests
    - Country-specific sections (e.g., "Health Canada Reporting Only")
    - Endotoxins (often with multiple test conditions)

    3. **HIERARCHY RULES**:
    - If a test appears UNDER a section header → It's a CHILD of that section
    - If a test has NO section above it → It's STANDALONE
    - Section headers with empty specs/results → PARENT type
    - Tests with actual data under sections → CHILD type
    - Format children as: "Parent Section - Test Name"

    4. **COMPLEX TABLE HANDLING (IMPORTANT)**:
    For tables with multiple descriptive columns that define test conditions:
    - Example: Endotoxins table with "Number of cycles" and "Number of vials to analyze"
    - Combine ALL descriptive columns into the test name
    - Format: "Parent - [Column1 value], [Column2 value]"
    - Real example: "Endotoxins - 1 cycle, 3 vials"
    - If a cell contains complex text like "2 from the first cycle and 1 from the second", include it fully
    - Each row becomes a separate child test with the combined description

    11. **MULTI-LINE CELL SPLITTING**:
    When a single cell contains multiple parameter specifications or results:
    - Each line in a multi-line cell is a SEPARATE test parameter
    - Split these into individual rows, matching nth spec line with nth result line
    - Example: CEX-UV with "APG: 16.0-32.3%\nMain Peak: 61.3-77.4%\nBPG: ≤11.5%" in spec cell
        and "23.7%\n69.8%\n6.5%" in result cell
    - Extract as THREE rows:
        * "Parent - CEX-UV - APG" | "16.0-32.3%" | "23.7"
        * "Parent - CEX-UV - Main Peak" | "61.3-77.4%" | "69.8"
        * "Parent - CEX-UV - BPG" | "≤11.5%" | "6.5"

    5. **SHARED SPECIFICATIONS**:
    When a single specification applies to multiple rows:
    - The specification (like "≤ 0.5 EU/mg") should be repeated for each child row
    - Each child gets its own result value
    - Don't create a separate row just for the specification

    6. **MULTI-LEVEL SPECIFICATIONS**:
    For tests with multiple specification lines (common in chromatography):
    - Example: CEX-UV with APG: range, Main Peak: range, BPG: range
    - Keep as ONE test entry with all specifications
    - Preserve the exact multi-line format in specification field

    **EXAMPLES OF CORRECT EXTRACTION:**

    Example 1 - Simple test:
    Row shows: pH | 6.5 - 7.5 | 6.8
    - Test: "pH"
    - Specification: "6.5 - 7.5"
    - Result: "6.8"

    Example 2 - Defect table:
    Row shows: Critical defects | 0.00 | 50 | 0 | 0
    Headers are: Defect type | AQL | Sample | Accept# | Found
    - Test: "Critical defects"
    - Specification: "AQL 0.00, Sample 50, Acceptance number 0"
    - Result: "0"

    Example 3 - No clear headers:
    Row shows: Assay (HPLC) 98.0 - 102.0 % 99.5 %
    - Test: "Assay (HPLC)"
    - Specification: "98.0 - 102.0 %"
    - Result: "99.5"
    Example 4 - Parent with slash:
    Line shows: Identification by HPLC-CAD/Deoxycholic Acid Assay | [empty] | [empty]
    Next line: Identification by HPLC-CAD | Retention time comparable | [result]
    Next line: Deoxycholic Acid Assay | 95.0-105.0% | [result]
    - Parent: "Identification by HPLC-CAD/Deoxycholic Acid Assay" (type="parent")
    - Child 1: "Identification by HPLC-CAD/Deoxycholic Acid Assay - Identification by HPLC-CAD" (type="child")
    - Child 2: "Identification by HPLC-CAD/Deoxycholic Acid Assay - Deoxycholic Acid Assay" (type="child")
    **WHEN THERE ARE NO CLEAR HEADERS:**
    1. First value = usually the test name
    2. Middle values = usually specifications (limits, methods, criteria)
    3. Last value = usually the result (what was measured)
    **REMEMBER**: 
    - Specifications define what's acceptable
    - Results show what actually happened
    - When in doubt, ask: "Is this telling me what SHOULD be (spec) or what IS (result)?"

    7. **PRESERVE EXACT CONTENT**:
    - Copy ALL text exactly including:
        * Reference numbers (<788>, USP, EP, etc.)
        * Method numbers (STM.B0127.ABC)
        * Parameter details (Non-Reduced, Reduced)
        * All parenthetical information
    - Extract units to separate column
    - Never modify or simplify test names

    8. **LAYOUT-BASED INTELLIGENCE**:
    - Tests at the SAME indentation level under a header = all children of that header
    - New section header at same level as previous = new parent category
    - Subsections under main sections = still children of main section
    - Visual grouping (spacing/lines) indicates related tests
    - Rows separated by clear borders/lines with complete test+spec+result = STANDALONE tests, NOT parent-child even if names seem related

    9. Format specifications: both limits = "X - Y", upper limit only = "≤ Y", lower limit only = "≥ X".

    10. If columns show "ANALYSIS" and "NAME" separately, combine them as "Analysis - Name" in the Test field.

    UNIVERSAL TEST DATA EXTRACTION - THINK LIKE A PHARMACEUTICAL SCIENTIST:

    CRITICAL: 
    - Return ONLY the JSON object, no explanations or additional text
    - For complex tables, combine ALL descriptive columns into the test name
    - Properly escape any special characters in strings (quotes, backslashes, etc.)
    - Ensure valid JSON syntax even if test names contain special characters
    - Please dont extract sl no or serial no for each parameter row and dont add it to the test paramter name i dont want it

    Return ONLY a valid JSON object with no additional text before or after:
    {{
    "page": {page_num},
    "test_data": [
        {{
        "test": "Test name or section header exactly as shown",
        "specification": "exact specification (including multi-line)",
        "result": "exact result",
        "unit": "extracted unit",
        "type": "parent/child/standalone",
        "parent_section": "name of parent section if child, empty if parent/standalone"
        }}
    ]
    }}"""

def get_content_uniformity_extraction_prompt(page_nums: List[int]) -> str:
    """
    Specialized prompt for IN-PROCESS CONTENT UNIFORMITY data
    Now handles multiple pages at once
    """
    
    pages_str = ", ".join(map(str, page_nums))
    
    return f"""Extract ALL test data from pages {pages_str} of this pharmaceutical Certificate of Analysis.
This data spans multiple pages - extract ALL related content uniformity data.

THINK LIKE A HUMAN READING THE DOCUMENT:
- If you see a table with multiple descriptive columns, combine them intelligently into the test name
- Each row with different descriptive information represents a different test protocol
- Don't extract compliance statements - always check for actual test chemical data
- If it's explaining (compliance, manufacturing, approvals) = NOT A TEST


CRITICAL EXTRACTION RULES:

1. **REMOVE NON-CHEMICAL TEST DATA**:
   Skip these completely:
   - Compliance statements: "The batch and its manufacture comply..."
   - Manufacturing text: "has been carried out", "have been executed"
   - Administrative rows: "Certificate Generated By", "Batch Released By", "Release Date"
   - Process Information, QA Review sections
   
   INTELLIGENT TEST RECOGNITION:
   If it starts with a test parameter (pH, Assay, Endotoxins) = IT'S A TEST!

2. **HIERARCHY DETECTION** (CRITICAL!):
   - Section headers (bold, larger font, separated) = PARENT type
   - Tests under sections = CHILD type (format as "Parent - Child")
   - Empty spec/result rows = usually PARENT
   - Actual test data rows = CHILD
   
3. **MULTI-VALUE SPECIFICATION SPLITTING**:
   When specs like "APG: ≤10.0%; Main Peak: ≥90.0%; BPG: ≤10.0%" appear:
   - Keep as ONE test entry with multi-line specification
   - Preserve exact format in specification field
   
4. **RESULT VALUE SPLITTING** (IMPORTANT):
   If result contains "/" like "0.20 % / < 0.2":
   - This should be TWO separate rows
   - Split the test name too if applicable
   - Each gets same specification but different result

5. **IN-PROCESS CONTENT UNIFORMITY SPECIAL HANDLING**:
   
   FORMAT RULES:
   - Add "Stage 1, Stage 2" between parameter and detail
   - Pattern: "IN-PROCESS CONTENT UNIFORMITY - [DRUG] - Stage 1, Stage 2 - [DETAIL]"
   
   CRITICAL REQUIREMENTS:
   ✓ Extract ALL bags (Bag.# 1, 2, 3, etc.) from ALL pages
   ✓ Extract ALL 4 summary rows for EACH drug:
     - Avg. (all samples, wt. correct)
     - RSD (all samples, wt. correct)
     - Min. (all samples, as is)
     - Max. (all samples, as is)
   ✓ Each drug (ETHINYL ESTRADIOL, NORETHINDRONE ACETATE) has its OWN summaries
   ✓ Copy specification to ALL rows of same parameter
   ✓ Summary rows have NO specification (leave empty)
   
   MULTI-PAGE HANDLING:
   - Bags might be on page 1, summaries on page 2
   - Check ALL provided pages for complete data
   - Don't miss summaries just because they're on a different page
   
   EXAMPLE OUTPUT:
   - IN-PROCESS CONTENT UNIFORMITY - ETHINYL ESTRADIOL - Stage 1, Stage 2 - Bag.# 1
   - IN-PROCESS CONTENT UNIFORMITY - ETHINYL ESTRADIOL - Stage 1, Stage 2 - Bag.# 2
   - IN-PROCESS CONTENT UNIFORMITY - ETHINYL ESTRADIOL - Stage 1, Stage 2 - Avg. (all samples, wt. correct)
   - IN-PROCESS CONTENT UNIFORMITY - ETHINYL ESTRADIOL - Stage 1, Stage 2 - RSD (all samples, wt. correct)
   - IN-PROCESS CONTENT UNIFORMITY - ETHINYL ESTRADIOL - Stage 1, Stage 2 - Min. (all samples, as is)
   - IN-PROCESS CONTENT UNIFORMITY - ETHINYL ESTRADIOL - Stage 1, Stage 2 - Max. (all samples, as is)

6. **MULTIPLE TEST CONDITIONS**:
   For tests like Endotoxins with different conditions:
   - "Endotoxins - 1 cycle, 3 vials"
   - "Endotoxins - 2 cycles, 2 from first cycle and 1 from second"
   - Extract ALL as separate tests - they're different protocols!

7. **UNIT EXTRACTION** (ALWAYS):
   - "99.2 %" → result="99.2", unit="%"
   - "< 0.02 EU/mg" → result="< 0.02", unit="EU/mg"
   - "<5" → result="<5", unit="" (no unit)
   - Extract units from RESULTS ONLY, not specifications

8. **COMPLEX TABLE HANDLING**:
   For tables with multiple descriptive columns:
   - Combine ALL columns into test name
   - Example: "Endotoxins - 1 cycle, 3 vials" (from two columns)
   - Each row = separate test with combined description

9. **PRESERVE EXACT CONTENT**:
   - Copy ALL text including:
     * Reference numbers (<788>, USP, EP)
     * Method numbers (STM.B0127.ABC)
     * Parameter details (Non-Reduced, Reduced)
     * All parenthetical information

10. **RELATIONSHIP RULES**:
    - Specified Impurities ≠ parent of Unspecified
    - Total (Specified and Unspecified) = standalone, not child
    - Use common sense for pharmaceutical groupings
11. **SHARED SPECIFICATIONS FOR UNIFORMITY TESTS** (CRITICAL!):
    When you see specifications that apply to multiple related uniformity tests:
    
    EXAMPLE SCENARIO:
    ```
    UNIFORMITY OF DOSAGE UNITS - ETHINYL ESTRADIOL - SD    Meet the requirements of USP <905>
    AV ≤ 15.0
    UNIFORMITY OF DOSAGE UNITS - ETHINYL ESTRADIOL - RSD
    ```
    
    CORRECT HANDLING:
    - The specification "Meet the requirements of USP <905>" applies to ALL related uniformity tests
    - The "AV ≤ 15.0" applies to ALL related uniformity tests  
    - Copy BOTH specifications to ALL tests: SD, AV, RSD, Min, Max, etc.
    - Combine specifications with line breaks: "Meet the requirements of USP <905>\nAV ≤ 15.0"
    
    CRITICAL RULES:
    ✓ NEVER leave uniformity test specifications empty if there are related specifications
    ✓ Copy ALL applicable specifications to EVERY related test
    ✓ For UNIFORMITY tests, if one test has specs, ALL similar tests should get the same specs
    ✓ Don't remove or truncate specifications even if they are long
    ✓ Preserve ALL reference numbers, USP citations, method details
    
    PRESERVE FULL DESCRIPTIONS:
    - Keep complete test names including all identification details
    - Don't remove or shorten "Description" or "Identification" content these are also under test parameter so dont remove it 
    - Include ALL parenthetical information and reference numbers
Return ONLY a valid JSON object:
{{
  "pages": {page_nums},
  "test_data": [
    {{
      "test": "Test name with proper formatting",
      "specification": "exact spec (empty for summary rows)",
      "result": "result WITHOUT units",
      "unit": "extracted unit",
      "type": "parent/child/standalone"
    }}
  ]
}}

CRITICAL: 
- Return ONLY JSON, no explanations
- Extract ALL summary statistics for content uniformity from ALL pages
- Don't add specifications to summary rows
- Split "/" results into separate rows
- Preserve all hierarchies
- Check ALL provided pages for complete data
"""

def extract_content_uniformity_batch(page_images: dict, page_batch: List[int], pdf_path: str = None) -> List[dict]:
    """
    Extract content uniformity data from a batch of pages - process each page individually
    """
    print(f"   📦 Processing batch of {len(page_batch)} pages individually: {page_batch}")
    
    all_tests = []
    
    # Process each page individually within the batch
    for page_num in page_batch:
        if page_num not in page_images:
            print(f"      ⚠️ Page {page_num} image not found")
            continue
            
        print(f"      📄 Processing page {page_num}...")
        
        # Get optimized image (compress only if needed)
        page_image_b64, img_format = get_optimized_image(pdf_path, page_num)
        
        # Create message for single page
        page_message = [{
            "type": "text", 
            "text": get_content_uniformity_extraction_prompt([page_num])  # Single page
        }, {
            "type": "image",
            "encoding": "base64", 
            "media_type": f"image/{img_format.lower()}",
            "data": page_image_b64
        }]
        
        messages = [{"role": "user", "content": page_message}]
        
        headers = {"X-API-Key": LLM_API_KEY}
        payload = {
            "messages": messages,
            "max_tokens": 16000,  # Smaller for individual pages
        }
        
        try:
            # Add this debug code right before the requests.post line:
            try:
                # Debug the request size and structure
                request_size = len(json.dumps(payload))
                print(f"        📊 Request size: {request_size:,} characters")
                #print(f"        📋 Payload structure: messages={len(payload['messages'])}, max_tokens={payload.get('max_tokens','default')}")
                
                if request_size > 50000:  # If larger than 50KB
                    print(f"        ⚠️ Large request detected - might cause 400 error")
                
                response = requests.post(LLM_URL, json=payload, headers=headers, timeout=120)
            except Exception as e:
                print(f"        ❌ Error sending request: {e}")
                return []
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data:
                    content = data['choices'][0]['message']['content']
                elif 'completion' in data:
                    content = data['completion']['content']
                else:
                    print(f"        ❌ Unknown response format for page {page_num}")
                    continue
                
                # Extract JSON from response
                parsed = extract_json_from_response(content)
                if parsed and 'test_data' in parsed:
                    page_tests = parsed['test_data']
                    print(f"        ✓ Extracted {len(page_tests)} tests from page {page_num}")
                    all_tests.extend(page_tests)
                else:
                    print(f"        ⚠️ No test data found on page {page_num}")
                    
            else:
                print(f"        ❌ API error for page {page_num}: {response.status_code}")
                if response.status_code == 400:
                    print(f"        📝 Error details: {response.text[:500]}...")  # Show first 500 chars of error
                
        except Exception as e:
            print(f"        ❌ Error processing page {page_num}: {e}")
    
    print(f"      ✅ Batch complete: {len(all_tests)} total tests from {len(page_batch)} pages")
    return all_tests

def extract_json_from_response(response_text: str) -> dict:
    """
    Extract and repair JSON from LLM response with robust error handling
    """
    try:
        # First try to find JSON in the response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            print("   ⚠️ No JSON structure found in response")
            return None
        
        json_string = json_match.group(0)
        print(f"   📏 JSON length: {len(json_string)} characters")
        
        # First attempt: try parsing directly
        try:
            return json.loads(json_string)
        except json.JSONDecodeError as e:
            print(f"   ⚠️ Initial JSON parse failed: {e}")
        
        # Check for truncation by counting structural elements
        open_braces = json_string.count('{')
        close_braces = json_string.count('}')
        open_brackets = json_string.count('[')
        close_brackets = json_string.count(']')
        
        missing_braces = open_braces - close_braces
        missing_brackets = open_brackets - close_brackets
        
        print(f"   🔍 Structural analysis: Missing }} x{missing_braces}, ] x{missing_brackets}")
        
        # Detect severe truncation
        total_missing = missing_braces + missing_brackets
        if total_missing > 3:
            print(f"   ⚠️ Severe truncation detected ({total_missing} missing elements)")
        
        # Attempt to repair JSON
        repaired_json = json_string
        
        # Add missing closing brackets and braces
        repaired_json += ']' * missing_brackets
        repaired_json += '}' * missing_braces
        
        # Second attempt: try parsing repaired JSON
        try:
            return json.loads(repaired_json)
        except json.JSONDecodeError as e:
            print(f"   ⚠️ Repaired JSON parse failed: {e}")
        
        # Third attempt: try fixing common issues
        try:
            # Remove trailing commas before closing brackets/braces
            fixed_json = re.sub(r',(\s*[}\]])', r'\1', repaired_json)
            return json.loads(fixed_json)
        except json.JSONDecodeError as e:
            print(f"   ⚠️ Fixed JSON parse failed: {e}")
        
        # Fourth attempt: progressive parsing
        try:
            # Try to find the completion part and parse that
            if '"validated_data"' in repaired_json:
                # Extract just the validated_data array
                validated_match = re.search(r'"validated_data"\s*:\s*(\[[\s\S]*?\])', repaired_json)
                if validated_match:
                    validated_array = validated_match.group(1)
                    # Add missing closing brackets if needed
                    validated_array += ']' * (validated_array.count('[') - validated_array.count(']'))
                    
                    # Try to parse the array
                    validated_data = json.loads(validated_array)
                    return {
                        "validated_data": validated_data,
                        "validation_summary": {"info": "Partial recovery from truncated response"}
                    }
        except Exception as e:
            print(f"   ⚠️ Progressive parsing failed: {e}")
        
        return None
        
    except Exception as e:
        print(f"   ❌ Critical error in JSON extraction: {e}")
        return None

def extract_all_test_data(page_images: dict, test_names: List[str], pdf_path: str, max_retries: int = 3) -> pd.DataFrame:
    """
    Extract all test data from PDF pages with special handling for content uniformity
    """
    
    print("   📝 Extracting all test data from PDF pages...")
    
    # Check if this is content uniformity data
    is_content_uniformity = detect_content_uniformity_data(test_names)
    
    #if is_content_uniformity:
    if False:
        print("   🎯 Using batch processing for IN-PROCESS CONTENT UNIFORMITY data")
        return extract_content_uniformity_data_parallel(page_images, pdf_path)
    else:
        # Use standard page-by-page extraction
        return extract_standard_test_data(page_images, max_retries)

def extract_content_uniformity_data_parallel(page_images: dict, pdf_path: str = None) -> pd.DataFrame:
    """Extract content uniformity data from all pages in sequential batch order"""
    
    print("   🚀 Starting sequential batch extraction for content uniformity...")
    
    # Create batches of pages in correct order
    page_list = sorted(page_images.keys())  # Ensure pages are in numeric order
    batch_size = 3  # Smaller batches for better success rate
    batches = []
    
    for i in range(0, len(page_list), batch_size):
        batch = page_list[i:i + batch_size]
        batches.append(batch)
    
    print(f"   📦 Created {len(batches)} batches for sequential processing")
    for i, batch in enumerate(batches):
        print(f"     Batch {i + 1}: pages {batch}")
    
    # Process batches SEQUENTIALLY to maintain order
    all_test_data = []
    
    for batch_index, batch_pages in enumerate(batches):
        print(f"   📦 Processing batch {batch_index + 1} of {len(batches)}: pages {batch_pages}")
        
        try:
            # Process this batch (each page within batch is still processed individually)
            batch_tests = extract_content_uniformity_batch(page_images, batch_pages, pdf_path)
            
            # Add results in order
            all_test_data.extend(batch_tests)
            print(f"   ✅ Batch {batch_index + 1} complete: {len(batch_tests)} tests added in order")
            
        except Exception as e:
            print(f"   ❌ Batch {batch_index + 1} failed: {e}")
            # Continue with next batch even if one fails
    
    print(f"   📊 Total extracted: {len(all_test_data)} tests in correct page order")
    
    # Convert to DataFrame
    if all_test_data:
        df = pd.DataFrame(all_test_data)
        
        # Remove type column if it exists
        if 'type' in df.columns:
            df = df.drop('type', axis=1)
        
        return df
    else:
        return pd.DataFrame(columns=['test', 'specification', 'result', 'unit'])

def extract_standard_test_data(page_images: dict, max_retries: int = 3) -> pd.DataFrame:
    """
    Standard page-by-page extraction for non-content uniformity data
    """
    all_tests = []
    failed_pages = []
    
    for page_num, page_image in page_images.items():
        print(f"   📄 Extracting from page {page_num}...")
        
        # Retry mechanism for each page
        page_extracted = False
        for attempt in range(max_retries):
            try:
                question = get_simple_extraction_prompt(page_num)
                response = ask_specific_question(page_image, question)
                
                # Use the robust JSON extraction function
                parsed = extract_json_from_response(response)
                if parsed and 'test_data' in parsed:
                    test_count = len(parsed['test_data'])
                    
                    if test_count > 0:
                        # Process extracted tests to build proper hierarchy
                        current_parent = None
                        for test in parsed['test_data']:
                            if test['type'] == 'parent':
                                current_parent = test['test']
                                all_tests.append(test)
                            elif test['type'] == 'child' and current_parent:
                                # Format child test with parent prefix if not already formatted
                                if ' - ' not in test['test'] and current_parent:
                                    test['test'] = f"{current_parent} - {test['test']}"
                                all_tests.append(test)
                            else:
                                all_tests.append(test)
                        
                        print(f"      ✓ Extracted {test_count} tests from page {page_num}")
                        page_extracted = True
                        break
                    else:
                        if attempt < max_retries - 1:
                            print(f"      ⚠️ No tests found on page {page_num}, retrying... (attempt {attempt + 2}/{max_retries})")
                        else:
                            print(f"      ⚠️ No tests found on page {page_num} after {max_retries} attempts")
                else:
                    if attempt < max_retries - 1:
                        print(f"      ❌ No test_data in response for page {page_num}, retrying... (attempt {attempt + 2}/{max_retries})")
                        
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"      ❌ Error parsing page {page_num}: {e}, retrying... (attempt {attempt + 2}/{max_retries})")
                else:
                    print(f"      ❌ Failed to extract from page {page_num} after {max_retries} attempts: {e}")
        
        if not page_extracted:
            failed_pages.append(page_num)
    
    # Report failed pages
    if failed_pages:
        print(f"   ⚠️ Failed to extract data from pages: {failed_pages}")
    
    # Create dataframe from all extracted tests
    if all_tests:
        # Remove parent_section field before creating dataframe (it was just for processing)
        for test in all_tests:
            if 'parent_section' in test:
                del test['parent_section']
        
        df = pd.DataFrame(all_tests)
        print(f"   📊 Total extracted: {len(df)} tests from {len(page_images)} pages")
        
        # Log hierarchy summary
        if 'type' in df.columns:
            parent_count = len(df[df['type'] == 'parent'])
            child_count = len(df[df['type'] == 'child'])
            standalone_count = len(df[df['type'] == 'standalone'])
            print(f"      - Parents: {parent_count}, Children: {child_count}, Standalone: {standalone_count}")
        
        return df
    else:
        print("   ⚠️ No tests extracted from any page")
        return pd.DataFrame(columns=['test', 'specification', 'result', 'unit', 'type'])

def chunked_validation_merge(original_df: pd.DataFrame, extracted_df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """Handle large datasets by evaluating quality and choosing the BEST one"""
    
    print("   📦 Evaluating data quality to choose best dataset...")
    
    original_tests = original_df.to_dict('records')
    extracted_tests = extracted_df.to_dict('records')
    
    # Quick check for uniformity data quality
    extracted_has_good_uniformity = any(
        ('uniformity' in str(test.get('test', '')).lower() and 
         any(indicator in str(test.get('test', '')).lower() for indicator in ['average', 'sd', 'rsd', 'av', 'min', 'max']))
        for test in extracted_tests
    )
    
    if extracted_has_good_uniformity:
        print("   🎯 Extracted has complete uniformity data with summaries")
        print("   ✅ Using EXTRACTED dataset (102 tests) - it's better quality")
        return extracted_df, {
            "total_original": len(original_df),
            "total_extracted": len(extracted_df),
            "decision": "used_extracted",
            "reason": "Extracted has complete uniformity data structure"
        }
    
    # For non-obvious cases, sample quality check
    print("   🔍 Sampling data quality...")
    
    quality_check_prompt = f"""Evaluate which dataset is better quality.

ORIGINAL SAMPLE (first 10 tests):
{json.dumps(original_tests[:10], indent=2)}

EXTRACTED SAMPLE (first 10 tests):  
{json.dumps(extracted_tests[:10], indent=2)}

FULL COUNTS: Original has {len(original_tests)} tests, Extracted has {len(extracted_tests)} tests

CHECK FOR:
1. Which has better structure (Parent - Child hierarchy)?
2. Which has units properly extracted?
3. Which has more complete data?
4. Which looks more accurate/professional?

RETURN:
{{
  "use_dataset": "original" or "extracted",
  "reason": "brief explanation"
}}"""

    try:
        response = ask_specific_question("", quality_check_prompt, is_large_data=False, llm_url=VALIDATION_LLM_URL)
        result = extract_json_from_response(response)
        
        if result and result.get('use_dataset') == 'extracted':
            print(f"   ✅ Using EXTRACTED dataset - {result.get('reason', 'better quality')}")
            return extracted_df, {
                "total_original": len(original_df),
                "total_extracted": len(extracted_df),
                "decision": "used_extracted",
                "reason": result.get('reason', 'Extracted data evaluated as better quality')
            }
        else:
            print(f"   ✅ Using ORIGINAL dataset - {result.get('reason', 'better quality')}")
            return original_df, {
                "total_original": len(original_df),
                "total_extracted": len(extracted_df),
                "decision": "used_original",
                "reason": result.get('reason', 'Original data evaluated as better quality')
            }
            
    except Exception as e:
        print(f"   ⚠️ Quality check failed: {e}")
        # Default to original if check fails
        print("   ✅ Using ORIGINAL dataset (default)")
        return original_df, {
            "total_original": len(original_df),
            "total_extracted": len(extracted_df),
            "decision": "used_original",
            "reason": "Quality check failed, defaulting to original"
        }

def validation_agent_merge(original_df: pd.DataFrame, extracted_df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """Use an intelligent validation agent to merge data instead of rules"""
    
    print("\n   🔄 Validation Agent: Intelligently merging data...")
    
    # If extraction failed or is empty, return original
    if len(extracted_df) == 0:
        print("   ⚠️ No extracted data to merge, using original")
        return original_df, {"info": "No extraction data available"}
    
    # Check data size and use chunked processing if needed
    original_tests = original_df.to_dict('records')
    extracted_tests = extracted_df.to_dict('records')
    
    # Estimate total size
    original_size = len(json.dumps(original_tests))
    extracted_size = len(json.dumps(extracted_tests))
    total_size = original_size + extracted_size
    
    print(f"   📊 Data sizes: Original={original_size}, Extracted={extracted_size}, Total={total_size}")
    
    # If data is too large, use chunked processing
    if total_size > 25000:  # 25KB threshold
        print("   📦 Using chunked processing for large dataset...")
        return chunked_validation_merge(original_df, extracted_df)
    
    # For smaller datasets, proceed with single request
    
    validation_prompt = f"""You are a GxP Data Integrity Specialist for pharmaceutical CoA validation. Your primary responsibility is to ensure regulatory-compliant test data structure is preserved.

    ====================================================================================
    SECTION 1: PRIMARY DIRECTIVE
    ====================================================================================

    **ABSOLUTE RULE**: IF EXTRACTED DATA HAS 'type' COLUMN WITH VALUES (parent/child/standalone), IT IS THE AUTHORITATIVE SOURCE.

    Look at EXTRACTED data FIRST:
    - Does it have a 'type' column? YES → It contains the TRUE document hierarchy
    - Does 'type' contain "parent", "child", "standalone" values? YES → This is GxP-validated structure
    - Are there tests with hierarchical names (containing " - ")? YES → Proper pharmaceutical grouping

    **IF ALL ABOVE ARE YES → USE EXTRACTED DATA AS YOUR PRIMARY SOURCE**

    ====================================================================================
    SECTION 2: INPUT DATA
    ====================================================================================

    ORIGINAL DATA (from unified Excel - potentially incomplete structure):
    {json.dumps(original_tests, indent=2)}

    EXTRACTED DATA (from PDF pages - GxP-validated extraction with 'type' column):
    {json.dumps(extracted_tests, indent=2)}

    ====================================================================================
    SECTION 3: DATA QUALITY ASSESSMENT (DO THIS FIRST!)
    ====================================================================================

    **STEP 1 - ANALYZE EXTRACTED DATA STRUCTURE**:
    Check the 'type' column in EXTRACTED data:
    - type="parent" → Section headers (may have empty spec/result)
    - type="child" → Tests under that section
    - type="standalone" → Independent tests

    Count each type and verify the hierarchy makes pharmaceutical sense.

    **STEP 2 - IDENTIFY HIERARCHICAL RELATIONSHIPS**:
    For each row with type="child":
    1. Find its parent (the nearest preceding row with type="parent")
    2. The child test name should be formatted as: "Parent Name - Child Test Name"
    3. If not already formatted, YOU MUST format it correctly

    Example:
    - Parent row: {{"test": "Purity", "type": "parent", "specification": "", "result": ""}}
    - Child row: {{"test": "Size exclusion chromatography", "type": "child", "specification": "≥ 97.5%", "result": "98.2"}}
    - Correct output: {{"test": "Purity - Size exclusion chromatography", "specification": "≥ 97.5%", "result": "98.2", "unit": "%"}}

    ====================================================================================
    SECTION 4: CRITICAL TRANSFORMATION RULES (APPLY IN THIS ORDER!)
    ====================================================================================

    **RULE 1 - MULTI-LINE SPECIFICATION SPLITTING (HIGHEST PRIORITY)**:

    When you encounter specifications with multiple parameters like:
    - "HMW: ≤ 2.2%, Monomer: ≥ 97.5%"
    - "APG: 16.0-32.3%, Main Peak: 61.3-77.4%, BPG: ≤11.5%"

    YOU MUST SPLIT INTO SEPARATE ROWS:

    Input: {{"test": "Purity - Size exclusion chromatography", "specification": "HMW: ≤ 2.2%, Monomer: ≥ 97.5%", "result": "1.8%, 98.2%"}}

    Output:
    - {{"test": "Purity - Size exclusion chromatography - HMW", "specification": "≤ 2.2%", "result": "1.8", "unit": "%"}}
    - {{"test": "Purity - Size exclusion chromatography - Monomer", "specification": "≥ 97.5%", "result": "98.2", "unit": "%"}}

    **Detection patterns for multi-line specs**:
    - Contains ":" followed by a value/range
    - Multiple parameters separated by comma, semicolon, or newline
    - Pattern: "Parameter1: value1, Parameter2: value2"

    **RULE 2 - HIERARCHY PRESERVATION**:

    Using the 'type' column from EXTRACTED:
    1. Build parent-child relationships
    2. Format all children as "Parent - Child"
    3. Maintain all hierarchical groupings

    **RULE 3 - PARENT ROW HANDLING**:

    Check each row with type="parent":
    - Has empty/null specification AND empty/null result? → Check if children exist
    - Children already contain full hierarchical names? → DELETE the parent row
    - Parent has actual test data? → KEEP it

    **RULE 4 - RESULT VALUE SPLITTING**:

    If result contains "/" like "0.20 % / < 0.2":
    - Create TWO separate rows
    - Same test name, same specification
    - Split the results: "0.20" and "< 0.2"

    **RULE 5 - UNIT EXTRACTION**:

    Extract units from results:
    - "99.2 %" → result="99.2", unit="%"
    - "< 0.02 EU/mg" → result="< 0.02", unit="EU/mg"
    - "<5" → result="<5", unit=""

    ====================================================================================
    SECTION 5: SPECIAL HANDLING PATTERNS
    ====================================================================================

    **CONTENT UNIFORMITY TESTS**:
    Format: "IN-PROCESS CONTENT UNIFORMITY - [DRUG] - Stage 1, Stage 2 - [DETAIL]"
    - Keep all bag numbers
    - Keep all summary statistics (Avg, RSD, Min, Max)
    - Summary rows have NO specification

    **SHARED SPECIFICATIONS**:
    When one specification applies to multiple rows:
    - Copy the specification to ALL related rows
    - Example: "Meet USP <905>" applies to all uniformity tests under that section

    **ENDOTOXINS WITH CONDITIONS**:
    Each condition is a separate test:
    - "Endotoxins - 1 cycle, 3 vials" 
    - "Endotoxins - 2 cycles, 2 from first cycle and 1 from second"

    ====================================================================================
    SECTION 6: FILTERING RULES (APPLY LAST!)
    ====================================================================================

    **DELETE THESE NON-PHARMACEUTICAL TESTS:**
     **PRODUCT IDENTIFICATION (MUST DELETE):**
    Remove rows that are just identifying the product:
    - Drug name with code in parentheses like "Ibrutinib (PCI-32765-00)" → Product identifier, NOT a test
    **MANUFACTURING/PROCESS PARAMETERS (MUST DELETE):**
    Remove any test where test name contains:
    - "Turbine Speed", "Sweep Speed", "Mixing Speed" → Equipment settings
    - "Batch Yield", "Process Yield", "Theoretical Yield" → Manufacturing metrics
    - "Flow Rate", "Feed Rate", "Spray Rate" → Process parameters
    - "RPM", "Hz" (when referring to equipment) → Machine settings
    - "Batch Size", "Lot Size" → Production quantities
    - "Mixer", "Blender", "Granulator" → Equipment names

    **PACKAGING DATA (MUST DELETE):**
    - "Gross Net Weight" → packaging weight
    - "Visual Product Check" → packaging inspection
    - "Evacuation", "Airless" → container test
    - "Burst Test", "Tube" → container test
    - "Cap fit", "Dispensing" → packaging component
    - "Temperature Check" (standalone) → shipping monitoring
    - "Lbl Front/Back/Side" → label inspection

    **SIMPLE DELETION RULE:**
    If it describes:
    - HOW the product was made →

    Remove any test where result is exactly:
    - "M" → checkmark
    - "OK" → checkmark
    - Single letters without numbers

    ====================================================================================
    SECTION 7: VALIDATION LOGIC FLOW
    ====================================================================================

    EXECUTE IN THIS EXACT ORDER:

    1. **LOAD EXTRACTED DATA** with type column
    2. **BUILD HIERARCHY MAP** from type="parent" and type="child" relationships
    3. **FORMAT CHILDREN** as "Parent - Child" if not already formatted
    4. **SPLIT MULTI-LINE SPECS** into separate rows (CHECK EVERY ROW!)
    5. **SPLIT SLASH RESULTS** into separate rows
    6. **EXTRACT UNITS** from all results
    7. **REMOVE EMPTY PARENTS** if children have full names
    8. **DELETE NON-PHARMA TESTS** based on filtering rules
    9. **VALIDATE OUTPUT** - ensure no multi-line specs remain

    ====================================================================================
    SECTION 8: COMPLIANCE REQUIREMENTS
    ====================================================================================

    **21 CFR PART 11 COMPLIANCE**: 
    The hierarchical structure with type="parent"/"child" is REQUIRED for:
    - FDA/EMA regulatory submissions
    - LIMS system integration  
    - Audit trail maintenance
    - USP/EP compliance

    **GXP VALIDATION**: 
    EXTRACTED data with 'type' column = validated document structure
    This structure MUST be preserved for regulatory compliance

    ====================================================================================
    SECTION 10: CRITICAL VALIDATION CHECKLIST
    ====================================================================================

    Before returning your response, verify:
    ☐ All multi-line specifications are split into separate rows
    ☐ All children are formatted as "Parent - Child"
    ☐ No empty parent rows remain if children exist
    ☐ All units are extracted from results
    ☐ All non-pharmaceutical tests are removed
    ☐ No specification contains multiple parameters (no ":" with commas)

    IF ANY CHECKBOX FAILS → GO BACK AND FIX IT!
    ====================================================================================
    ====================================================================================
    SECTION 11: JSON OUTPUT ONLY
    ====================================================================================
    
    You have completed all validation steps.
    Your ONLY task now is to output JSON.
    
    ⚠️ CRITICAL RULES:
    - First character of response must be: {{
    - Last character of response must be: }}
    - NO text before the JSON
    - NO text after the JSON
    - NO explanations
    - NO "Here is the validated data:" type text
    - ONLY the JSON structure
    
    RETURN ONLY THIS JSON FORMAT (no other text):
    {{
        "validated_data": [
            {{
                "test": "properly formatted hierarchical test name",
                "specification": "single parameter specification only",
                "result": "result WITHOUT units",
                "unit": "extracted unit or empty string"
            }}
        ],
        "validation_summary": {{
            "decision": "used_extracted",
            "reason": "Extracted data has complete hierarchy with type column",
            "hierarchies_preserved": ["list of parent-child structures maintained"],
            "multi_line_specs_split": ["list of tests that were split into multiple rows"],
            "gxp_compliance": "confirmed",
            "total_original": {len(original_tests)},
            "total_extracted": {len(extracted_tests)},
            "total_validated": 0
        }}
    }}"""

    # Send to LLM with large data flag using Claude 4 Sonnet for validation
    response = ask_specific_question("", validation_prompt, is_large_data=True, llm_url=VALIDATION_LLM_URL)
    
    # Handle case where request is still too large
    if response == "REQUEST_TOO_LARGE":
        print("   ⚠️ Request still too large even with increased tokens, using chunked processing...")
        return chunked_validation_merge(original_df, extracted_df)
    
    try:
        # Use the robust JSON extraction function
        result = extract_json_from_response(response)
        
        if not result:
            print("   ⚠️ Failed to extract valid JSON from response, using original data")
            return original_df, {"info": "JSON extraction failed"}
        
        validated_data = result.get('validated_data', [])
        summary = result.get('validation_summary', {})
        
        if not validated_data:
            print("   ⚠️ No validated data in response, using original")
            return original_df, {"info": "Validation returned no data"}
        
        # Create validated dataframe
        validated_df = pd.DataFrame(validated_data)
        
        print(f"   📊 Validation complete:")
        print(f"      - Original tests: {summary.get('total_original', len(original_df))}")
        print(f"      - Extracted tests: {summary.get('total_extracted', len(extracted_df))}")
        print(f"      - Validated tests: {len(validated_df)}")
        print(f"      - Tests replaced: {len(summary.get('replaced_tests', []))}")
        print(f"      - Tests added: {len(summary.get('added_tests', []))}")
        print(f"      - Tests kept from original: {len(summary.get('kept_original', []))}")
        print(f"      - Multi-value specs preserved: {len(summary.get('multi_value_preserved', []))}")
        
        # Show some examples of replacements
        if summary.get('replaced_tests'):
            print(f"   📝 Example replacements:")
            for test in summary.get('replaced_tests', [])[:3]:
                print(f"      - {test}")
                
        # Show preserved multi-value specs
        if summary.get('multi_value_preserved'):
            print(f"   📝 Preserved multi-value formatting:")
            for test in summary.get('multi_value_preserved', [])[:3]:
                print(f"      - {test}")
        
        return validated_df, summary
        
    except Exception as e:
        print(f"   ❌ Error in validation: {e}")
        import traceback
        print(f"   📝 Full traceback: {traceback.format_exc()}")
        return original_df, {"error": str(e)}

def save_intermediate_extraction(extracted_df: pd.DataFrame, output_path: str):
    """Save intermediate extraction results for inspection"""
    
    print(f"\n   💾 Saving intermediate extraction to: {output_path}")
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Raw extraction
        extracted_df.to_excel(writer, sheet_name="Raw Extraction", index=False)
        
        # Summary statistics
        summary_data = {
            "Total Tests": len(extracted_df),
            "Parent Rows": len(extracted_df[extracted_df['type'] == 'parent']) if 'type' in extracted_df.columns else 0,
            "Child Rows": len(extracted_df[extracted_df['type'] == 'child']) if 'type' in extracted_df.columns else 0,
            "Standalone Rows": len(extracted_df[extracted_df['type'] == 'standalone']) if 'type' in extracted_df.columns else 0,
            "Tests with Units": len(extracted_df[extracted_df['unit'].notna() & (extracted_df['unit'] != '')]) if 'unit' in extracted_df.columns else 0,
            "Empty Results": len(extracted_df[(extracted_df['result'] == '') | extracted_df['result'].isna()]) if 'result' in extracted_df.columns else 0
        }
        
        summary_df = pd.DataFrame(list(summary_data.items()), columns=["Metric", "Count"])
        summary_df.to_excel(writer, sheet_name="Extraction Summary", index=False)
    
    print(f"   ✅ Intermediate file saved for inspection")

def calculate_extraction_confidence(original_df: pd.DataFrame, merged_df: pd.DataFrame) -> dict:
    """Calculate confidence metrics for the merged data"""
    
    metrics = {}
    
    if len(merged_df) == 0:
        return {'overall_score': 0, 'data_preservation': 0, 'enhancement_score': 0}
    
    # Data preservation score
    original_tests = set(original_df['test'].tolist())
    merged_tests = set(merged_df['test'].tolist())
    
    preserved = len([t for t in original_tests if any(t in m for m in merged_tests)])
    preservation_score = (preserved / len(original_tests)) * 100 if original_tests else 100
    metrics['data_preservation'] = preservation_score
    
    # Enhancement score (new tests or relationships)
    new_tests = len(merged_tests - original_tests)
    hierarchical = len([t for t in merged_tests if ' - ' in str(t)])
    enhancement_score = min(100, (new_tests + hierarchical) / len(merged_df) * 100)
    metrics['enhancement_score'] = enhancement_score
    
    # Overall score
    metrics['overall_score'] = (preservation_score * 0.7 + enhancement_score * 0.3)
    
    return metrics

def create_corrected_excel(df: pd.DataFrame, product_info: dict, output_path: str, qa_report: dict = None):
    """Create the final corrected Excel file with QA report"""
    if 'type' in df.columns:
        df = df.drop(columns=['type'])
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        
        # Sheet 1: Certificate of Analysis
        sheet_name = "Certificate of Analysis"
        
        # Title
        title_df = pd.DataFrame([["Certificate of Analysis", "", "", ""]], 
                               columns=["", "", "", ""])
        title_df.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=0)
        
        # Product info
        info_start = 2
        for idx, (key, value) in enumerate(product_info.items()):
            row_df = pd.DataFrame([[key, value, "", ""]], columns=["", "", "", ""])
            row_df.to_excel(writer, sheet_name=sheet_name, index=False, header=False, 
                           startrow=info_start + idx)
        
        # Test data
        test_start = info_start + len(product_info) + 2
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=test_start)
        
        # Formatting
        ws = writer.sheets[sheet_name]
        
        # Title formatting
        ws['A1'].font = Font(size=16, bold=True)
        ws['A1'].alignment = Alignment(horizontal='center')
        ws.merge_cells('A1:D1')
        
        # Column widths
        ws.column_dimensions['A'].width = 80
        ws.column_dimensions['B'].width = 45
        ws.column_dimensions['C'].width = 35
        ws.column_dimensions['D'].width = 25
        
        # Sheet 2: Test Data Only
        df.to_excel(writer, sheet_name="Test Data Only", index=False)
        
        # Sheet 3: QA Report (if available)
        if qa_report:
            qa_data = []
            qa_data.append(['Extraction Summary', ''])
            qa_data.append(['Original Tests', qa_report.get('original_tests', 0)])
            qa_data.append(['Extracted Tests', qa_report.get('extracted_tests', 0)])
            qa_data.append(['Final Tests', qa_report.get('final_tests', 0)])
            qa_data.append(['', ''])
            qa_data.append(['Changes Made', ''])
            qa_data.append(['Tests Added', qa_report.get('tests_added', 0)])
            qa_data.append(['Tests Replaced', qa_report.get('tests_replaced', 0)])
            qa_data.append(['Tests Kept Original', qa_report.get('tests_kept_original', 0)])
            qa_data.append(['', ''])
            qa_data.append(['Confidence Scores', ''])
            qa_data.append(['Data Preservation', f"{qa_report.get('data_preservation', 0):.1f}%"])
            qa_data.append(['Enhancement Score', f"{qa_report.get('enhancement_score', 0):.1f}%"])
            qa_data.append(['Overall Score', f"{qa_report.get('overall_score', 0):.1f}%"])
            
            qa_df = pd.DataFrame(qa_data, columns=['Metric', 'Value'])
            qa_df.to_excel(writer, sheet_name="QA Report", index=False)

def process_coa_optimized(pdf_path: str, blocks_json_path: str, unified_excel_path: str, 
                         base_path: str, enhanced_product_info: dict = None, 
                         progress_callback=None) -> Dict[str, str]:
    """
    Optimized CoA processing with separated extraction and comparison with progress reporting
    
    Args:
        pdf_path: Path to the PDF file
        blocks_json_path: Path to the Textract blocks JSON file
        unified_excel_path: Path to the unified Excel file
        base_path: Base directory for output files
        enhanced_product_info: Enhanced product information from GPT
        progress_callback: Optional callback function for progress updates (progress, message)
    """
    try:
        print("🚀 Starting Optimized CoA Validation Agent")
        print("=" * 70)
        
        # Initial progress update
        if progress_callback:
            progress_callback(61, "Starting enhanced validation agent...")
        
        # Extract original filename for output naming
        original_filename = os.path.splitext(os.path.basename(pdf_path))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("\n1️⃣ Loading original data from unified Excel...")
        if progress_callback:
            progress_callback(62, "Loading original test data...")
        original_df = pd.read_excel(unified_excel_path, sheet_name='Test Data Only')
        
        # Use enhanced metadata if provided, but normalize it
        if enhanced_product_info:
            product_info = normalize_product_metadata(enhanced_product_info)
            print(f"   ✅ Using normalized enhanced metadata with {len(product_info)} fields")
        else:
            product_info = extract_standard_product_metadata(unified_excel_path)
            print(f"   📊 Extracted metadata from Excel: {len(product_info)} fields")
        
        print(f"   📊 Original data: {len(original_df)} tests")
        
        # Get test names for detection
        test_names = original_df['test'].tolist() if 'test' in original_df.columns else []
        
        # Find pages with test data AND detect content type
        print("\n2️⃣ Finding pages with test data and detecting content type...")
        if progress_callback:
            progress_callback(63, "Finding test pages in document...")
        test_pages, is_content_uniformity = find_pages_with_tests(pdf_path, base_path, unified_excel_path)
        
        if not test_pages:
            print("❌ No test pages found - using original data")
            return {
                'enhanced_excel_path': unified_excel_path,
                'enhanced_json_path': None,
                'validation_status': 'no_enhancement_needed'
            }
        
        print(f"   🎯 Found test data on pages: {test_pages}")
        # NEW: ADD HIERARCHY ANALYSIS HERE

        # Continue with existing code...
        if False:
            print(f"   📦 Content uniformity data detected - will use batch processing")
            if progress_callback:
                progress_callback(64, "Processing uniformity data across multiple pages...")
        
        # Convert pages to images
        print("\n3️⃣ Converting PDF pages to images...")
        if progress_callback:
            progress_callback(65, f"Converting {len(test_pages)} pages to images...")
        page_images = {}
        for page_num in test_pages:
            page_images[page_num] = extract_page_as_image(pdf_path, page_num)
            print(f"   📄 Page {page_num} converted")
        
        # STEP 1: Extract all test data from PDF with appropriate method
        print("\n4️⃣ Extracting all test data from PDF pages...")
        if progress_callback:
            progress_callback(66, f"Extracting data from {len(test_pages)} pages...")
        
        if False:
            print("   🚀 Using BATCH PROCESSING for UNIFORMITY data")
            print("   📦 Processing multiple pages together for complete data extraction")
            if progress_callback:
                progress_callback(67, "Processing uniformity data with batch extraction...")
            extracted_df = extract_content_uniformity_data_parallel(page_images, pdf_path)
        else:
            print("   📄 Using standard page-by-page extraction")
            if progress_callback:
                progress_callback(67, "Extracting test data page by page...")
            extracted_df = extract_standard_test_data(page_images, max_retries=3)
        
        # Save intermediate extraction for inspection
        intermediate_path = os.path.join(base_path, f"{original_filename}_intermediate_extraction_{timestamp}.xlsx")
        save_intermediate_extraction(extracted_df, intermediate_path)
        
        # STEP 2: Use validation agent to merge data
        print("\n5️⃣ Using Validation Agent to merge data...")
        if progress_callback:
            progress_callback(68, "Preparing validation agent...")
        time.sleep(0.1)  # Small delay for progress visibility
        if progress_callback:
            progress_callback(69, "Loading validation models...")
        time.sleep(0.1)
        if progress_callback:
            progress_callback(70, "Starting validation merge...")
        time.sleep(0.1)
        if progress_callback:
            progress_callback(71, "Validating extracted parameters...")
        merged_df, validation_summary = validation_agent_merge(original_df, extracted_df)
        print("\n   🔄 Applying result value mapping...")
        if 'result' in merged_df.columns:
            # Define the mapping function inline
            def map_result_to_zero(val):
                """Map specific values to 0 - WHOLE WORDS ONLY"""
                val_str = str(val).strip()
                
                # Use word boundaries \b to match whole words only
                whole_word_mappings = [
                    (r'\bND\b', '0'),
                    (r'\bNot Detected\b', '0'),
                    (r'\bNone Detected\b', '0'),
                    (r'\bAbsent\b', '0'),
                    (r'\b<QL\b', '0')
                ]
                
                for pattern, replacement in whole_word_mappings:
                    if re.search(pattern, val_str):  # REMOVED re.IGNORECASE
                        return replacement
                
                return val_str
                        
            # Apply the mapping
            merged_df['result'] = merged_df['result'].apply(map_result_to_zero)
            
            # Count how many values were mapped
            mapped_count = len(merged_df[merged_df['result'] == '0'])
            print(f"   ✅ Result values mapped ({mapped_count} values converted to 0)")
        # Continue with rest of processing...
        # Calculate confidence metrics
        print("\n6️⃣ Calculating confidence metrics...")
        if progress_callback:
            progress_callback(76, f"Merging {len(merged_df)} extracted tests...")
        confidence_metrics = calculate_extraction_confidence(original_df, merged_df)
        print(f"   📊 Confidence Scores:")
        print(f"      - Data Preservation: {confidence_metrics['data_preservation']:.1f}%")
        print(f"      - Enhancement Score: {confidence_metrics['enhancement_score']:.1f}%")
        print(f"      - Overall Score: {confidence_metrics['overall_score']:.1f}%")
        
        # Prepare QA report
        qa_report = {
            'original_tests': len(original_df),
            'extracted_tests': len(extracted_df),
            'final_tests': len(merged_df),
            'tests_added': len(validation_summary.get('added_tests', [])),
            'tests_replaced': len(validation_summary.get('replaced_tests', [])),
            'tests_kept_original': len(validation_summary.get('kept_original', [])),
            'data_preservation': confidence_metrics['data_preservation'],
            'enhancement_score': confidence_metrics['enhancement_score'],
            'overall_score': confidence_metrics['overall_score'],
            'content_type': 'uniformity' if is_content_uniformity else 'standard'
        }
        
        # Create output files
        enhanced_excel_path = os.path.join(base_path, f"{original_filename}_enhanced.xlsx")
        enhanced_json_path = os.path.join(base_path, f"{original_filename}_enhanced.json")
        
        print("\n7️⃣ Creating enhanced Excel file...")
        if progress_callback:
            progress_callback(79, "Creating enhanced report...")
        create_corrected_excel(merged_df, product_info, enhanced_excel_path, qa_report)
        
        # Save enhanced JSON
        json_output = {
            "product_info": product_info,
            "test_data": merged_df.to_dict(orient='records'),
            "qa_report": qa_report,
            "validation_summary": validation_summary,
            "extraction_timestamp": timestamp,
            "intermediate_extraction_path": intermediate_path
        }
        
        with open(enhanced_json_path, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=2)
        
        if progress_callback:
            progress_callback(80, "Validation complete - enhanced report ready")
        
        print(f"\n✅ Enhancement complete!")
        print(f"   - Enhanced Excel: {enhanced_excel_path}")
        print(f"   - Enhanced JSON: {enhanced_json_path}")
        print(f"   - Intermediate extraction: {intermediate_path}")
        print(f"   - Content type: {'Uniformity (batch processed)' if is_content_uniformity else 'Standard'}")
        
        # Final summary
        print(f"\n📈 Final Summary:")
        print(f"   - Original tests: {len(original_df)}")
        print(f"   - Extracted from PDF: {len(extracted_df)}")
        print(f"   - Final merged: {len(merged_df)}")
        print(f"   - Net change: {len(merged_df) - len(original_df)}")
        print(f"   - Overall confidence: {confidence_metrics['overall_score']:.1f}%")
        
        return {
            'enhanced_excel_path': enhanced_excel_path,
            'enhanced_json_path': enhanced_json_path,
            'intermediate_extraction_path': intermediate_path,
            'validation_status': 'enhanced',
            'confidence_score': confidence_metrics['overall_score'],
            'qa_report': qa_report
        }
        
    except Exception as e:
        print(f"❌ Error in optimized processing: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return {
            'enhanced_excel_path': unified_excel_path,
            'enhanced_json_path': None,
            'validation_status': 'enhancement_failed',
            'error': str(e)
        }

def main():
    # File paths
    folder = r"C:\Users\BAPATAR\Downloads\validation_test"
    pdf_path = os.path.join(folder, "CoA - CoC - lot 0001903354 (1).pdf")
    excel_path = os.path.join(folder, "CoA - CoC - lot 0001903354 (1)_unified (1).xlsx")
    blocks_json_path = os.path.join(folder, "CoA - CoC - lot 0001903354 (1)_blocks.json")
    
    # Run optimized processing
    result = process_coa_optimized(
        pdf_path=pdf_path,
        blocks_json_path=blocks_json_path,
        unified_excel_path=excel_path,
        base_path=folder,
        enhanced_product_info=None  # Will extract from Excel
    )
    
    if result['validation_status'] == 'enhanced':
        print("\n🎉 Processing completed successfully!")
        print(f"   Check the intermediate extraction at: {result.get('intermediate_extraction_path')}")
    else:
        print(f"\n⚠️ Processing status: {result['validation_status']}")

if __name__ == "__main__":
    main()

def get_optimized_image(pdf_path: str, page_num: int, max_size_bytes=4_800_000):
    """Get optimized image, only compress if it exceeds size limit"""
    
    pdf_document = fitz.open(pdf_path)
    page = pdf_document.load_page(page_num - 1)
    
    # Start with high quality - try 300 DPI PNG first
    pix = page.get_pixmap(alpha=False, dpi=300)
    img_bytes = pix.pil_tobytes(format="PNG")
    
    size_mb = len(img_bytes) / 1_000_000
    print(f"        📊 Original image: 300 DPI PNG, {size_mb:.1f}MB")
    
    # If it's under the limit, use it as-is
    if len(img_bytes) <= max_size_bytes:
        print(f"        ✅ Image size OK, using original quality")
        pdf_document.close()
        return base64.b64encode(img_bytes).decode("utf-8"), "PNG"
    
    # Only compress if needed
    print(f"        ⚠️ Image too large ({size_mb:.1f}MB), compressing...")
    
    # Try JPEG compression first
    img_bytes = pix.pil_tobytes(format="JPEG", optimize=True, quality=85)
    size_mb = len(img_bytes) / 1_000_000
    print(f"        📉 Compressed to JPEG 85%: {size_mb:.1f}MB")
    
    if len(img_bytes) <= max_size_bytes:
        pdf_document.close()
        return base64.b64encode(img_bytes).decode("utf-8"), "JPEG"
    
    # If still too large, reduce DPI
    pix = page.get_pixmap(alpha=False, dpi=200)
    img_bytes = pix.pil_tobytes(format="JPEG", optimize=True, quality=80)
    size_mb = len(img_bytes) / 1_000_000
    print(f"        📉 Further compressed to 200 DPI JPEG 80%: {size_mb:.1f}MB")
    
    pdf_document.close()
    return base64.b64encode(img_bytes).decode("utf-8"), "JPEG"

