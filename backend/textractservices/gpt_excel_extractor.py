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



class GPTCoAExtractor:


    def __init__(self, api_key: str, api_url: str, model: Optional[str] = None):

        if not api_key:
            raise ValueError("API key is required.")
        if not api_url:
            raise ValueError("API URL is required.")

        self.api_key = api_key
        self.api_url = api_url
        self.model = model or "claude-3.7-sonnet"  # Default to Claude 3.7 Sonnet if not specified
        
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"

        }

    def extract_text_from_excel(self, excel_path: str) -> str:

        try:
           
            xls = pd.ExcelFile(excel_path)
            text_content = ""

            for sheet_name in xls.sheet_names:
                
                
                df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, dtype=str)
                df = df.fillna('') 

                
                sheet_text = f"Sheet: {sheet_name}\n"
                for _, row in df.iterrows():
                    
                    row_text = " | ".join(map(str, row.tolist()))
                    sheet_text += row_text + "\n"

                text_content += sheet_text + "\n\n"



            return text_content
        except Exception as e:
            print(f"Error extracting text from Excel: {e}")
            return ""

    def create_prompt(self, excel_text: str) -> str:
   

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
        
        3.  Format test names with proper hierarchical relationships:
            - For child tests: "Parent - Child" (e.g., "MC Powder - Appearance")
            - For sub-child tests: "Parent - Child - SubChild" (e.g., "MC Powder - Related Substances - Individual degradation products")
            - PRESERVE ALL NUMBERS AND PARENTHESES in test names, like "1. Appearance" or "Test (1)" or "(1)Individual"
        
        4.  For each test parameter identified, extract:
            - The complete hierarchical test name (as described above)
            - Specification
            - Result value
            - Unit (if available)

        5.  Structure the extracted test data as a list of objects under the `test_data` key. Each object should contain 'test', 'specification', 'result', and 'unit' keys. Use null or omit keys if information is not found for a specific test.
        
        6.  Return ONLY the final JSON object, enclosed in triple backticks (```json ... ```). Do not include any introductory text, explanations, or summaries outside the JSON structure.

        Pay special attention to:
        - Indentation or formatting in the document that indicates hierarchy
        - Numbered items (like "1.", "(1)", etc.) which should be preserved in test names
        - Tests that appear to be grouped under headings
        - Multi-level nesting (parent, child, sub-child relationships)
        7. if the sepcification and result columns are empty the test paramneter might be a parent to the below rows like only 30% chances example under specified impurites we may have childresn or like that check it and sentence or derivation
        Desired JSON Output Structure:
        8. please check relationships correclty like specified impurites has chemicals not unspecified if there 
        example Specified Impurities - Unspecified (each) there the speciifed impurites is not parent to unspecified unspeciifed in unique
        Specified Impurities - Total (Specified and Unspecified) here too here the total (Specified and Unspecified) is seperate row not child because it is just showing the total so it wont come under 
        Specified Impurities - Arginine Adduct here too so dont add like this

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
        """
        return prompt

    def query_gpt(self, prompt: str, max_retries: int = 3) -> Dict:


        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,  # Set max tokens to 4000
            "model": self.model  # Always include model parameter
        }

        for attempt in range(max_retries):
            try:
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
                
                if e.response is not None:
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

        if "error" in response:
            print(f"Cannot extract JSON, API response contains error: {response['error']}")
            return None

        try:

            if 'choices' in response and response['choices']:
                message = response['choices'][0].get('message', {})
                completion_text = message.get('content')

            else:
                
                completion_text = json.dumps(response) 
                print("Warning: Unknown response structure. Attempting to find JSON in the raw response.")


            if not completion_text or not isinstance(completion_text, str):
                print(f"Error: Could not find text content in LLM response. Response: {response}")
                return None

            
            json_str = None
            
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', completion_text, re.IGNORECASE)
            if json_match:
                json_str = json_match.group(1).strip() 
                print("Found JSON block in markdown.")
            else:
                
                json_start_outer = completion_text.find('{')
                json_end_outer = completion_text.rfind('}') + 1
                if (json_start_outer != -1 and json_end_outer != -1 and json_end_outer > json_start_outer):
                    json_str = completion_text[json_start_outer:json_end_outer].strip() 
                    print("Found JSON by start/end braces.")

            if json_str is None:
                print(f"Error: Could not find valid JSON structure in response text: {completion_text[:500]}...")
                return None


            is_escaped = r'\n' in json_str and r'\"' in json_str
            
            if is_escaped:
                print("Detected double-escaped JSON. Attempting to unescape...")
                try:

                    decoded_str = json_str.encode().decode('unicode_escape')
                    
                    
                    try:
                        extracted_data = json.loads(decoded_str)
                        print("Successfully parsed JSON after unescaping.")
                        return extracted_data
                    except json.JSONDecodeError:

                        print("Unescaped but still not valid JSON. Continuing with normal cleanup...")
                        json_str = decoded_str  
                except Exception as decode_err:
                    print(f"Error decoding escaped string: {decode_err}")

            json_start_actual = json_str.find('{')
            if json_start_actual == -1:
                print(f"Error: Could not find opening brace '{{' in the potential JSON string: {json_str[:500]}...")
                return None
            
            
            cleaned_json_str = json_str[json_start_actual:].strip()
            
            
            try:
                extracted_data = json.loads(cleaned_json_str)
                print("Successfully parsed JSON from LLM response.")
                return extracted_data
            except json.JSONDecodeError as json_err:
                print(f"Error: Failed to decode JSON string. Error: {json_err}")
                print(f"Cleaned JSON String (attempted): {cleaned_json_str[:500]}...")
                
                
                print("Trying one more approach - removing all backslashes...")
                try:
                    
                    final_attempt = cleaned_json_str.replace('\\"', '"').replace('\\n', '\n')
                    extracted_data = json.loads(final_attempt)
                    print("Successfully parsed JSON after removing backslashes.")
                    return extracted_data
                except json.JSONDecodeError as final_err:
                    print(f"Final attempt failed: {final_err}")
                    return None
                
        except Exception as e:
            print(f"Unexpected error extracting JSON from response: {e}")
            print(f"Raw Response (start): {str(response)[:500]}...")
            return None

    def create_dataframe(self, extracted_data: Dict) -> Tuple[pd.DataFrame, Dict]:
 
        try:
            product_info = extracted_data.get('product_info', {})
            test_data = extracted_data.get('test_data', [])

            if not isinstance(test_data, list):
                print(f"Warning: 'test_data' is not a list in the extracted JSON. Found type: {type(test_data)}")
                test_data = []
            if not isinstance(product_info, dict):
                 print(f"Warning: 'product_info' is not a dictionary in the extracted JSON. Found type: {type(product_info)}")
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

    def process_excel(self, excel_path: str) -> Tuple[pd.DataFrame, Dict]:

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
        
        # Auto-save results to the same directory as the Excel file
        output_dir = os.path.dirname(excel_path)
        base_filename = os.path.splitext(os.path.basename(excel_path))[0]
        print(f"Step 6: Auto-saving results to {output_dir}")
        self.save_results(df, product_info, output_dir, base_filename)

        return df, product_info

    def save_results(self, df: pd.DataFrame, product_info: Dict, output_dir: str, base_filename: str) -> None:
        """
        Save extracted data to files and create a unified Excel file with both metadata and test data
        """
        try:
            os.makedirs(output_dir, exist_ok=True)

            # Save to CSV (keeping for backward compatibility)
            csv_path = os.path.join(output_dir, f"{base_filename}_data.csv")
            df.to_csv(csv_path, index=False, encoding='utf-8') 
            print(f"Test data saved to {csv_path}")

            # Save product info JSON (keeping for backward compatibility)
            json_path = os.path.join(output_dir, f"{base_filename}_info.json")
            with open(json_path, 'w', encoding='utf-8') as f: 
                json.dump(product_info, f, indent=2, ensure_ascii=False) 
            print(f"Product info saved to {json_path}")
            
            # Save combined JSON (keeping for backward compatibility)
            combined_path = os.path.join(output_dir, f"{base_filename}_results.json")
            combined_data = {
                "product_info": product_info,
                "test_data": df.to_dict(orient='records')
            }
            with open(combined_path, 'w', encoding='utf-8') as f:
                json.dump(combined_data, f, indent=2, ensure_ascii=False)
            print(f"Combined results saved to {combined_path}")
            
            # Create a well-formatted unified Excel file with both metadata and test data
            unified_excel_path = os.path.join(output_dir, f"{base_filename}_unified.xlsx")
            self.create_unified_excel(df, product_info, unified_excel_path)
            print(f"Unified Excel file created at {unified_excel_path}")
            
        except Exception as e:
             print(f"Error saving results: {e}")
    
    def create_unified_excel(self, df: pd.DataFrame, product_info: Dict, excel_path: str) -> None:
        """
        Create a well-formatted Excel file containing both product metadata and test data
        """
        try:
            # Create a new Excel writer
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                # Create the main sheet with a professional layout
                workbook = writer.book
                
                # Create sheet for COA data
                sheet_name = "Certificate of Analysis"
                
                # Start with metadata section
                metadata_df = pd.DataFrame(columns=["Metadata", "Value"])
                
                # Add title row
                metadata_df.loc[0] = ["Certificate of Analysis", ""]
                
                # Add product information
                row_idx = 1
                for key, value in product_info.items():
                    if value:  # Only include non-empty values
                        # Format the key for display (capitalize, replace underscores with spaces)
                        display_key = key.replace('_', ' ').title()
                        metadata_df.loc[row_idx] = [display_key, value]
                        row_idx += 1
                
                # Add a separator row
                metadata_df.loc[row_idx] = ["", ""]
                row_idx += 1
                metadata_df.loc[row_idx] = ["Test Parameters", ""]
                row_idx += 1
                
                # Write metadata to Excel
                metadata_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
                
                # Append test data below metadata
                if not df.empty:
                    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=row_idx + 1)
                
                # Get the worksheet to apply formatting
                worksheet = writer.sheets[sheet_name]
                
                # Format the title
                title_cell = worksheet["A1"]
                title_cell.font = openpyxl.styles.Font(bold=True, size=16)
                worksheet.merge_cells("A1:B1")
                
                # Format the "Test Parameters" header
                test_params_row = row_idx + 1
                test_header_cell = worksheet.cell(row=test_params_row, column=1)
                test_header_cell.font = openpyxl.styles.Font(bold=True, size=14)
                worksheet.merge_cells(f"A{test_params_row}:B{test_params_row}")
                
                # Format column widths
                for col in worksheet.columns:
                    max_length = 0
                    # Check if the first cell is a merged cell
                    if hasattr(col[0], 'column_letter'):
                        column = col[0].column_letter
                        for cell in col:
                            if cell.value:
                                cell_length = len(str(cell.value))
                                if cell_length > max_length:
                                    max_length = cell_length
                        adjusted_width = (max_length + 2) * 1.2
                        worksheet.column_dimensions[column].width = min(adjusted_width, 50)
                
                # Add borders to cells with data
                thin_border = openpyxl.styles.Border(
                    left=openpyxl.styles.Side(style='thin'),
                    right=openpyxl.styles.Side(style='thin'),
                    top=openpyxl.styles.Side(style='thin'),
                    bottom=openpyxl.styles.Side(style='thin')
                )
                
                # Apply borders and formatting to metadata section
                for row in range(2, row_idx):
                    for col in range(1, 3):
                        cell = worksheet.cell(row=row, column=col)
                        cell.border = thin_border
                        if col == 1:  # Keys column
                            cell.font = openpyxl.styles.Font(bold=True)
                            cell.fill = openpyxl.styles.PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                
                # Apply borders and formatting to test data if exists
                if not df.empty:
                    # Get the header row for test data
                    header_row = row_idx + 2
                    # Get the number of columns from DataFrame
                    num_cols = len(df.columns)
                    
                    # Format the headers
                    for col in range(1, num_cols + 1):
                        cell = worksheet.cell(row=header_row, column=col)
                        cell.font = openpyxl.styles.Font(bold=True)
                        cell.fill = openpyxl.styles.PatternFill(start_color="E6E6E6", end_color="E6E6E6", fill_type="solid")
                        cell.border = thin_border
                    
                    # Format data cells
                    for row in range(header_row + 1, header_row + len(df) + 1):
                        for col in range(1, num_cols + 1):
                            cell = worksheet.cell(row=row, column=col)
                            cell.border = thin_border
                
                # Create a second sheet with just the raw test data (easier for data analysis)
                if not df.empty:
                    df.to_excel(writer, sheet_name="Test Data Only", index=False)
                
                # Create a third sheet with just the metadata
                metadata_only_df = pd.DataFrame(columns=["Metadata", "Value"])
                idx = 0
                for key, value in product_info.items():
                    if value:
                        display_key = key.replace('_', ' ').title()
                        metadata_only_df.loc[idx] = [display_key, value]
                        idx += 1
                
                if not metadata_only_df.empty:
                    metadata_only_df.to_excel(writer, sheet_name="Metadata Only", index=False)
            
            print(f"Created unified Excel file with professional formatting at {excel_path}")
            return excel_path
            
        except Exception as e:
            print(f"Error creating unified Excel file: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return None


def main():
    parser = argparse.ArgumentParser(description='Extract CoA data from Excel using a GPT-based LLM API')
    parser.add_argument('excel_path', help='Path to the Excel file')
    parser.add_argument('--api-key', help='LLM API key (or set LLM_API_KEY env var)')
    parser.add_argument('--api-url', help='LLM API endpoint URL (or set LLM_API_URL env var)')
    parser.add_argument('--output-dir', default='', help='Output directory (default: same as Excel file)')
    parser.add_argument('--model', default=None, help='Specific LLM model name to use (optional, depends on API provider)')

    args = parser.parse_args()

    
    api_key = REDACTED
    api_url = args.api_url or os.environ.get('LLM_API_URL')

    if not api_key or not api_url:
        print("API Key/URL not found in args or standard env vars. Trying to load from env.py...")
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
            print("Warning: Could not import env.py. API Key/URL must be provided via args or standard env vars (LLM_API_KEY, LLM_API_URL).")
        except Exception as e:
            print(f"Warning: Error loading config from env.py: {e}")
 


    if not api_key:
        print("Error: LLM API key not provided or found. Use --api-key, set LLM_API_KEY, or configure in env.py.")
        return
    if not api_url:
        print("Error: LLM API URL not provided or found. Use --api-url, set LLM_API_URL, or configure in env.py.")
        return

    try:
        
        print(f"Initializing GPTCoAExtractor with API URL: {api_url}")
        extractor = GPTCoAExtractor(api_key=api_key, api_url=api_url, model=args.model)

        
        print(f"Processing Excel file: {args.excel_path}")
        start_time = time.time()
        df, product_info = extractor.process_excel(args.excel_path)
        end_time = time.time()
        print(f"Processing finished in {end_time - start_time:.2f} seconds.")

        if not df.empty or product_info: 
            # Results are already saved in process_excel, skip duplicate saving
            print("\nExtracted Product Info:")
            print(json.dumps(product_info, indent=2))
            print("\nExtracted Test Data Sample:")
            print(df.head())
            print(f"\nTotal test data rows: {len(df)}")
        else:
            print("No data extracted from Excel or extraction failed.")

    except ValueError as ve:
         print(f"Configuration Error: {ve}")
    except Exception as e:
        print(f"An unexpected error occurred during processing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Example Usage (replace with your actual details):
    # Set environment variables (alternative to command-line args)
    # os.environ['LLM_API_KEY'] = 'YOUR_API_KEY'
    # os.environ['LLM_API_URL'] = 'YOUR_API_ENDPOINT_URL'
    # os.environ['COA_APP_ENV'] = 'local' # Specify environment for env.py lookup

    # If running directly, you might need to simulate command-line arguments
    # Example:
    # import sys
    # sys.argv = ['gpt_excel_extractor.py', 'path/to/your/coa.xlsx'] # Assumes env vars are set or env.py is used

    main()
