import base64
from collections import defaultdict
import time  
import csv
import json
import re
import os
import traceback
import numpy as np
import pandas as pd
from openpyxl import load_workbook
import requests
import urllib3
import PyPDF2, fitz
from datetime import datetime
from PIL import Image
import io
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
import boto3
import botocore

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
#os.environ['TEXTRACT_ENV'] = 'local'
# Check environment for boto3 configuration
textract_env = os.getenv('TEXTRACT_ENV')
print(f"TEXTRACT_ENV: {textract_env}")

# Configure boto3 session based on environment
if textract_env == 'local':
    boto3_session = None
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

llm_url = None
llm_api_key = REDACTED

# Simple helper functions replacing those from spec_range.py
def check_units(value, unit):
    return value, unit

def map_metadata(key, value):
    return key, value

def map_result_value(value, unit):
    return value

def rename_key_single(key):
    return key

def validate_continue_page_header(header):
    return True

def validate_ignore_page_header(header):
    return True

def validate_lower_limit_column(col_name):
    return "lower" in col_name.lower() or "min" in col_name.lower()

def validate_result_column(col_name):
    return "result" in col_name.lower() or "sample" in col_name.lower()

def validate_specification_column(col_name):
    return "spec" in col_name.lower() or "requirement" in col_name.lower()

def validate_test_column(col_name):
    return "test" in col_name.lower() or "parameter" in col_name.lower()

def validate_units_column(col_name):
    return "unit" in col_name.lower()

def validate_upper_limit_column(col_name):
    return "upper" in col_name.lower() or "max" in col_name.lower()

class TextractProcessor:
    def __init__(self, region_name=None, output_path=None):
        """
        Initialize the TextractProcessor with simplified parameters
        
        Args:
            region_name: AWS region (optional)
            output_path: Path to save output files (optional)
        """
        print(f"TextractProcessor initializing with region: {region_name or 'us-east-1'}")
        
        # Store the region name for later use
        self.region_name = region_name or 'us-east-1'
        
        # Initialize instance variables
        self.json_data_list = []
        self.table_row_box = {}
        self.blocks_map = {}
        self.tab_ind = 0
        self.base_path_basic = output_path or './output'
        self.key_value_boxes = {}
        self.key_vals = {}
        self.ignore_page_header = []
        self.continue_page_header = []
        self.metadata_names = ["Manufacturing Date","Expiry Date","Product Name",
                                "Product Number","Product Code","Manufacturer",
                                "Packaging Site","Storage", "Batch Number", "Material Number", 
                                "Product Name", "DoM", "Fill Date"]

        # Ensure output directory exists
        os.makedirs(self.base_path_basic, exist_ok=True)
        print(f"Output directory created/confirmed: {self.base_path_basic}")
        
        # We'll create AWS clients on demand in each method that needs them
        
        # Progress callback support
        self.progress_callback = None
    
    def set_progress_callback(self, callback):
        """Set a callback function for progress updates"""
        self.progress_callback = callback
    
    def update_progress(self, progress: int, message: str):
        """Update progress if callback is set"""
        if self.progress_callback:
            self.progress_callback(progress, message)

    def get_text(self, block, blocks_map):
        """Extracts text from a given block and its children (for WORD and LINE blocks), with error handling for missing blocks."""
        text = ''
        box = defaultdict(int)
        if 'Relationships' in block:
            for relationship in block['Relationships']:
                if relationship['Type'] == 'CHILD':
                    for child_id in relationship['Ids']:
                        child_block = blocks_map.get(child_id)  # Use get() to safely handle missing blocks
                        if child_block is not None:
                            if child_block['BlockType'] == 'WORD' or child_block['BlockType'] == 'LINE':
                                text += child_block['Text'] + ' '
                            if child_block['BlockType'] == 'SELECTION_ELEMENT' and child_block['SelectionStatus'] == 'SELECTED':
                                text += 'X '
                            box['text'] = text
                            box["Left"] = min(box.get('Left',1),child_block['Geometry']['BoundingBox']['Left'])
                            box["Top"] = min(box.get('Top',1),child_block['Geometry']['BoundingBox']['Top'])
                            box["Right"] = max(box.get('Right',0),child_block['Geometry']['BoundingBox']['Left'] + child_block['Geometry']['BoundingBox']['Width'])
                            box["Bottom"] = max(box.get('Bottom',0),child_block['Geometry']['BoundingBox']['Top'] + child_block['Geometry']['BoundingBox']['Height'])
                            box["Confidence"] = max(box["Confidence"], child_block["Confidence"])
                            box["Page"] = child_block["Page"]
                        else:
                            print(f"Warning: Block with Id {child_id} not found in blocks_map.")
            box["Width"] = box['Right']-box['Left']
            box["Height"] = box['Bottom']-box['Top']
        return text.strip(), box

    def merge(self, dict1, dict2):
        for i in dict2.keys():
            dict1[i] = dict2[i]
        return dict1

    def get_key_value_sets(self, blocks):
        blocks_map = {block['Id']: block for block in blocks}
        key_value_blocks = [block for block in blocks if block['BlockType'] == 'KEY_VALUE_SET']

        key_value_pairs = {}
        for block in key_value_blocks:
            key = ''
            value = ''
            if block['EntityTypes'] == ['KEY']:
                key, box = self.get_text(block, blocks_map)
                self.key_value_boxes[key.strip()] = box
                for relation in block.get('Relationships', []):
                    if relation['Type'] == 'VALUE':
                        for value_id in relation['Ids']:
                            value, box = self.get_text(blocks_map.get(value_id, {}), blocks_map)
                key_value_pairs[key.strip()] = [value.strip(), box]
                self.key_value_boxes[value.strip()] = box

        return key_value_pairs

    def get_table_csv_results(self, blocks):
        block_types = []
        table_blocks = []
        for block in blocks:
            self.blocks_map[block['Id']] = block
            if block['BlockType'] not in block_types:
                block_types.append(block['BlockType'])

            if block['BlockType'] == "TABLE":
                table_blocks.append(block)
        if len(table_blocks) <= 0:
            return "<b> NO Table FOUND </b>"
        csv_f = ''
        for table in table_blocks:
            self.tab_ind += 1
            csv_f += self.generate_table_csv(table, self.blocks_map, self.tab_ind)
            csv_f += '\n\n'

        return csv_f

    def get_line_block_results(self, blocks):
        for block in blocks:
            if block['BlockType'] in ['LINE', 'WORD']:
                # Simple validation to identify headers
                if block['Text'].lower().startswith('page') or block['Text'].lower().startswith('continued'):
                    if 'page' in block['Text'].lower():
                        self.ignore_page_header.append(block["Page"])
                    if 'continued' in block['Text'].lower():
                        self.continue_page_header.append(block["Page"])

    def generate_table_csv(self, table_result, blocks_map, table_index):
        rows, box = self.get_rows_columns_map(table_result, blocks_map)
        table_id = 'Table_' + str(table_index)
        csv_f = 'Table: {0}\n\n'.format(table_id)
        self.table_row_box[table_index] = box

        # Determine the maximum number of columns in any row
        max_columns = 0
        for row_index, cols in rows.items():
            max_columns = max(max_columns, max(cols.keys()) if cols else 0)
        
        # Create properly formatted CSV with consistent number of columns
        for row_index, cols in rows.items():
            row_text = ""
            # Ensure each row has the same number of columns with proper escaping
            for col_index in range(1, max_columns + 1):
                cell_text = cols.get(col_index, "").replace(',', '|').replace('"', '""')
                # Properly quote cells with commas or quotes
                if ',' in cell_text or '"' in cell_text or '\n' in cell_text:
                    cell_text = f'"{cell_text}"'
                row_text += cell_text + ","
            
            csv_f += row_text.rstrip(',') + '\n'  # Remove trailing comma
            
        csv_f += '\n\n\n'
        return csv_f

    def get_rows_columns_map(self, table_result, blocks_map):
        rows = {}
        row_boxes = {}
        for relationship in table_result['Relationships']:
            if relationship['Type'] == 'CHILD':
                for child_id in relationship['Ids']:
                    cell = blocks_map[child_id]
                    if cell['BlockType'] == 'CELL':
                        row_index = cell['RowIndex']
                        col_index = cell['ColumnIndex']
                        if row_index not in rows:
                            rows[row_index] = {}
                            row_boxes[row_index] = {}
                        
                        text, box = self.get_text(cell, blocks_map)
                        rows[row_index][col_index] = text
                        row_boxes[row_index][col_index] = box
        
        return rows, row_boxes
    
    def check_header(self, row):
        headers = {}
        for ind, col in enumerate(row):
            col = col.lower().strip()
            if "result" in col or "sample" in col:
                headers["result"] = ind
            elif "specif" in col or "spec." in col or "acceptance" in col or "req" in col:
                headers["specification"] = ind
            elif "test" in col or "parameter" in col or "characteristic" in col:
                headers["test"] = ind
            elif "unit" in col:
                headers["units"] = ind
            elif "lower" in col or "min" in col:
                headers["lower_limit"] = ind
            elif "upper" in col or "max" in col:
                headers["upper_limit"] = ind
        return headers
    
    def fill_row_based_on_header(self, row, header_map, curr_table, line):
        row_json = {}
        for key, ind in header_map.items():
            row_json[key] = row[ind] if ind < len(row) else ""
        
        for i in self.metadata_names:
            if i in self.key_vals.keys():
                row_json[i] = self.key_vals[i]
        
        row_json["table"] = curr_table
        row_json["line"] = line
        row_json["box"] = self.table_row_box[curr_table]
        
        return row_json

    def fill_row_based_on_data(self, result, test, specification, units, lower_limit, upper_limit, box, llm):
        row_json = {}
        row_json["result"] = result
        row_json["test"] = test
        row_json["specification"] = specification
        row_json["units"] = units
        row_json["lower_limit"] = lower_limit
        row_json["upper_limit"] = upper_limit
        row_json["box"] = box
        row_json["predictions"] = llm
        
        for i in self.metadata_names:
            if i in self.key_vals.keys():
                row_json[i] = self.key_vals[i]
        
        return row_json

    def read_csv_convert_to_df(self, file, key_value_pairs):
        data = []
        current_table = None
        headers = {}
        
        with open(file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith('Table: '):
                    current_table = line.replace('Table: ', '').strip()
                    headers = {}
                    continue
                
                row = line.split(',')
                row = [x.strip() for x in row if x.strip()]
                
                if not row:
                    continue
                
                if not headers and len(row) > 1:
                    headers = self.check_header(row)
                    continue
                
                if headers and len(row) > 1:
                    row_json = self.fill_row_based_on_header(row, headers, current_table, line)
                    data.append(row_json)
        
        # Update the key-value pairs
        for key, (value, box) in key_value_pairs.items():
            self.key_vals[key] = value
        
        # Create a dataframe
        df = pd.DataFrame(data)
        
        # Add extra COA details as rows
        df = self.add_extra_coa_details_as_new_rows(key_value_pairs, df)
        
        return df

    def add_extra_coa_details_as_new_rows(self, key_value_pairs, df):
        # Extract metadata to add as rows
        additional_rows = []
        
        for key, (value, box) in key_value_pairs.items():
            if key in self.metadata_names:
                continue  # Skip metadata that's already included
            
            # Create a new row for this key-value pair
            row = {"test": key, "result": value}
            
            # Add any existing metadata
            for meta in self.metadata_names:
                if meta in self.key_vals:
                    row[meta] = self.key_vals[meta]
            
            additional_rows.append(row)
        
        # Add the new rows to the dataframe
        if additional_rows:
            additional_df = pd.DataFrame(additional_rows)
            df = pd.concat([df, additional_df], ignore_index=True)
        
        return df

    def extract_data_from_response(self, responses):
        blocks = []
        for page in responses:
            if 'Blocks' in page:
                blocks.extend(page['Blocks'])
            else:
                print(f"Warning: 'Blocks' key not found in response page. Skipping this page.")
        
        key_value_pairs = self.get_key_value_sets(blocks)
        table_data = self.get_table_csv_results(blocks)
        self.get_line_block_results(blocks)
        
        return key_value_pairs, table_data

    def get_pdf_page_dimensions(self, pdf_path):
        pdf_dimensions = {}
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pdf_dimensions[page_num + 1] = (page.rect.width, page.rect.height)
            doc.close()
        except Exception as e:
            print(f"Error getting PDF dimensions: {e}")
        return pdf_dimensions
    
    def get_pred(self, pdf_path, box, page_number):
        try:
            # Get page dimensions
            pdf_dimensions = self.get_pdf_page_dimensions(pdf_path)
            if page_number not in pdf_dimensions:
                return ""
            
            page_width, page_height = pdf_dimensions[page_number]
            
            # Extract dimensions and position
            left = box.get('Left', 0) * page_width
            top = box.get('Top', 0) * page_height
            width = box.get('Width', 0) * page_width
            height = box.get('Height', 0) * page_height
            
            # Open the PDF file
            doc = fitz.open(pdf_path)
            page = doc.load_page(page_number - 1)  # PyMuPDF is 0-indexed
            
            # Define the rectangle to extract (left, top, right, bottom)
            rect = fitz.Rect(left, top, left + width, top + height)
            
            # Extract text from the region
            text = page.get_text("text", clip=rect)
            
            # Close the PDF
            doc.close()
            
            return text.strip()
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return ""

    def add_block_info_to_json(self, json_data_list, blocks_map, pdf_path):
        """Add additional information from blocks to the JSON data."""
        updated_json_data_list = []
        
        # Get the real PDF page dimensions for each page
        pdf_dimensions = self.get_pdf_page_dimensions(pdf_path)

        for record in json_data_list:
            # Skip if no box information
            if 'box' not in record or not record['box']:
                updated_json_data_list.append(record)
                continue
            
            # Get the page number
            page = None
            box = None
            confidence = 0
            
            # If it's a row with a specific cell, use that information
            if isinstance(record['box'], dict) and record.get('line'):
                # Try to parse row and column from the line
                cells = record['box']
                if cells:
                    for cell_key, cell_box in cells.items():
                        if 'Page' in cell_box:
                            page = cell_box['Page']
                            box = cell_box
                            confidence = cell_box.get('Confidence', 0)
                            break
            
            # Skip if we couldn't determine the page
            if not page or not box:
                updated_json_data_list.append(record)
                continue

            # Get predictions from the PDF for this block
            pred = self.get_pred(pdf_path, box, page)
            
            # Get page dimensions
            page_width, page_height = pdf_dimensions.get(page, (612, 792))  # Default to standard US Letter size
            
            # Calculate block dimensions as percentages of the page
            block_width_percentage = box.get('Width', 0)
            block_height_percentage = box.get('Height', 0)
            block_left_percentage = box.get('Left', 0)
            block_top_percentage = box.get('Top', 0)
            
            # Check if this is a metadata record
            is_metadata = False
            for meta_name in self.metadata_names:
                if meta_name in record and record[meta_name]:
                    is_metadata = True
                    break
            
            # Add information to the record
            record.update({
                'page': page,
                'confidence': confidence,
                'blockWidth': block_width_percentage,
                'blockHeight': block_height_percentage,
                'blockLeft': block_left_percentage,      # % from the left
                'blockTop': block_top_percentage,         # % from the top
                'page_width': page_width,
                'page_height': page_height,
                "predictions": pred
            })

            # Always include metadata records, and include non-metadata records with results
            if is_metadata or record['result']:
                updated_json_data_list.append(record)

        return updated_json_data_list

    def extract_text_from_block(self, block, block_map):
        """Extract text from a block and its children recursively"""
        text = block.get("Text", "")
        
        # If the block already has text, return it
        if text:
            return text
            
        # Otherwise try to get text from children
        if "Relationships" in block:
            child_texts = []
            for relationship in block["Relationships"]:
                if relationship["Type"] == "CHILD":
                    for child_id in relationship["Ids"]:
                        if child_id in block_map:
                            child_block = block_map[child_id]
                            # Recursively get text from child blocks
                            child_text = self.extract_text_from_block(child_block, block_map)
                            if child_text:
                                child_texts.append(child_text)
            
            if child_texts:
                return " ".join(child_texts)
        
        return text

    def process_layout_blocks(self, all_blocks, blocks_map, pdf_path, layout_markdown_path):
        """
        Process LAYOUT blocks and create markdown from the already retrieved blocks
        
        Args:
            all_blocks: List of all blocks from Textract response
            blocks_map: Dictionary mapping block IDs to blocks
            pdf_path: Path to the original PDF file
            layout_markdown_path: Path to save the markdown file
        """
        print("Processing LAYOUT blocks...")
        
        # Extract LAYOUT specific blocks organized by page
        layout_by_page = {}
        layout_stats = {}
        
        for block in all_blocks:
            if block["BlockType"].startswith("LAYOUT_"):
                # Extract text content using our utility function
                full_text = self.extract_text_from_block(block, blocks_map)
                
                # Organize by page
                page_num = block.get("Page", 0)
                if page_num not in layout_by_page:
                    layout_by_page[page_num] = []
                
                layout_by_page[page_num].append({
                    "type": block["BlockType"],
                    "id": block["Id"],
                    "text": full_text,
                    "confidence": block.get("Confidence", 0),
                    "geometry": block.get("Geometry", {})
                })
                
                # Track statistics
                block_type = block["BlockType"]
                if block_type not in layout_stats:
                    layout_stats[block_type] = 0
                layout_stats[block_type] += 1
        
        # Generate markdown content
        print("Generating layout markdown content...")
        markdown_content = []
        markdown_content.append("# Document Layout Analysis\n\n")
        markdown_content.append(f"**Source:** {os.path.basename(pdf_path)}\n")
        markdown_content.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Add statistics
        markdown_content.append("## Layout Statistics\n\n")
        for block_type, count in layout_stats.items():
            layout_name = block_type.replace("LAYOUT_", "").replace("_", " ").title()
            markdown_content.append(f"- **{layout_name}:** {count} blocks\n")
        markdown_content.append("\n---\n\n")
        
        # Add content by page
        for page_num in sorted(layout_by_page.keys()):
            markdown_content.append(f"## Page {page_num}\n\n")
            
            page_blocks = layout_by_page[page_num]
            # Sort blocks by their vertical position (top to bottom)
            page_blocks.sort(key=lambda x: x["geometry"].get("BoundingBox", {}).get("Top", 0))
            
            for block in page_blocks:
                if block["text"].strip():  # Only include blocks with text content
                    block_type_clean = block["type"].replace("LAYOUT_", "").replace("_", " ").title()
                    confidence = block["confidence"]
                    
                    # Format based on block type
                    if block["type"] == "LAYOUT_TITLE":
                        markdown_content.append(f"# {block['text']}\n")
                        markdown_content.append(f"*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
                    elif block["type"] == "LAYOUT_SECTION_HEADER":
                        markdown_content.append(f"## {block['text']}\n")
                        markdown_content.append(f"*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
                    elif block["type"] == "LAYOUT_HEADER":
                        markdown_content.append(f"### Header: {block['text']}\n")
                        markdown_content.append(f"*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
                    elif block["type"] == "LAYOUT_FOOTER":
                        markdown_content.append(f"### Footer: {block['text']}\n")
                        markdown_content.append(f"*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
                    elif block["type"] == "LAYOUT_PAGE_NUMBER":
                        markdown_content.append(f"**Page Number:** {block['text']}\n")
                        markdown_content.append(f"*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
                    elif block["type"] == "LAYOUT_LIST":
                        markdown_content.append(f"**List Items:**\n")
                        # Format as list items
                        lines = block["text"].split("\n")
                        for line in lines:
                            if line.strip():
                                markdown_content.append(f"- {line.strip()}\n")
                        markdown_content.append(f"\n*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
                    elif block["type"] == "LAYOUT_TABLE":
                        markdown_content.append(f"**Table Content:**\n")
                        markdown_content.append(f"```\n{block['text']}\n```\n")
                        markdown_content.append(f"*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
                    elif block["type"] == "LAYOUT_FIGURE":
                        markdown_content.append(f"**Figure:** {block['text'] if block['text'] else '[Image/Figure detected]'}\n")
                        markdown_content.append(f"*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
                    elif block["type"] == "LAYOUT_KEY_VALUE":
                        markdown_content.append(f"**Key-Value Pairs:**\n")
                        markdown_content.append(f"{block['text']}\n")
                        markdown_content.append(f"*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
                    else:  # LAYOUT_TEXT or any other type
                        markdown_content.append(f"{block['text']}\n\n")
                        markdown_content.append(f"*{block_type_clean} (Confidence: {confidence:.1f}%)*\n\n")
            
            markdown_content.append("---\n\n")
        
        # Save markdown file
        with open(layout_markdown_path, "w", encoding="utf-8") as f:
            f.writelines(markdown_content)
        
        print(f"Layout markdown saved to: {layout_markdown_path}")
        
        # Print summary
        print(f"Layout extraction summary:")
        print(f"- Total pages processed: {len(layout_by_page)}")
        print(f"- Total layout blocks: {sum(layout_stats.values())}")
        print(f"- Block types found: {list(layout_stats.keys())}")

    def process_pdf_and_save_to_excel(self, pdf_path, csv_file_path, excel_output_path):
        """
        Process a PDF file and save results to Excel for GPT extractor
        Now includes layout extraction as markdown
        
        Args:
            pdf_path: Path to the PDF file
            csv_file_path: Path to save intermediate CSV output
            excel_output_path: Path to save Excel output for GPT extractor
        
        Returns:
            Path to the Excel file
        """
        print(f"\n=== Starting process_pdf_and_save_to_excel ===")
        print(f"PDF path: {pdf_path}")
        print(f"CSV path: {csv_file_path}")
        print(f"Excel path: {excel_output_path}")
        # Create AWS clients using the configured session
        print("Creating AWS clients...")
        if use_session and boto3_session:
            textract_client = boto3_session.client("textract", region_name=self.region_name, verify=False)
            s3_client = boto3_session.client("s3", region_name=self.region_name, verify=False)
            print("AWS clients created using session")
        else:
            textract_client = boto3.client("textract", region_name=self.region_name, verify=False)
            s3_client = boto3.client("s3", region_name=self.region_name, verify=False)
            print("AWS clients created using default boto3 (IAM role)")
        
        # Define S3 bucket and key
        s3_bucket_name = "ost-intelligent-parsing-test"
        s3_file_key = f"ocr-chatbot-temp/temp/{os.path.basename(pdf_path)}"
        print(f"Using S3 bucket: {s3_bucket_name}, key: {s3_file_key}")
        
        try:
            # Step 1: Upload the PDF to S3
            print(f"Uploading PDF to S3...")
            self.update_progress(18, "Uploading PDF to S3...")
            s3_client.upload_file(pdf_path, s3_bucket_name, s3_file_key)
            print("PDF uploaded to S3 successfully")
            self.update_progress(20, "PDF uploaded successfully")
            
            # Step 2: Start Textract job using S3 location with LAYOUT feature
            print("Starting Textract document analysis job with TABLES, FORMS, and LAYOUT features...")
            response = textract_client.start_document_analysis(
                DocumentLocation={
                    "S3Object": {
                        "Bucket": s3_bucket_name,
                        "Name": s3_file_key
                    }
                },
                FeatureTypes=["TABLES"]
            )
            job_id = response["JobId"]
            print(f"Textract job started with ID: {job_id}")
            self.update_progress(22, f"Textract job started (ID: {job_id[:8]}...)")
            
            # Step 3: Wait for job completion
            print("Waiting for Textract job to complete...")
            pages = []
            wait_count = 0
            while True:
                job_response = textract_client.get_document_analysis(JobId=job_id)
                status = job_response["JobStatus"]
                
                if status == "SUCCEEDED":
                    print("Textract job completed successfully")
                    self.update_progress(35, "Textract analysis completed")
                    pages = [job_response]
                    next_token = REDACTED
                    
                    # Get all pages
                    while next_token:
                        job_response = textract_client.get_document_analysis(
                            JobId=job_id,
                            NextToken=REDACTED
                        )
                        pages.append(job_response)
                        next_token = REDACTED
                    
                    break
                elif status == "FAILED":
                    print(f"Textract job failed: {job_response.get('StatusMessage', 'Unknown error')}")
                    raise Exception(f"Textract job failed: {job_response.get('StatusMessage', 'Unknown error')}")
                else:
                    wait_count += 1
                    # Progress from 22% to 34% during waiting (max 6 wait cycles = 30 seconds)
                    progress = min(34, 22 + (wait_count * 2))
                    print(f"Job status: {status}, waiting... (attempt {wait_count})")
                    self.update_progress(progress, f"Analyzing document (attempt {wait_count})")
                    time.sleep(5)  # Wait 5 seconds before checking again
            
            # Save raw blocks for debugging
            json_output_path = os.path.join(os.path.dirname(excel_output_path), f"{os.path.splitext(os.path.basename(pdf_path))[0]}_blocks.json")
            print(f"Saving raw Textract blocks to: {json_output_path}")
            with open(json_output_path, "w", encoding="utf-8") as json_file:
                json.dump(pages, json_file, default=str)
            print("Textract blocks saved successfully")
            
            # Step 4: Process the results
            print("Processing Textract results...")
            all_blocks = []
            for page in pages:
                if "Blocks" in page:
                    all_blocks.extend(page["Blocks"])
            
            # Extract data for tables and forms
            blocks_map = {block["Id"]: block for block in all_blocks}
            key_value_pairs = self.get_key_value_sets(all_blocks)
            table_data = self.get_table_csv_results(all_blocks)
            self.get_line_block_results(all_blocks)
            
            # Write to CSV
            with open(csv_file_path, "w", newline="", encoding="utf-8") as csv_file:
                csv_file.write(table_data)
            
            # Convert to Excel
            self.direct_csv_to_excel(csv_file_path, excel_output_path)
            print(f"Excel file created at: {excel_output_path}")
            
            # Step 5: Process layout data and create markdown
            print("Processing layout data...")
            layout_markdown_path = os.path.join(os.path.dirname(excel_output_path), f"{os.path.splitext(os.path.basename(pdf_path))[0]}_layout.md")
            self.process_layout_blocks(all_blocks, blocks_map, pdf_path, layout_markdown_path)
            
            # Clean up S3 object and CSV file
            try:
                print(f"Cleaning up S3 object...")
                s3_client.delete_object(Bucket=s3_bucket_name, Key=s3_file_key)
                print("S3 cleanup successful")
            except Exception as e:
                print(f"S3 cleanup error (non-critical): {str(e)}")
            
            # Clean up the CSV file
            try:
                if os.path.exists(csv_file_path):
                    os.remove(csv_file_path)
                    print(f"Cleaned up CSV file: {csv_file_path}")
            except Exception as e:
                print(f"CSV cleanup error (non-critical): {str(e)}")
            
            return excel_output_path
            
        except Exception as e:
            print(f"Error processing PDF: {str(e)}")
            print(f"Full traceback: {traceback.format_exc()}")
            print("Falling back to simplified table extraction...")
            
            # Create simple CSV with a header for fallback
            with open(csv_file_path, "w", newline="", encoding="utf-8") as csv_file:
                csv_file.write("Table: Fallback\n\n")
                csv_file.write("Test,Specification,Result,Units\n")
                csv_file.write("Document could not be processed,See PDF for details,,\n")
            
            # Convert CSV directly to Excel
            self.direct_csv_to_excel(csv_file_path, excel_output_path)
            
            return excel_output_path

    def direct_csv_to_excel(self, csv_file_path, excel_output_path):
        """
        Directly converts CSV to Excel without pandas CSV parsing
        
        Args:
            csv_file_path: Path to the CSV file
            excel_output_path: Path to save the Excel file
        """
        from openpyxl import Workbook
        
        # Create a new workbook
        wb = Workbook()
        ws = wb.active
        
        # Read the CSV file line by line
        tables = []
        current_table = None
        table_data = []
        
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines
                if not line:
                    continue
                
                # Check for table headers
                if line.startswith('Table:'):
                    # Save previous table if exists
                    if current_table and table_data:
                        tables.append((current_table, table_data))
                    
                    # Start new table
                    current_table = line.replace('Table:', '').strip()
                    table_data = []
                    continue
                
                # Add data rows
                cells = []
                # Simple CSV parsing - split by comma but respect quotes
                in_quotes = False
                cell = ''
                
                for char in line:
                    if char == '"':
                        in_quotes = not in_quotes
                        cell += char
                    elif char == ',' and not in_quotes:
                        cells.append(cell)
                        cell = ''
                    else:
                        cell += char
                
                # Don't forget the last cell
                if cell:
                    cells.append(cell)
                
                # Add to table data
                if cells:
                    table_data.append(cells)
        
        # Add the last table if exists
        if current_table and table_data:
            tables.append((current_table, table_data))
        
        # If no tables were found, create a basic one
        if not tables:
            tables = [('Fallback', [
                ['Test', 'Specification', 'Result', 'Units'],
                ['Document could not be processed with Textract', 'See PDF for details', '', '']
            ])]
        
        # Write tables to Excel
        for i, (table_name, data) in enumerate(tables):
            # Create a new sheet for each table
            if i > 0:
                ws = wb.create_sheet(f"Table_{i+1}")
            else:
                ws.title = "Table_1"
            
            # Add table name as header
            ws.append([f"Table: {table_name}"])
            ws.append([])  # Empty row
            
            # Add data
            for row in data:
                # Clean the values
                cleaned_row = [cell.strip('"') for cell in row]
                ws.append(cleaned_row)
        
        # Save the workbook
        wb.save(excel_output_path)

def process_direct_file(pdf_file_path, base_path=None, progress_callback=None):
    """
    Process a PDF file and convert to Excel for GPT extraction
    
    Args:
        pdf_file_path: Path to the PDF file
        base_path: Base directory path for output files
        progress_callback: Optional callback function for progress updates (progress, message)
        
    Returns:
        excel_file_path: Path to the generated Excel file
    """
    # Generate file paths
    file_name = os.path.basename(pdf_file_path).split('.')[0]
    
    # Set up paths
    if not base_path:
        base_path = './output'
    
    os.makedirs(base_path, exist_ok=True)
    csv_file_path = os.path.join(base_path, f"{file_name}_temp.csv")  # Intermediate CSV
    excel_file_path = os.path.join(base_path, f"{file_name}_textract.xlsx")  # Intermediate Excel for GPT
    
    try:
        # Progress update: Starting
        if progress_callback:
            progress_callback(15, "Uploading document to S3...")
        
        # Create TextractProcessor instance
        processor = TextractProcessor(region_name='us-east-1', output_path=base_path)
        
        # Progress update: Processing starts
        if progress_callback:
            progress_callback(20, "Starting Textract analysis...")
        
        # Set progress callback on processor if it supports it
        if hasattr(processor, 'set_progress_callback'):
            processor.set_progress_callback(progress_callback)
        
        # Process PDF using S3 and Textract - this will generate the Excel file
        excel_path = processor.process_pdf_and_save_to_excel(pdf_file_path, csv_file_path, excel_file_path)
        
        # Progress update: Completed
        if progress_callback:
            progress_callback(35, "Textract processing complete")
        
        # Return the path to the generated Excel file
        return excel_path
        
    except Exception as e:
        print(f"Error processing file: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return None


if __name__=='__main__':
    # Test with a local file
    pdf_path = input("Enter path to PDF file: ")
    if os.path.exists(pdf_path):
        excel_path = process_direct_file(pdf_path)
        print(f"Excel file created at: {excel_path}")
    else:
        print(f"File not found: {pdf_path}")
