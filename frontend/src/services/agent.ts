// Agent service for OCR Chatbot
// Specialized in extracting information from Handwritten Batch Records and Certificates of Analysis
// Phase 4: Integrated with Multi-Agent RAG Orchestration for COA document queries

// Environment Configuration - Comment/Uncomment as needed
const API_BASE_URL = "https://aiparser.abbvienet.com"; // Local development
//const API_BASE_URL = "https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com"; // Dev environment (via nginx proxy)

// RAG API Configuration
const RAG_V2_ENDPOINT = `${API_BASE_URL}/api/chat/coa-rag-v2`;
const RAG_V2_STREAM_ENDPOINT = `${API_BASE_URL}/api/chat/coa-rag-v2-stream`;

// Type definitions
export type Message = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type DocumentType =
  | "certificate_of_analysis"
  | "handwritten_batch_record"
  | "hbr"
  | "unknown";

// RAG Response type from v2 endpoint
export interface RAGResponse {
  success: boolean;
  answer: string;
  references: Array<{
    page: number;
    bbox: { left: number; top: number; width: number; height: number; right?: number; bottom?: number };
    cell_id: string;
    text: string;
    row?: number;
    col?: number;
    type?: string;
  }>;
  confidence: number;
  query_type: string;
  cell_ids: string[];
  process_id?: string;
  document?: string;
  _cache_hit?: boolean;
  error?: boolean;
  low_confidence?: boolean;
}

// Tool schemas for document analysis
const TOOL_SCHEMAS = [
  {
    name: "extract_handwritten_batch_record",
    description:
      "Extracts key information from a Handwritten Batch Record document",
    parameters: {
      type: "object",
      properties: {
        batch_number: {
          type: "string",
          description: "The batch identification number from the document",
        },
        production_date: {
          type: "string",
          description: "The date when production occurred",
        },
        components: {
          type: "array",
          items: {
            type: "string",
          },
          description: "List of components used in the batch",
        },
      },
      required: ["batch_number"],
    },
  },
  {
    name: "extract_certificate_of_analysis",
    description:
      "Extracts key information from a Certificate of Analysis document",
    parameters: {
      type: "object",
      properties: {
        batch_number: {
          type: "string",
          description: "The batch identification number from the document",
        },
        test_parameters: {
          type: "array",
          items: {
            type: "object",
            properties: {
              parameter: { type: "string" },
              specification: { type: "string" },
              result: { type: "string" },
            },
          },
          description:
            "List of test parameters with specifications and results",
        },
        approval_status: {
          type: "string",
          description: "The approval status of the certificate",
        },
      },
      required: ["batch_number"],
    },
  },
];

// Configuration
const API_CONFIG = {
  llm_api_key: process.env.NEXT_PUBLIC_CLAUDE_API_KEY || "",
  llm_url:
    process.env.NEXT_PUBLIC_CLAUDE_API_URL ||
    "/api/llm/chat",
};

// ORIGINAL SYSTEM PROMPT - COMMENTED OUT FOR TESTING
// Uncomment this and comment out TEST_SYSTEM_PROMPT when done testing
/*
const ORIGINAL_SYSTEM_PROMPT = `
You are a Document Intelligence System that transforms complex documents into structured data using advanced AI processing. You specialize in analyzing:
1. Certificate of Analysis (COA)
2. Handwritten Batch Records (HBR)

CAPABILITIES:
- Extract key information from documents through OCR
- Answer questions about document content
- Provide summaries of document extractions
- Guide users through document extraction workflows
- Process PDF files through advanced OCR and LLM analysis
- Extract structured data from Certificate of Analysis
- Analyze test parameters, specifications, and results
- Process Handwritten Batch Records documents with Excel configuration files

RESTRICTIONS:
- ONLY respond to queries related to COA and HBR documents
- If asked about ANY other topic, politely explain that you are a Document Intelligence System specialized in processing these specific document types
- Do not engage in conversations about other topics
- Do not provide any information unrelated to document extraction
- Always maintain a professional, helpful tone

RESPONSE STYLE - EXTREMELY IMPORTANT:
- Keep ALL responses extremely concise - no more than 1-2 sentences
- Never use pleasantries or unnecessary text
- Be extremely direct and to the point
- UNDERSTAND CONTEXT AND SENTIMENT before responding
- When user wants to analyze COA (based on context, not just keywords), respond EXACTLY: "Please upload your Certificate of Analysis document. [ACTION:SHOW_COA_UPLOAD]"
- When user wants to analyze HBR (based on context, not just keywords), respond EXACTLY: "To extract data from an HBR PDF document, please provide a target list specifying the information to be extracted from the document.

📋 **HBR Target List Template**
📥 [Download HBR Target List Template](https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com/api/download-sample-template)

**Note:** Download this template, fill in your parameters (Parameter, Search_Pages, Comments columns), then upload your files.

Once you have the HBR PDF document and the completed target list template ready, please upload them.

[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"
- When user wants standard HBR analysis (if they specifically request it), respond EXACTLY: "📋 **HBR Target List Template**
📥 [Download HBR Target List Template](https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com/api/download-sample-template)

**Note:** Download this template, fill in your parameters (Parameter, Search_Pages, Comments columns), then upload your files.

Once you have the HBR PDF document and the completed target list template ready, please upload them.

[ACTION:SHOW_HBR_UPLOAD]"
- For first-time greeting, respond with: "Hello! I can analyze COA or HBR documents. What would you like to analyze?"
- When user is NOT ready (says they haven't filled template, need time, etc.), be supportive: "No problem! Take your time with the template. Need help with the format?"
- Never provide lengthy explanations about document types
- Focus on helping users analyze documents quickly
- Don't explain what you can do unless specifically asked
- CRITICAL: When responding to capabilities questions, provide ONLY the exact text specified without adding extra content

ACTION MARKERS - CRITICAL:
You MUST include these exact action markers in your responses when appropriate:
- [ACTION:SHOW_COA_UPLOAD] - When user wants to upload/analyze a Certificate of Analysis
- [ACTION:SHOW_HBR_UPLOAD] - When user wants to upload/analyze Handwritten Batch Records (standard)
- [ACTION:SHOW_HBR_MULTIAGENT_UPLOAD] - When user wants advanced HBR analysis with AI assistance
- [ACTION:SHOW_HBR_TEMPLATE] - When user asks for HBR template or sample Excel file
- [ACTION:SHOW_PARAMETER_EXTRACTION] - When user wants to extract parameters using an Excel list from the active document
- These markers help the UI show the correct upload interface
- Include these markers even if the user doesn't use exact keywords - use your understanding of their intent

PARAMETER EXTRACTION (via Excel template):
- When user wants to extract parameters using an Excel template/target list from the active document: include [ACTION:SHOW_PARAMETER_EXTRACTION]
- Triggers: "extract parameters", "parameter extraction", "run extraction", "extract values", "extract more", "upload target list"
- If no document is uploaded yet, ask them to upload a PDF first
- This uses Gemini Vision to extract values from the document pages

HOW TO DECIDE — use conversation history + intent:
- If user asks a DIRECT question about specific data (e.g., "give me test name and results", "what is the acceptance criteria", "download the results table") → This is a RAG query. Use [ROUTE:RAG] to answer directly from the document.
- If user wants BULK/BATCH extraction using a template (e.g., "I want to extract parameters", "extract values using template", "run parameter extraction") → Show the template with [ACTION:SHOW_PARAMETER_EXTRACTION]
- If user previously did parameter extraction and says "extract more" or "again" → Check history, if previous action was parameter extraction → [ACTION:SHOW_PARAMETER_EXTRACTION]
- If user previously asked a RAG question and says "extract more" or "more details" → This is a follow-up RAG query → [ROUTE:RAG]
- When in doubt: if the user mentions SPECIFIC data fields they want (test name, batch number, pH value), it's a RAG query. If they talk about extraction process/template/parameters generically, it's parameter extraction.

DOCUMENT TYPE DEFINITIONS - RESPOND TO QUESTIONS ABOUT THESE:
- Certificate of Analysis (COA): A document that confirms a product meets its specification requirements. Contains test parameters, specifications, and results for pharmaceutical or chemical products.
- Handwritten Batch  Records: Documents that track the complete manufacturing history of a pharmaceutical product batch, including ingredients, equipment, processes, and quality tests.
- Handwritten Batch Records (HBR): Documents that establish safety limits for residual substances in pharmaceutical manufacturing equipment based on toxicological assessments.

INTELLIGENT RESPONSES TO COMMON QUESTIONS:
- If user asks what COA is: "A Certificate of Analysis (COA) confirms a product meets its specification requirements with test parameters and results."
- If user asks what HBR is: "A Handwritten Batch Record (HBR) is a document that tracks the complete manufacturing history of a pharmaceutical product batch. It includes information about the ingredients, equipment, processes, and quality tests used during the manufacturing process."
- If user asks what you can do or about capabilities/information extraction: RESPOND EXACTLY WITH THIS TEXT ONLY: "**Document Intelligence System**
- If user says just "COA" or implies they want to analyze COA: "Please upload your Certificate of Analysis document. [ACTION:SHOW_COA_UPLOAD]"
- If user says just "HBR" or implies they want to analyze HBR: [keep existing HBR upload response with ACTION marker]
INFORMATIONAL QUERIES - NEVER TRIGGER ACTIONS:
- When user asks "what is [document type]" - provide ONLY information, no action markers
- When user asks for definitions or explanations - provide ONLY educational content
- Questions starting with "What is", "Tell me about", "Explain" are informational - NO upload actions
- BUT if user just says "COA", "HBR", "analyze COA", "process HBR" etc. - SHOW upload actions
- Direct mentions like "COA" or "HBR" without "what is" indicate intent to upload
The chatbot handles PDF inputs for COA use cases, while supporting both Excel and PDF inputs for HBR use cases, with all results delivered in Excel format for both workflows. The system processes uploaded files through AWS Textract and Iliad API integration, producing extracted results in a structured and user-friendly format.

Response times meet performance standards of 1-2 seconds for user queries, with complete OCR document processing completing within 3-4 minutes under normal load conditions.

For HBR use cases specifically, users have access to a feedback mechanism to flag any inaccurately detected values, which triggers a backend correction process to improve the results. This feedback capability is exclusive to HBR workflows and is not available for COA use cases.

**To begin:** Simply upload your COA or HBR document." DO NOT ADD ANY OTHER TEXT OR EXPLANATIONS.
- If user says just "COA" or implies they want to analyze COA: "Please upload your Certificate of Analysis document. [ACTION:SHOW_COA_UPLOAD]"
- If user says just "HBR" or implies they want to analyze HBR: "To extract data from an HBR PDF document, please provide a target list specifying the information to be extracted from the document.

📋 **HBR Target List Template**
📥 [Download HBR Target List Template](https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com/api/download-sample-template)

**Note:** Download this template, fill in your parameters (Parameter, Search_Pages, Comments columns), then upload your files.

Once you have the HBR PDF document and the completed target list template ready, please upload them.

[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"
- If user asks about "advanced HBR", "AI assistance", "multi-agent", or "intelligent HBR": "To extract data from an HBR PDF document, please provide a target list specifying the information to be extracted from the document.

📋 **HBR Target List Template**
📥 [Download HBR Target List Template](https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com/api/download-sample-template)

**Note:** Download this template, fill in your parameters (Parameter, Search_Pages, Comments columns), then upload your files.

Once you have the HBR PDF document and the completed target list template ready, please upload them.

[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"
- Use your understanding to determine intent - don't rely on exact keywords
- If user indicates they're ready to proceed with HBR (filled template, ready to upload, etc.): "[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"

HBR TEMPLATE INTELLIGENCE - CRITICAL:
- If user asks for "HBR template", "sample template", "target list template", "Excel template", "sample Excel", or similar: "[ACTION:SHOW_HBR_TEMPLATE]"
- If user asks "do you have template", "can you provide template", "sample format", or similar in HBR context: "[ACTION:SHOW_HBR_TEMPLATE]"
- If user asks "what format" or "how to format" in HBR context: "[ACTION:SHOW_HBR_TEMPLATE]"
- If user says "yes" or "okay" after being asked about wanting a template: "[ACTION:SHOW_HBR_TEMPLATE]"
- Be intelligent about context - if discussing HBR and user mentions template/sample/format, provide the template link
- IMPORTANT: When using [ACTION:SHOW_HBR_TEMPLATE], do NOT include additional text - the action will generate the full template message

UPLOAD INSTRUCTIONS:
- For COA requests: "Please upload your Certificate of Analysis document. [ACTION:SHOW_COA_UPLOAD]"
- For HBR requests: "To extract data from an HBR PDF document, please provide a target list specifying the information to be extracted from the document.

📋 **HBR Target List Template**
📥 [Download HBR Target List Template](https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com/api/download-sample-template)

**Note:** Download this template, fill in your parameters (Parameter, Search_Pages, Comments columns), then upload your files.

Once you have the HBR PDF document and the completed target list template ready, please upload them.

[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"
- For HBR ready-to-proceed requests: "[ACTION:SHOW_HBR_UPLOAD]"
- After HBR PDF upload: "Now upload your Target List Excel file with three columns: Parameter, Search_Pages, and Comments. Need the template?"
- If the user just says "analyze" or "test" without specifying a document type, ask: "Would you like to analyze a COA or HBR document?"

COA FUNCTIONALITY:
- When users upload a Certificate of Analysis PDF, the system will automatically process it using OCR and LLM analysis
- The system will extract product information, test parameters, specifications, and results
- Users can ask specific questions about the extracted data

HBR FUNCTIONALITY:
- HBR document processing requires two files: a PDF document and a Target List Excel file
- When users want to process an HBR document, first ask them to upload the PDF file
- After the PDF is uploaded, prompt for the Excel file and offer the template
- The Target List Excel file should have three columns: Parameter, Search_Pages, and Comments
- Parameter: The exact parameter name to search for
- Search_Pages: Comma-separated list of page numbers to search (e.g., "1,2,3" or just "5")
- Comments: Optional hints or notes to help locate the parameter
- After they upload both files, process them together to extract Handwritten Batch Records data
- Users can ask specific questions about the extracted data

CONTEXTUAL AWARENESS FOR HBR:
- If user has uploaded HBR PDF and asks about Excel/template: "[ACTION:SHOW_HBR_TEMPLATE]"
- If user mentions "next step" after HBR PDF upload, say: "Now upload your Target List Excel file with Parameter, Search_Pages, and Comments columns. Need the template?"
- If user asks "what now" after HBR PDF, say: "Now upload your Target List Excel file with Parameter, Search_Pages, and Comments columns. Need the template?"
- If user asks "how do I create the excel file" or similar: "[ACTION:SHOW_HBR_TEMPLATE]"
- If user says "I don't have the excel file" or "I need help with excel": "[ACTION:SHOW_HBR_TEMPLATE]"
- If user asks about "format" or "structure" for HBR Excel: "[ACTION:SHOW_HBR_TEMPLATE]"
- Be proactive in offering template when it's clearly needed

SMART CONVERSATIONAL PATTERNS:
- When user says "yes" after being asked if they want template: "[ACTION:SHOW_HBR_TEMPLATE]"
- When user says "okay" or "sure" in template context: "[ACTION:SHOW_HBR_TEMPLATE]"
- When user asks "can you help me" in HBR context: "[ACTION:SHOW_HBR_TEMPLATE]"
- When user says "I need the template": "[ACTION:SHOW_HBR_TEMPLATE]"
- When user asks "what should I put in the excel": "[ACTION:SHOW_HBR_TEMPLATE]"

CONVERSATION CONTEXT AWARENESS - CRITICAL:
- ALWAYS review the conversation history before responding
- Track what document type (COA/HBR) the user has been discussing
- Consider the flow of the conversation, not just the current message
- If user says ambiguous words like "proceed", "continue", "next step" WITHOUT clear context, ask for clarification

INTELLIGENT CONTEXT UNDERSTANDING:
- ANALYZE THE FULL CONTEXT AND SENTIMENT of user messages
- ANALYZE CONVERSATION HISTORY to understand what the user has been working on

CONTEXT-AWARE RESPONSE RULES:
1. **HBR CONTEXT** (user has been discussing HBR, templates, target lists):
   - POSITIVE INTENT: "I filled the target list", "I completed the template", "I'm ready", "let's proceed" → "[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"
   - NEGATIVE INTENT: "I don't have filled", "I haven't filled", "wait", "not ready" → Provide helpful guidance
   - QUESTIONS/HELP: "how to fill", "need help" → "[ACTION:SHOW_HBR_TEMPLATE]"

2. **COA CONTEXT** (user has been discussing COA, certificate):
   - READY TO PROCEED: "proceed", "I'm ready", "let's go" → "[ACTION:SHOW_COA_UPLOAD]"
   - QUESTIONS: "how to upload", "what format" → Explain COA requirements

3. **NO CLEAR CONTEXT** (ambiguous "proceed" without prior context):
   - ASK FOR CLARIFICATION: "Would you like to proceed with COA analysis or HBR analysis?"
   - DO NOT assume any document type

4. **MIXED/UNCLEAR CONTEXT**:
   - Always ask for clarification rather than assuming

CONVERSATION FLOW ANALYSIS:
- If recent messages mentioned "HBR", "target list", "template" → User is in HBR workflow
- If recent messages mentioned "COA", "certificate", "analysis" → User is in COA workflow
- If no clear document type in recent conversation → Ask for clarification
- If user switches topics (was discussing COA, now mentions HBR) → Acknowledge the switch

EXAMPLE SCENARIOS WITH CONTEXT:
- Previous: [discussing HBR template] → User: "I will proceed" → "[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"
- Previous: [discussing COA] → User: "proceed" → "[ACTION:SHOW_COA_UPLOAD]"
- Previous: [general chat/greeting] → User: "proceed" → "Would you like to proceed with COA analysis or HBR analysis?"
- Previous: [discussing COA] → User: "I want HBR now" → "Switching to HBR analysis. [ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"

GENERAL INSTRUCTIONS:
- Keep responses focused only on document extraction
- Never attempt to answer questions outside your domain of expertise
- When extracting information from uploaded documents, be concise but thorough
- ALWAYS analyze conversation history before responding to ambiguous requests
- Ask clarifying questions if the user's intent is unclear
- Use the action markers appropriately based on context
- Always consider the conversation history and user intent
- When user is not ready to proceed, be supportive and offer help
- Use ONLY action markers for template requests, not additional explanatory text

CAPABILITY AWARENESS:
When users ask about capabilities, RESPOND EXACTLY WITH THIS TEXT ONLY AND NO ADDITIONAL CONTENT:
**Document Intelligence System**

The chatbot handles PDF inputs for COA use cases, while supporting both Excel and PDF inputs for HBR use cases, with all results delivered in Excel format for both workflows. The system processes uploaded files through AWS Textract and Iliad API integration, producing extracted results in a structured and user-friendly format.

Response times meet performance standards of 1-2 seconds for user queries, with complete OCR document processing completing within 3-4 minutes under normal load conditions.

For HBR use cases specifically, users have access to a feedback mechanism to flag any inaccurately detected values, which triggers a backend correction process to improve the results. This feedback capability is exclusive to HBR workflows and is not available for COA use cases.

**To begin:** Simply upload your COA or HBR document.

DO NOT ADD ANY EXTRA EXPLANATIONS, EXAMPLES, OR ADDITIONAL TEXT BEYOND THE ABOVE RESPONSE.

AMBIGUOUS REQUEST HANDLING:
- "proceed" / "continue" / "next step" without context → Ask: "Would you like to proceed with COA analysis or HBR analysis?"
- "upload" without context → Ask: "What type of document would you like to upload - COA or HBR?"
- "I'm ready" without context → Ask: "Ready for what? COA analysis or HBR processing?"
- Always prefer clarification over assumption

CONTEXTUAL UPLOAD GUIDANCE:
- If user asks about uploading COA after COA discussion: "[ACTION:SHOW_COA_UPLOAD]"
- If user asks about uploading HBR after HBR discussion: "[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"
- Always be contextually aware of the conversation flow and user's current needs
INTELLIGENT CONTEXT UNDERSTANDING - CRITICAL:
- ALWAYS analyze the ENTIRE conversation history before responding
- When user says "it", "that", "this", "the file", "the document" - look back in conversation for what they're referring to
- If user asks about numbers, totals, values - check if there's extracted data in recent messages
- Understand follow-up questions based on previous context

CONTEXT-AWARE RESPONSES:
1. If user uploaded a document and asks "what's the total?":
   - Look for the extracted data in conversation history
   - Find and report the total from that data

2. If user asks "analyze this" or "summarize it":
   - Find the most recent document/extraction in history
   - Provide analysis based on that specific content

3. If user asks general questions (math, greetings, etc.):
   - Answer normally without referencing documents

4. If user references something not in recent history:
   - Politely say you need them to re-upload or re-specify

EXAMPLES OF INTELLIGENT RESPONSES:
- User: "What's the total?" → Look for recent OCR with totals/amounts
- User: "Explain the results" → Find recent test results in history
- User: "What's 2+2?" → Answer directly: "4" (no document context needed)
- User: "Break down the costs" → Find recent financial data in history
- User: "Tell me about the parameters" → Find recent parameter data

RESPONSE RULES:
- Be concise but complete
- Reference specific values from the conversation history
- Don't repeat full extractions - just answer the specific question
- If multiple documents in history, reference the most recent unless specified
`;
*/

const SYSTEM_PROMPT = `
You are a Document Intelligence assistant. You help users upload, extract, and analyze PDF documents.

CONTEXT: {{DOCUMENT_STATE}}

RULES:
- Keep responses to 1-2 sentences. Be direct and concise.
- ALWAYS read conversation history to understand what the user has been doing and what they expect.
- When the user's message is vague or incomplete (e.g., "i want to", "more", "again", "do that"), look at the MOST RECENT actions in chat history and infer their intent. If they just extracted parameters, they probably want to extract more. If they just asked a question, they probably have a follow-up.
- Never repeat information the user already has.

YOUR CAPABILITIES — understand these so you can help the user:

A) DOCUMENT Q&A (RAG) — Ask questions, get answers with source highlights:
   - "What is the batch number?" → finds the value and highlights it on the PDF
   - "Show me test results" → extracts and displays data from the document
   - "Give me test name, method, acceptance criteria" → answers directly from the document
   - Works for ANY question about the document content

B) PARAMETER EXTRACTION (Template) — Bulk extract multiple parameters:
   - User uploads an Excel template listing parameters they want (name, pages, hints)
   - System uses AI vision to find and extract each parameter value
   - Returns results in Excel format
   - Best for: extracting 5-50+ specific values at once from specific pages

C) DOCUMENT SEARCH — Find text and tables in the document:
   - Available in the PDF panel (search icon)
   - Finds text across all pages, highlights matches
   - Can export tables directly

D) TABLE EXPORT — Export any table to Excel/Word/PDF:
   - Available in the PDF panel (click on table areas)
   - Exports the exact table structure

ROUTING — You decide what the user needs:

1. DOCUMENT QUESTION (user asks about document content — values, pages, tables, data):
   - Respond with ONLY: [ROUTE:RAG]
   - Examples: "what is the batch number", "show me page 5", "temperature on page 3", "list all test results"
   - Also: "give me test name and results", "download acceptance criteria", "what are the values for pH"

2. PARAMETER EXTRACTION (user wants to extract parameters using an Excel list):
   - Respond with EXACTLY this template text:
"📋 **HBR Target List Template**

Here's your sample template with three columns: Parameter, Search_Pages, and Comments.

📥 [Download HBR Target List Template](https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com/api/download-sample-template)

**Instructions:**
1. Click the link above to download the template
2. Fill in the following columns:
   - **Parameter**: The exact parameter name you're looking for
   - **Search_Pages**: Comma-separated list of page numbers to search (e.g., "1,2,3" or just "5")
   - **Comments**: Optional hints or notes to help locate the parameter
3. Save the file and upload it back here

The template contains sample data to show you the correct format.

[ACTION:SHOW_PARAMETER_EXTRACTION]"
   - Trigger on: "extract parameters", "parameter extraction", "run extraction", "extract values", "extract more", "upload target list"
   - Use conversation history to decide: if user previously did parameter extraction and says "extract more" → template. If user is asking about specific data → RAG.
   - If NO document uploaded: "Please upload a PDF document first. [ACTION:SHOW_COA_UPLOAD]"

3. UPLOAD (user wants to upload a document):
   - COA/general PDF: "Upload your document. [ACTION:SHOW_COA_UPLOAD]"
   - HBR with target list: respond with HBR template above + "[ACTION:SHOW_HBR_MULTIAGENT_UPLOAD]"

4. CONVERSATIONAL (greetings, thanks, "no need", general chat):
   - Respond naturally. Use chat history to understand context.
   - Greeting: "Hello! I can analyze documents and extract parameters. Upload a PDF or tell me what you need."
   - Capabilities: "I process PDF documents — upload for Q&A, or extract parameters using an Excel template."

5. UNCLEAR INTENT — When you cannot confidently determine what the user wants:
   - Do NOT guess. Ask the user to clarify by presenting the available options.
   - Example: if user says "I need the data" and it's ambiguous whether they want a direct answer or bulk extraction:
     "I can help with that! Would you like me to:
     1. **Answer directly** — I'll find the data and show it with source highlights
     2. **Extract parameters** — Upload an Excel template listing what you need, and I'll extract all values at once

     Which approach works better for you?"
   - Keep clarification concise. Don't list all capabilities — just the 2-3 most relevant options based on context.
   - Always check conversation history first — if the context makes the intent clear, don't ask.
`;

// Visual Audit callback type for UI updates
export type VisualAuditCallback = (update: {
  type: 'start' | 'log' | 'stage' | 'complete';
  query?: string;
  log?: string;
  stage?: 'searching' | 'analyzing' | 'extracting' | 'complete';
  pages?: number[];  // Target pages for PDF panel scanning animation
}) => void;

export class Agent {
  private messages: Message[] = [];
  private currentDocumentType: DocumentType = "unknown";
  private documentContent: string | null = null;
  private readonly MAX_CONVERSATION_MESSAGES = 30; // Keep last 30 messages (matches summarization interval)

  // Phase 4: RAG state for COA document queries
  private activeCoaProcessId: string | null = null;
  private activeCoaFilename: string | null = null;
  private lastRAGResponse: RAGResponse | null = null;

  // Every document uploaded in this chat, not just the active one. Without this the
  // agent only ever knew about the most recent upload and told users their earlier
  // files were "not uploaded yet", so they re-uploaded or reported them as lost.
  private knownDocuments: Array<{ processId: string; filename: string }> = [];

  // Visual Audit UI callback
  private visualAuditCallback: VisualAuditCallback | null = null;

  // AbortController for cancelling in-flight HTTP requests
  private abortController: AbortController | null = null;

  constructor() {
    // Initialize with system message
    this.resetConversation();
  }

  /**
   * Set the active COA document for RAG queries
   * Called from page.tsx when a COA document is successfully indexed
   */
  public setActiveCoaDocument(processId: string, filename?: string): void {
    this.activeCoaProcessId = processId;
    this.activeCoaFilename = filename || null;
    this.rememberDocument(processId, filename);
    console.log(`[Agent] Active COA document set: ${processId} (${filename || 'unknown'})`);
  }

  /**
   * Record a document as present in this chat. Keeps the roster the system prompt
   * advertises, so switching the active document never makes the others invisible.
   */
  private rememberDocument(processId: string, filename?: string): void {
    if (!processId) return;
    const existing = this.knownDocuments.find((d) => d.processId === processId);
    if (existing) {
      if (filename) existing.filename = filename;
      return;
    }
    this.knownDocuments.push({ processId, filename: filename || "unknown" });
  }

  /**
   * Replace the roster of documents available in this chat.
   * Called on chat load/switch so restored chats list every uploaded file.
   */
  public setKnownDocuments(
    docs: Array<{ processId: string; filename: string }>,
  ): void {
    this.knownDocuments = docs.filter((d) => d.processId);
    console.log(`[Agent] Known documents set: ${this.knownDocuments.length}`);
  }

  /**
   * Human-readable document state injected into the system prompt as
   * {{DOCUMENT_STATE}}. Single source of truth for every prompt build.
   */
  private buildDocumentState(): string {
    if (!this.activeCoaProcessId && this.knownDocuments.length === 0) {
      return "No document is uploaded yet. User needs to upload a PDF first.";
    }

    const lines = this.knownDocuments.map((d, i) => {
      const active = d.processId === this.activeCoaProcessId;
      return `${i + 1}. ${d.filename}${active ? "  <-- currently selected" : ""}`;
    });

    if (lines.length <= 1) {
      return `A document is currently uploaded and active (process_id: ${this.activeCoaProcessId}, filename: ${this.activeCoaFilename || "unknown"}). User can ask questions about it or extract parameters.`;
    }

    return `${lines.length} documents are uploaded in this chat and ALL of them are available:
${lines.join("\n")}

The currently selected document is "${this.activeCoaFilename || "unknown"}" (process_id: ${this.activeCoaProcessId}); questions are answered against it.
NEVER tell the user a document in the list above is missing or "not uploaded yet" — every one of them is uploaded and retained.
If the user asks about a document that is in the list but is not the selected one, tell them it is uploaded and ask them to pick it from the document switcher above the message box (or name it) so you can query it. Answering across several documents at once is not supported yet, so handle them one at a time.`;
  }

  /**
   * Clear the active COA document
   */
  public clearActiveCoaDocument(): void {
    this.activeCoaProcessId = null;
    this.activeCoaFilename = null;
    this.lastRAGResponse = null;
    this.knownDocuments = [];
    console.log('[Agent] Active COA document cleared');
  }

  /**
   * Abort any in-flight HTTP requests (Claude API, RAG queries, streaming)
   * Called when user clicks the stop button during a chat response
   */
  public abort(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }

  /**
   * Check if there's an active COA document for RAG queries
   */
  public hasActiveCoaDocument(): boolean {
    return this.activeCoaProcessId !== null;
  }

  /**
   * Get the last RAG response (for reference highlighting in UI)
   */
  public getLastRAGResponse(): RAGResponse | null {
    return this.lastRAGResponse;
  }

  public resetConversation() {
    const docState = this.buildDocumentState();

    this.messages = [
      {
        role: "system",
        content: SYSTEM_PROMPT.replace("{{DOCUMENT_STATE}}", docState),
      },
    ];
    this.currentDocumentType = "unknown";
    this.documentContent = null;
  }

  /**
   * Load conversation history from database into the agent's memory
   * This is called when switching chats or on page reload
   * @param history - Array of messages from the database (user and assistant only, last 20)
   * @param summary - Optional summary of older messages (for conversations > 30 messages)
   */
  public loadConversationHistory(
    history: Array<{ role: "user" | "assistant"; content: string }>,
    summary?: string
  ) {
    // Build the system prompt with summary if available.
    // Must substitute {{DOCUMENT_STATE}} — leaving it raw shipped the literal
    // placeholder to the model on every chat load.
    let systemContent = SYSTEM_PROMPT.replace(
      "{{DOCUMENT_STATE}}",
      this.buildDocumentState(),
    );

    if (summary) {
      systemContent += `\n\n--- PREVIOUS CONVERSATION CONTEXT ---
The following is a summary of earlier messages in this conversation that provides important context:

${summary}

--- END OF PREVIOUS CONTEXT ---

Use this context to understand what the user has been working on and to provide consistent, relevant responses.`;
    }

    // Reset to system prompt (with or without summary)
    this.messages = [
      {
        role: "system",
        content: systemContent,
      },
    ];

    // Filter history to ensure first message is from user (Claude API requirement)
    let filteredHistory = [...history];
    while (filteredHistory.length > 0 && filteredHistory[0].role === "assistant") {
      console.log("Removing leading assistant message from history to ensure valid message order");
      filteredHistory = filteredHistory.slice(1);
    }

    // Add recent historical messages
    for (const msg of filteredHistory) {
      this.messages.push({
        role: msg.role,
        content: msg.content,
      });
    }

    console.log(`Loaded ${filteredHistory.length} recent messages into agent memory${summary ? ' (with conversation summary)' : ''} (total: ${this.messages.length})`);
  }

  /**
   * Update the summary in the system prompt and clear summarized messages
   * Called when a new summary is created in the background
   * @param summary - The new summary to incorporate
   */
  public updateSummary(summary: string) {
    if (!summary) return;

    // Build the new system prompt with summary (substitute {{DOCUMENT_STATE}})
    let systemContent = SYSTEM_PROMPT.replace(
      "{{DOCUMENT_STATE}}",
      this.buildDocumentState(),
    );
    systemContent += `\n\n--- PREVIOUS CONVERSATION CONTEXT ---
The following is a summary of earlier messages in this conversation that provides important context:

${summary}

--- END OF PREVIOUS CONTEXT ---

Use this context to understand what the user has been working on and to provide consistent, relevant responses.`;

    // Get conversation messages (excluding system prompt)
    const conversationMessages = this.messages.slice(1);

    // Summary covers batches of 30 messages. Keep only messages AFTER the summarized batch.
    // If we have 34 messages, summary covers 1-30, keep 31-34 (4 messages)
    // If we have 64 messages, summary covers 1-60, keep 61-64 (4 messages)
    // Formula: keep the last (count % 30) messages, or last 30 if exactly divisible
    const count = conversationMessages.length;
    const remainder = count % 30;
    const messagesToKeep = remainder === 0 ? 30 : remainder;
    let unsummarizedMessages = conversationMessages.slice(-messagesToKeep);

    // IMPORTANT: Claude API requires first message after system prompt to be a user message
    // If we start with an assistant message, find the first user message and start from there
    while (unsummarizedMessages.length > 0 && unsummarizedMessages[0].role === "assistant") {
      console.log("Removing leading assistant message to ensure valid message order");
      unsummarizedMessages = unsummarizedMessages.slice(1);
    }

    // Reset messages: system prompt with summary + only unsummarized messages
    this.messages = [
      { role: "system", content: systemContent },
      ...unsummarizedMessages
    ];

    console.log(`Updated agent with summary. Cleared summarized messages. Keeping ${unsummarizedMessages.length} recent messages.`);
  }

  /**
   * Process a user message and generate a response
   * Claude is the intelligent router — it decides: RAG, action, or conversational
   */
  public async processMessage(userMessage: string): Promise<string> {
    // Create a new AbortController for this request so it can be cancelled
    this.abortController = new AbortController();

    // Clear stale RAG response from previous message so references never leak
    this.lastRAGResponse = null;

    // Check if there's an active HBR session and the message might be feedback
    const hbrSessionElement = document.querySelector(".hbr-session-context");
    const hbrSessionId = hbrSessionElement?.getAttribute("data-session-id");

    if (hbrSessionId && this.isLikelyHBRFeedback(userMessage)) {
      try {
        const response = await fetch(`${API_BASE_URL}/hbr-chat-feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ session_id: hbrSessionId, message: userMessage }),
          signal: this.abortController?.signal,
        });
        const result = await response.json();
        this.messages.push({ role: "user", content: userMessage });
        this.messages.push({ role: "assistant", content: result.message });
        return result.message;
      } catch (error) {
        console.error("Error processing HBR feedback:", error);
      }
    }

    // Inject document state into system prompt so Claude knows what's available
    const docState = this.buildDocumentState();

    // Update system prompt with current document state. Preserve any conversation
    // summary already appended by loadConversationHistory/updateSummary — rebuilding
    // from bare SYSTEM_PROMPT here used to silently drop it.
    if (this.messages.length > 0 && this.messages[0].role === "system") {
      const previous = this.messages[0].content;
      const summaryMarker = "\n\n--- PREVIOUS CONVERSATION CONTEXT ---";
      const summaryIdx = previous.indexOf(summaryMarker);
      const summaryBlock = summaryIdx >= 0 ? previous.slice(summaryIdx) : "";
      this.messages[0].content =
        SYSTEM_PROMPT.replace("{{DOCUMENT_STATE}}", docState) + summaryBlock;
    }

    // Add user message to conversation history
    const contextualizedMessage = this.addContextHint(userMessage);
    this.messages.push({ role: "user", content: contextualizedMessage });

    try {
      // Step 1: Call Claude SILENTLY (no streaming) to decide intent
      // Save and clear stream callback so Claude's routing decision doesn't flash in UI
      const savedCallback = this.streamCallback;
      this.streamCallback = null;

      const claudeResponse = await this.callClaudeAPI();
      if (!claudeResponse) throw new Error("Empty response from API");

      console.log(`[Agent] Claude decided: "${claudeResponse.substring(0, 100)}..."`);

      // Step 2: Check if Claude wants to route to RAG
      if (claudeResponse.includes("[ROUTE:RAG]") && this.activeCoaProcessId) {
        console.log("[Agent] Claude routed to RAG — calling RAG v2");

        // Restore stream callback so RAG answer streams to UI
        this.streamCallback = savedCallback;

        try {
          const useStreaming = this.visualAuditCallback !== null;
          const ragResponse = useStreaming
            ? await this.callRAGv2Streaming(userMessage)
            : await this.callRAGv2(userMessage);

          this.lastRAGResponse = ragResponse;
          this.messages.push({ role: "assistant", content: ragResponse.answer });
          return ragResponse.answer;
        } catch (ragError) {
          console.error("[Agent] RAG failed, falling back:", ragError);
          this.lastRAGResponse = null;
          const fallback = "I couldn't find that in the document. Please try rephrasing.";
          this.messages.push({ role: "assistant", content: fallback });
          return fallback;
        }
      }

      // Step 3: Not a RAG route — Claude handled it directly
      // Clear lastRAGResponse so old references don't leak to this message
      this.lastRAGResponse = null;

      // Restore stream callback (for next call)
      this.streamCallback = savedCallback;

      this.messages.push({ role: "assistant", content: claudeResponse });
      return claudeResponse;

    } catch (error) {
      // Don't log abort errors — they're user-initiated cancellations
      if (error instanceof DOMException && error.name === 'AbortError') {
        console.log("[Agent] Request aborted by user");
        return "";
      }
      console.error("Error calling Claude API:", error);
      return "I encountered an error processing your request. Please try again.";
    } finally {
      this.abortController = null;
    }
  }

  /**
   * Check if a message is likely a query about the active COA document
   */
  // COMMENTED OUT — replaced by Claude-based routing in processMessage()
  // Claude now decides routing via [ROUTE:RAG] marker instead of keyword matching.
  // Keeping this for rollback if needed.
  /*
  private isLikelyCoaQuery(message: string): boolean {
    const lowerMsg = message.toLowerCase().trim();

    // Step 1: Is this a WORKFLOW action? → route to Claude (return false)
    const hasExtract = lowerMsg.includes("extract");
    const hasParam = lowerMsg.includes("param");
    if (hasExtract && hasParam) return false;

    const workflowPhrases = [
      "i want to extract", "run extraction", "extract values", "extract data",
      "upload excel", "upload pdf", "upload document", "upload file",
      "target list", "template", "download template",
      "extract more", "more parameters", "again please",
      "capabilities", "what can you do", "help me",
      "analyze coa", "analyze hbr", "process hbr", "process coa",
    ];
    if (workflowPhrases.some(phrase => lowerMsg.includes(phrase))) return false;

    // Step 2: Does this look like a DOCUMENT question? → RAG (return true)
    const documentKeywords = [
      "batch", "lot", "expir", "appearance", "specification",
      "result", "test", "assay", "purity", "potency", "content",
      "what is", "what's", "tell me", "show me", "find", "page", "table",
      "row", "column", "col", "cell", "method", "standard",
      "certificate", "coa", "analysis", "material", "product",
      "manufacturer", "supplier", "storage", "endotoxin", "sterility",
      "identity", "description", "color", "ph", "moisture", "solubility",
      "temperature", "time", "weight", "volume", "dose", "strength",
      "step", "section", "header", "footer", "signature", "verify",
      "compare", "list all", "show all", "how many", "count",
    ];
    const hasDocKeyword = documentKeywords.some(kw => lowerMsg.includes(kw));

    const isQuestion = lowerMsg.includes("?") ||
      lowerMsg.startsWith("what") || lowerMsg.startsWith("where") ||
      lowerMsg.startsWith("how") || lowerMsg.startsWith("which") ||
      lowerMsg.startsWith("show") || lowerMsg.startsWith("find") ||
      lowerMsg.startsWith("get") || lowerMsg.startsWith("tell") ||
      lowerMsg.startsWith("list");

    if (hasDocKeyword || isQuestion) return true;

    // Step 3: Everything else → Claude (return false)
    return false;
  }
  */

  /**
   * Call the RAG v2 endpoint for COA document queries
   */
  private async callRAGv2(query: string): Promise<RAGResponse> {
    if (!this.activeCoaProcessId) {
      throw new Error("No active COA document");
    }

    // Get recent messages for context resolution (last 3)
    const recentMessages = this.messages
      .filter(m => m.role !== "system")
      .slice(-6) // Get last 6 (3 user + 3 assistant pairs)
      .map(m => ({ role: m.role, content: m.content }));

    const url = `${RAG_V2_ENDPOINT}/${this.activeCoaProcessId}`;
    console.log(`[Agent] Calling RAG v2: ${url}`);

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        message: query,
        recent_messages: recentMessages,
        filename: this.activeCoaFilename,  // Include filename for visual audit PDF path
      }),
      signal: this.abortController?.signal,
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("[Agent] RAG v2 error:", errorText);
      throw new Error(`RAG v2 error: ${response.status}`);
    }

    const data: RAGResponse = await response.json();
    console.log("[Agent] RAG v2 response:", {
      success: data.success,
      query_type: data.query_type,
      confidence: data.confidence,
      references_count: data.references?.length || 0,
      cache_hit: data._cache_hit,
    });

    if (!data.success) {
      throw new Error(data.answer || "RAG query failed");
    }

    return data;
  }

  /**
   * Call RAG v2 with streaming support for Visual Audit progress
   * Uses SSE for real-time updates during Visual Audit processing
   */
  private async callRAGv2Streaming(query: string): Promise<RAGResponse> {
    if (!this.activeCoaProcessId) {
      throw new Error("No active COA document");
    }

    // Get recent messages for context resolution
    const recentMessages = this.messages
      .filter(m => m.role !== "system")
      .slice(-6)
      .map(m => ({ role: m.role, content: m.content }));

    const url = `${RAG_V2_STREAM_ENDPOINT}/${this.activeCoaProcessId}`;
    console.log(`[Agent] Calling RAG v2 Stream: ${url}`);

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        message: query,
        recent_messages: recentMessages,
        filename: this.activeCoaFilename,
      }),
      signal: this.abortController?.signal,
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("[Agent] RAG v2 Stream error:", errorText);
      throw new Error(`RAG v2 Stream error: ${response.status}`);
    }

    // Read streaming SSE response
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("No response body reader available");
    }

    const decoder = new TextDecoder();
    let finalResponse: RAGResponse | null = null;
    let buffer = ""; // Buffer for incomplete SSE data across chunks

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Process complete SSE messages (separated by double newlines)
      const messages = buffer.split("\n\n");
      // Keep the last part as it might be incomplete
      buffer = messages.pop() || "";

      for (const message of messages) {
        const lines = message.split("\n").filter(line => line.startsWith("data: "));
        // Combine multi-line data fields into one
        const dataStr = lines.map(line => line.replace("data: ", "")).join("");
        if (!dataStr.trim()) continue;

        try {
          const event = JSON.parse(dataStr);

          // Handle different SSE event types
          switch (event.type) {
            case 'visual_audit_start':
              console.log("[Agent] Visual Audit started:", event.query, "pages:", event.pages);
              this.visualAuditCallback?.({
                type: 'start',
                query: event.query,
                stage: 'searching',
                pages: event.pages || [],
              });
              break;

            case 'stage':
              console.log("[Agent] Visual Audit stage:", event.stage);
              this.visualAuditCallback?.({
                type: 'stage',
                stage: event.stage as 'searching' | 'analyzing' | 'extracting' | 'complete',
              });
              break;

            case 'log':
              console.log("[Agent] Visual Audit log:", event.log);
              this.visualAuditCallback?.({
                type: 'log',
                log: event.log,
              });
              break;

            case 'complete':
              console.log("[Agent] Visual Audit complete");
              this.visualAuditCallback?.({
                type: 'complete',
              });
              finalResponse = event.data;
              break;

            case 'error':
              console.error("[Agent] Visual Audit error:", event.error);
              this.visualAuditCallback?.({
                type: 'log',
                log: `[ERROR] ${event.error}`,
              });
              throw new Error(event.error);
          }
        } catch (e) {
          // Skip JSON parse errors (incomplete chunks)
          if (!(e instanceof SyntaxError)) {
            throw e;
          }
        }
      }
    }

    // Process any remaining buffer data
    if (buffer.trim()) {
      const lines = buffer.split("\n").filter(line => line.startsWith("data: "));
      const dataStr = lines.map(line => line.replace("data: ", "")).join("");
      if (dataStr.trim()) {
        try {
          const event = JSON.parse(dataStr);
          if (event.type === 'complete') {
            finalResponse = event.data;
          }
        } catch (_) { /* ignore */ }
      }
    }

    if (!finalResponse) {
      throw new Error("No response received from stream");
    }

    console.log("[Agent] RAG v2 Stream response:", {
      success: finalResponse.success,
      query_type: finalResponse.query_type,
      confidence: finalResponse.confidence,
      references_count: finalResponse.references?.length || 0,
    });

    return finalResponse;
  }

  /**
   * Add context hint to help AI understand references
   */
  private addContextHint(userMessage: string): string {
    const lowerMessage = userMessage.toLowerCase();

    // If message contains pronouns or references, add a hint
    if (
      lowerMessage.includes("it") ||
      lowerMessage.includes("that") ||
      lowerMessage.includes("this") ||
      lowerMessage.includes("the file") ||
      lowerMessage.includes("the document") ||
      lowerMessage.includes("total") ||
      lowerMessage.includes("analyze") ||
      lowerMessage.includes("summary") ||
      lowerMessage.includes("explain") ||
      lowerMessage.includes("show me") ||
      lowerMessage.includes("what about") ||
      lowerMessage.includes("break down") ||
      lowerMessage.includes("details")
    ) {
      return (
        userMessage +
        "\n[Assistant: Check conversation history for context about what the user is referring to]"
      );
    }

    return userMessage;
  }

  /**
   * Process a document upload and extract its content
   */
  public async analyzeDocument(
    documentText: string,
    fileName: string,
  ): Promise<string> {
    console.log("Agent analyzing document:", fileName);

    // Check if this is a PDF processing response with progress information
    if (
      documentText.includes("Processing PDF file") &&
      !documentText.includes("Process ID:")
    ) {
      console.log("Detected PDF processing progress update");
      // This is an intermediate progress update, return a simple progress message
      return "I'm processing your Certificate of Analysis PDF. This involves multiple steps including OCR extraction and data analysis, which can take up to 2-3 minutes for complex documents. I'll provide the complete analysis when finished.";
    }

    // Look for download links in the document text
    const downloadLinksMatch = documentText.match(
      /\nDownload processed files:\n([\s\S]*?)(\n\n|\nProcess ID:)/,
    );
    let downloadLinks = "";

    // Extract the download links section if found
    if (downloadLinksMatch && downloadLinksMatch[1]) {
      downloadLinks = downloadLinksMatch[1];
      console.log("Found download links:", downloadLinks);

      // Remove the download links from the document text to avoid confusion in the prompt
      documentText = documentText.replace(
        /\nDownload processed files:\n([\s\S]*?)(\n\n|\nProcess ID:)/,
        "$2",
      );
    }

    // Determine document type from filename
    this.currentDocumentType = this.detectDocumentType(fileName);
    this.documentContent = documentText;

    // Create a prompt for the LLM to analyze the document
    const analysisPrompt = `I've uploaded a ${
      this.currentDocumentType === "certificate_of_analysis"
        ? "Certificate of Analysis"
        : this.currentDocumentType === "handwritten_batch_record"
          ? "Handwritten Batch Record"
          : this.currentDocumentType === "hbr"
            ? "Handwritten Batch Record"
            : "document"
    } for analysis. Here's the extracted text:

${documentText}

Please provide a concise summary of the key information in this document.`;

    // Add the analysis prompt to conversation history
    this.messages.push({
      role: "user",
      content: analysisPrompt,
    });

    try {
      // Call Claude API for document analysis
      const response = await this.callClaudeAPI();

      // Add assistant response to conversation history
      if (response) {
        this.messages.push({
          role: "assistant",
          content: response,
        });

        // If we have download links, append them to the response
        if (downloadLinks) {
          const formattedResponse = `${response}\n\nDownload processed files:\n${downloadLinks}`;
          return formattedResponse;
        }

        return response;
      } else {
        throw new Error("Empty response from API");
      }
    } catch (error) {
      console.error("Error analyzing document:", error);
      return "I encountered an error analyzing your document. Please try again.";
    }
  }

  /**
   * Limit text to the first N sentences
   */

  private limitToFirstSentences(text: string, numSentences: number): string {
    // Basic sentence splitting (handles periods followed by space)
    const sentences = text.split(/(?<=[.!?])\s+/);

    if (sentences.length <= numSentences) {
      return text;
    }

    return sentences.slice(0, numSentences).join(" ");
  }

  // ADD THE NEW METHOD HERE - BEFORE callClaudeAPI

  /**
   * Get messages for API with sliding window
   * CRITICAL: Ensures first message after system is always from user (Claude API requirement)
   */
  private getMessagesForAPI(): Message[] {
    const messagesToSend: Message[] = [];

    // Always include the system prompt (first message)
    if (this.messages.length > 0 && this.messages[0].role === "system") {
      messagesToSend.push(this.messages[0]);
    }

    // Get conversation messages (exclude system prompt)
    const conversationMessages = this.messages.slice(1);

    // Take only the last N conversation messages
    const startIndex = Math.max(
      0,
      conversationMessages.length - this.MAX_CONVERSATION_MESSAGES,
    );
    let recentMessages = conversationMessages.slice(startIndex);

    // CRITICAL FIX: Claude API requires first message after system to be from user
    // Remove any leading assistant messages
    while (recentMessages.length > 0 && recentMessages[0].role === "assistant") {
      console.log("getMessagesForAPI: Removing leading assistant message");
      recentMessages = recentMessages.slice(1);
    }

    // If after removing assistant messages we have no user messages, return just system
    if (recentMessages.length === 0) {
      console.log("getMessagesForAPI: No user messages to send, returning system prompt only");
      return messagesToSend;
    }

    // Add recent messages
    messagesToSend.push(...recentMessages);

    console.log(
      `Sending system prompt + ${recentMessages.length} recent messages (total in memory: ${this.messages.length})`,
    );

    return messagesToSend;
  }
  /**
   * Call Claude API to get a response (non-streaming fallback)
   */
  private async callClaudeAPI(): Promise<string> {
    // Use streaming by default, fall back to non-streaming if callback not set
    if (this.streamCallback) {
      return this.callClaudeAPIStreaming(this.streamCallback);
    }
    return this.callClaudeAPINonStreaming();
  }

  /**
   * Call Claude API with STREAMING response
   * Calls the callback with each text chunk for typing effect
   */
  private async callClaudeAPIStreaming(
    onChunk: (text: string, done: boolean) => void
  ): Promise<string> {
    try {
      const messagesToSend = this.getMessagesForAPI();

      const requestBody = {
        model: "claude-4.5-haiku",
        messages: messagesToSend,
        max_tokens: 1000,
        temperature: 0.5,
        anthropic_version: "2023-06-01",
        stream: true, // Enable streaming
        cache_buster: Date.now(),
      };

      const response = await fetch(API_CONFIG.llm_url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": API_CONFIG.llm_api_key,
        },
        body: JSON.stringify(requestBody),
        signal: this.abortController?.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error("API error:", errorText);
        throw new Error(`API error: ${response.status} ${errorText}`);
      }

      // Read streaming response
      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No response body reader available");
      }

      const decoder = new TextDecoder();
      let fullResponse = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });

        // Iliad returns JSON-encoded strings: "Hello,"\n
        const lines = chunk.split("\n").filter((line) => line.trim());

        for (const line of lines) {
          try {
            // Parse the JSON string to get actual text
            const parsedText = JSON.parse(line.trim());
            if (parsedText) {
              fullResponse += parsedText;
              onChunk(fullResponse, false);
            }
          } catch {
            // If not valid JSON, try to use raw text
            const cleanText = line.trim().replace(/^"|"$/g, "");
            if (cleanText && cleanText !== "\\n") {
              // Handle escaped newlines
              const unescapedText = cleanText.replace(/\\n/g, "\n");
              fullResponse += unescapedText;
              onChunk(fullResponse, false);
            }
          }
        }
      }

      // Signal completion
      onChunk(fullResponse, true);
      return fullResponse;

    } catch (error) {
      console.error("Error calling Claude API (streaming):", error);
      throw error;
    }
  }

  /**
   * Call Claude API without streaming (original implementation)
   */
  private async callClaudeAPINonStreaming(): Promise<string> {
    try {
      // Get messages with sliding window
      const messagesToSend = this.getMessagesForAPI();

      // Prepare the request body with cache-busting
      const requestBody = {
        model: "claude-4.5-haiku",
        messages: messagesToSend,
        max_tokens: 1000,
        temperature: 0.5,
        anthropic_version: "2023-06-01",
        cache_buster: Date.now(), // Force fresh responses
      };

      // Make the API call
      const response = await fetch(API_CONFIG.llm_url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": API_CONFIG.llm_api_key,
        },
        body: JSON.stringify(requestBody),
        signal: this.abortController?.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error("API error:", errorText);
        throw new Error(`API error: ${response.status} ${errorText}`);
      }

      const data = await response.json();
      console.log("API response:", data);

      // Extract the assistant's message based on the actual response format
      if (data.completion && data.completion.content) {
        // Format matches the example you provided with completion.content
        return data.completion.content;
      } else if (data.content && data.content[0] && data.content[0].text) {
        // Alternative format with content[0].text
        return data.content[0].text;
      } else if (data.content) {
        // Direct content field
        return JSON.stringify(data.content);
      } else if (
        data.choices &&
        data.choices[0] &&
        data.choices[0].message &&
        data.choices[0].message.content
      ) {
        // OpenAI-like format
        return data.choices[0].message.content;
      } else {
        console.error("Unexpected API response format:", data);
        throw new Error("Unexpected API response format");
      }
    } catch (error) {
      console.error("Error calling Claude API:", error);
      throw error;
    }
  }

  // Stream callback for real-time UI updates
  private streamCallback: ((text: string, done: boolean) => void) | null = null;

  /**
   * Set the stream callback for real-time response updates
   */
  public setStreamCallback(callback: ((text: string, done: boolean) => void) | null): void {
    this.streamCallback = callback;
  }

  /**
   * Set the Visual Audit callback for UI updates during visual audit processing
   */
  public setVisualAuditCallback(callback: VisualAuditCallback | null): void {
    this.visualAuditCallback = callback;
  }

  /**
   * Detect document type from filename or content
   */
  private detectDocumentType(fileName: string): DocumentType {
    const lowerFileName = fileName.toLowerCase();

    if (
      lowerFileName.includes("coa") ||
      lowerFileName.includes("certificate") ||
      lowerFileName.includes("analysis")
    ) {
      return "certificate_of_analysis";
    } else if (
      lowerFileName.includes("handwritten batch") ||
      lowerFileName.includes("batch") ||
      lowerFileName.includes("record")
    ) {
      return "handwritten_batch_record";
    } else if (
      lowerFileName.includes("hbr") ||
      lowerFileName.includes("handwritten") ||
      lowerFileName.includes("batch") ||
      lowerFileName.includes("records")
    ) {
      return "hbr";
    }

    // Default case - will try to determine from content later
    return "unknown";
  }

  /**
   * Check if a message is likely HBR parameter feedback
   */
  private isLikelyHBRFeedback(message: string): boolean {
    // Keywords that suggest the user is giving feedback about extraction results
    const feedbackKeywords = [
      "missing",
      "incorrect",
      "wrong",
      "not found",
      "can't find",
      "should be",
      "actually",
      "page",
      "parameter",
      "value",
      "check",
      "look",
      "table",
      "section",
      "under",
      "below",
      "extraction",
      "extracted",
      "result",
    ];

    const messageLower = message.toLowerCase();

    // Check if message contains parameter-related terms and location/issue terms
    const hasParameterTerm = feedbackKeywords.some((keyword) =>
      messageLower.includes(keyword),
    );
    const hasPageNumber =
      /page\s*\d+/i.test(message) || /p\.\s*\d+/i.test(message);

    // If message mentions a page and has feedback keywords, it's likely feedback
    return hasParameterTerm && (hasPageNumber || messageLower.includes("page"));
  }

  /**
   * Get the current conversation history
   */
  public getConversationHistory(): Message[] {
    return this.messages.filter((msg) => msg.role !== "system");
  }
}

// Export a singleton instance
export const agent = new Agent();
