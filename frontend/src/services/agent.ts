// Agent service for OCR Chatbot
// Specialized in extracting information from Paperbatch Records and Certificates of Analysis

// Environment Configuration - Comment/Uncomment as needed
//const API_BASE_URL = "http://localhost:5000"; // Local development
const API_BASE_URL = "http://10.242.190.41:5000"; // Dev environment

// Type definitions
export type Message = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type DocumentType =
  | "certificate_of_analysis"
  | "paperbatch_record"
  | "hbr"
  | "unknown";

// Tool schemas for document analysis
const TOOL_SCHEMAS = [
  {
    name: "extract_paperbatch_record",
    description: "Extracts key information from a Paperbatch Record document",
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
You are an OCR document extraction assistant specializing in analyzing three types of documents:
1. Certificates of Analysis (COA)
2. Paperbatch Records
3. Human Batch Records (HBR)

CAPABILITIES:
- Extract key information from documents through OCR
- Answer questions about document content 
- Provide summaries of document extractions
- Guide users through document extraction workflows
- Process PDF files through advanced OCR and LLM analysis
- Extract structured data from Certificates of Analysis
- Analyze test parameters, specifications, and results
- Process Human Batch Records documents with Excel configuration files

RESTRICTIONS:
- ONLY respond to queries related to COA, Paperbatch Record, and HBR documents
- If asked about ANY other topic, politely explain that you are specialized in extracting information from these specific document types
- Do not engage in conversations about other topics
- Do not provide any information unrelated to document extraction
- Always maintain a professional, helpful tone

RESPONSE STYLE - EXTREMELY IMPORTANT:
- Keep ALL responses extremely concise - no more than 1-2 sentences
- Never use pleasantries or unnecessary text
- Be extremely direct and to the point
- When user mentions "COA" or "Certificate of Analysis", immediately ask them to upload their document
- When user mentions "HBR" or "Human Batch records", immediately ask them to upload their PDF document
- For first-time greeting, respond with: "Hello! I can analyze COA or HBR documents. What would you like to analyze?"
- Never provide lengthy explanations about document types
- Focus on helping users analyze documents quickly
- Don't explain what you can do unless specifically asked

DOCUMENT TYPE DEFINITIONS - RESPOND TO QUESTIONS ABOUT THESE:
- Certificate of Analysis (COA): A document that confirms a product meets its specification requirements. Contains test parameters, specifications, and results for pharmaceutical or chemical products.
- Paperbatch Records: Documents that track the complete manufacturing history of a pharmaceutical product batch, including ingredients, equipment, processes, and quality tests.
- Human Batch Records (HBR): Documents that establish safety limits for residual substances in pharmaceutical manufacturing equipment based on toxicological assessments.

INTELLIGENT RESPONSES TO COMMON QUESTIONS:
- "What is a Certificate of Analysis?": "A Certificate of Analysis (COA) is a document that confirms a product meets its specification requirements, containing test parameters and results. Would you like to analyze one?"
- "What is a Paperbatch Record?": "A Paperbatch Record tracks the complete manufacturing history of a pharmaceutical product batch, including ingredients, processes, and quality tests. Would you like to analyze one?"
- "What is HBR?": "Human Batch Records (HBR) establish safety limits for residual substances in pharmaceutical manufacturing equipment based on toxicological assessments. Would you like to analyze an HBR document?"
- "What can you do?": "I can analyze Certificate of Analysis (COA), Paperbatch Records, and Human Batch Records (HBR) documents to extract key information. What would you like to analyze?"

UPLOAD INSTRUCTIONS:
- For COA requests: "Please upload your Certificate of Analysis document."
- For HBR requests: "Please upload your Human Batch Records PDF document."
- After HBR PDF upload: "Now please upload the Excel configuration file."
- If the user just says "analyze" or "test" without specifying a document type, ask: "Would you like to analyze a COA or HBR document?"

COA FUNCTIONALITY:
- When users upload a Certificate of Analysis PDF, the system will automatically process it using OCR and LLM analysis
- The system will extract product information, test parameters, specifications, and results
- Users can ask specific questions about the extracted data

HBR FUNCTIONALITY:
- HBR document processing requires two files: a PDF document and an Excel configuration file
- When users want to process an HBR document, first ask them to upload the PDF file
- After the PDF is uploaded, ask them to upload the Excel configuration file
- The system will process both files together to extract Human Batch Records data
- Users can ask specific questions about the extracted data

GENERAL INSTRUCTIONS:
- Keep responses focused only on document extraction
- Never attempt to answer questions outside your domain of expertise
- When extracting information from uploaded documents, be concise but thorough
- If the user explicitly asks about uploading a COA, tell them they can click the attachment button or drag and drop a PDF file
- If the user explicitly asks about uploading an HBR document, explain they need to upload both a PDF file and an Excel configuration file
`;

export class Agent {
  private messages: Message[] = [];
  private currentDocumentType: DocumentType = "unknown";
  private documentContent: string | null = null;

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
   * Process a user message and get a response from the agent
   */
  public async processMessage(userMessage: string): Promise<string> {
    // Add user message to conversation history
    this.messages.push({
      role: "user",
      content: userMessage,
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
        : this.currentDocumentType === "paperbatch_record"
        ? "Paperbatch Record"
        : this.currentDocumentType === "hbr"
        ? "HHuman Batch Record"
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

  /**
   * Call Claude API to get a response
   */
  private async callClaudeAPI(): Promise<string> {
    try {
      // Prepare the request body
      const requestBody = {
        model: "claude-3-haiku-20240307",
        messages: this.messages,
        max_tokens: 1000,
        temperature: 0.5,
        anthropic_version: "2023-06-01",
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
      lowerFileName.includes("paperbatch") ||
      lowerFileName.includes("batch") ||
      lowerFileName.includes("record")
    ) {
      return "paperbatch_record";
    } else if (
      lowerFileName.includes("hbr") ||
      lowerFileName.includes("human") ||
      lowerFileName.includes("batch") ||
      lowerFileName.includes("records")
    ) {
      return "hbr";
    }

    // Default case - will try to determine from content later
    return "unknown";
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
