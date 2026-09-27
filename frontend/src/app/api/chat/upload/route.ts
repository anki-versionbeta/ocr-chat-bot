import { NextRequest, NextResponse } from "next/server";

// Route segment config for Next.js 13
export const runtime = "nodejs";
export const maxDuration = 300; // 5 minutes

/**
 * API route for uploading files
 * This forwards directly to the backend's /upload-coa endpoint
 */
export async function POST(request: NextRequest) {
  try {
    // Get the form data
    const formData = await request.formData();

    // Log the request
    console.log("Processing upload request at /api/chat/upload");

    // Backend service URL - adjust as needed
    const backendUrl = process.env.BACKEND_URL || "http://localhost:5000";
    const uploadUrl = `${backendUrl}/upload-coa`;

    console.log(`Forwarding to backend at: ${uploadUrl}`);

    // Forward the request to the backend
    const response = await fetch(uploadUrl, {
      method: "POST",
      body: formData,
    });

    console.log("Backend response status:", response.status);

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
  } catch (error) {
    console.error("Error in upload API route:", error);

    return NextResponse.json(
      { error: `File upload failed: ${(error as Error).message}` },
      { status: 500 }
    );
  }
}
