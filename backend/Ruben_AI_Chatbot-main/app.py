import os
import dataiku
import io
import json
import re
import requests
import traceback
import pypandoc
import pandas as pd
import aiofiles
import asyncio
import aiohttp
from pathlib import Path
from flask import Flask, request, jsonify, session
from flask_caching import Cache
from flask_session import Session
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader, PdfWriter

# Import custom modules
from processors.text_processor import TextProcessor
from processors.table_processor import TableProcessor
from services.iliad_service import IliadService
from services.embedding_service import EmbeddingService
from agents.question_rephraser_copy import QuestionRephraser
from agents.information_retriever_copy import InformationRetriever
from agents.hybrid_search import HybridSearch

from langchain_openai import AzureChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_anthropic import ChatAnthropic

################# Flask App Setup #################
app.secret_key = 'REDACTED'
app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR='/app/dataiku_data/design/snt/managed_folders/SNTAUDITANDKNOWLEDGEMANAGMENTTOOL/cxAIoVwi', #Flask_Session
    SESSION_PERMANENT=False,
    SESSION_USE_SIGNER=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,
    SESSION_SERVER_SIDE=True,
    UPLOAD_FOLDER='/app/dataiku_data/design/snt/managed_folders/SNTAUDITANDKNOWLEDGEMANAGMENTTOOL/XPh740vs',
    OUTPUT_FOLDER=dataiku.Folder("Chunked_files").get_path()
)
Session(app)
cache = Cache(app)
CHUNK_SIZE = 10 * 1024 * 1024

################# Environment Variables #################
ILIAD_API_KEY = REDACTED
ILIAD_URL = ""
USER_TOKEN = REDACTED
ANTHROPIC_API_KEY = REDACTED

################# Service Initialization #################
iliad_service = IliadService(iliad_url=ILIAD_URL, iliad_api_key=ILIAD_API_KEY, user_token=USER_TOKEN)
embedding_service = EmbeddingService(iliad_url=ILIAD_URL, iliad_api_key=ILIAD_API_KEY, user_token=USER_TOKEN)
text_processor = TextProcessor(anthropic_api_url=ILIAD_URL, anthropic_api_key=ANTHROPIC_API_KEY)
table_processor = TableProcessor(anthropic_api_url=ILIAD_URL, anthropic_api_key=ANTHROPIC_API_KEY)
hybrid_search = HybridSearch(base_url=ILIAD_URL, api_key=ILIAD_API_KEY, user_token=USER_TOKEN)
question_rephraser = QuestionRephraser(api_key=ANTHROPIC_API_KEY, api_url=ILIAD_URL)
information_retriever = InformationRetriever(
    api_key=REDACTED
    iliad_url=ILIAD_URL, iliad_api_key=ILIAD_API_KEY,
    user_token=REDACTED
)

################# LLM Request Wrapper #################
class IliadRequest:
    def __init__(self, key, url, modeltype):
        self.key = key
        self.url = url
        self.modeltype = modeltype
        self.llm = None
        self.send_request_to_model()

    def send_request_to_model(self):
        if self.modeltype == 'gpt':
            self.llm = AzureChatOpenAI(
                api_key=REDACTED
                azure_endpoint=self.url,
                openai_api_version="2023-07-01-preview",
                azure_deployment='gpt-4o-mini',
                temperature=0.1
            )
        elif self.modeltype == 'claude':
            url = self.url + '/anthropic'
            self.llm = ChatAnthropic(
                anthropic_api_url=url,
                api_key=REDACTED
                model_name="claude-3-7-sonnet-20250219"
            )

def get_fallback_llm():
    key = ILIAD_API_KEY
    url = ILIAD_URL
    model = "gpt"
    llm_class = IliadRequest(key, url, model)
    return llm_class.llm

################# Prompt Template #################
qa_template = """
You are an assistant that answers questions based on the list of source documents provided.
Be concise, accurate, and only answer based on the information in the content provided.
If the answer is not in the context, say "I don't have that information in the content provided."
Each document contains the chunk text, filename and the matching score with the question provided.
Here are the list of documents and the chat history. Here is the context:
{context}
------------------------------------------------------------------------------------------
List of documents:
{document_list}
------------------------------------------------------------------------------------------
Here's the chat history.
{chat_history_text}
-------------------------------------------------------------------------------------------
Answer the below question based on the content and the conversation history. 
Question: {question}
Maintain consistency with your previous answers.
If you've already answered a similar question, you can refer to and build upon your previous answer.
If not, give a proper answer to that question being asked.
Format your answer in a clear, professional manner.

Let's think through this step by step:
1. What specific information from the documents is relevant to the question?
2. How does this information help answer the question?
3. Is there any conflicting information in the documents?
4. What is the most accurate answer based on the documents?
The answer should include the filenames at the end from where the text was used for generating answer.
Answer:
"""
qa_prompt = PromptTemplate(
    template=qa_template,
    input_variables=["context", "document_list", "chat_history_text", "question"]
)
llm = get_fallback_llm()
qa_chain = qa_prompt | llm | StrOutputParser()

################# Utility Functions #################
def generate_response(prompt):
    BASE_URL = ILIAD_URL
    response = requests.post(
        url=BASE_URL + "/api/v1/chat/gpt-4o-mini-global",
        json={"messages": [{"role": "user", "content": prompt}]},
        headers={"x-api-key": ILIAD_API_KEY}
    )
    return response.json()['completion']['content']

def generate_summary(text):
    prompt = f"Provide a one line summary of the following document:\n\n{text}"
    return generate_response(prompt)

def extract_keywords(text):
    prompt = f"Extract some important keywords for the following text. Not more than 20 keywords:\n\n{text}"
    return generate_response(prompt)

def process_document_with_auto_metadata(file_path, file_name):
    text = text_processor.extract_text_with_aws_textract(file_path)
    tables = []
    if file_path.lower().endswith(('png', 'jpg', 'jpeg', 'pdf')):
        tables = table_processor.extract_tables(file_path)
    summary = generate_summary(text)
    keywords = extract_keywords(text)
    metadata = {
        "filename": file_name,
        "document_summary": summary,
        "keywords": keywords,
        "has_tables": len(tables) > 0,
        "table_count": len(tables),
    }
    return {"metadata": metadata}

def split_pdf_by_max_size(file_path, max_chunk_size=CHUNK_SIZE):
    output_dir = app.config['OUTPUT_FOLDER']
    reader = PdfReader(file_path)
    base_name, ext = os.path.splitext(os.path.basename(file_path))
    chunk_files = []
    writer = PdfWriter()
    current_size = 0
    chunk_index = 1

    def write_chunk(writer, chunk_index):
        chunk_name = f"{base_name}_part{chunk_index}{ext}"
        chunk_path = os.path.join(output_dir, chunk_name)
        with open(chunk_path, 'wb') as f:
            writer.write(f)
        chunk_files.append(os.path.basename(chunk_path))

    for page in reader.pages:
        temp_writer = PdfWriter()
        temp_writer.add_page(page)
        temp_buffer = io.BytesIO()
        temp_writer.write(temp_buffer)
        page_size = len(temp_buffer.getvalue())

        if current_size + page_size > max_chunk_size and writer.pages:
            write_chunk(writer, chunk_index)
            chunk_index += 1
            writer = PdfWriter()
            current_size = 0

        writer.add_page(page)
        current_size += page_size

    if writer.pages:
        write_chunk(writer, chunk_index)
    return chunk_files

def clear_files_in_folder(folder_path):
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        os.remove(file_path)

def docx_to_pdf(input_path, output_path):
    output = pypandoc.convert_file(input_path, "pdf", outputfile=output_path) 
    print(f"Converted the docx file {input_path.split('/')[-1]} to pdf:", output_path.split('/')[-1])
                   
def read_excel_and_unpack(file_path):
    dfs_dict = pd.read_excel(file_path, engine="openpyxl", sheet_name=None)
    dfs_list = [df.ffill() for df in dfs_dict.values()]
    sheet_names = list(dfs_dict.keys())
    return dfs_list,sheet_names


async def summarize_table_with_langchain(df):
    try:
        table_text = df.to_csv(index=False)
        prompt_text = (

                f"{table_text}\n\n"

                "Please convert this table into a structured textual description, row by row. "

                "Each row must be described in a complete sentence or set of sentences, explicitly stating the value of each column. "

                "Do not summarize, group, or generalize repeated values — even if multiple rows or columns have the same value, mention each one separately. "

                "Avoid using phrases like 'the rest', 'others', or 'similarly'. "

                "Do not use bullet points or lists. Do not analyze or interpret the data. "

                "Ensure the output is suitable for semantic retrieval in a vector database by preserving all original data exactly as presented."

        )
 
        payload = {

            "messages": [{

                "role": "user",

                "content": [{"type": "text", "text": prompt_text}]

            }]

        }
 
        BASE_URL = "https://api-epic.ir-gateway.abbvienet.com/iliad"
        ILIAD_API_KEY = REDACTED
 
        async with aiohttp.ClientSession() as session:

            async with session.post(

                url=f"{BASE_URL}/api/v1/chat/gpt-4o",

                json=payload,

                headers={"x-api-key": ILIAD_API_KEY}

            ) as response:

                response.raise_for_status()

                content = (await response.json())["completion"]["content"]

                return {

                    "summary": {

                        "structured_description": content

                    }

                }
 
    except Exception as e:

        return {

            "summary": {

                "structured_description": f"Error: {str(e)}"

            }

        }
    
def iliad_request_pdf(filename, source_name):
    for chunk_filename in os.listdir(app.config['OUTPUT_FOLDER']):
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], chunk_filename)
        final_data = process_document_with_auto_metadata(file_path, filename)
        source_url = f'{ILIAD_URL}/api/v1/sources/{source_name}/documents'
        header = {"x-api-key": ILIAD_API_KEY, "x-user-token": USER_TOKEN}
        custom_fields = {
            "filename": final_data['metadata']['filename'],
            "document_summary": final_data['metadata']['document_summary'],
            "keywords": final_data['metadata']['keywords']
        }
        requests.post(
            url=source_url,
            headers=header,
            files={"file": open(file_path, 'rb')},
            params={"custom_fields": json.dumps(custom_fields)}
        )

async def iliad_request_xlsx(temp_file_path, converted_txt_path, source_name):
    basename, ext = os.path.splitext(temp_file_path.split("/")[-1])
    
    total_df, sheet_names = read_excel_and_unpack(temp_file_path)
    summary_list = []

    for i in range(len(total_df)):
        summary_list.append(sheet_names[i])        
        result = await summarize_table_with_langchain(total_df[i])
        summary_list.append(result['summary']['structured_description'])
        
    with open(converted_txt_path, "w") as f:
            for idx, item in enumerate(summary_list, 1):
                f.write(f"{item}\n")
                if idx % 2 == 0:
                    f.write("\n")
    
    file_path = converted_txt_path
    source_url = f'{ILIAD_URL}/api/v1/sources/{source_name}/documents'
    header = {"x-api-key": ILIAD_API_KEY, "x-user-token": USER_TOKEN}
    custom_fields = {
        "filename": temp_file_path.split("/")[-1]
    }
    
    requests.post(url=source_url, 
                  headers=header,
                  files={"file": open(file_path, 'rb')} ,
                  params={"custom_fields": json.dumps(custom_fields)}
                 )

# ========== NEW FUNCTION FOR COA-RAG INTEGRATION ==========
# This function accepts blocks.json from COA extraction to avoid duplicate Textract calls
# Instead of calling AWS Textract again, it reads the existing blocks.json file
# and extracts the raw text just like the normal Ruben pipeline would
def iliad_request_pdf_from_blocks(blocks_json_path, filename, source_name):
    """
    Index a document using existing AWS Textract blocks.json from COA extraction.
    This avoids calling Textract twice - reuses COA's Textract response.

    Args:
        blocks_json_path: Path to the blocks.json file from COA extraction
        filename: Original filename for metadata
        source_name: Iliad source name (format: coa_<process_id>)
    """
    print(f"[COA-RAG Integration] Starting indexing for {filename} using existing Textract data")

    try:
        # === STEP 1: Extract raw text from blocks.json (NO new Textract call) ===
        # This reads the COA's Textract output and extracts text lines
        # exactly like Ruben's text_processor would do with a fresh Textract call
        with open(blocks_json_path, 'r', encoding='utf-8') as f:
            blocks_data = json.load(f)

        # Extract text from LINE blocks (same as text_processor.extract_text_with_aws_textract)
        text_lines = []
        for page in blocks_data:
            if isinstance(page, dict) and 'Blocks' in page:
                for block in page['Blocks']:
                    if block.get('BlockType') == 'LINE' and 'Text' in block:
                        text_lines.append(block['Text'])

        raw_text = "\n".join(text_lines)
        print(f"[COA-RAG Integration] Extracted {len(text_lines)} lines of text from blocks.json")

        # === STEP 2: Generate metadata using existing Ruben functions ===
        # Use the same summary and keyword extraction that Ruben normally uses
        summary = generate_summary(raw_text)
        keywords = extract_keywords(raw_text)
        print(f"[COA-RAG Integration] Generated summary and keywords")

        # === STEP 3: Create source if it doesn't exist ===
        # Each COA gets its own source in Iliad for isolated searching
        try:
            # Check if source exists
            existing_sources = iliad_service.list_sources()
            if source_name not in existing_sources:
                print(f"[COA-RAG Integration] Creating new source: {source_name}")
                # Create source with same custom fields as regular Ruben documents
                custom_fields_def = {
                    "filename": {"type": "text"},
                    "document_summary": {"type": "text"},
                    "keywords": {"type": "text"},
                    "has_tables": {"type": "boolean"},
                    "table_count": {"type": "integer"}
                }

                # Create the source
                response = requests.post(
                    url=f"{ILIAD_URL}/api/v1/sources",
                    headers={"x-api-key": ILIAD_API_KEY, "x-user-token": USER_TOKEN},
                    json={
                        "source": source_name,
                        "description": f"COA Document - {filename}",
                        "custom_fields": custom_fields_def
                    }
                )
                if response.status_code != 200:
                    print(f"[COA-RAG Integration] Warning: Could not create source: {response.text}")
        except Exception as e:
            print(f"[COA-RAG Integration] Source check/creation failed: {e}")

        # === STEP 4: Save raw text as temporary file for upload ===
        # Iliad requires file upload, so we create a temp text file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(raw_text)
            temp_text_path = f.name

        print(f"[COA-RAG Integration] Created temp file for upload: {temp_text_path}")

        # === STEP 5: Upload to Iliad with metadata ===
        # Same upload process as regular Ruben documents
        source_url = f'{ILIAD_URL}/api/v1/sources/{source_name}/documents'
        header = {"x-api-key": ILIAD_API_KEY, "x-user-token": USER_TOKEN}

        # Prepare custom fields (same structure as regular Ruben documents)
        custom_fields = {
            "filename": filename,
            "document_summary": summary,
            "keywords": keywords,
            "has_tables": True,  # COA documents typically have tables
            "table_count": 0     # Could be enhanced to count actual tables
        }

        # Upload the document
        with open(temp_text_path, 'rb') as f:
            response = requests.post(
                url=source_url,
                headers=header,
                files={"file": f},
                params={"custom_fields": json.dumps(custom_fields)}
            )

        # Clean up temp file
        os.remove(temp_text_path)

        if response.status_code == 200:
            print(f"[COA-RAG Integration] ✅ Successfully indexed {filename} in source {source_name}")
        else:
            print(f"[COA-RAG Integration] ⚠️ Upload response: {response.status_code} - {response.text}")

        return True

    except Exception as e:
        print(f"[COA-RAG Integration] ❌ Error indexing document: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
# ========== END OF NEW FUNCTION ==========

################# Flask Routes #################

@app.route('/upload', methods=['POST'])
async def upload_document():
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file part"}), 400
        file = request.files['file']
        source_name = request.form.get('source_name')
        if not file or not source_name:
            return jsonify({"status": "error", "message": "Missing file or source name"}), 400
        file_name = file.filename
        if "/" in file_name:
            file_name = file_name.split("/")[-1]
        filename = secure_filename(file_name)
        temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_file_path)

        basename, ext = os.path.splitext(temp_file_path.split("/")[-1])
        
        if ext == '.docx': 
            converted_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{basename}.pdf") 
            print("Converting from DOCX to PDF")
            docx_to_pdf(temp_file_path, converted_pdf_path )
            print("PDF chunking Process")
            split_pdf_by_max_size(converted_pdf_path)
            iliad_request_pdf(filename, source_name)
        elif ext == '.pdf': 
            print("PDF chunking Process")
            split_pdf_by_max_size(temp_file_path) 
            iliad_request_pdf(filename, source_name)
        elif ext == '.xlsx':
            converted_txt_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{basename}.txt") 
            print("Using Excel Handling method")
            await iliad_request_xlsx(temp_file_path, converted_txt_path, source_name)
        else : 
            pass
                
#         split_pdf_by_max_size(temp_file_path)

        clear_files_in_folder(app.config['OUTPUT_FOLDER']) ## 
        os.remove(temp_file_path)
        return jsonify({"status": "success", "message": "Document processed and uploaded successfully"})
    except Exception as e:
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            clear_files_in_folder(app.config['OUTPUT_FOLDER'])
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/upload_folder', methods=['POST'])
async def upload_folder():
    try:
        if 'files[]' not in request.files:
            return jsonify({"status": "error", "message": "No files part"}), 400
        files = request.files.getlist('files[]')
        source_name = request.form.get('source_name')
        if not files or not source_name:
            return jsonify({"status": "error", "message": "Missing files or source name"}), 400
        for file in files:
            filename = secure_filename(file.filename)
            temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(temp_file_path)

            basename, ext = os.path.splitext(temp_file_path.split("/")[-1])
            
            if ext == '.docx': 
                converted_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{basename}.pdf") 
                print("Converting from DOCX to PDF")
                docx_to_pdf(temp_file_path, converted_pdf_path )
                print("PDF chunking Process")
                split_pdf_by_max_size(converted_pdf_path)
                iliad_request_pdf(filename, source_name)
            elif ext == '.pdf': 
                print("PDF chunking Process")
                split_pdf_by_max_size(temp_file_path) 
                iliad_request_pdf(filename, source_name)
            elif ext == '.xlsx':
                converted_txt_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{basename}.txt") 
                print("Using Excel Handling method")
                await iliad_request_xlsx(temp_file_path, converted_txt_path, source_name)
            else : 
                pass
            
#             split_pdf_by_max_size(temp_file_path)

            clear_files_in_folder(app.config['OUTPUT_FOLDER'])
            os.remove(temp_file_path)
        return jsonify({"status": "success", "message": "All documents in the folder processed and uploaded successfully"})
    except Exception as e:
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            clear_files_in_folder(app.config['OUTPUT_FOLDER'])
            os.remove(temp_file_path)
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/list_sources', methods=['GET'])
def list_sources():
    try:
        sources = iliad_service.list_sources()
        #sources = [x for x in sources if 'cassandra' in x]
        sources = [x for x in sources if 'reuben' in x]
        return jsonify({"sources": sources})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/list_source_documents', methods=['POST'])
def list_source_documents():
    try:
        data = request.get_json()
        if not data or 'source' not in data:
            return jsonify({"error": "Missing source parameter"}), 400
        source_name = data['source']
        documents = iliad_service.list_documents(source_name)
        return jsonify({"documents": documents})
    except Exception as e:
        return jsonify({"error": str(e), "documents": []}), 500

@app.route('/delete_document', methods=['DELETE'])
def delete_document():
    try:
        source_name = request.form.get('source_name')
        document_ids = request.form.getlist('deleteId')
        if not document_ids or not source_name:
            return jsonify({"status": "error", "message": "Missing document_ids or source name"}), 400
        header = {"x-api-key": ILIAD_API_KEY, "x-user-token": USER_TOKEN}
        for del_file in document_ids:
            source_url = f"{ILIAD_URL}/api/v1/sources/{source_name}/documents/{del_file}"
            requests.delete(url=source_url, headers=header)
        return jsonify({"status": "success", "message": "Document Deleted Successfully"}), 204
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/chat', methods=['POST'])
async def chat_endpoint():
    try:
        question = request.form.get('question')
        source_name = request.form.get('source_name')
        selectedFileList = request.form.get('selectedFileList') # Return type: str  file1.pdf,file2.pdf
        
        if not question or not source_name or not selectedFileList:
            return jsonify({"error": "Missing question or source name or No files Selected"}), 400
        result = hybrid_search.answer_question(source_name, question, selectedFileList)
        context = result['passages']
#         session.clear()

        if 'chat_history' not in session:
            session['chat_history'] = []
        
        chat_history = session['chat_history']
        
        filtered_chat_history = []
        for entry in chat_history:
            ans_text = entry.get('answer', '').lower()
            filenames = selectedFileList.split(',') if isinstance(selectedFileList, str) else selectedFileList
            print("filenames",filenames)
            for filename in filenames:
                if filename.lower() in ans_text:
                    filtered_chat_history.append(entry)
                    break  # no need to check other filenames for this entry
        print("History for LLM ", filtered_chat_history)
        history_text = ""
        if filtered_chat_history:
            history_text = "Previous conversation:\n"
            for value in filtered_chat_history:
                history_text += f"Human: {value['question']}\nAI: {value['answer']}\n\n"
        try:
            print("###### Context ###############")
            print(context)
            print("############ Doc List #########")
            print(selectedFileList)
            print("############# Chat history ###############")
            print(history_text)
            print("################### Question ##################")
            print(question)
            print("############# Answer ####################")
            
            answer = await qa_chain.ainvoke({
                "context": context,
                "document_list": selectedFileList,
                "chat_history_text": history_text,
                "question": question,
            })
            print(answer)
            chat_history.append({"question": question, "answer": answer})
            session['chat_history'] = chat_history[-10:] if len(chat_history) > 10 else chat_history
            session.modified = True
#             print("Entire ChatHistory ",chat_history)
            return jsonify({
                "status": "success",
                "question": question,
                "answer": answer,
                "rephrased_questions": [question]
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({'error': f"Error processing your question: {str(e)}"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f"Error: {str(e)}"}), 500
    
    
@app.route('/clear_session', methods=['POST'])
async def clear_current_session():
    try:
        session.clear()
        print("Current Session was Cleared")
        return jsonify({"status": "success", "message": "The current session is deleted"}), 204
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500
    