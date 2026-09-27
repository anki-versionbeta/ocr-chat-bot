# processors/table_processor.py

import os
import tempfile
import base64
import json
import pandas as pd
from typing import Dict, Any, List, Optional

# Disable SSL verification for AWS services
os.environ['AWS_CA_BUNDLE'] = ''  # Disable SSL verification
os.environ['CURL_CA_BUNDLE'] = ''

import boto3
from img2table.document import PDF, Image
from img2table.ocr import TextractOCR
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage

class TableProcessor:
    """
    Class for extracting and processing tables from documents.
    """
    
    def __init__(
        self, 
        anthropic_api_url: str, 
        anthropic_api_key: str, 
        aws_access_key_id: Optional[str] ="REDACTED" ,
        aws_secret_access_key: Optional[str] = "REDACTED",
        aws_session_token: Optional[str] = "REDACTED",
        aws_region: str = "us-east-1",
        model_name: str = "claude-3-haiku-20240307"
    ):
        """
        Initialize the table processor.
        
        Args:
            anthropic_api_url: URL for the Anthropic API
            anthropic_api_key: Anthropic API key
            aws_access_key_id: AWS access key ID for Textract
            aws_secret_access_key: AWS secret access key for Textract
            aws_region: AWS region for Textract
            model_name: Name of the model to use for analysis
        """
        self.llm = ChatAnthropic(
            anthropic_api_url=anthropic_api_url,
            api_key=REDACTED
            model_name=model_name
        )
        
        # AWS credentials
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_session_token = aws_session_token
        self.aws_region = aws_region
        
        # Initialize OCR if AWS credentials are available
        if aws_access_key_id and aws_secret_access_key:
            self.textract_ocr = TextractOCR(
                aws_access_key_id=REDACTED
                aws_secret_access_key=REDACTED
                aws_session_token=REDACTED
                region=aws_region
            )
            self.use_textract = True
        else:
            self.textract_ocr = None
            self.use_textract = False
    
    def extract_tables(self, file_path: str, **settings) -> List[Dict[str, Any]]:
        """
        Extract tables from images or PDF files.
        
        Args:
            file_path: Path to the document file
            **settings: Additional settings for table extraction
                - implicit_rows (bool): Whether to detect implicit rows (default: True)
                - borderless_tables (bool): Whether to detect borderless tables (default: True)
                - min_confidence (int): Minimum confidence for OCR (default: 50)
            
        Returns:
            A list of extracted tables with metadata
        """
        # Get settings with defaults
        implicit_rows = settings.get('implicit_rows', True)
        borderless_tables = settings.get('borderless_tables', True)
        min_confidence = settings.get('min_confidence', 50)
        
        print(f"Starting table extraction with settings: implicit_rows={implicit_rows}, borderless_tables={borderless_tables}, min_confidence={min_confidence}")
        
        try:
            # Check file type
            if file_path.lower().endswith('.pdf'):
                # Process PDF
                return self._extract_tables_from_pdf(
                    file_path, 
                    implicit_rows=implicit_rows,
                    borderless_tables=borderless_tables,
                    min_confidence=min_confidence
                )
            else:
                # Process image
                return self._extract_tables_from_image(
                    file_path,
                    implicit_rows=implicit_rows,
                    borderless_tables=borderless_tables,
                    min_confidence=min_confidence
                )
        except Exception as e:
            print(f"Error extracting tables: {e}")
            return []
    
    def _extract_tables_from_pdf(
        self, 
        pdf_path: str, 
        implicit_rows: bool = True,
        borderless_tables: bool = True,
        min_confidence: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Extract tables from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            implicit_rows: Whether to detect implicit rows
            borderless_tables: Whether to detect borderless tables
            min_confidence: Minimum confidence for OCR
            
        Returns:
            A list of extracted tables with metadata
        """
        try:
            # Check if Textract is available
            if not self.use_textract:
                print("AWS Textract is not available for table extraction")
                return []
            
            print("Loading PDF document")
            pdf_doc = PDF(
                src=pdf_path,
                detect_rotation=True,
                pdf_text_extraction=True
            )
            
            print("Starting OCR table extraction with Textract")
            extracted_tables = pdf_doc.extract_tables(
                ocr=self.textract_ocr,
                implicit_rows=implicit_rows,
                borderless_tables=borderless_tables,
                min_confidence=min_confidence
            )
            
            print(f"Extracted tables from {len(extracted_tables)} pages")
            
            # Process extracted tables
            tables = []
            for page_idx, (page_num, page_tables) in enumerate(extracted_tables.items()):
                print(f"Processing page {page_num+1} with {len(page_tables)} tables")
                
                for idx, table in enumerate(page_tables):
                    # Get DataFrame representation
                    df = table.df
                    
                    # Skip empty tables
                    if df.empty:
                        print(f"WARNING: Table {idx+1} on page {page_num+1} has an empty DataFrame")
                        continue
                    
                    # Clean column names
                    clean_columns = self._clean_column_names(df.columns)
                    
                    # Clean table data
                    clean_data = self._clean_table_data(df, clean_columns)
                    
                    # Generate a title if none exists
                    title = table.title
                    if not title or title.strip() == '':
                        title = f"Table {idx+1} on Page {page_num+1}"
                    
                    # Skip tables with no data
                    if not clean_data:
                        print(f"WARNING: Table {idx+1} on page {page_num+1} has empty records")
                        continue
                    
                    # Analyze table structure
                    table_metadata = self._analyze_table_structure(df, clean_columns, title)
                    
                    # Create table object
                    table_data = {
                        "table_id": f"p{page_num+1}_t{idx+1}",
                        "page": page_num + 1,
                        "table_index": idx + 1,
                        "column_names": clean_columns,
                        "data": clean_data,
                        "metadata": {
                            **table_metadata,
                            "title": title,
                            "rows": len(clean_data),
                            "columns": len(clean_columns)
                        }
                    }
                    
                    tables.append(table_data)
            
            print(f"Processed {len(tables)} tables in total")
            return tables
            
        except Exception as e:
            print(f"Error in extract_tables_from_pdf: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_tables_from_image(
        self, 
        image_path: str, 
        implicit_rows: bool = True,
        borderless_tables: bool = True,
        min_confidence: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Extract tables from an image file.
        
        Args:
            image_path: Path to the image file
            implicit_rows: Whether to detect implicit rows
            borderless_tables: Whether to detect borderless tables
            min_confidence: Minimum confidence for OCR
            
        Returns:
            A list of extracted tables with metadata
        """
        try:
            # Check if Textract is available
            if not self.use_textract:
                print("AWS Textract is not available for table extraction")
                return []
            
            print("Loading image document")
            image_doc = Image(src=image_path)
            
            print("Starting OCR table extraction with Textract")
            extracted_tables = image_doc.extract_tables(
                ocr=self.textract_ocr,
                implicit_rows=implicit_rows,
                borderless_tables=borderless_tables,
                min_confidence=min_confidence
            )
            
            # Process extracted tables
            tables = []
            for idx, table in enumerate(extracted_tables):
                # Get DataFrame representation
                df = table.df
                
                # Skip empty tables
                if df.empty:
                    print(f"WARNING: Table {idx+1} has an empty DataFrame")
                    continue
                
                # Clean column names
                clean_columns = self._clean_column_names(df.columns)
                
                # Clean table data
                clean_data = self._clean_table_data(df, clean_columns)
                
                # Generate a title if none exists
                title = table.title
                if not title or title.strip() == '':
                    title = f"Table {idx+1}"
                
                # Skip tables with no data
                if not clean_data:
                    print(f"WARNING: Table {idx+1} has empty records")
                    continue
                
                # Analyze table structure
                table_metadata = self._analyze_table_structure(df, clean_columns, title)
                
                # Create table object
                table_data = {
                    "table_id": f"t{idx+1}",
                    "table_index": idx + 1,
                    "column_names": clean_columns,
                    "data": clean_data,
                    "metadata": {
                        **table_metadata,
                        "title": title,
                        "rows": len(clean_data),
                        "columns": len(clean_columns)
                    }
                }
                
                tables.append(table_data)
            
            print(f"Processed {len(tables)} tables in total")
            return tables
            
        except Exception as e:
            print(f"Error in extract_tables_from_image: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _clean_column_names(self, columns):
        """Clean and normalize column names."""
        clean_columns = []
        for col in columns:
            if not isinstance(col, str):
                col_text = f"Column_{col}" if isinstance(col, (int, float)) else str(col)
            else:
                col_text = col.strip()
                
                # Replace problematic characters
                col_text = col_text.replace('\n', ' ').replace('\r', '')
                
                # Remove excess spaces
                col_text = ' '.join(col_text.split())
                
                # If empty after cleaning, provide a placeholder
                if not col_text:
                    col_text = f"Column_{len(clean_columns)+1}"
            
            clean_columns.append(col_text)
            
        return clean_columns
    
    def _clean_table_data(self, df, clean_columns):
        """Clean and normalize table data."""
        clean_data = []
        for _, row in df.iterrows():
            clean_row = {}
            for i, col in enumerate(df.columns):
                # Get cell value
                value = row[col]
                
                # Handle None values
                if value is None:
                    value = ""
                else:
                    # Convert to string and clean
                    value = str(value).strip()
                    
                    # Remove problematic characters
                    value = value.replace('\r', '')
                    
                    # Remove excess spaces
                    value = ' '.join(value.split())
                
                # Store with clean column name
                clean_row[clean_columns[i]] = value
            
            # Only add non-empty rows
            if any(v.strip() for v in clean_row.values()):
                clean_data.append(clean_row)
        
        return clean_data
    
    def _analyze_table_structure(self, df, columns, title):
        """Analyze table structure and provide metadata."""
        # Determine column types
        column_types = {}
        for col in columns:
            # Check for numeric columns
            numeric_count = 0
            for val in df[df.columns[columns.index(col)]]:
                if val is not None and str(val).strip() and self._is_numeric(str(val)):
                    numeric_count += 1
            
            # If more than 50% of values are numeric, consider it a numeric column
            if numeric_count > len(df) / 2:
                column_types[col] = "numeric"
            else:
                column_types[col] = "text"
        
        # Determine if table has header row
        has_header = True  # Assume tables have headers
        
        # Determine table category based on title and content
        category = self._determine_table_category(title, columns)
        
        return {
            "column_types": column_types,
            "has_header": has_header,
            "category": category
        }
    
    def _is_numeric(self, value):
        """Check if a string value is numeric."""
        # Remove common numeric formatting characters
        value = value.replace(',', '').replace('$', '').replace('%', '')
        
        try:
            float(value)
            return True
        except ValueError:
            return False
    
    def _determine_table_category(self, title, columns):
        """Determine table category based on title and columns."""
        title_lower = title.lower()
        columns_lower = [col.lower() for col in columns]
        
        # Financial table detection
        financial_terms = ['revenue', 'expense', 'income', 'profit', 'loss', 'balance', 'cash flow', 'financial']
        if any(term in title_lower for term in financial_terms) or any(any(term in col for term in financial_terms) for col in columns_lower):
            return "financial"
        
        # Date-based table detection
        date_terms = ['date', 'year', 'month', 'quarter', 'period']
        if any(term in title_lower for term in date_terms) or any(any(term in col for term in date_terms) for col in columns_lower):
            return "time_series"
        
        # Default category
        return "general"
    
    def table_to_text(self, table_data: Dict[str, Any]) -> str:
        """
        Convert a table to a textual representation for embedding.
        
        Args:
            table_data: Dictionary containing table data and metadata
            
        Returns:
            Textual representation of the table
        """
        metadata = table_data.get("metadata", {})
        title = metadata.get("title", f"Table {table_data.get('table_id', '')}")
        
        # Start with the title
        text_parts = [f"# {title}", ""]
        
        # Add column headers
        column_names = table_data.get("column_names", [])
        if column_names:
            text_parts.append(" | ".join(column_names))
            text_parts.append("-" * len(" | ".join(column_names)))
        
        # Add the data rows
        for row in table_data.get("data", []):
            row_values = [str(row.get(col, "")) for col in column_names]
            text_parts.append(" | ".join(row_values))
        
        return "\n".join(text_parts)
    
    def analyze_table(self, table_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a table to extract useful metadata.
        
        Args:
            table_data: Dictionary containing table data and metadata
            
        Returns:
            Dictionary containing table analysis
        """
        try:
            # Get column names and data
            column_names = table_data.get("column_names", [])
            data = table_data.get("data", [])
            title = table_data.get("metadata", {}).get("title", f"Table {table_data.get('table_id', '')}")
            
            # Skip analysis if table is empty
            if not column_names or not data:
                return {
                    "table_title": title,
                    "description": "Empty table",
                    "subject": "Unknown",
                    "column_descriptions": {}
                }
            
            # Convert to DataFrame for analysis
            df = pd.DataFrame(data)
            
            # Convert a sample of the table to JSON for LLM analysis
            sample_size = min(5, len(df))
            sample_json = df.head(sample_size).to_json(orient='records')
            
            # Use LLM to generate a description of the table
            analysis_prompt = f"""
            Analyze this table and provide the following information:
            1. A descriptive title for the table based on its contents
            2. A brief description of what the table contains
            3. The main subject or entity that the table describes
            4. Key column descriptions
            
            Here's information about the table:
            - Current title: {title}
            - Number of rows: {len(df)}
            - Number of columns: {len(column_names)}
            - Column names: {', '.join(column_names)}
            - Sample data (first {sample_size} rows): {sample_json}
            
            Respond with a JSON object containing these fields:
            {{
                "table_title": "Descriptive title",
                "description": "Brief description of the table contents",
                "subject": "Main subject/entity",
                "column_descriptions": {{"column_name": "description", ...}}
            }}
            """
            
            analysis_message = HumanMessage(content=analysis_prompt)
            analysis_response = self.llm.invoke([analysis_message])
            
            # Parse the JSON response
            response_text = analysis_response.content
            
            # Extract the JSON part from the response
            import re
            json_match = re.search(r'({.*})', response_text.replace('\n', ''), re.DOTALL)
            if json_match:
                table_analysis = json.loads(json_match.group(1))
            else:
                # Fallback if JSON parsing fails
                table_analysis = {
                    "table_title": title,
                    "description": "Extracted table from document",
                    "subject": "Unknown",
                    "column_descriptions": {}
                }
            
            return table_analysis
            
        except Exception as e:
            print(f"Error analyzing table: {e}")
            return {
                "table_title": title,
                "description": "Extracted table from document",
                "subject": "Unknown",
                "column_descriptions": {}
            }