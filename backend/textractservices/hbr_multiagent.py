import pandas as pd
import fitz  # PyMuPDF
from PIL import Image
import io
import base64
import requests
import json
from typing import Dict, List, Any, TypedDict
from datetime import datetime
import os
from concurrent.futures import ThreadPoolExecutor
from langgraph.graph import StateGraph
import re # Added for safe_json_parse
import threading  # For thread-safe progress tracking

# Configuration
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from langchain.schema.messages import BaseMessage

# Configuration - UPDATED FOR LANGCHAIN
ANTHROPIC_API_URL = "https://api-epic.ir-gateway.abbvienet.com/iliad/anthropic"
API_KEY = REDACTED
MODEL_NAME = "claude-3-7-sonnet-20250219"  # Claude Opus 4.1

# Initialize the Claude model globally
claude_model = ChatAnthropic(
    anthropic_api_url=ANTHROPIC_API_URL,
    api_key=REDACTED
    model_name=MODEL_NAME,
    max_tokens=REDACTED
    temperature=0.05,
)
LARGE_RESPONSE_MODEL = "claude-3-7-sonnet-20250219"  # Claude 3.7 for merger and validator

# Initialize Claude 3.7 model for merger (handles large responses)
claude_merger_model = ChatAnthropic(
    anthropic_api_url=ANTHROPIC_API_URL,
    api_key=REDACTED
    model_name=LARGE_RESPONSE_MODEL,
    max_tokens=REDACTED
    temperature=0.1,  # Slightly higher for flexibility
)

# Also update validator model with more tokens
claude_validator_model = ChatAnthropic(
    anthropic_api_url=ANTHROPIC_API_URL,
    api_key=REDACTED
    model_name=LARGE_RESPONSE_MODEL,
    max_tokens=REDACTED
    temperature=0.1,
)
# Global thread-safe progress counter
_progress_lock = threading.Lock()
_global_progress = 25  # Start after coordinator
# State definition
class GraphState(TypedDict):
    pdf_path: str
    config_excel: str
    current_task: str
    total_pages: int  # Changed from all_pages_images: Dict[int, str]
    excel_data: str
    agent_decisions: List[Dict]
    final_results: List[Dict]
    conversation_history: List[str]
    progress_callback: Any  # Progress callback function

def excel_to_json_string(excel_path: str) -> str:
    """Convert Excel to JSON string for Claude, handling empty rows and data cleaning"""
    try:
        df = pd.read_excel(excel_path)
        
        # Clean the dataframe
        # 1. Remove completely empty rows
        df = df.dropna(how='all')
        
        # 2. Remove rows where all values are empty strings
        df = df.replace('', pd.NA).dropna(how='all')
        
        # 3. Fill NaN values with empty strings for JSON consistency
        df = df.fillna('')
        
        # 4. Reset index after cleaning
        df = df.reset_index(drop=True)
        
        print(f"   📊 Excel data cleaned: {len(df)} rows remaining after removing empty rows")
        
        return df.to_json(orient='records', indent=2)
    except Exception as e:
        print(f"   ❌ Error converting Excel to JSON: {e}")
        return '[]'  # Return empty JSON array as fallback

def call_claude_agent(role: str, task: str, context: Dict, temperature: float = 0.05,use_validator_model: bool = False,use_merger_model: bool = False) -> str:
    """Call Claude using LangChain with improved error handling"""
    
    # Build the agent prompt
    agent_prompt = f"""You are an AI agent with the role: {role}

Your current task: {task}

Context provided:
{json.dumps(context, indent=2)}

CRITICAL: You must respond with valid JSON only. Do not include any text before or after the JSON.
Make your decision and provide output in JSON format.
Think step by step about what needs to be done."""
    
    try:
        # Create messages list
        messages = []
        
        # Check if we have images in context
        if "images" in context:
            # For image processing, create a complex message with multiple parts
            content_parts = [{"type": "text", "text": agent_prompt}]
            
            for img_data in context["images"]:
                # LangChain expects image data in a specific format
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{img_data.get('format', 'png').lower()};base64,{img_data['base64']}"
                    }
                })
            
            # Create HumanMessage with multimodal content
            message = HumanMessage(content=content_parts)
        else:
            # Simple text message
            message = HumanMessage(content=agent_prompt)
        
        messages.append(message)
        
        # Use a temporary model with custom temperature if needed
        if use_merger_model:
            # Use Claude 3.7 for merger with high token limit
            print(f"   🔧 Using Claude 3.7 Sonnet (50k tokens) for {role}")
            response = claude_merger_model.invoke(messages)
        elif use_validator_model:
            # Use Claude 3.7 for validator
            print(f"   🔧 Using Claude 3.7 Sonnet for {role}")
            response = claude_validator_model.invoke(messages)
        elif temperature != 0.05:
            # Use custom temperature with main model
            temp_model = ChatAnthropic(
                anthropic_api_url=ANTHROPIC_API_URL,
                api_key=REDACTED
                model_name=MODEL_NAME,
                max_tokens=REDACTED
                temperature=temperature
            )
            response = temp_model.invoke(messages)
        else:
            # Use default model
            response = claude_model.invoke(messages)
        
        # Extract the content from the response
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Validate response
        if not response_text or response_text.strip() == '':
            print(f"   ⚠️ Empty response from Claude for role: {role}")
            return '{"error": "Empty response from Claude"}'
        
        print(f"   ✅ Claude response for {role}: {len(response_text)} characters")
        return response_text
        
    except Exception as e:
        print(f"   ⚠️ Error calling Claude for role: {role}: {e}")
        return f'{{"error": "Request failed: {str(e)}"}}'

def safe_json_parse(json_string: str, fallback_value: dict = None) -> dict:
    """Safely parse JSON with fallback values (remains the same)"""
    if fallback_value is None:
        fallback_value = {}
    
    if not json_string or json_string.strip() == '':
        print("   ⚠️ Empty JSON string provided")
        return fallback_value
    
    try:
        json_match = re.search(r'\{[\s\S]*\}', json_string)
        if json_match:
            json_str = json_match.group(0)
        else:
            print("   ⚠️ No JSON structure found in response")
            return fallback_value
        
        parsed_json = json.loads(json_str)
        
        if isinstance(parsed_json, dict) and "error" in parsed_json:
            print(f"   ⚠️ Error response detected: {parsed_json.get('error')}")
            return fallback_value
        
        return parsed_json
    except json.JSONDecodeError as e:
        print(f"   ⚠️ JSON parsing failed: {e}")
        print(f"   Raw string (first 200 chars): {json_string[:200]}")
        return fallback_value
    except Exception as e:
        print(f"   ⚠️ Unexpected error parsing JSON: {e}")
        return fallback_value

def get_optimized_image(pdf_path: str, page_num: int, max_size_bytes=3_900_000):
    """Get optimized image with preprocessing for better OCR accuracy"""
    
    import cv2
    import numpy as np
    from PIL import Image
    import io
    
    pdf_document = fitz.open(pdf_path)
    page = pdf_document.load_page(page_num - 1)
    
    # Extract at 300 DPI for best quality
    pix = page.get_pixmap(alpha=False, dpi=300)
    
    # Convert to numpy array for preprocessing
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    
    # Convert RGBA to RGB if needed
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
    elif img.shape[2] == 1:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    
    # CRITICAL PREPROCESSING - 30% accuracy improvement
    # 1. Local brightness adjustment (HIGHEST IMPACT)
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    l_channel, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    l_channel = clahe.apply(l_channel)
    lab = cv2.merge([l_channel, a, b])
    img = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    
    # 2. Denoise while preserving edges
    img = cv2.bilateralFilter(img, 9, 75, 75)
    
    # 3. Sharpen text
    kernel = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
    img = cv2.filter2D(img, -1, kernel)
    
    # Convert to PIL Image
    pil_img = Image.fromarray(img)
    
    # Try different compression strategies
    # First: High quality JPEG with optimal settings
    buffer = io.BytesIO()
    pil_img.save(buffer, 'JPEG', 
                 quality=92,
                 optimize=True,
                 progressive=True,
                 subsampling=0)  # 4:4:4 for text
    img_bytes = buffer.getvalue()
    
    size_mb = len(img_bytes) / 1_000_000
    base64_size_mb = (len(img_bytes) * 1.34) / 1_000_000
    print(f"        📊 Enhanced JPEG @ 300 DPI Q92: {size_mb:.1f}MB (→ ~{base64_size_mb:.1f}MB base64)")
    
    if len(img_bytes) <= max_size_bytes:
        print(f"        ✅ Using enhanced image with preprocessing")
        pdf_document.close()
        return base64.b64encode(img_bytes).decode("utf-8"), "JPEG"
    
    # If still too large, reduce quality gradually
    for quality in [85, 80, 75]:
        buffer = io.BytesIO()
        pil_img.save(buffer, 'JPEG', 
                     quality=quality,
                     optimize=True,
                     progressive=True)
        img_bytes = buffer.getvalue()
        
        if len(img_bytes) <= max_size_bytes:
            size_mb = len(img_bytes) / 1_000_000
            print(f"        ✅ Enhanced JPEG @ 300 DPI Q{quality}: {size_mb:.1f}MB")
            pdf_document.close()
            return base64.b64encode(img_bytes).decode("utf-8"), "JPEG"
    
    
    pix = page.get_pixmap(alpha=False, dpi=250)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    
    
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    l_channel = lab[:,:,0]
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    lab[:,:,0] = clahe.apply(l_channel)
    img = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    
    pil_img = Image.fromarray(img)
    buffer = io.BytesIO()
    pil_img.save(buffer, 'JPEG', quality=85, optimize=True)
    img_bytes = buffer.getvalue()
    
    size_mb = len(img_bytes) / 1_000_000
    print(f"        📉 Final: Enhanced 250 DPI JPEG Q85: {size_mb:.1f}MB")
    
    pdf_document.close()
    return base64.b64encode(img_bytes).decode("utf-8"), "JPEG"

# LEAD AGENT - Combined prompt with all rules
def lead_agent(state: GraphState) -> GraphState:
    print("\n[LEAD AGENT - Claude]")
    
    if state.get('progress_callback'):
        state['progress_callback'](15, "Analyzing Excel configuration...")
    
    # COMBINED TASK - All existing rules + fixes
    task = """Analyze the Excel configuration to decide batching strategy.
    
    CRITICAL RULES:
    1. ALWAYS include page 1 (it has Batch No: parameter) - NEVER skip it
    2. Extract UNIQUE page numbers from search_pages column
    3. Count how many parameters each page has
    4. Create BALANCED batches based on WORKLOAD, not just page count
    5. Each batch should have roughly 10-15 PARAMETERS (not pages)
    6. Heavy pages (like page 76 with 6+ parameters) might be in a smaller batch
    7. Light pages (with 1-2 parameters) can be grouped together
    
    DYNAMIC WORKER CALCULATION:
    - Count total parameters across all pages
    - Calculate: total_parameters / 12 = number of workers needed
    - Minimum 3 workers, maximum 10 workers
    - Adjust if needed to keep each worker at 10-20 parameters
    
    WORKLOAD BALANCING EXAMPLE:
    - Page 76: 6 parameters → Could be alone or with 2-3 light pages
    - Pages 1,10,11: 1+6+1=8 parameters → Good batch
    - Pages 42,43,44,45,46: 2+1+1+3+1=8 parameters → Good batch
    
    Target: Each worker processes 10-15 parameters ideally (max 20)
    
    If a single page has many parameters (>5), consider:
    - Putting it in a smaller batch
    - Or even alone if it has 10+ parameters
    
    IMPORTANT:
    - Page 1 MUST be in the first batch (it has Batch No:)
    - Create as many workers as needed based on total parameters
    - For ~73 parameters: create ~6 workers
    - For 100+ parameters: create 8-10 workers
    
    Return valid JSON:
    {
        "num_workers": <calculated based on total parameters>,
        "batch_strategy": "workload_balanced",
        "page_batches": [
            [1, ...],  // MUST start with page 1
            [pages for worker 2],
            [pages for worker 3],
            ...  // As many workers as needed
        ],
        "workload_distribution": [
            {"worker": 1, "pages": [...], "parameter_count": N},
            {"worker": 2, "pages": [...], "parameter_count": N},
            ...
        ],
        "total_target_pages": <unique page count>,
        "total_parameters": <total parameter count>,
        "special_instructions": "Balanced by parameter density with page 1 included"
    }"""
    
    context = {
        "excel_config": state["excel_data"],
        "total_pages_in_pdf": state["total_pages"]
    }
    
    print(f"   📊 Processing Excel config for {state['total_pages']} PDF pages")
    
    response = call_claude_agent("Lead Agent - Workload Balanced Strategy", task, context)
    
    lead_decision = safe_json_parse(response, {
        "num_workers": 5,
        "batch_strategy": "workload_balanced",
        "page_batches": [[1]],  # Default with page 1
        "total_target_pages": state["total_pages"],
        "special_instructions": "Default strategy"
    })
    
    # VALIDATION: Just ensure page 1 is included
    cleaned_batches = []
    seen_pages = set()
    page_1_found = False
    
    for batch in lead_decision.get("page_batches", []):
        cleaned_batch = []
        for page in batch:
            if page not in seen_pages:
                cleaned_batch.append(page)
                seen_pages.add(page)
                if page == 1:
                    page_1_found = True
        
        if cleaned_batch:
            cleaned_batches.append(cleaned_batch)
    
    # If Claude missed page 1, add it
    if not page_1_found:
        print("   ⚠️ Page 1 was missing, adding it to first batch")
        if cleaned_batches:
            cleaned_batches[0].insert(0, 1)
            cleaned_batches[0].sort()
        else:
            cleaned_batches = [[1]]
    
    lead_decision["page_batches"] = cleaned_batches
    lead_decision["num_workers"] = len(cleaned_batches)
    
    # Show workload distribution
    if "workload_distribution" in lead_decision:
        print(f"   📊 Workload Distribution:")
        for worker_info in lead_decision.get("workload_distribution", []):
            print(f"      Worker {worker_info['worker']}: {worker_info['parameter_count']} parameters from pages {worker_info['pages']}")
    else:
        print(f"   ✅ Lead strategy: {len(cleaned_batches)} workers")
        for i, batch in enumerate(cleaned_batches):
            print(f"      Worker {i+1}: pages {batch}")
    
    state["agent_decisions"].append({
        "agent": "lead",
        "decision": json.dumps(lead_decision)
    })
    
    return state

# AGENT 2: Worker Agent (Claude extracts from images) - FIXED
# AGENT 2: Worker Agent - Using EXACT pattern from working code
# AGENT 2: Worker Agent - WITH COMMENTS COLUMN SUPPORT
# CORRECT WORKER AGENT - Keeps existing pharmaceutical prompt + adds fixes
def worker_agent(pages: List[int], state: GraphState, worker_id: int) -> List[Dict]:
    """Worker agent using LangChain for image processing"""
    print(f"\n[WORKER AGENT {worker_id} - Claude]")
    print(f"   📄 Processing {len(pages)} pages individually: {pages}")
    
    lead_decision = safe_json_parse(state["agent_decisions"][0]["decision"])
    all_extractions = []
    
    # Parse Excel config to get parameter-comment mappings
    try:
        excel_data = json.loads(state["excel_data"])
    except:
        excel_data = []
    
    global _global_progress, _progress_lock
    
    for idx, page_num in enumerate(pages):
        print(f"      📄 Processing page {page_num}...")
        
        with _progress_lock:
            _global_progress += 3
            current_progress = min(_global_progress, 62)
        
        if state.get('progress_callback'):
            state['progress_callback'](current_progress, f"Worker {worker_id}: Processing page {page_num}...")
        
        # Get parameters specific to this page with their comments
        page_parameters = []
        for item in excel_data:
            search_pages = str(item.get("Search_Pages", ""))
            if str(page_num) in search_pages.replace(" ", "").split(","):
                page_parameters.append({
                    "parameter": item.get("Parameter", ""),
                    "comment": item.get("Comments", ""),
                    "search_pages": search_pages
                })
        
        if not page_parameters:
            print(f"        ⚠️ No parameters expected on page {page_num}")
            continue
            
        print(f"        📋 Parameters to extract from page {page_num}:")
        for param in page_parameters:
            print(f"           - {param['parameter']} (Location: {param['comment']})")
        
        try:
            page_image_b64, img_format = get_optimized_image(state["pdf_path"], page_num)
            
            # Build parameter list with comments for guidance
            params_with_guidance = json.dumps(page_parameters, indent=2)
            
            # KEEP EXISTING PHARMACEUTICAL PROMPT + ADD FIXES
            task = f"""Extract parameters from page {page_num} of this pharmaceutical GxP batch record document.

            CRITICAL PHARMACEUTICAL DOCUMENT UNDERSTANDING:
            This is a GxP batch record with quality control data. Pharmaceutical documents contain:
            - Numbers as primary data (counts, measurements, percentages, calculations)
            - Defect tables AND calculation forms
            - Test results AND summary calculations
            - Both tabular data AND mathematical formulas

            DOCUMENT STRUCTURE RECOGNITION:
            1. **Defect Tables**: Rows and columns with counts
            2. **Calculation Forms**: Mathematical expressions with results
            - Look for formulas like: (A) + (B) + (C) = [RESULT]
            - Extract the FINAL RESULT after equals sign
            3. **Summary Sections**: Calculated totals and percentages
            4. **Reconciliation Sheets**: May combine tables and calculations

            VISUAL INTERPRETATION:
            - In tables: numeric values in cells (0, 1, 2, 11, 255, etc.)
            - In calculations: handwritten results after "=" signs
            - "0" (zero) is circular - common for "no defects"
            - Formulas show process: (value) + (value) = RESULT
            - Extract the RESULT, not the formula components

            INTELLIGENT EXTRACTION APPROACH:
            1. First identify what TYPE of section this is:
            - Is it a data table?
            - Is it a calculation form?
            - Is it a summary section?
            2. Apply appropriate extraction method:
            - For tables: look in specific columns
            - For calculations: find the result after "="
            - For summaries: find the final computed value

            EXTRACTION BASED ON USER INTENT:
            - NO COMMENT/EMPTY → Extract the primary value (could be in a table cell OR a calculation result)
            - WITH COMMENTS → The comment guides what to extract:
            * "calculated value" → Look for calculation results
            * "total" → Find sum/total results
            * "critical value" → Look in critical column OR critical calculation
            * "Step X.X" → Look in that specific step section
            * "top of the page" → Look at the header/top area

            SPECIFIC PATTERNS TO RECOGNIZE:
            - "Calculate batch total of defects" → Find formula result (e.g., 0 + 13 + 368 + 18 = 399, extract "399")
            - "Percentage of [type] defects" → Find percentage calculation result
            - "Total quantity" → Find the final count/sum

            ============= NEW ADDITIONS FOR THIS PAGE =============
            
            PARAMETERS TO EXTRACT FROM THIS SPECIFIC PAGE:
            {params_with_guidance}
            
            CRITICAL VALUE EXTRACTION RULES:
            1. Extract values EXACTLY as they appear - DO NOT normalize or interpret
            2. For tables with multiple time points/readings:
               - If you see: 18  18  17  17  17
               - Extract as: "18,18,17,17,17" or "18, 18, 17, 17, 17"
               - DO NOT extract as: "17-18" or average them
            3. For ranges already in document (like "14.25 - 15.53"), keep as is
            4. NEVER calculate averages or summarize multiple values
            
            OUTPUT FORMAT:
            {{
                "extractions": [
                    {{
                        "parameter": "exact parameter name from Excel",
                        "comment": "the comment that guided extraction", 
                        "page": {page_num},
                        "value": "EXACT value(s) as shown (e.g., '18,18,17,17,17' for multiple readings)",
                        "confidence": "high/medium/low",
                        "location_found": "where you found it (e.g., Step 5.3, table row, calculation)",
                        "notes": "any relevant observations"
                    }}
                ]
            }}

            REMEMBER:
            - Documents mix tables AND calculations - recognize both
            - For calculations, extract the RESULT not the formula
            - For tables with multiple columns/time points, extract ALL values
            - "Calculate" in parameter name often means find a formula result
            - Handwritten values after "=" signs are important results
            - NEVER normalize multiple values into ranges or averages"""
            
            content_parts = [
                {"type": "text", "text": task},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{img_format.lower()};base64,{page_image_b64}"
                    }
                }
            ]
            
            message = HumanMessage(content=content_parts)
            response = claude_model.invoke([message])
            content = response.content if hasattr(response, 'content') else str(response)
            
            result = safe_json_parse(content)
            page_extractions = result.get("extractions", [])
            
            if page_extractions:
                print(f"        ✓ Extracted {len(page_extractions)} parameters from page {page_num}")
                for ext in page_extractions:
                    print(f"          - {ext.get('parameter')}: {ext.get('value')} ({ext.get('confidence', 'unknown')} confidence)")
                all_extractions.extend(page_extractions)
            else:
                print(f"        ⚠️ No parameters found on page {page_num}")
                    
        except Exception as e:
            print(f"        ❌ Error processing page {page_num}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"   ✅ Worker {worker_id} complete: {len(all_extractions)} total extractions")
    return all_extractions

# Parallel execution coordinator
def parallel_worker_coordinator(state: GraphState) -> GraphState:
    print("\n[PARALLEL COORDINATOR]")
    
    # Continue progress after batch creation (after 18%)
    if state.get('progress_callback'):
        state['progress_callback'](20, "Launching parallel workers...")
    
    try:
        # Parse lead agent's decision
        if not state["agent_decisions"]:
            print("   ❌ No lead agent decisions found")
            state["agent_decisions"].append({
                "agent": "parallel_workers",
                "results": []
            })
            return state
            
        lead_decision = safe_json_parse(state["agent_decisions"][0]["decision"])
        page_batches = lead_decision.get("page_batches", [])
        
        if not page_batches:
            print("   ⚠️ No page batches found in lead decision, creating default batch")
            # Create a default batch from all available pages
            all_pages = list(range(1, state["total_pages"] + 1))
            if all_pages:
                # Split pages into batches of 5
                page_batches = [all_pages[i:i+5] for i in range(0, len(all_pages), 5)]
        
        print(f"Launching {len(page_batches)} workers in parallel...")
        
        if state.get('progress_callback'):
            state['progress_callback'](22, f"Launching {len(page_batches)} workers in parallel...")
        
        # Execute workers in parallel
        with ThreadPoolExecutor(max_workers=min(len(page_batches), 3)) as executor:
            futures = []
            
            for worker_id, batch in enumerate(page_batches):
                if batch:  # Only submit if batch is not empty
                    future = executor.submit(worker_agent, batch, state, worker_id + 1)
                    futures.append(future)
            
            # Collect results
            all_results = []
            for future in futures:
                try:
                    results = future.result(timeout=300)  # 5 minute timeout per worker
                    if results:
                        all_results.extend(results)
                except Exception as e:
                    print(f"   ⚠️ Worker error: {e}")
                    continue
        
        print(f"   ✅ Parallel coordination complete: {len(all_results)} results collected")
        
        # Add progress update when complete
        if state.get('progress_callback'):
            state['progress_callback'](65, f"All workers complete: {len(all_results)} parameters extracted")
        
        state["agent_decisions"].append({
            "agent": "parallel_workers",
            "results": all_results
        })
        
    except Exception as e:
        print(f"   ❌ Error in parallel coordination: {e}")
        # Add empty results to prevent downstream errors
        state["agent_decisions"].append({
            "agent": "parallel_workers",
            "results": []
        })
    
    return state

# AGENT 3: Merger Agent - INTELLIGENT PYTHON-BASED ORDERING
# NEW: Fast Python-based merger that orders results according to target list
def merger_agent(state: GraphState) -> GraphState:
    print("\n[MERGER AGENT - Intelligent Python Ordering]")

    # Add progress update
    if state.get('progress_callback'):
        state['progress_callback'](70, "Merging and ordering results from all workers...")

    # Get worker results
    worker_results = []
    if state["agent_decisions"]:
        worker_results = state["agent_decisions"][-1].get("results", [])

    print(f"   📊 Processing {len(worker_results)} total worker results")

    # Get target list order from Excel
    try:
        excel_requirements = json.loads(state["excel_data"])
        print(f"   📋 Loaded {len(excel_requirements)} parameters from target list")
    except:
        excel_requirements = []
        print(f"   ⚠️ Could not load Excel requirements")

    # Create a mapping of parameter names to their target list index
    # Keep FIRST occurrence for duplicate parameter names
    # Strip whitespace to handle trailing spaces in Excel
    param_order_map = {}
    for idx, req in enumerate(excel_requirements):
        param_name = (req.get("Parameter", "") or req.get("parameter", "")).strip()
        if param_name and param_name not in param_order_map:
            param_order_map[param_name] = idx

    print(f"   🔢 Created ordering map for {len(param_order_map)} parameters")

    # Sort worker results according to target list order
    def get_sort_key(result):
        param = result.get("parameter", "").strip()  # Strip whitespace from extracted params too
        page = result.get("page", 0)
        # Primary sort: target list order, Secondary sort: page number
        order_index = param_order_map.get(param, 99999)  # Unknown params go to end
        return (order_index, page)

    # Sort all results intelligently using target list order
    cumulative_merged = sorted(worker_results, key=get_sort_key)

    print(f"   ✅ Sorted {len(cumulative_merged)} results according to target list order")

    # Identify missing parameters
    print(f"   🔧 Checking for missing parameters...")

    required_params = set(param_order_map.keys())
    found_params = set(r.get("parameter", "") for r in cumulative_merged)
    missing_params = required_params - found_params
    missing_parameters = [{"parameter": p, "expected_pages": "check Excel"} for p in missing_params]

    # Create final merged decision
    final_merger_decision = {
        "merged_results": cumulative_merged,
        "missing_parameters": missing_parameters,
        "merge_statistics": {
            "total_extractions": len(cumulative_merged),
            "unique_parameters": len(found_params),
            "missing_count": len(missing_params)
        }
    }

    print(f"\n   ✅ Python-based merge complete (instant):")
    print(f"      - Total extractions: {len(cumulative_merged)}")
    print(f"      - Unique parameters found: {len(found_params)}")
    print(f"      - Missing parameters: {len(missing_params)}")
    print(f"      - Results ordered by target list ✓")

    state["agent_decisions"].append({
        "agent": "merger",
        "decision": json.dumps(final_merger_decision)
    })

    return state

# AGENT 4: Validator Agent (Claude validates)
def validator_agent(state: GraphState) -> GraphState:
    print("\n[VALIDATOR AGENT - Claude 3.7 Sonnet]")
    
    # Add progress update
    if state.get('progress_callback'):
        state['progress_callback'](80, "Validating extracted parameters...")
    
    merger_decision = safe_json_parse(state["agent_decisions"][-1]["decision"])
    
    task = """Validate the merged results:
    1. Check all required parameters were found
    2. Check confidence levels
    3. Identify any suspicious values
    
    Return:
    {
        "validation_status": "pass/fail",
        "issues": [
            {"type": "missing", "parameter": "X", "pages_checked": [2,3]},
            {"type": "low_confidence", "parameter": "Y", "current_value": "..."}
        ],
        "summary": {
            "total_required": <n>,
            "successfully_extracted": <n>,
            "missing": <n>,
            "low_confidence": <n>
        }
    }"""
    
    context = {
        "merged_results": merger_decision,
        "excel_requirements": state["excel_data"]
    }
    
    response = call_claude_agent("Validator Agent", task, context)
    state["agent_decisions"].append({
        "agent": "validator",
        "decision": response
    })
    
    return state

# AGENT 5: Interactive Feedback Agent (Handles user queries from frontend)
# AGENT 5: Interactive Feedback Agent (Handles user queries from frontend)
def feedback_agent(state: GraphState) -> GraphState:
    """
    Process user feedback about missing or incorrect parameters
    """
    print("\n[INTERACTIVE FEEDBACK AGENT - User Initiated]")
    
    # Get user request from state (passed from API)
    user_request = state.get("user_feedback_request")
    
    if not user_request:
        print("   ❌ No user feedback request found")
        return state
    
    print(f"   📝 User feedback received:")
    print(f"      Parameter: {user_request.get('parameter')}")
    print(f"      Issue: {user_request.get('issue_type')}")  # 'missing' or 'incorrect'
    print(f"      Current value: {user_request.get('current_value', 'N/A')}")
    print(f"      User hint: {user_request.get('hint')}")
    
    task = f"""A user found an issue with the extraction results and needs help.
    
    Issue details:
    - Parameter: "{user_request['parameter']}"
    - Issue type: {user_request['issue_type']}
    - Page where it should be: {user_request.get('expected_page', 'unknown')}
    - Current extracted value: "{user_request.get('current_value', 'none')}"
    - User's hint: "{user_request['hint']}"
    
    Based on this feedback, determine:
    1. Which pages to check (including the expected page and nearby pages)
    2. What specific patterns to look for based on the hint
    3. How to identify the correct value
    
    Respond with:
    {{
        "search_strategy": {{
            "pages_to_check": [list of page numbers],
            "search_patterns": ["specific patterns to look for"],
            "extraction_guidance": "detailed guidance for extraction"
        }}
    }}"""
    
    context = {
        "user_feedback": user_request,
        "total_pages": state["total_pages"],
        "excel_config": state["excel_data"],
        "previous_results": state.get("final_results", [])
    }
    
    response = call_claude_agent("Feedback Agent", task, context)
    
    feedback_data = safe_json_parse(response, {
        "search_strategy": {
            "pages_to_check": [user_request.get('expected_page', 1)],
            "search_patterns": [],
            "extraction_guidance": ""
        }
    })
    
    # Store the feedback decision
    state["agent_decisions"].append({
        "agent": "feedback",
        "interaction": {
            "user_request": user_request,
            "search_strategy": feedback_data["search_strategy"],
            "pages_to_recheck": feedback_data["search_strategy"]["pages_to_check"]
        }
    })
    
    return state

# Add new API endpoint function for production use

# AGENT 6: Reprocessing Agent (Processes based on user's specific hints)
# AGENT 6: Reprocessing Agent - FIXED with direct API call pattern
# AGENT 6: Reprocessing Agent - WITH COMMENTS SUPPORT
def reprocessing_agent(state: GraphState) -> GraphState:
    """
    Reprocesses specific pages based on interactive user feedback
    Now properly uses comments column for guidance
    """
    print("\n[REPROCESSING AGENT - Claude]")
    
    feedback_interaction = state["agent_decisions"][-1].get("interaction", {})
    
    if not feedback_interaction:
        return state
    
    # Get the search strategy from feedback agent
    pages_to_check = feedback_interaction.get("pages_to_recheck", [])
    parameter = feedback_interaction["user_request"]["missing_parameter"]
    user_hint = feedback_interaction.get("user_final_hint", "")
    
    # Try to find the comment for this parameter from Excel config
    parameter_comment = ""
    try:
        import json
        excel_data = json.loads(state["excel_data"])
        for item in excel_data:
            if item.get("parameter") == parameter:
                parameter_comment = item.get("comments", "")
                break
    except:
        pass
    
    print(f"\nReprocessing '{parameter}' based on user interaction")
    print(f"Parameter comment from Excel: '{parameter_comment}'")
    print(f"Checking pages: {pages_to_check}")
    print(f"User hint: {user_hint}")
    
    reprocessed_results = []
    
    # Check each recommended page
    for page_num in pages_to_check:
        if page_num < 1 or page_num > state["total_pages"]:
            continue
            
        print(f"   📄 Checking page {page_num}...")
        
        try:
            # Get optimized image
            page_image_b64, img_format = get_optimized_image(state["pdf_path"], page_num)
            
            # Build the task with comment guidance
            task = f"""Extract parameters from page {page_num} of this pharmaceutical GxP batch record document.

            CRITICAL PHARMACEUTICAL DOCUMENT UNDERSTANDING:
            This is a GxP batch record with quality control data. Pharmaceutical documents contain:
            - Numbers as primary data (counts, measurements, percentages, calculations)
            - Defect tables AND calculation forms
            - Test results AND summary calculations
            - Both tabular data AND mathematical formulas

            DOCUMENT STRUCTURE RECOGNITION:
            1. **Defect Tables**: Rows and columns with counts
            2. **Calculation Forms**: Mathematical expressions with results
            - Look for formulas like: (A) + (B) + (C) = [RESULT]
            - Extract the FINAL RESULT after equals sign
            3. **Summary Sections**: Calculated totals and percentages
            4. **Reconciliation Sheets**: May combine tables and calculations

            VISUAL INTERPRETATION:
            - In tables: numeric values in cells (0, 1, 2, 11, 255, etc.)
            - In calculations: handwritten results after "=" signs
            - "0" (zero) is circular - common for "no defects"
            - Formulas show process: (value) + (value) = RESULT
            - Extract the RESULT, not the formula components

            INTELLIGENT EXTRACTION APPROACH:
            1. First identify what TYPE of section this is:
            - Is it a data table?
            - Is it a calculation form?
            - Is it a summary section?
            2. Apply appropriate extraction method:
            - For tables: look in specific columns
            - For calculations: find the result after "="
            - For summaries: find the final computed value

            EXTRACTION BASED ON USER INTENT:
            - NO COMMENT/EMPTY → Extract the primary value (could be in a table cell OR a calculation result)
            - WITH COMMENTS → The comment guides what to extract:
            * "calculated value" → Look for calculation results
            * "total" → Find sum/total results
            * "critical value" → Look in critical column OR critical calculation

            SPECIFIC PATTERNS TO RECOGNIZE:
            - "Calculate batch total of defects" → Find formula result (e.g., 0 + 13 + 368 + 18 = 399, extract "399")
            - "Percentage of [type] defects" → Find percentage calculation result
            - "Total quantity" → Find the final count/sum

            PARAMETER MATCHING:
            Parameters to extract: {state["excel_data"]}

            OUTPUT FORMAT:
            {{
                "extractions": [
                    {{
                        "parameter": "exact parameter name from Excel",
                        "comment": "the comment that guided extraction", 
                        "page": {page_num},
                        "value": "extracted value exactly as interpreted",
                        "confidence": "high/medium/low",
                        "notes": "any relevant observations (e.g., 'extracted from calculation result', 'found in formula')"
                    }}
                ]
            }}

            REMEMBER:
            - Documents mix tables AND calculations - recognize both
            - For calculations, extract the RESULT not the formula
            - "Calculate" in parameter name often means find a formula result
            - Handwritten values after "=" signs are important results"""
            
            # Create message
            page_message = [{
                "type": "text", 
                "text": task
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
                "max_tokens": 16000
            }
            
            # Direct API call
            response = requests.post(LLM_URL, json=payload, headers=headers, timeout=120)
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data:
                    content = data['choices'][0]['message']['content']
                elif 'completion' in data:
                    content = data['completion']['content']
                else:
                    print(f"        ❌ Unknown response format for page {page_num}")
                    continue
                
                # Extract result
                result = safe_json_parse(content)
                if result and result.get("value"):
                    print(f"        ✅ Found on page {page_num}: {result['value']} {result.get('unit', '')}")
                    print(f"        📍 Location: {result.get('location_found', 'N/A')}")
                    print(f"        📋 Value type: {result.get('value_type', 'unknown')}")
                    reprocessed_results.append(result)
                    break  # Stop if found
                else:
                    print(f"        ❌ Not found on page {page_num}")
                    
            else:
                print(f"        ❌ API error for page {page_num}: {response.status_code}")
                if response.status_code == 400:
                    print(f"        📝 Error details: {response.text[:500]}...")
                
        except Exception as e:
            print(f"        ❌ Error processing page {page_num}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    state["agent_decisions"].append({
        "agent": "reprocessing",
        "results": reprocessed_results,
        "search_details": {
            "parameter": parameter,
            "comment": parameter_comment,
            "pages_checked": pages_to_check,
            "hint_used": user_hint,
            "found": len(reprocessed_results) > 0
        }
    })
    
    return state

# AGENT 7: Final Output Agent (Claude creates final report)
# AGENT 7: Final Output Agent (Claude creates final report)
# FINAL OUTPUT AGENT - COMPLETE FIX (Ensures ALL parameters are saved)
def final_output_agent(state: GraphState) -> GraphState:
    print("\n[FINAL OUTPUT AGENT - Direct Save]")
    
    if state.get('progress_callback'):
        state['progress_callback'](90, "Creating final Excel report...")
    
    # Get merger results directly
    merger_decision = {}
    all_merged_results = []
    
    try:
        # Find merger decision
        for decision in state["agent_decisions"]:
            if decision.get("agent") == "merger":
                merger_decision = safe_json_parse(decision.get("decision", "{}"))
                all_merged_results = merger_decision.get("merged_results", [])
                break
        
        print(f"   📊 Retrieved {len(all_merged_results)} merged results")
        
        # Get any reprocessed results
        reprocessed = []
        for decision in reversed(state["agent_decisions"]):
            if decision.get("agent") == "reprocessing":
                reprocessed = decision.get("results", [])
                break
        
        if reprocessed:
            print(f"   📊 Adding {len(reprocessed)} reprocessed results")
            all_merged_results.extend(reprocessed)
        
    except Exception as e:
        print(f"   ⚠️ Error gathering results: {e}")
    
    # CRITICAL: Skip Claude for large result sets to avoid truncation
    if len(all_merged_results) > 50:
        print(f"   ℹ️ Large result set ({len(all_merged_results)} items) - using direct save")
        
        # Process results directly without Claude
        final_results = []
        
        for result in all_merged_results:
            # Clean up each result
            cleaned = {
                "parameter": result.get("parameter", ""),
                "page": result.get("page", ""),
                "value": str(result.get("value", "")),
                "unit": ""
            }
            
            # Add comment if exists
            if result.get("comment"):
                cleaned["comment"] = result.get("comment", "")
            
            # Extract unit from value if present
            value_str = str(result.get("value", ""))
            
            # Common unit patterns
            unit_patterns = [
                (r'(\d+\.?\d*)\s*(%)', '%'),
                (r'(\d+\.?\d*)\s*(g/L)', 'g/L'),
                (r'(\d+\.?\d*)\s*(g/mL)', 'g/mL'),
                (r'(\d+\.?\d*)\s*(kg)', 'kg'),
                (r'(\d+\.?\d*)\s*(L)', 'L'),
                (r'(\d+\.?\d*)\s*(mL)', 'mL'),
                (r'(\d+\.?\d*)\s*(LPM)', 'LPM'),
                (r'(\d+\.?\d*)\s*(psig)', 'psig'),
                (r'(\d+\.?\d*)\s*(°C)', '°C'),
            ]
            
            import re
            for pattern, unit in unit_patterns:
                match = re.search(pattern, value_str)
                if match:
                    cleaned["value"] = match.group(1)
                    cleaned["unit"] = unit
                    break
            
            final_results.append(cleaned)
        
        # Calculate statistics
        unique_params = set(r["parameter"] for r in final_results)
        unique_pages = set(r["page"] for r in final_results)
        
        final_data = {
            "final_results": final_results,
            "statistics": {
                "total_parameters": len(unique_params),
                "total_extractions": len(final_results),
                "successfully_extracted": len(final_results),
                "extraction_rate": "100%",
                "pages_processed": len(unique_pages)
            },
            "still_missing": []
        }
        
    else:
        # For smaller sets, can use Claude but with explicit instructions
        print(f"   📤 Small result set - using Claude for formatting")
        
        task = """Format the extraction results for final output.
        
        CRITICAL: KEEP EVERY SINGLE EXTRACTION - DO NOT REMOVE ANY
        
        Rules:
        1. Keep ALL rows even if parameter appears multiple times
        2. Split value and unit properly
        3. Remove confidence, location_found, notes columns
        4. Keep comment column if present
        
        Return JSON with ALL results:
        {
            "final_results": [...every single extraction...],
            "statistics": {...},
            "still_missing": []
        }"""
        
        context = {
            "merged_results": all_merged_results,
            "excel_requirements": state["excel_data"][:1000]  # Truncate to avoid token limits
        }
        
        response = call_claude_agent("Final Output Agent", task, context)
        final_data = safe_json_parse(response, {})
        
        # FALLBACK: If Claude returned fewer results, use original
        if len(final_data.get("final_results", [])) < len(all_merged_results):
            print(f"   ⚠️ Claude returned only {len(final_data.get('final_results', []))} results")
            print(f"   ✅ Using all {len(all_merged_results)} original results instead")
            
            # Use the direct processing from above
            final_results = []
            for result in all_merged_results:
                cleaned = {
                    "parameter": result.get("parameter", ""),
                    "page": result.get("page", ""),
                    "value": str(result.get("value", "")),
                    "unit": ""
                }
                if result.get("comment"):
                    cleaned["comment"] = result.get("comment", "")
                final_results.append(cleaned)
            
            final_data["final_results"] = final_results
    
    # Save to Excel
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = os.path.splitext(os.path.basename(state.get("pdf_path", "unknown")))[0]
        
        current_dir = os.getcwd()
        if "backend" in current_dir:
            temp_dir = os.path.join(current_dir, "temp", "hbr_results")
        else:
            temp_dir = os.path.join(current_dir, "backend", "temp", "hbr_results")
        
        os.makedirs(temp_dir, exist_ok=True)
        
        output_filename = f"{pdf_filename}_hbr_multiagent_results_{timestamp}.xlsx"
        output_path = os.path.join(temp_dir, output_filename)
        
        final_results = final_data.get("final_results", [])
        
        print(f"\n   📊 Saving {len(final_results)} extractions to Excel...")
        
        if final_results:
            df = pd.DataFrame(final_results)
            
            # Remove only metadata columns, keep data columns
            columns_to_remove = ['confidence', 'location_found', 'notes', 'extraction_type', 'consistency']
            for col in columns_to_remove:
                if col in df.columns:
                    df = df.drop(col, axis=1)
            
            # Determine column order
            if 'comment' in df.columns:
                column_order = ['parameter', 'comment', 'page', 'value', 'unit']
            else:
                column_order = ['parameter', 'page', 'value', 'unit']
            
            # Only keep columns that exist
            column_order = [col for col in column_order if col in df.columns]
            
            # Add any remaining columns
            for col in df.columns:
                if col not in column_order:
                    column_order.append(col)
            
            df = df[column_order]
            
            # Fill empty values
            df = df.fillna('')
            
            # Create Excel with multiple sheets
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # Main results
                df.to_excel(writer, sheet_name='Extraction Results', index=False)
                
                # Statistics
                unique_params = df['parameter'].nunique()
                total_rows = len(df)
                unique_pages = df['page'].nunique()
                
                stats_df = pd.DataFrame([
                    ["Total Unique Parameters", unique_params],
                    ["Total Extractions", total_rows],
                    ["Pages with Data", unique_pages],
                    ["Average Extractions per Page", round(total_rows/unique_pages, 1) if unique_pages > 0 else 0]
                ], columns=["Metric", "Value"])
                stats_df.to_excel(writer, sheet_name='Statistics', index=False)
                
                # Parameter frequency (how many times each parameter appears)
                param_freq = df['parameter'].value_counts().reset_index()
                param_freq.columns = ['Parameter', 'Count']
                param_freq.to_excel(writer, sheet_name='Parameter Frequency', index=False)
                
                # Page coverage (how many parameters per page)
                page_coverage = df.groupby('page')['parameter'].count().reset_index()
                page_coverage.columns = ['Page', 'Parameter Count']
                page_coverage = page_coverage.sort_values('Page')
                page_coverage.to_excel(writer, sheet_name='Page Coverage', index=False)
            
            print(f"\n✅ Results saved to: {output_path}")
            print(f"   📁 Location: {os.path.abspath(output_path)}")
            print(f"\n📊 Final Statistics:")
            print(f"   Total Extractions Saved: {total_rows}")
            print(f"   Unique Parameters: {unique_params}")
            print(f"   Pages with Data: {unique_pages}")
            
            # Show top parameters by frequency
            top_params = param_freq.head(5)
            if not top_params.empty:
                print(f"\n   📈 Most Frequent Parameters:")
                for _, row in top_params.iterrows():
                    print(f"      - {row['Parameter']}: {row['Count']} times")
            
            state["output_excel_path"] = output_path
            
        else:
            print(f"\n⚠️ No results to save to Excel")
            state["output_excel_path"] = None
            
    except Exception as e:
        print(f"   ❌ Error saving Excel: {e}")
        import traceback
        traceback.print_exc()
        state["output_excel_path"] = None
    
    # Store final data
    state["final_results"] = json.dumps(final_data)
    
    # Final progress
    if state.get('progress_callback'):
        state['progress_callback'](95, "Finalizing HBR extraction...")
        state['progress_callback'](100, "HBR extraction complete!")
    
    return state
# Add these NEW functions after final_output_agent (after line 674):

def build_feedback_workflow():
    """Build workflow for user-initiated feedback"""
    workflow = StateGraph(GraphState)
    
    workflow.add_node("feedback", feedback_agent)
    workflow.add_node("reprocess", reprocessing_agent)
    workflow.add_node("update_final", update_final_output_agent)
    
    workflow.add_edge("feedback", "reprocess")
    workflow.add_edge("reprocess", "update_final")
    
    workflow.set_entry_point("feedback")
    
    return workflow.compile()

def update_final_output_agent(state: GraphState) -> GraphState:
    """Update final results with reprocessed values"""
    print("\n[UPDATE FINAL OUTPUT AGENT]")
    
    # Get reprocessing results
    reprocessed = []
    for decision in reversed(state["agent_decisions"]):
        if decision.get("agent") == "reprocessing":
            reprocessed = decision.get("results", [])
            break
    
    if not reprocessed:
        print("   ⚠️ No reprocessed results to update")
        return state
    
    # Load existing final results
    try:
        final_data = json.loads(state.get("final_results", "{}"))
        existing_results = final_data.get("final_results", [])
        
        # Update or add reprocessed results
        for new_result in reprocessed:
            parameter = new_result.get("parameter")
            page = new_result.get("page")
            
            # Find and replace existing result
            replaced = False
            for i, existing in enumerate(existing_results):
                if (existing.get("parameter") == parameter and 
                    existing.get("page") == page):
                    # Replace with new result
                    existing_results[i] = {
                        "parameter": parameter,
                        "page": page,
                        "value": new_result.get("value"),
                        "unit": new_result.get("unit", "")
                    }
                    replaced = True
                    print(f"   ✅ Replaced value for {parameter} on page {page}")
                    break
            
            # If not found, add as new result
            if not replaced:
                existing_results.append({
                    "parameter": parameter,
                    "page": page,
                    "value": new_result.get("value"),
                    "unit": new_result.get("unit", "")
                })
                print(f"   ✅ Added new value for {parameter} on page {page}")
        
        # Update statistics
        total_params = len(set(r["parameter"] for r in existing_results))
        successful = len([r for r in existing_results if r.get("value")])
        
        final_data["final_results"] = existing_results
        final_data["statistics"]["successfully_extracted"] = successful
        final_data["statistics"]["extraction_rate"] = f"{(successful/total_params*100):.1f}%" if total_params > 0 else "0%"
        
        # Save updated results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = os.path.splitext(os.path.basename(state.get("pdf_path", "unknown")))[0]
        
        # Save in the same directory
        current_dir = os.getcwd()
        if "backend" in current_dir:
            temp_dir = os.path.join(current_dir, "temp", "hbr_results")
        else:
            temp_dir = os.path.join(current_dir, "backend", "temp", "hbr_results")
        
        os.makedirs(temp_dir, exist_ok=True)
        
        output_filename = f"{pdf_filename}_hbr_multiagent_updated_{timestamp}.xlsx"
        output_path = os.path.join(temp_dir, output_filename)
        
        # Create DataFrame
        df = pd.DataFrame(existing_results)
        if 'confidence' in df.columns:
            df = df.drop('confidence', axis=1)
        df.to_excel(output_path, index=False)
        
        print(f"\n✅ Updated results saved to: {output_path}")
        state["updated_excel_path"] = output_path
        state["final_results"] = json.dumps(final_data)
        
    except Exception as e:
        print(f"   ❌ Error updating final results: {e}")
        import traceback
        traceback.print_exc()
    
    return state

def process_user_feedback(
    pdf_path: str,
    excel_path: str,
    parameter: str,
    issue_type: str,  # 'missing' or 'incorrect'
    expected_page: int,
    current_value: str = None,
    hint: str = "",
    previous_state: Dict = None
) -> Dict[str, Any]:
    """
    Process user feedback about missing or incorrect parameters
    
    Args:
        pdf_path: Path to PDF file
        excel_path: Path to Excel config
        parameter: Parameter name with issue
        issue_type: 'missing' or 'incorrect'
        expected_page: Page where parameter should be
        current_value: Current extracted value (if incorrect)
        hint: User's hint about where/how to find it
        previous_state: Previous extraction state
        
    Returns:
        Dictionary with status and feedback results matching FastAPI expectations
    """
    
    print(f"\n[DEBUG] ========== process_user_feedback START ==========")
    print(f"[DEBUG] Function called from: hbr_multiagent.py")
    print(f"[DEBUG] PDF path: {pdf_path}")
    print(f"[DEBUG] Excel path: {excel_path}")
    print(f"[DEBUG] Parameter: {parameter}")
    print(f"[DEBUG] Expected page: {expected_page}")
    print(f"[DEBUG] User hint: {hint}")
    print(f"[DEBUG] Issue type: {issue_type}")
    print(f"[DEBUG] Has previous state: {previous_state is not None}")
    
    # Parse the user's hint to understand what they're asking for
    task = f"""A user is having trouble finding a parameter in the extraction results.

User's feedback:
- Parameter: "{parameter}"
- Expected page: {expected_page}
- User's message: "{hint}"
- Issue type: {issue_type}

Based on this feedback, analyze:
1. What the user is looking for - could be ANY type of value (specification, actual result, limit, range, etc.)
2. If no specific hint is given, just look for the parameter value as it appears in the document
3. Why it might have been missed
4. What pages to check (including nearby pages)
5. Specific patterns or locations to look for

IMPORTANT: 
- If the user's hint mentions a specific type of value (like "specification" or "actual"), focus on that
- If NO specific type is mentioned, just extract whatever value is associated with the parameter
- Don't assume it's always a specification value

Return a helpful response:
{{
    "understood_request": "what the user wants (be specific based on their hint, or general if no hint)",
    "likely_issue": "why it was missed",
    "pages_to_check": [list of page numbers],
    "search_guidance": "specific patterns to look for based on the hint (or general extraction if no hint)",
    "assistant_message": "helpful message to the user"
}}"""
    
    try:
        print(f"[DEBUG] Calling Claude agent...")
        
        # Call Claude to analyze the feedback
        response = call_claude_agent("Feedback Analyzer", task, {
            "user_feedback": {
                "parameter": parameter,
                "hint": hint,
                "expected_page": expected_page
            },
            "excel_path": excel_path
        })
        
        print(f"[DEBUG] Claude response received, length: {len(response)}")
        print(f"[DEBUG] Claude raw response (first 200 chars): {response[:200]}")
        
        feedback_analysis = safe_json_parse(response, {
            "understood_request": "Find parameter value",
            "likely_issue": "Parameter may have been missed",
            "pages_to_check": [expected_page],
            "search_guidance": "",
            "assistant_message": "I'll help you find that parameter."
        })
        
        print(f"[DEBUG] Parsed feedback analysis: {json.dumps(feedback_analysis, indent=2)}")
        
        # Build return structure
        return_data = {
            "status": "success",
            "feedback_processed": {
                "parameter": parameter,
                "issue_type": issue_type,
                "result": "ready_for_reprocessing",
                "assistant_message": feedback_analysis.get("assistant_message", "I understand you're looking for the parameter."),
                "recommendations": {
                    "pages_to_check": feedback_analysis.get("pages_to_check", [expected_page]),
                    "what_to_look_for": feedback_analysis.get("search_guidance", ""),
                    "understood_request": feedback_analysis.get("understood_request", "")
                }
            },
            "updated_excel_path": None  # No Excel update at this stage, just analysis
        }
        
        print(f"[DEBUG] Return data structure: {json.dumps(return_data, indent=2)}")
        print(f"[DEBUG] ========== process_user_feedback END SUCCESS ==========\n")
        
        return return_data
        
    except Exception as e:
        print(f"[DEBUG] ❌ Exception occurred: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"[DEBUG] Full traceback:")
        traceback.print_exc()
        
        error_return = {
            "status": "error",
            "error": str(e),
            "feedback_processed": {
                "parameter": parameter,
                "issue_type": issue_type,
                "result": "error"
            },
            "updated_excel_path": None  # Include this key even on error
        }
        
        print(f"[DEBUG] Error return data: {json.dumps(error_return, indent=2)}")
        print(f"[DEBUG] ========== process_user_feedback END ERROR ==========\n")
        
        return error_return
# Build the graph WITHOUT preprocessing
def build_claude_graph():
    """Build the LangGraph workflow - without automatic feedback"""
    workflow = StateGraph(GraphState)
    
    # Add nodes
    workflow.add_node("lead", lead_agent)
    workflow.add_node("workers", parallel_worker_coordinator)
    workflow.add_node("merger", merger_agent)
    workflow.add_node("validator", validator_agent)
    workflow.add_node("final", final_output_agent)
    
    # Linear flow WITHOUT automatic feedback
    workflow.add_edge("lead", "workers")
    workflow.add_edge("workers", "merger")
    workflow.add_edge("merger", "validator")
    workflow.add_edge("validator", "final")  # Go directly to final
    
    workflow.set_entry_point("lead")
    
    return workflow.compile()

# Create a separate workflow for user feedbac

# Main execution
def run_claude_multiagent(pdf_path: str, excel_path: str, progress_callback=None):
    """Run the Claude-powered multi-agent system"""
    # Reset global progress counter for new session
    global _global_progress
    _global_progress = 25
    
    print("="*80)
    print("CLAUDE MULTI-AGENT OCR SYSTEM (OPTIMIZED)")
    print("="*80)
    
    # Start multiagent processing at reasonable level (continuing after app.py's 5%)
    if progress_callback:
        progress_callback(8, "Initializing multi-agent HBR system...")
    
    # Convert Excel for Claude
    print("Loading PDF and Excel...")
    if progress_callback:
        progress_callback(10, "Loading PDF and Excel configuration...")
        
    excel_json = excel_to_json_string(excel_path)
    
    # Get PDF page count without converting all images
    pdf_document = fitz.open(pdf_path)
    total_pages = len(pdf_document)
    pdf_document.close()
    
    print(f"✅ PDF has {total_pages} pages")
    print(f"✅ Loaded configuration from Excel")
    
    if progress_callback:
        progress_callback(12, f"PDF loaded: {total_pages} pages detected")
    
    # Initialize state with PDF path instead of pre-converted images
    initial_state = {
        "pdf_path": pdf_path,
        "config_excel": excel_path,
        "current_task": "extraction",
        "total_pages": total_pages,
        "excel_data": excel_json,
        "agent_decisions": [],
        "final_results": [],
        "conversation_history": [],
        "progress_callback": progress_callback  # Add progress callback to state
    }
    
    # Run the workflow
    app = build_claude_graph()
    final_state = app.invoke(initial_state)
    
    print("\n" + "="*80)
    print("EXECUTION COMPLETE")
    print("="*80)
    
    return final_state

# Example usage
if __name__ == "__main__":
    pdf_path: str
    config_excel: str 
    current_task: str
    total_pages: int  # Changed from all_pages_images: Dict[int, str]
    excel_data: str
    agent_decisions: List[Dict]
    final_results: List[Dict]
    conversation_history: List[str]
    excel_path = "config.xlsx"
    
    result = run_claude_multiagent(pdf_path, excel_path)


