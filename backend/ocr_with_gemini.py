"""
OCR with Gemini - Visual + Text Reasoning Test

This test combines:
1. Existing OCR chunk from Weaviate (text extraction)
2. Visual image of the PDF page
3. Gemini's multimodal reasoning to validate and extract data

The idea: Gemini sees both the extracted text AND the original image,
allowing it to resolve ambiguities and validate OCR accuracy.
"""

import requests
import json
import base64
import fitz  # PyMuPDF
import os
import sys
from datetime import datetime

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Configuration
WEAVIATE_URL = "http://10.242.190.53:8080"
ILIAD_URL = "https://api-epic.ir-gateway.abbvienet.com/iliad"
ILIAD_API_KEY = REDACTED

# Models to test
GEMINI_MODEL = "gemini-3.1-pro-preview"  # Latest quality model


def get_chunk_from_weaviate(process_id: str, chunk_id: str) -> dict:
    """Fetch specific chunk from Weaviate."""
    query = f'''
    {{
        Get {{
            DocumentChunk(
                where: {{
                    operator: And,
                    operands: [
                        {{path: ["process_id"], operator: Equal, valueText: "{process_id}"}},
                        {{path: ["chunk_id"], operator: Equal, valueText: "{chunk_id}"}}
                    ]
                }}
                limit: 1
            ) {{
                chunk_id
                chunk_index
                page
                chunk_type
                layout_type
                content
                markdown
                cell_grounding
                bbox_left
                bbox_top
                bbox_right
                bbox_bottom
            }}
        }}
    }}
    '''

    response = requests.post(
        f"{WEAVIATE_URL}/v1/graphql",
        json={"query": query},
        timeout=30
    )

    data = response.json()
    chunks = data.get("data", {}).get("Get", {}).get("DocumentChunk", [])
    return chunks[0] if chunks else None


def extract_page_as_image(pdf_path: str, page_number: int) -> str:
    """Extract a specific page from PDF as base64 image."""
    doc = fitz.open(pdf_path)

    # Page number is 1-indexed, fitz uses 0-indexed
    page_idx = page_number - 1

    if page_idx < 0 or page_idx >= len(doc):
        raise ValueError(f"Page {page_number} not found. PDF has {len(doc)} pages.")

    page = doc[page_idx]

    # Render page at high resolution
    mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
    pix = page.get_pixmap(matrix=mat)

    # Convert to base64
    img_bytes = pix.tobytes("png")
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")

    doc.close()

    return img_base64


def call_gemini_with_image(
    model: str,
    prompt: str,
    image_base64: str,
    chunk_text: str = None
) -> dict:
    """
    Call Gemini with both image and text context.

    Uses the OpenAI-compatible endpoint with vision support.
    """

    # Build messages with image
    messages = []

    # System context with chunk text
    if chunk_text:
        system_content = f"""You are analyzing a document page. You have TWO sources of information:

1. OCR-EXTRACTED TEXT (from AWS Textract):
{chunk_text}

2. VISUAL IMAGE of the same page (attached)

Your task: Use BOTH sources to accurately extract and validate information.
- The OCR text provides structured data but may have errors
- The visual image shows the original document including handwriting
- Compare both to resolve any ambiguities or OCR errors
"""
        messages.append({"role": "system", "content": system_content})

    # User message with image
    user_content = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{image_base64}"
            }
        },
        {
            "type": "text",
            "text": prompt
        }
    ]

    messages.append({"role": "user", "content": user_content})

    # Call Gemini via Iliad
    response = requests.post(
        f"{ILIAD_URL}/api/llm/v1/chat/completions",
        headers={
            "X-API-Key": ILIAD_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "model": model,
            "messages": messages,
            "max_tokens": 4000
        },
        timeout=120
    )

    if response.status_code == 200:
        data = response.json()
        return {
            "success": True,
            "content": data["choices"][0]["message"]["content"],
            "model": model,
            "usage": data.get("usage", {})
        }
    else:
        return {
            "success": False,
            "error": response.text,
            "status_code": response.status_code
        }


def main():
    print("=" * 80)
    print("OCR WITH GEMINI - VISUAL + TEXT REASONING TEST")
    print("=" * 80)

    # Configuration
    pdf_path = r"C:\Users\BAPATAR\Downloads\BR-1003 1000962712.pdf"
    process_id = "b5b3648f-1da1-4ab5-bd3d-5f935c0288b5"
    chunk_id = "3104fa70_chunk_339"  # The table chunk with step 7.3
    page_number = 31

    print(f"\n[CONFIG]")
    print(f"  PDF: {pdf_path}")
    print(f"  Page: {page_number}")
    print(f"  Process ID: {process_id}")
    print(f"  Chunk ID: {chunk_id}")
    print(f"  Model: {GEMINI_MODEL}")

    # Step 1: Get chunk from Weaviate
    print(f"\n[STEP 1] Fetching chunk from Weaviate...")
    chunk = get_chunk_from_weaviate(process_id, chunk_id)

    if not chunk:
        print("  ERROR: Chunk not found!")
        return

    print(f"  Found chunk: {chunk['chunk_id']}")
    print(f"  Type: {chunk['chunk_type']} / {chunk['layout_type']}")
    print(f"  Content preview: {chunk['content'][:200]}...")

    # Step 2: Extract page as image
    print(f"\n[STEP 2] Extracting page {page_number} as image...")

    if not os.path.exists(pdf_path):
        print(f"  ERROR: PDF not found at {pdf_path}")
        return

    image_base64 = extract_page_as_image(pdf_path, page_number)
    print(f"  Image extracted: {len(image_base64)} bytes (base64)")

    # Step 3: Call Gemini with both image and chunk text
    print(f"\n[STEP 3] Calling Gemini {GEMINI_MODEL}...")
    print(f"  Sending: Image + OCR chunk text")

    # The prompt asking for strikethrough before/after values
    extraction_prompt = """
Look at this document page and find ALL strikethrough/crossed-out text.

For EACH strikethrough you find, tell me:
1. ORIGINAL VALUE (the text that is crossed out/struck through)
2. NEW VALUE (the text written next to it or above it as correction)

Format your answer as a simple table:

| Location | Original (struck out) | New Value (correction) |
|----------|----------------------|------------------------|
| example  | old text             | new text               |

Look carefully at:
- Mix Start Time area
- Elapsed Mix Time area
- Perform/Date column
- Confirm/Date column
- Any footer corrections
- Any signatures

Just show me what was crossed out and what replaced it. Be specific with the actual text/numbers.
"""

    start_time = datetime.now()

    result = call_gemini_with_image(
        model=GEMINI_MODEL,
        prompt=extraction_prompt,
        image_base64=image_base64,
        chunk_text=chunk['content']
    )

    elapsed = (datetime.now() - start_time).total_seconds()

    # Step 4: Display results
    print(f"\n[STEP 4] Results (took {elapsed:.2f}s)")
    print("=" * 80)

    if result["success"]:
        print(f"\nMODEL: {result['model']}")
        print(f"TOKENS: {result.get('usage', {})}")
        print(f"\n{'=' * 80}")
        print("GEMINI'S ANALYSIS:")
        print("=" * 80)
        print(result["content"])
    else:
        print(f"\nERROR: {result.get('error', 'Unknown error')}")
        print(f"Status: {result.get('status_code', 'N/A')}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
