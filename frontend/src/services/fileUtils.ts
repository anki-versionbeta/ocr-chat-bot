/**
 * Utility functions for handling document files in the OCR Chatbot
 */

// Environment Configuration - Comment/Uncomment as needed
//const API_BASE_URL = "http://localhost:5000"; // Local development
const API_BASE_URL = "http://10.242.190.41:5000"; // Dev environment

/**
 * Extract text from a file
 * This now uploads the file to the backend OCR service when it's a PDF
 */
export async function extractTextFromFile(
  file: File,
  progressCallback?: (
    stage: "uploading" | "extracting" | "analyzing",
    progress: number
  ) => void,
  documentType?: "coa" | "hbr_pdf" | "hbr_excel",
  hbrProcessId?: string
): Promise<string> {
  // For text files, read directly
  if (file.type === "text/plain") {
    return await file.text();
  }

  // For PDF files, send to our backend OCR service
  if (file.type === "application/pdf" || file.name.endsWith(".pdf")) {
    console.log("Processing PDF file:", file.name);

    // If document type is specified as HBR PDF, use the HBR upload handler
    if (documentType === "hbr_pdf") {
      return await handleHbrPdfUpload(file, progressCallback);
    }

    // Otherwise use the standard COA upload handler
    return await handlePdfUpload(file, progressCallback);
  }

  // For Excel files (HBR configuration)
  if (
    file.type ===
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
    file.type === "application/vnd.ms-excel" ||
    file.name.endsWith(".xlsx") ||
    file.name.endsWith(".xls")
  ) {
    console.log("Processing Excel file:", file.name);

    // If document type is specified as HBR Excel and we have a process ID, use the HBR Excel upload handler
    if (documentType === "hbr_excel" && hbrProcessId) {
      return await handleHbrExcelUpload(file, hbrProcessId, progressCallback);
    }

    // If not specified as HBR Excel or no process ID, return an error message
    return `[Error: Excel files are only supported for HBR configuration. Please upload a PDF file first.]`;
  }

  // For other files (images), we'll need to use the backend for OCR in the future
  return `[This is placeholder text. In production, the file ${file.name} would be sent to the backend for OCR processing.]`;
}

/**
 * Handle PDF file upload to the backend OCR service
 */
async function handlePdfUpload(
  file: File,
  progressCallback?: (
    stage: "uploading" | "extracting" | "analyzing",
    progress: number
  ) => void
): Promise<string> {
  try {
    // Simulate more detailed upload progress
    progressCallback?.("uploading", 0);

    // Create FormData object to send the file
    const formData = new FormData();
    formData.append("file", file);

    // Immediately start the upload without artificial delays
    progressCallback?.("uploading", 10);
    console.log("Uploading PDF file to backend...");

    // Call the direct upload-coa endpoint which is faster and doesn't require authentication
    const response = await fetch(`${API_BASE_URL}/upload-coa`, {
      method: "POST",
      body: formData,
    });

    console.log("Backend response status:", response.status);
    progressCallback?.("uploading", 50);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend error response:", errorText);
      throw new Error(errorText || "Failed to process PDF file");
    }

    progressCallback?.("extracting", 70);
    const data = await response.json();
    console.log("Received data from backend:", data);
    progressCallback?.("analyzing", 90);

    // Create a formatted text representation
    let extractedText = "";

    if (data.message) {
      extractedText += data.message + "\n\n";
    }

    if (data.extracted_text) {
      extractedText += data.extracted_text;
    }

    // Add download links if available with enhanced styling
    if (data.download_links) {
      extractedText += "\n\n### Download Processed Files\n\n";

      // Special highlight for the unified Excel file (most important)
      if (data.download_links["Unified Excel Report"]) {
        const downloadUrl = data.download_links["Unified Excel Report"];
        const fullUrl = (downloadUrl as string).startsWith("http")
          ? (downloadUrl as string)
          : `${API_BASE_URL}${downloadUrl}`;
        console.log(`Download link for Unified Excel Report: ${fullUrl}`);
        extractedText += `📊 **[Download Complete Excel Report](${fullUrl})** - Recommended\n\n`;
      }

      // Add other download links
      Object.entries(data.download_links).forEach(([name, url]) => {
        if (name !== "Unified Excel Report") {
          let icon = "📄";
          if (name.includes("Excel")) icon = "📊";
          if (name.includes("CSV")) icon = "📋";
          if (name.includes("JSON")) icon = "🔍";

          // Make sure the URL is absolute
          const fullUrl = (url as string).startsWith("http")
            ? (url as string)
            : `${API_BASE_URL}${url}`;
          console.log(`Download link for ${name}: ${fullUrl}`);
          extractedText += `${icon} [${name}](${fullUrl})\n`;
        }
      });

      // Add a direct download button with JavaScript
      extractedText +=
        "\n\nIf the download links above don't work, please use these direct download buttons:\n\n";

      // First add the unified Excel report if available
      if (data.download_links["Unified Excel Report"]) {
        const downloadUrl = data.download_links["Unified Excel Report"];
        const fullUrl = (downloadUrl as string).startsWith("http")
          ? (downloadUrl as string)
          : `${API_BASE_URL}${downloadUrl}`;

        extractedText += `<div class="direct-download-button" data-url="${fullUrl}" data-filename="Unified Excel Report">Download Complete Excel Report</div>\n`;
      }

      // Then add other download buttons
      Object.entries(data.download_links).forEach(([name, url]) => {
        if (name !== "Unified Excel Report") {
          const fullUrl = (url as string).startsWith("http")
            ? (url as string)
            : `${API_BASE_URL}${url}`;

          extractedText += `<div class="direct-download-button" data-url="${fullUrl}" data-filename="${name}">${name}</div>\n`;
        }
      });
    }

    // Add process ID if available
    if (data.process_id) {
      extractedText += `\n\n*Process ID: ${data.process_id}*`;
    }

    // Processing complete
    progressCallback?.("analyzing", 100);
    return extractedText;
  } catch (error) {
    console.error("Error uploading PDF file:", error);
    return `[Error processing ${file.name}: ${
      (error as Error).message
    }]\n\nPlease check that:\n1. The backend server is running\n2. The file is a valid PDF document`;
  }
}

/**
 * Handle HBR PDF file upload to the backend
 */
async function handleHbrPdfUpload(
  file: File,
  progressCallback?: (
    stage: "uploading" | "extracting" | "analyzing",
    progress: number
  ) => void
): Promise<string> {
  try {
    // Show upload progress
    progressCallback?.("uploading", 0);

    // Create FormData object to send the file
    const formData = new FormData();
    formData.append("file", file);

    // Start the upload
    progressCallback?.("uploading", 20);
    console.log("Uploading HBR PDF file to backend...");

    // Call the HBR PDF upload endpoint
    const response = await fetch(`${API_BASE_URL}/upload-hbr-pdf`, {
      method: "POST",
      body: formData,
    });

    console.log("Backend response status:", response.status);
    progressCallback?.("uploading", 50);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend error response:", errorText);
      throw new Error(errorText || "Failed to process HBR PDF file");
    }

    progressCallback?.("extracting", 70);
    const data = await response.json();
    console.log("Received data from backend:", data);
    progressCallback?.("analyzing", 100);

    if (!data.success) {
      throw new Error(data.error || "Unknown error processing HBR PDF file");
    }

    // Create a formatted response message
    const extractedText = `## HBR PDF File Uploaded Successfully

**File:** ${file.name}
**Process ID:** ${data.process_id}

${data.message}

Please upload the Excel configuration file next to complete the HBR processing.

<hbr_process_id>${data.process_id}</hbr_process_id>`;

    return extractedText;
  } catch (error) {
    console.error("Error uploading HBR PDF file:", error);
    return `[Error processing ${file.name}: ${
      (error as Error).message
    }]\n\nPlease check that:\n1. The backend server is running\n2. The file is a valid PDF document`;
  }
}

/**
 * Handle HBR Excel configuration file upload to the backend
 */
async function handleHbrExcelUpload(
  file: File,
  processId: string,
  progressCallback?: (
    stage: "uploading" | "extracting" | "analyzing",
    progress: number
  ) => void
): Promise<string> {
  try {
    // Show upload progress
    progressCallback?.("uploading", 0);

    // Create FormData object to send the file
    const formData = new FormData();
    formData.append("file", file);
    formData.append("process_id", processId);

    // Start the upload
    progressCallback?.("uploading", 20);
    console.log("Uploading HBR Excel file to backend...");

    // Call the HBR Excel upload endpoint
    const response = await fetch(`${API_BASE_URL}/upload-hbr-excel`, {
      method: "POST",
      body: formData,
    });

    console.log("Backend response status:", response.status);
    progressCallback?.("uploading", 50);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend error response:", errorText);
      throw new Error(errorText || "Failed to process HBR Excel file");
    }

    progressCallback?.("extracting", 70);
    const data = await response.json();
    console.log("Received data from backend:", data);
    progressCallback?.("analyzing", 90);

    if (!data.success) {
      throw new Error(data.error || "Unknown error processing HBR Excel file");
    }

    // Create a formatted text representation
    let extractedText = "";

    if (data.message) {
      extractedText += data.message + "\n\n";
    }

    // Add download links if available
    if (data.download_links) {
      extractedText += "### Download Processed Files\n\n";

      // Add download links with full URL
      Object.entries(data.download_links).forEach(([name, url]) => {
        let icon = "📄";
        if (name.includes("Excel")) icon = "📊";
        if (name.includes("CSV")) icon = "📋";
        if (name.includes("JSON")) icon = "🔍";

        // Make sure the URL is absolute
        const fullUrl = (url as string).startsWith("http")
          ? (url as string)
          : `${API_BASE_URL}${url}`;

        console.log(`Download link for ${name}: ${fullUrl}`);
        extractedText += `${icon} [${name}](${fullUrl})\n`;
      });

      // Add a direct download button with JavaScript
      extractedText +=
        "\n\nIf the download links above don't work, please use this direct download button:\n\n";

      Object.entries(data.download_links).forEach(([name, url]) => {
        const fullUrl = (url as string).startsWith("http")
          ? (url as string)
          : `${API_BASE_URL}${url}`;

        extractedText += `<div class="direct-download-button" data-url="${fullUrl}" data-filename="${name}">${name}</div>\n`;
      });
    }

    // Add process ID if available
    if (data.process_id) {
      extractedText += `\n\n*Process ID: ${data.process_id}*`;
    }

    // Processing complete
    progressCallback?.("analyzing", 100);
    return extractedText;
  } catch (error) {
    console.error("Error uploading HBR Excel file:", error);
    return `[Error processing ${file.name}: ${
      (error as Error).message
    }]\n\nPlease check that:\n1. The backend server is running\n2. The file is a valid Excel document\n3. You have uploaded the PDF file first`;
  }
}

/**
 * Utility function to determine if a file is a supported document type
 */
export function isSupportedDocumentType(file: File): boolean {
  const supportedTypes = [
    "text/plain",
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ];

  return (
    supportedTypes.includes(file.type) ||
    file.name.endsWith(".pdf") ||
    file.name.endsWith(".docx") ||
    file.name.endsWith(".doc") ||
    file.name.endsWith(".txt") ||
    file.name.endsWith(".jpg") ||
    file.name.endsWith(".jpeg") ||
    file.name.endsWith(".png") ||
    file.name.endsWith(".xlsx") ||
    file.name.endsWith(".xls")
  );
}

/**
 * Format file size for display
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return bytes + " bytes";
  } else if (bytes < 1024 * 1024) {
    return (bytes / 1024).toFixed(1) + " KB";
  } else {
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }
}
