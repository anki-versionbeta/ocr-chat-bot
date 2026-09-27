import { NextRequest, NextResponse } from "next/server";

// Define maximum request size
export const config = {
  api: {
    // Disable default body parsing to handle file uploads
    bodyParser: false,
    // Set response limit
    responseLimit: "10mb",
    // Set longer timeout for long-running OCR processes
    externalResolver: true,
  },
};

/**
 * API route for uploading Certificate of Analysis (CoA) files
 * This proxies the request to the backend service
 */
export async function POST(request: NextRequest) {
  try {
    // Forward the request to our backend service
    const formData = await request.formData();

    // Log the file being processed
    const file = formData.get("file") as File;

    if (!file) {
      console.error("No file found in the request");
      return NextResponse.json(
        { error: "No file found in the request" },
        { status: 400 }
      );
    }

    console.log(
      `Processing file upload: ${file.name}, size: ${file.size} bytes, type: ${file.type}`
    );

    // Backend service URL - adjust as needed
    const backendUrl = process.env.BACKEND_URL || "http://localhost:5000";
    const uploadUrl = `${backendUrl}/upload-coa`;

    console.log(`Forwarding to backend at: ${uploadUrl}`);

    // Check if backend is available first
    try {
      const pingResponse = await fetch(`${backendUrl}/ping`, {
        method: "GET",
        signal: AbortSignal.timeout(3000), // 3 second timeout
      });

      if (!pingResponse.ok) {
        console.error(
          `Backend ping failed with status: ${pingResponse.status}`
        );
        return NextResponse.json(
          {
            error:
              "Backend server is not responding properly. Please ensure the backend server is running.",
          },
          { status: 503 }
        );
      }

      console.log("Backend server is available, proceeding with upload");
    } catch (pingError) {
      console.error("Backend ping failed:", pingError);
      return NextResponse.json(
        {
          error:
            "Could not connect to backend server. Please ensure the backend server is running.",
        },
        { status: 503 }
      );
    }

    // Try to connect to backend
    try {
      // Forward the request to the backend with timeout
      const controller = new AbortController();
      // Increase timeout to 5 minutes (300000 ms) for Textract + GPT processing
      const timeoutId = setTimeout(() => controller.abort(), 300000);

      const response = await fetch(uploadUrl, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // Check if the request was successful
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`Backend error (${response.status}): ${errorText}`);

        return NextResponse.json(
          { error: `Backend processing failed: ${errorText}` },
          { status: response.status }
        );
      }

      // Return the response from the backend
      const data = await response.json();
      console.log("Successfully processed file, returning data to client");

      return NextResponse.json(data);
    } catch (fetchErrorUnknown) {
      const fetchError = fetchErrorUnknown as {
        name?: string;
        message?: string;
      };
      console.error(`Error connecting to backend at ${uploadUrl}:`, fetchError);

      // Check if it's a timeout error
      if (fetchError.name === "AbortError") {
        return NextResponse.json(
          {
            error:
              "Connection to backend timed out. Please check that the backend server is running.",
          },
          { status: 504 }
        );
      }

      return NextResponse.json(
        {
          error: `Could not connect to backend server at ${backendUrl}. Please check that the server is running.`,
          details: fetchError.message || "Unknown error",
        },
        { status: 502 }
      );
    }
  } catch (error) {
    console.error("Error in upload-coa API route:", error);

    return NextResponse.json(
      { error: `File upload failed: ${(error as Error).message}` },
      { status: 500 }
    );
  }
}
