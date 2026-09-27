/**
 * Utility functions for handling document files in the OCR Chatbot
 */

// Environment Configuration - Comment/Uncomment as needed
//const API_BASE_URL = "http://localhost:5000"; // Local development
const API_BASE_URL =
  "https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com"; // Dev environment (via nginx proxy)

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
  documentType?: "coa" | "hbr_pdf" | "hbr_excel" | "hbr_excel_multiagent",
  hbrProcessId?: string,
  onProcessIdReceived?: (processId: string) => void
): Promise<string> {
  // For text files, read directly
  if (file.type === "text/plain") {
    return await file.text();
  }

  try {
    // For PDF files, send to our backend OCR service
    if (file.type === "application/pdf" || file.name.endsWith(".pdf")) {
      console.log("Processing PDF file:", file.name);

      try {
        // If document type is specified as HBR PDF, use the HBR upload handler
        if (documentType === "hbr_pdf") {
          const result = await handleHbrPdfUpload(file, progressCallback);

          // Check for Textract errors in the response
          if (
            result.toLowerCase().includes("textract") &&
            result.toLowerCase().includes("error")
          ) {
            console.error("Textract error detected in response");
            progressCallback?.("analyzing", 0);
            return `[Error processing ${file.name}: Textract service failed. Please try again or check server logs for details.]`;
          }

          return result;
        }

        // Otherwise use the standard COA upload handler
        const result = await handlePdfUpload(
          file,
          progressCallback,
          onProcessIdReceived
        );

        // Check for Textract errors in the response
        if (
          result.toLowerCase().includes("textract") &&
          result.toLowerCase().includes("error")
        ) {
          console.error("Textract error detected in response");
          progressCallback?.("analyzing", 0);
          return `[Error processing ${file.name}: Textract service failed. Please try again or check server logs for details.]`;
        }

        return result;
      } catch (error) {
        console.error("Error in PDF processing:", error);

        // Make sure progress callback is reset
        progressCallback?.("analyzing", 0);

        // For timeout errors, continue waiting instead of showing timeout message
        if (
          (error as Error).message.toLowerCase().includes("timeout") ||
          (error as Error).message.toLowerCase().includes("no updates received")
        ) {
          console.warn(
            "Frontend timeout detected, but continuing to wait for backend processing"
          );
          // Re-throw the error to be handled by the caller, which will continue processing
          throw error;
        }

        // If we reach here, there was an error
        if (error instanceof Error) {
          console.error("Error during file processing:", error);

          // Don't format cancellation errors - just re-throw them silently
          const errorMessage = error.message.toLowerCase();
          if (
            errorMessage.includes("cancelled by user") ||
            errorMessage.includes("process cancelled")
          ) {
            console.log(
              "File processing cancelled by user, re-throwing silently"
            );
            throw error;
          }

          // Re-throw the error to be handled by the caller
          throw error;
        }

        // Format a user-friendly error message
        return `[Error processing ${file.name}: ${
          (error as Error).message
        }]\n\nPlease check that:\n1. The backend server is running\n2. The file is a valid PDF document\n3. Your network connection is stable`;
      }
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

      try {
        // If document type is specified as HBR Excel and we have a process ID, use the appropriate HBR Excel upload handler
        if (documentType === "hbr_excel_multiagent" && hbrProcessId) {
          const result = await handleHbrExcelUploadMultiAgent(
            file,
            hbrProcessId,
            progressCallback
          );

          // Check for Textract errors in the response
          if (
            result.toLowerCase().includes("textract") &&
            result.toLowerCase().includes("error")
          ) {
            console.error("Textract error detected in response");
            progressCallback?.("analyzing", 0);
            return `[Error processing ${file.name}: Textract service failed. Please try again or check server logs for details.]`;
          }

          return result;
        } else if (documentType === "hbr_excel" && hbrProcessId) {
          const result = await handleHbrExcelUpload(
            file,
            hbrProcessId,
            progressCallback
          );

          // Check for Textract errors in the response
          if (
            result.toLowerCase().includes("textract") &&
            result.toLowerCase().includes("error")
          ) {
            console.error("Textract error detected in response");
            progressCallback?.("analyzing", 0);
            return `[Error processing ${file.name}: Textract service failed. Please try again or check server logs for details.]`;
          }

          return result;
        }

        // If not specified as HBR Excel or no process ID, return an error message
        progressCallback?.("analyzing", 0);
        return `[Error: Excel files are only supported for HBR configuration. Please upload a PDF file first.]`;
      } catch (error) {
        console.error("Error in Excel processing:", error);

        // Don't format cancellation errors - just re-throw them
        const errorMessage = (error as Error).message.toLowerCase();
        if (
          errorMessage.includes("cancelled by user") ||
          errorMessage.includes("process cancelled")
        ) {
          console.log(
            "Excel processing: Process cancelled by user, re-throwing silently"
          );

          // Reset progress callback before re-throwing
          progressCallback?.("analyzing", 0);

          throw error; // Re-throw to be handled by the caller silently
        }

        // Make sure progress callback is reset
        progressCallback?.("analyzing", 0);

        // Format a user-friendly error message
        return `[Error processing Excel file ${file.name}: ${
          (error as Error).message
        }]\n\nPlease check that:\n1. The backend server is running\n2. The file is a valid Excel document\n3. You have uploaded the PDF file first`;
      }
    }

    // For other files (images), we'll need to use the backend for OCR in the future
    return `[This is placeholder text. In production, the file ${file.name} would be sent to the backend for OCR processing.]`;
  } catch (error) {
    console.error("Error in extractTextFromFile:", error);

    // Don't format cancellation errors - just re-throw them
    const errorMessage = (error as Error).message.toLowerCase();
    if (
      errorMessage.includes("cancelled by user") ||
      errorMessage.includes("process cancelled")
    ) {
      console.log(
        "extractTextFromFile: Process cancelled by user, re-throwing silently"
      );

      // Reset progress callback before re-throwing
      progressCallback?.("analyzing", 0);

      throw error; // Re-throw to be handled by the caller silently
    }

    // Make sure progress callback is reset
    progressCallback?.("analyzing", 0);

    // Format a user-friendly error message
    return `[Error processing ${file.name}: ${
      (error as Error).message
    }]\n\nPlease check that:\n1. The backend server is running\n2. The file is a valid document\n3. Your network connection is stable`;
  }
}

/**
 * Handle HBR parameter feedback request
 */
export async function handleHbrParameterFeedback(
  sessionId: string,
  parameter: string,
  userMessage: string,
  pagesAlreadyChecked: number[] = []
): Promise<string> {
  try {
    console.log(
      `Requesting feedback for parameter: ${parameter} in session: ${sessionId}`
    );

    const response = await fetch(`${API_BASE_URL}/hbr-feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: sessionId,
        missing_parameter: parameter,
        user_message: userMessage,
        pages_already_checked: pagesAlreadyChecked,
      }),
    });

    console.log("Feedback response status:", response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Feedback error response:", errorText);
      throw new Error(errorText || "Failed to get parameter feedback");
    }

    const data = await response.json();
    console.log("Received feedback data:", data);

    if (!data.success) {
      throw new Error(data.error || "Unknown error getting parameter feedback");
    }

    // Add reprocess button to the response
    let responseText = data.message;

    if (data.recommended_pages && data.recommended_pages.length > 0) {
      responseText += `\n\n<div class="reprocess-parameter-button" data-session-id="${sessionId}" data-parameter="${parameter}" data-recommended-pages="${data.recommended_pages.join(
        ","
      )}" data-placeholder="Enter specific hint (e.g., 'look in table header', 'bottom of page')">🔄 Search recommended pages with your hint</div>`;
    }

    return responseText;
  } catch (error) {
    console.error("Error getting HBR parameter feedback:", error);
    return `[Error getting feedback for ${parameter}: ${
      (error as Error).message
    }]\n\nPlease check that the backend server is running.`;
  }
}

/**
 * Handle HBR parameter reprocessing with user hint
 */
export async function handleHbrParameterReprocess(
  sessionId: string,
  parameter: string,
  userHint: string,
  recommendedPages: number[] = []
): Promise<string> {
  try {
    console.log(`Reprocessing parameter: ${parameter} with hint: ${userHint}`);

    const response = await fetch(`${API_BASE_URL}/hbr-reprocess`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: sessionId,
        parameter: parameter,
        user_hint: userHint,
        recommended_pages: recommendedPages,
      }),
    });

    console.log("Reprocess response status:", response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Reprocess error response:", errorText);
      throw new Error(errorText || "Failed to reprocess parameter");
    }

    const data = await response.json();
    console.log("Received reprocess data:", data);

    if (!data.success) {
      throw new Error(data.error || "Unknown error reprocessing parameter");
    }

    return data.message;
  } catch (error) {
    console.error("Error reprocessing HBR parameter:", error);
    return `[Error reprocessing ${parameter}: ${
      (error as Error).message
    }]\n\nPlease check that the backend server is running.`;
  }
}

/**
 * Poll for upload progress
 */
async function pollProgress(
  processId: string,
  progressCallback?: (
    stage: "uploading" | "extracting" | "analyzing",
    progress: number
  ) => void
): Promise<void> {
  let lastStage = "";
  let attempts = 0;
  const maxAttempts = 300; // 5 minutes max (300 * 1 second)

  while (attempts < maxAttempts) {
    try {
      const response = await fetch(
        `${API_BASE_URL}/upload-progress/${processId}`
      );
      if (response.ok) {
        const progress = await response.json();

        // Update progress callback
        if (progress.stage !== "unknown" && progress.stage !== "completed") {
          progressCallback?.(progress.stage as any, progress.progress);

          // Log stage changes
          if (progress.stage !== lastStage) {
            console.log(`Progress: ${progress.stage} - ${progress.message}`);
            lastStage = progress.stage;
          }
        }

        // Stop polling if completed
        if (progress.stage === "completed" || progress.progress === 100) {
          break;
        }
      }
    } catch (error) {
      console.error("Error polling progress:", error);
    }

    // Wait 1 second before next poll
    await new Promise((resolve) => setTimeout(resolve, 10000));
    attempts++;
  }
}

/**
 * Handle PDF file upload to the backend OCR service
 */
async function handlePdfUpload(
  file: File,
  progressCallback?: (
    stage: "uploading" | "extracting" | "analyzing",
    progress: number
  ) => void,
  onProcessIdReceived?: (processId: string) => void
): Promise<string> {
  try {
    // Start with 0% progress
    progressCallback?.("uploading", 0);

    // Create FormData object to send the file
    const formData = new FormData();
    formData.append("file", file);

    console.log("Uploading PDF file to backend...");

    // Start the upload
    const response = await fetch(`${API_BASE_URL}/upload-coa`, {
      method: "POST",
      body: formData,
    });

    console.log("Backend response status:", response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend error response:", errorText);
      // Make sure to call progressCallback with final values before throwing the error
      progressCallback?.("analyzing", 0);
      throw new Error(errorText || "Failed to process PDF file");
    }

    const initialData = await response.json();
    console.log("Received initial response from backend:", initialData);

    // Extract process_id and start SSE streaming
    if (initialData.process_id) {
      const processId = initialData.process_id;
      console.log("Got process_id, starting SSE progress stream:", processId);

      // Notify caller of the process ID
      onProcessIdReceived?.(processId);

      let isCompleted = false;
      let finalData: any = null;
      let hasError = false;
      let errorMessage = "";
      let wasCancelled = false;

      const eventSource = new EventSource(
        `${API_BASE_URL}/upload-progress-stream/${processId}`
      );
      // Create promise to track SSE completion
      const ssePromise = new Promise<void>((resolve, reject) => {
        // Add a timeout to automatically close SSE if no updates for 30 minutes (extended for large documents)
        let lastUpdateTime = Date.now();
        const noUpdateTimeout = setInterval(() => {
          const timeSinceLastUpdate = Date.now() - lastUpdateTime;
          if (timeSinceLastUpdate > 1800000) {
            // 30 minutes instead of 5 minutes
            console.warn(
              "No SSE updates received for 30 minutes, but backend may still be processing"
            );
            clearInterval(noUpdateTimeout);
            if (!isCompleted) {
              // Don't reset progress callback - let it continue
              console.log(
                "SSE timeout reached, but allowing backend to continue processing"
              );
              eventSource.close();
              // Don't reject the promise - just close the connection and let backend finish
              resolve(); // Resolve instead of reject to avoid showing errors
            }
          }
        }, 60000); // Check every 1 minute instead of 30 seconds

        eventSource.onmessage = (event) => {
          try {
            // Update the last update time
            lastUpdateTime = Date.now();

            const progressData = JSON.parse(event.data);

            if (progressData.type === "heartbeat") {
              console.log("Heartbeat received at:", new Date().toISOString());
              return; // Skip processing for heartbeat
            }

            // Handle timeout gracefully
            if (progressData.stage === "timeout") {
              console.log(
                "Frontend timeout reached, but backend continues processing"
              );
              return; // Don't show error, just continue
            }

            console.log(
              `Progress update: ${progressData.stage} ${progressData.progress}% - ${progressData.message}`
            );

            // Check if the message contains error information but processing continues
            if (
              progressData.message &&
              progressData.message.toLowerCase().includes("error") &&
              !progressData.stage.toLowerCase().includes("error")
            ) {
              // Log the error but don't reject if processing continues
              console.warn("Warning in processing:", progressData.message);
              hasError = true;
              errorMessage = progressData.message;

              // If this is a critical error like Textract failure, close the connection
              if (
                progressData.message.toLowerCase().includes("textract") &&
                progressData.message.toLowerCase().includes("error")
              ) {
                console.error(
                  "Critical Textract error detected, closing SSE connection"
                );
                clearInterval(noUpdateTimeout);
                progressCallback?.("analyzing", 0);
                eventSource.close();
                reject(
                  new Error(
                    "Textract processing failed: " + progressData.message
                  )
                );
                return;
              }
            }

            // Update UI with real progress
            if (progressData.stage === "uploading") {
              progressCallback?.("uploading", progressData.progress);
            } else if (progressData.stage === "extracting") {
              progressCallback?.("extracting", progressData.progress);
            } else if (progressData.stage === "analyzing") {
              progressCallback?.("analyzing", progressData.progress);
            } else if (progressData.stage === "completed") {
              progressCallback?.("analyzing", 100);
              isCompleted = true;
              clearInterval(noUpdateTimeout);
              eventSource.close();
              resolve();
            } else if (progressData.stage === "error") {
              // This is a critical error that should stop processing
              clearInterval(noUpdateTimeout);
              progressCallback?.("analyzing", 0);
              eventSource.close();
              reject(new Error(progressData.message || "Processing failed"));
            } else if (progressData.stage === "cancelled") {
              // Process was cancelled by user
              clearInterval(noUpdateTimeout);
              progressCallback?.("analyzing", 0);
              eventSource.close();
              console.log("✅ Process cancelled - stopping progress tracking");
              isCompleted = true;
              wasCancelled = true;
              resolve();
            }
          } catch (error) {
            console.error("Error parsing SSE data:", error);
            // Make sure to reset progress callback on error
            clearInterval(noUpdateTimeout);
            progressCallback?.("analyzing", 0);
            eventSource.close();
            reject(
              new Error(
                `Error parsing progress data: ${(error as Error).message}`
              )
            );
          }
        };

        eventSource.onerror = (error) => {
          console.error("SSE connection error:", error);
          // Make sure to reset progress callback on error
          clearInterval(noUpdateTimeout);
          progressCallback?.("analyzing", 0);
          eventSource.close();

          // Only reject if we haven't completed
          if (!isCompleted) {
            reject(new Error("Lost connection to progress stream"));
          }
        };

        // Timeout after 60 minutes for very large documents (extended to wait longer)
        setTimeout(() => {
          if (!isCompleted) {
            // Log timeout but don't reset progress - backend might still be working
            clearInterval(noUpdateTimeout);
            console.log(
              "SSE main timeout reached after 60 minutes, but backend may still be processing"
            );
            eventSource.close();
            // Resolve instead of reject to avoid showing timeout errors
            resolve();
          }
        }, 60 * 60 * 1000); // Increased from 15 to 60 minutes
      });

      // Wait for SSE to complete
      await ssePromise;

      // If process was cancelled, return immediately without any message
      if (wasCancelled) {
        console.log("🚫 Process was cancelled, returning empty result");
        throw new Error("Process cancelled by user");
      }

      // If processing completed, try to get the final results
      if (isCompleted) {
        try {
          const resultResponse = await fetch(
            `${API_BASE_URL}/coa-result/${processId}`
          );
          if (resultResponse.ok) {
            finalData = await resultResponse.json();
            console.log("Got final results:", finalData);
          }
        } catch (error) {
          console.error("Error getting final results:", error);
        }
      }

      // Use final data if available, otherwise use initial data
      const data = finalData || initialData;

      // If we have a process_id from the final data, make sure to report it
      if (data && data.process_id && onProcessIdReceived) {
        console.log(
          "Reporting final process ID from COA result:",
          data.process_id
        );
        onProcessIdReceived(data.process_id);
      }

      // Create a formatted text representation
      let extractedText = "";

      // If we only have initial data (async processing), show a message
      if (!finalData && initialData) {
        extractedText = `## Document Processing Started\n\n`;
        extractedText += `Your document is being processed in the background.\n\n`;
        extractedText += `The processing typically takes 2-3 minutes. The results will be available once processing is complete.`;
        return extractedText;
      }

      // Add warning about partial success if applicable
      if (hasError) {
        extractedText += `⚠️ **Note:** There were some issues during processing, but we were able to complete the analysis using fallback methods.\n\n`;
        if (errorMessage) {
          extractedText += `*Warning: ${errorMessage}*\n\n`;
        }
      }

      if (data.message) {
        extractedText += data.message + "\n\n";
      }

      if (data.extracted_text) {
        extractedText += data.extracted_text;
      }

      // Add download links if available with enhanced styling
      if (data.download_links) {
        extractedText += "\n\n### Download Results\n\n";

        // Find the most important result file (enhanced, unified, or results file)
        let primaryFile = null;
        let primaryUrl = null;

        // Priority order: Enhanced report > Unified report > Results file
        for (const [name, url] of Object.entries(data.download_links)) {
          if (name.includes("Enhanced") || name.includes("enhanced")) {
            primaryFile = name;
            primaryUrl = url;
            break;
          } else if (name.includes("Unified") || name.includes("unified")) {
            primaryFile = name;
            primaryUrl = url;
          } else if (
            !primaryFile &&
            (name.includes("results") || name.includes("Results"))
          ) {
            primaryFile = name;
            primaryUrl = url;
          }
        }

        // If no specific result file found, use the first Excel file
        if (!primaryFile) {
          for (const [name, url] of Object.entries(data.download_links)) {
            if (name.includes(".xlsx") || name.includes("Excel")) {
              primaryFile = name;
              primaryUrl = url;
              break;
            }
          }
        }

        // Show only the primary result file as a direct download button
        if (primaryFile && primaryUrl) {
          const fullUrl = (primaryUrl as string).startsWith("http")
            ? (primaryUrl as string)
            : `${API_BASE_URL}${primaryUrl}`;

          extractedText += `<div class="direct-download-button" data-url="${fullUrl}" data-filename="${primaryFile}">Download Results</div>\n`;
        }
      }

      // Process ID is kept for internal tracking but not displayed to user

      // Processing complete
      progressCallback?.("analyzing", 100);
      return extractedText;
    } else {
      throw new Error("No process_id received from backend");
    }
  } catch (error) {
    console.error("Error uploading PDF file:", error);
    // Ensure we call progressCallback with final values before propagating the error
    progressCallback?.("analyzing", 0);
    throw error; // Re-throw the error to be handled by the caller
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
      // Make sure to call progressCallback with final values before throwing the error
      progressCallback?.("analyzing", 0);
      throw new Error(errorText || "Failed to process HBR PDF file");
    }

    progressCallback?.("extracting", 70);
    const data = await response.json();
    console.log("Received data from backend:", data);
    progressCallback?.("analyzing", 100);

    if (!data.success) {
      throw new Error(data.error || "Unknown error processing HBR PDF file");
    }

    // Check for warnings or partial success in the response
    let extractedText = data.message;

    // If there are warnings but processing was successful, add a note
    if (data.warnings && data.success) {
      extractedText = `⚠️ **Note:** There were some issues during processing, but we were able to complete the analysis.\n\n${extractedText}`;
    }

    return extractedText;
  } catch (error) {
    console.error("Error uploading HBR PDF file:", error);
    // Ensure we call progressCallback with final values before propagating the error
    progressCallback?.("analyzing", 0);
    throw error; // Re-throw the error to be handled by the caller
  }
}

/**
 * Handle HBR Excel configuration file upload to the backend (multi-agent version)
 */
async function handleHbrExcelUploadMultiAgent(
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
    formData.append("hbr_pdf_process_id", processId);

    // Start the upload
    progressCallback?.("uploading", 20);
    console.log("Uploading HBR Excel file to multi-agent backend...");

    // Call the HBR multi-agent Excel upload endpoint first to get the actual process ID
    const response = await fetch(`${API_BASE_URL}/upload-hbr-multiagent`, {
      method: "POST",
      body: formData,
    });

    console.log("Backend response status:", response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend error response:", errorText);
      progressCallback?.("analyzing", 0);
      throw new Error(
        errorText || "Failed to process HBR Excel file with multi-agent system"
      );
    }

    const initialData = await response.json();
    console.log("Received initial data from multi-agent backend:", initialData);

    // Get the actual process ID from the response
    const actualProcessId = initialData.process_id;
    console.log(
      `HBR Excel processing with actual process ID: ${actualProcessId}`
    );

    // Set up progress monitoring using Server-Sent Events with the actual process ID
    let isCompleted = false;
    let finalData: any = null;
    let hasError = false;
    let errorMessage = "";

    const eventSource = new EventSource(
      `${API_BASE_URL}/upload-progress-stream/${actualProcessId}`
    );

    // Create promise to track SSE completion
    const ssePromise = new Promise<void>((resolve, reject) => {
      let lastUpdateTime = Date.now();
      const noUpdateTimeout = setInterval(() => {
        const timeSinceLastUpdate = Date.now() - lastUpdateTime;
        if (timeSinceLastUpdate > 1800000) {
          // 30 minutes
          console.warn(
            "No SSE updates received for 30 minutes, but backend may still be processing"
          );
          lastUpdateTime = Date.now();
        }
      }, 60000); // Check every 1 minute

      eventSource.onmessage = (event) => {
        try {
          lastUpdateTime = Date.now();
          const progressData = JSON.parse(event.data);
          console.log(
            `HBR Progress update: ${progressData.stage} ${progressData.progress}% - ${progressData.message}`
          );

          // Check if the message contains error information
          if (
            progressData.message &&
            progressData.message.toLowerCase().includes("error") &&
            !progressData.stage.toLowerCase().includes("error")
          ) {
            hasError = true;
            errorMessage = progressData.message;
          }

          // Call the progress callback
          if (progressCallback) {
            const stage =
              progressData.stage === "processing"
                ? "analyzing"
                : progressData.stage;
            progressCallback(
              stage as "uploading" | "extracting" | "analyzing",
              progressData.progress
            );
          }

          // Check for completion
          if (
            progressData.stage === "completed" ||
            progressData.progress >= 100
          ) {
            console.log("HBR processing completed");
            isCompleted = true;
            clearInterval(noUpdateTimeout);
            eventSource.close();
            resolve();
          }
        } catch (error) {
          console.error("Error parsing HBR progress data:", error);
        }
      };

      eventSource.onerror = (error) => {
        console.error("HBR EventSource error:", error);
        clearInterval(noUpdateTimeout);
        eventSource.close();
        reject(error);
      };
    });

    // Wait for processing to complete via SSE
    await ssePromise;

    // Try to get final results using the actual process ID
    if (isCompleted) {
      try {
        const resultResponse = await fetch(
          `${API_BASE_URL}/hbr-result/${actualProcessId}`
        );
        if (resultResponse.ok) {
          finalData = await resultResponse.json();
          console.log("Got HBR final results:", finalData);
        }
      } catch (error) {
        console.error("Error getting HBR final results:", error);
      }
    }

    // Use final data if available, otherwise use initial data
    const data = finalData || initialData;

    if (!data.success) {
      throw new Error(
        data.error ||
          "Unknown error processing HBR Excel file with multi-agent system"
      );
    }

    // Create a formatted text representation with multi-agent features
    let extractedText = "";

    // Check for warnings or partial success in the response
    if (data.warnings && data.success) {
      extractedText += `⚠️ **Note:** There were some issues during processing, but we were able to complete the analysis.\n\n`;
      if (typeof data.warnings === "string") {
        extractedText += `*Warning: ${data.warnings}*\n\n`;
      } else if (Array.isArray(data.warnings)) {
        extractedText += `*Warnings: ${data.warnings.join(", ")}*\n\n`;
      }
    }

    if (data.message) {
      extractedText += data.message + "\n\n";
    }

    // Add missing parameters section with feedback capability if available
    if (data.missing_parameters && data.missing_parameters.length > 0) {
      extractedText +=
        "### ❓ Missing Parameters - Interactive Help Available\n\n";
      extractedText +=
        "The following parameters could not be found automatically. Click on any parameter for AI assistance:\n\n";

      data.missing_parameters.forEach((param: any, index: number) => {
        const paramName =
          typeof param === "string"
            ? param
            : param.parameter || param.name || `Parameter ${index + 1}`;
        extractedText += `<div class="missing-parameter-button" data-session-id="${data.session_id}" data-parameter="${paramName}">🔍 Get help finding: ${paramName}</div>\n`;
      });

      extractedText += "\n💡 **Interactive Features:**\n";
      extractedText += "• Click any missing parameter for AI assistance\n";
      extractedText += "• Get page recommendations and search hints\n";
      extractedText += "• Provide hints for targeted re-extraction\n\n";
    }

    // Add download links if available
    if (data.download_links) {
      extractedText += "### Download Results\n\n";

      // Find the most important result file
      let primaryFile = null;
      let primaryUrl = null;

      // Look for results or multi-agent results file
      for (const [name, url] of Object.entries(data.download_links)) {
        if (
          name.includes("results") ||
          name.includes("Results") ||
          name.includes("Multi-Agent")
        ) {
          primaryFile = name;
          primaryUrl = url;
          break;
        }
      }

      // If no results file found, use the first Excel file
      if (!primaryFile) {
        for (const [name, url] of Object.entries(data.download_links)) {
          if (name.includes(".xlsx") || name.includes("Excel")) {
            primaryFile = name;
            primaryUrl = url;
            break;
          }
        }
      }

      // Show only the primary result file as a direct download button
      if (primaryFile && primaryUrl) {
        const fullUrl = (primaryUrl as string).startsWith("http")
          ? (primaryUrl as string)
          : `${API_BASE_URL}${primaryUrl}`;

        extractedText += `<div class="direct-download-button" data-url="${fullUrl}" data-filename="${primaryFile}">Download Results</div>\n`;
      }
    }

    // Store session ID for chat context (hidden)
    if (data.session_id) {
      extractedText += `<div class="hbr-session-context" data-session-id="${data.session_id}" style="display:none;"></div>`;
    }

    // Processing complete
    progressCallback?.("analyzing", 100);
    return extractedText;
  } catch (error) {
    console.error(
      "Error uploading HBR Excel file to multi-agent system:",
      error
    );
    // Ensure we call progressCallback with final values before propagating the error
    progressCallback?.("analyzing", 0);
    throw error; // Re-throw the error to be handled by the caller
  }
}

/**
 * Handle HBR Excel configuration file upload to the backend (original version)
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
      // Make sure to call progressCallback with final values before throwing the error
      progressCallback?.("analyzing", 0);
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
      extractedText += "### Download Results\n\n";

      // Find the most important result file
      let primaryFile = null;
      let primaryUrl = null;

      // Look for results file
      for (const [name, url] of Object.entries(data.download_links)) {
        if (name.includes("results") || name.includes("Results")) {
          primaryFile = name;
          primaryUrl = url;
          break;
        }
      }

      // If no results file found, use the first Excel file
      if (!primaryFile) {
        for (const [name, url] of Object.entries(data.download_links)) {
          if (name.includes(".xlsx") || name.includes("Excel")) {
            primaryFile = name;
            primaryUrl = url;
            break;
          }
        }
      }

      // Show only the primary result file as a direct download button
      if (primaryFile && primaryUrl) {
        const fullUrl = (primaryUrl as string).startsWith("http")
          ? (primaryUrl as string)
          : `${API_BASE_URL}${primaryUrl}`;

        extractedText += `<div class="direct-download-button" data-url="${fullUrl}" data-filename="${primaryFile}">Download Results</div>\n`;
      }
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
    // Ensure we call progressCallback with final values before propagating the error
    progressCallback?.("analyzing", 0);
    throw error; // Re-throw the error to be handled by the caller
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

/**
 * Cancel a running process
 */
export async function cancelProcess(processId: string): Promise<boolean> {
  try {
    console.log("🛑 Cancelling process:", processId);
    const response = await fetch(
      `${API_BASE_URL}/cancel-process/${processId}`,
      {
        method: "POST",
      }
    );

    if (response.ok) {
      const result = await response.json();
      console.log("✅ Process cancelled successfully:", result);
      return true;
    } else {
      console.error("❌ Failed to cancel process:", response.status);
      return false;
    }
  } catch (error) {
    console.error("❌ Error cancelling process:", error);
    return false;
  }
}
