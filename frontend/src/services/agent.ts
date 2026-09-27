// Agent service for OCR Chatbot
// Specialized in extracting information from Handwritten Batch Records and Certificates of Analysis

// Environment Configuration - Comment/Uncomment as needed
//const API_BASE_URL = "http://localhost:5000"; // Local development
const API_BASE_URL =
  "https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com"; // Dev environment (via nginx proxy)

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
  llm_api_key:
    process.env.NEXT_PUBLIC_CLAUDE_API_KEY ||
    "IHnmjp7BE3ijTUzqnaAHAMK7elgQVZYs",
  llm_url:
    process.env.NEXT_PUBLIC_CLAUDE_API_URL ||
    "https://api-epic.ir-gateway.abbvienet.com/iliad/api/v1/chat/claude-3-haiku",
};

// System prompt that defines the agent's capabilities and restrictions
const SYSTEM_PROMPT = `
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
- These markers help the UI show the correct upload interface
- Include these markers even if the user doesn't use exact keywords - use your understanding of their intent

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

export class Agent {
  private messages: Message[] = [];
  private currentDocumentType: DocumentType = "unknown";
  private documentContent: string | null = null;
  private readonly MAX_CONVERSATION_MESSAGES = 20;
  constructor() {
    // Initialize with system message
    this.resetConversation();
  }

  public resetConversation() {
    this.messages = [
      {
        role: "system",
        content: SYSTEM_PROMPT,
      },
    ];
    this.currentDocumentType = "unknown";
    this.documentContent = null;
  }

  /**
   * Process a user message and generate a response
   */
  public async processMessage(userMessage: string): Promise<string> {
    // Check if there's an active HBR session and the message might be feedback
    const hbrSessionElement = document.querySelector(".hbr-session-context");
    const hbrSessionId = hbrSessionElement?.getAttribute("data-session-id");

    if (hbrSessionId && this.isLikelyHBRFeedback(userMessage)) {
      // This might be feedback about HBR results
      try {
        const response = await fetch(`${API_BASE_URL}/hbr-chat-feedback`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            session_id: hbrSessionId,
            message: userMessage,
          }),
        });

        const result = await response.json();

        if (result.needs_clarification) {
          // Need more information from user
          this.messages.push({
            role: "user",
            content: userMessage,
          });
          this.messages.push({
            role: "assistant",
            content: result.message,
          });
          return result.message;
        } else if (result.success) {
          // Successfully processed feedback
          this.messages.push({
            role: "user",
            content: userMessage,
          });
          this.messages.push({
            role: "assistant",
            content: result.message,
          });
          return result.message;
        } else {
          // Failed to find parameter
          this.messages.push({
            role: "user",
            content: userMessage,
          });
          this.messages.push({
            role: "assistant",
            content: result.message,
          });
          return result.message;
        }
      } catch (error) {
        console.error("Error processing HBR feedback:", error);
        // Fall through to regular processing
      }
    }

    // Add context hint for better understanding
    const contextualizedMessage = this.addContextHint(userMessage);

    // Add user message to conversation history
    this.messages.push({
      role: "user",
      content: contextualizedMessage,
    });

    try {
      // Call Claude API
      const response = await this.callClaudeAPI();

      // Add assistant response to conversation history
      if (response) {
        this.messages.push({
          role: "assistant",
          content: response,
        });
        return response;
      } else {
        throw new Error("Empty response from API");
      }
    } catch (error) {
      console.error("Error calling Claude API:", error);
      return "I encountered an error processing your request. Please try again.";
    }
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
    fileName: string
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
      /\nDownload processed files:\n([\s\S]*?)(\n\n|\nProcess ID:)/
    );
    let downloadLinks = "";

    // Extract the download links section if found
    if (downloadLinksMatch && downloadLinksMatch[1]) {
      downloadLinks = downloadLinksMatch[1];
      console.log("Found download links:", downloadLinks);

      // Remove the download links from the document text to avoid confusion in the prompt
      documentText = documentText.replace(
        /\nDownload processed files:\n([\s\S]*?)(\n\n|\nProcess ID:)/,
        "$2"
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
      conversationMessages.length - this.MAX_CONVERSATION_MESSAGES
    );
    const recentMessages = conversationMessages.slice(startIndex);

    // Add recent messages
    messagesToSend.push(...recentMessages);

    console.log(
      `Sending system prompt + ${recentMessages.length} recent messages (total in memory: ${this.messages.length})`
    );

    return messagesToSend;
  }
  /**
   * Call Claude API to get a response
   */
  private async callClaudeAPI(): Promise<string> {
    try {
      // Get messages with sliding window
      const messagesToSend = this.getMessagesForAPI(); // ADD THIS LINE

      // Prepare the request body with cache-busting
      const requestBody = {
        model: "claude-3-haiku-20240307",
        messages: messagesToSend, // CHANGE from this.messages to messagesToSend
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
      messageLower.includes(keyword)
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
