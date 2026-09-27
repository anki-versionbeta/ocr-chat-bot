import { NextRequest, NextResponse } from "next/server";
import path from "path";

/**
 * API route for downloading files
 * This forwards directly to the backend's /download endpoint
 */
export async function GET(request: NextRequest) {
  try {
    // Get the file path from the URL
    const url = new URL(request.url);
    const filePath = url.pathname.replace("/api/download", "");

    // Prevent path traversal attacks
    const normalized = path.posix.normalize(filePath);
    if (normalized.includes("..") || normalized.startsWith("/..")) {
      return NextResponse.json(
        { error: "Invalid file path" },
        { status: 400 }
      );
    }

    // Backend service URL - adjust as needed
    const backendUrl = process.env.BACKEND_URL || "http://localhost:5000";
    const downloadUrl = `${backendUrl}/download${normalized}`;

    console.log(`Forwarding download request to backend at: ${downloadUrl}`);

    // Forward the request to the backend
    const response = await fetch(downloadUrl);

    if (!response.ok) {
      console.error(
        `Backend error (${response.status}): ${await response.text()}`
      );
      return NextResponse.json(
        { error: `File download failed: ${response.statusText}` },
        { status: response.status }
      );
    }

    // Get the content type and file name from the response
    const contentType =
      response.headers.get("content-type") || "application/octet-stream";
    const contentDisposition = response.headers.get("content-disposition");
    const rawFileName =
      contentDisposition?.split("filename=")[1]?.replace(/"/g, "") ||
      "download";
    // Sanitize filename to prevent header injection
    const fileName = path.basename(rawFileName);

    // Get the file data
    const fileData = await response.arrayBuffer();

    // Return the file data with appropriate headers
    return new NextResponse(fileData, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${fileName}"`,
      },
    });
  } catch (error) {
    console.error("Error in download API route:", error);
    return NextResponse.json(
      { error: `File download failed: ${(error as Error).message}` },
      { status: 500 }
    );
  }
}
