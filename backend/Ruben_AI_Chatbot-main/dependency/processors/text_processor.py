
# processors/text_processor.py

import os
import tempfile
import base64
import json

# Disable SSL verification for AWS services
os.environ['AWS_CA_BUNDLE'] = ''  # Disable SSL verification
os.environ['CURL_CA_BUNDLE'] = ''

import boto3
from typing import Dict, Any, List
#import textract
from concurrent.futures import ThreadPoolExecutor
import fitz  # PyMuPDF
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage
AWS_REGION = "us-east-1"
AWS_ACCESS_KEY = "AKIAREDACTEDREDACTED"
AWS_SECRET_KEY = REDACTED
AWS_SESSION_TOKEN = REDACTED
textract_client = boto3.client(
    'textract',
    region_name=AWS_REGION,
    aws_access_key_id=REDACTED
    aws_secret_access_key=REDACTED
    aws_session_token=REDACTED
    verify=False  # Disable SSL verification
)

import requests



class TextProcessor:
    """
    Class for extracting and processing text from various document formats.
    """
    
    def __init__(self, anthropic_api_url: str, anthropic_api_key: str, model_name: str = "claude-3-7-sonnet-20250219"):
        """
        Initialize the text processor.
        
        Args:
            anthropic_api_url: URL for the Anthropic API
            anthropic_api_key: Anthropic API key
            model_name: Name of the model to use for summarization
        """
        self.llm = ChatAnthropic(
            anthropic_api_url="https://api-epic.ir-gateway.abbvienet.com/iliad/anthropic",
            api_key=REDACTED
            model_name=model_name
        )
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
        )
        
        # Initialize AWS Textract client if credentials are available
        try:
            
            print("using Aws extract")
            AWS_REGION = "us-east-1"
            AWS_ACCESS_KEY = "AKIAREDACTEDREDACTED"
            AWS_SECRET_KEY = REDACTED
            AWS_SESSION_TOKEN = REDACTED
            textract_client = boto3.client(
                            'textract',
                             region_name=AWS_REGION,
                             aws_access_key_id=REDACTED
                             aws_secret_access_key=REDACTED
                             aws_session_token=REDACTED
                             verify=False)  # Disable SSL verification
            self.textract_client = textract_client
                                       
            self.use_aws_textract = True
        except Exception as e:
            print(f"AWS Textract initialization failed: {e}")
            self.use_aws_textract = False
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from various document formats using textract.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Extracted text from the document
        """
        try:
            text = textract.process(file_path).decode('utf-8')
            return text
        except Exception as e:
            print(f"Error extracting text with textract: {e}")
            return ""
    
    def extract_text_with_aws_textract(self, file_path: str) -> str:
        """
        Extract text from documents using AWS Textract.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Extracted text from the document
        """
        if not self.use_aws_textract:
            print("AWS Textract not available, using standard textract")
            return self.extract_text(file_path)
        
        try:
            # Handle PDFs by converting to images first
            if file_path.lower().endswith('.pdf'):
                return self.process_pdf_with_aws_textract(file_path)
            
            # For images, process directly
            with open(file_path, "rb") as image_file:
                image_bytes = image_file.read()
                
            response = self.textract_client.analyze_document(
                Document={'Bytes': image_bytes},
                FeatureTypes=["FORMS", "TABLES", "SIGNATURES"]
            )
            
            # Extract text from all LINE blocks
            text_lines = [
                block['Text'] for block in response.get("Blocks", []) 
                if block.get('BlockType') == 'LINE' and 'Text' in block
            ]
            
            return "\n".join(text_lines)
        except Exception as e:
            print(f"Error extracting text with AWS Textract: {e}")
            return self.extract_text(file_path)  # Fallback to standard textract
    
    def process_pdf_with_aws_textract(self, pdf_path: str) -> str:
        """
        Process a PDF file by converting to images and then using AWS Textract.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Extracted text from all PDF pages
        """
        try:
            # Convert PDF to images
            pdf_document = fitz.open(pdf_path)
            temp_dir = tempfile.mkdtemp()
            image_paths = []
            
            def process_page(page_num):
                page = pdf_document.load_page(page_num)
                pix = page.get_pixmap(dpi=150)  # Reduce DPI for faster processing
                image_filename = f"page_{page_num + 1}.png"
                image_path = os.path.join(temp_dir, image_filename)
                pix.save(image_path)
                return image_path
            
            # Process pages in parallel
            with ThreadPoolExecutor(max_workers=min(os.cpu_count(), len(pdf_document))) as executor:
                image_paths = list(executor.map(process_page, range(len(pdf_document))))
            
            # Extract text from each image
            all_text = []
            
            def process_image(img_path):
                with open(img_path, "rb") as image_file:
                    image_bytes = image_file.read()
                
                response = self.textract_client.analyze_document(
                    Document={'Bytes': image_bytes},
                    FeatureTypes=["FORMS", "TABLES"]
                )
                
                text_lines = [
                    block['Text'] for block in response.get("Blocks", []) 
                    if block.get('BlockType') == 'LINE' and 'Text' in block
                ]
                
                return "\n".join(text_lines)
            
            # Process images in parallel
            with ThreadPoolExecutor(max_workers=5) as executor:
                page_texts = list(executor.map(process_image, image_paths))
            
            # Clean up temporary directory
            for img_path in image_paths:
                os.remove(img_path)
            os.rmdir(temp_dir)
            
            return "\n\n".join(page_texts)
        except Exception as e:
            print(f"Error processing PDF with AWS Textract: {e}")
            return self.extract_text(pdf_path)  # Fallback to standard textract
    
    def extract_tables_and_forms(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Extract tables and forms using AWS Textract.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            List of extracted tables and forms with their positions
        """
        if not self.use_aws_textract:
            print("AWS Textract not available for table extraction")
            return []
        
        try:
            with open(file_path, "rb") as file:
                image_bytes = file.read()
            
            response = self.textract_client.analyze_document(
                Document={'Bytes': image_bytes},
                FeatureTypes=["FORMS", "TABLES"]
            )
            
            blocks = response.get("Blocks", [])
            
            # Process tables
            tables = []
            table_blocks = [block for block in blocks if block['BlockType'] == 'TABLE']
            
            for table_block in table_blocks:
                table_id = table_block['Id']
                table_cells = [block for block in blocks if block['BlockType'] == 'CELL' and 
                              block.get('EntityTypes') != ['COLUMN_HEADER'] and
                              'Relationships' in block]
                
                # Organize cells into rows and columns
                table_data = []
                for cell in table_cells:
                    row_index = cell['RowIndex']
                    col_index = cell['ColumnIndex']
                    
                    # Get text from cell
                    cell_text = ""
                    if 'Relationships' in cell:
                        for relationship in cell['Relationships']:
                            if relationship['Type'] == 'CHILD':
                                child_ids = relationship['Ids']
                                for child_id in child_ids:
                                    child_block = next((b for b in blocks if b['Id'] == child_id), None)
                                    if child_block and child_block['BlockType'] == 'WORD':
                                        cell_text += child_block['Text'] + " "
                    
                    # Add cell to table data
                    while len(table_data) < row_index:
                        table_data.append([])
                    
                    row = table_data[row_index - 1]
                    while len(row) < col_index:
                        row.append("")
                    
                    row.append(cell_text.strip())
                
                tables.append({
                    'table_id': table_id,
                    'data': table_data,
                    'bounding_box': table_block['Geometry']['BoundingBox']
                })
            
            return tables
        except Exception as e:
            print(f"Error extracting tables with AWS Textract: {e}")
            return []
    
    def generate_summary(self, text: str, max_length: int = 2000) -> str:
        """
        Generate a concise summary of document text using LLM.
        
        Args:
            text: The document text to summarize
            max_length: Maximum length of text to send to the LLM
            
        Returns:
            A concise summary of the document
        """
        # Truncate text if it's too long
        summary_prompt = f"Provide a concise summary of the following document:\n\n{text[:max_length]}"
        if len(text) > max_length:
            summary_prompt += "... [text truncated]"
            
        summary_message = HumanMessage(content=summary_prompt)
        summary_response = self.llm.invoke([summary_message])
        return summary_response.content
    
    def extract_keywords(self, text: str, max_length: int = 2000) -> List[str]:
        """
        Extract key topics and keywords from the document.
        
        Args:
            text: The document text
            max_length: Maximum length of text to send to the LLM
            
        Returns:
            A list of extracted keywords
        """
        # Truncate text if it's too long
        keywords_prompt = f"""
        Extract the most important keywords and key phrases from the following document. 
        Focus on domain-specific terminology, important concepts, and entities.
        Return only a list of keywords and key phrases, one per line:
        
        {text[:max_length]}
        """
        if len(text) > max_length:
            keywords_prompt += "... [text truncated]"
            
        keywords_message = HumanMessage(content=keywords_prompt)
        keywords_response = self.llm.invoke([keywords_message])
        
        # Parse the response to get keywords
        keywords = [
            kw.strip() for kw in keywords_response.content.split('\n') 
            if kw.strip() and not kw.strip().startswith('#')
        ]
        
        return keywords
    
    def split_text(self, text: str) -> List[str]:
        """
        Split text into manageable chunks for embedding.
        
        Args:
            text: The document text to split
            
        Returns:
            A list of text chunks
        """
        return self.text_splitter.split_text(text)
    
    def process_document(self, file_path: str, file_name: str) -> Dict[str, Any]:
        """
        Process a document to extract text, metadata, and prepare for embedding.
        
        Args:
            file_path: Path to the document file
            file_name: Name of the document file
            
        Returns:
            A dictionary containing processed document data
        """
        # Determine the best extraction method based on file type
        if self.use_aws_textract and file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.pdf')):
            # Use AWS Textract for image-based documents
            text = self.extract_text_with_aws_textract(file_path)
            # Also extract tables if available
            tables = self.extract_tables_and_forms(file_path)
            print(tables)
        else:
            # Use standard textract for other document types
            text = self.extract_text(file_path)
            tables = []
        
        # Generate summary
        summary = self.generate_summary(text)
        
        # Extract keywords
        keywords = self.extract_keywords(text)
        
        # Split text for embedding
        chunks = self.split_text(text)
        
        # Gather metadata
        metadata = {
            "filename": file_name,
            "document_summary": summary,
            "keywords": ", ".join(keywords),
            "chunk_count": len(chunks),
            "has_tables": len(tables) > 0,
            "table_count": len(tables)
        }
        
        return {
            "text": text,
            "chunks": chunks,
            "tables": tables,
            "metadata": metadata
        }                            