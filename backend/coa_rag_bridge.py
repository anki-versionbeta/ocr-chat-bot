"""
========================================
COA-RAG Bridge Module
========================================
This standalone module bridges COA extraction with Ruben's RAG indexing.
It has NO Flask or FastAPI dependencies - can be used by both applications.

Purpose:
- Takes blocks.json from COA extraction
- Indexes in Iliad using Ruben's approach
- Avoids duplicate Textract calls
- No framework dependencies
========================================
"""

import os
import json
import requests
import tempfile
import traceback
from typing import Optional, Dict, Any


class COARagBridge:
    """
    Standalone bridge between COA extraction and Ruben RAG indexing.
    No Flask/FastAPI dependencies - pure Python.
    """

    def __init__(self):
        # Iliad configuration (same as both apps use)
        self.iliad_url = "https://api-epic.ir-gateway.abbvienet.com/iliad"
        self.iliad_api_key = "IHnmjp7BE3ijTUzqnaAHAMK7elgQVZYs"
        self.user_token = ""

        print("[COA-RAG Bridge] Initialized")

    def extract_text_from_blocks(self, blocks_json_path: str) -> str:
        """
        Extract raw text from COA's blocks.json file.
        This mimics what Ruben's text_processor does with Textract.

        Args:
            blocks_json_path: Path to blocks.json from COA extraction

        Returns:
            Raw text extracted from LINE blocks
        """
        try:
            with open(blocks_json_path, 'r', encoding='utf-8') as f:
                blocks_data = json.load(f)

            # Extract text from LINE blocks (same as Ruben's text processor)
            text_lines = []
            for page in blocks_data:
                if isinstance(page, dict) and 'Blocks' in page:
                    for block in page['Blocks']:
                        if block.get('BlockType') == 'LINE' and 'Text' in block:
                            text_lines.append(block['Text'])

            return "\n".join(text_lines)
        except Exception as e:
            print(f"[COA-RAG Bridge] Error extracting text: {e}")
            return ""

    def generate_summary(self, text: str, max_length: int = 2000) -> str:
        """
        Generate summary using LLM (same as Ruben's approach).
        """
        try:
            # Truncate if too long
            if len(text) > max_length:
                text = text[:max_length] + "..."

            prompt = f"Provide a one line summary of the following document:\n\n{text}"

            response = requests.post(
                url=f"{self.iliad_url}/api/v1/chat/gpt-4o-mini-global",
                json={"messages": [{"role": "user", "content": prompt}]},
                headers={"x-api-key": self.iliad_api_key}
            )

            if response.status_code == 200:
                return response.json()['completion']['content']
            else:
                return "Certificate of Analysis document"

        except Exception as e:
            print(f"[COA-RAG Bridge] Summary generation failed: {e}")
            return "Certificate of Analysis document"

    def extract_keywords(self, text: str, max_length: int = 2000) -> str:
        """
        Extract keywords using LLM (same as Ruben's approach).
        """
        try:
            # Truncate if too long
            if len(text) > max_length:
                text = text[:max_length] + "..."

            prompt = f"Extract some important keywords for the following text. Not more than 20 keywords:\n\n{text}"

            response = requests.post(
                url=f"{self.iliad_url}/api/v1/chat/gpt-4o-mini-global",
                json={"messages": [{"role": "user", "content": prompt}]},
                headers={"x-api-key": self.iliad_api_key}
            )

            if response.status_code == 200:
                return response.json()['completion']['content']
            else:
                return "COA, certificate, analysis, quality, test, results"

        except Exception as e:
            print(f"[COA-RAG Bridge] Keyword extraction failed: {e}")
            return "COA, certificate, analysis"

    def create_iliad_source(self, source_name: str, description: str) -> bool:
        """
        Create a new source in Iliad if it doesn't exist.
        """
        try:
            # Check if source exists
            response = requests.get(
                url=f"{self.iliad_url}/api/v1/sources",
                headers={"x-api-key": self.iliad_api_key, "x-user-token": self.user_token}
            )

            if response.status_code == 200:
                existing_sources = response.json().get('sources', [])
                if source_name in existing_sources:
                    print(f"[COA-RAG Bridge] Source {source_name} already exists")
                    return True

            # Create source with custom fields
            custom_fields = {
                "filename": {"type": "text"},
                "document_summary": {"type": "text"},
                "keywords": {"type": "text"},
                "has_tables": {"type": "boolean"},
                "table_count": {"type": "integer"},
                "document_type": {"type": "text"}
            }

            response = requests.post(
                url=f"{self.iliad_url}/api/v1/sources",
                headers={"x-api-key": self.iliad_api_key, "x-user-token": self.user_token},
                json={
                    "source": source_name,
                    "description": description,
                    "custom_fields": custom_fields
                }
            )

            if response.status_code in [200, 201]:
                print(f"[COA-RAG Bridge] Created source: {source_name}")
                return True
            else:
                print(f"[COA-RAG Bridge] Failed to create source: {response.text}")
                return False

        except Exception as e:
            print(f"[COA-RAG Bridge] Source creation error: {e}")
            return False

    def index_coa_document(
        self,
        blocks_json_path: str,
        original_filename: str,
        process_id: str,
        product_info: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Main function to index COA document for RAG.

        Args:
            blocks_json_path: Path to blocks.json from COA extraction
            original_filename: Original COA filename
            process_id: COA process ID for unique source naming
            product_info: Optional product information from COA extraction

        Returns:
            Source name if successful, None if failed
        """
        try:
            print(f"[COA-RAG Bridge] Starting indexing for {original_filename}")

            # Step 1: Extract text from blocks.json
            raw_text = self.extract_text_from_blocks(blocks_json_path)
            if not raw_text:
                print("[COA-RAG Bridge] No text extracted from blocks.json")
                return None

            print(f"[COA-RAG Bridge] Extracted {len(raw_text)} characters of text")

            # Step 2: Generate metadata
            summary = self.generate_summary(raw_text)
            keywords = self.extract_keywords(raw_text)

            # Step 3: Create source
            source_name = f"coa_{process_id[:8]}"
            if not self.create_iliad_source(source_name, f"COA - {original_filename}"):
                print("[COA-RAG Bridge] Failed to create source")
                # Continue anyway - source might already exist

            # Step 4: Prepare document for upload
            # Add product info to the text if available
            if product_info:
                product_text = "\n\nPRODUCT INFORMATION:\n"
                for key, value in product_info.items():
                    product_text += f"{key}: {value}\n"
                raw_text = product_text + "\n" + raw_text

            # Step 5: Upload document to Iliad
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(raw_text)
                temp_path = f.name

            try:
                custom_fields = {
                    "filename": original_filename,
                    "document_summary": summary,
                    "keywords": keywords,
                    "has_tables": True,
                    "table_count": 0,
                    "document_type": "COA"
                }

                with open(temp_path, 'rb') as f:
                    response = requests.post(
                        url=f"{self.iliad_url}/api/v1/sources/{source_name}/documents",
                        headers={"x-api-key": self.iliad_api_key, "x-user-token": self.user_token},
                        files={"file": f},
                        params={"custom_fields": json.dumps(custom_fields)}
                    )

                if response.status_code in [200, 201]:
                    print(f"[COA-RAG Bridge] ✅ Successfully indexed in source: {source_name}")
                    return source_name
                else:
                    print(f"[COA-RAG Bridge] Upload failed: {response.status_code} - {response.text}")
                    return None

            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        except Exception as e:
            print(f"[COA-RAG Bridge] Error during indexing: {e}")
            traceback.print_exc()
            return None


# Singleton instance for easy import
coa_rag_bridge = COARagBridge()