/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  env: {
    BACKEND_URL: process.env.BACKEND_URL || "http://localhost:5000",
  },
  // Configure API routes
  api: {
    bodyParser: {
      sizeLimit: "10mb",
    },
    responseLimit: "10mb",
    // Increase the timeout for long-running processes
    externalResolver: true,
  },
  experimental: {
    // Increase serverless function timeout for OCR processing
    serverComponentsExternalPackages: ["pdf-parse"],
    // Increase response timeout for API routes
    serverActions: {
      bodySizeLimit: "10mb",
      timeout: 300, // 5 minutes in seconds
    },
  },
  // Enable CORS for API routes
  async headers() {
    return [
      {
        source: "/api/:path*",
        headers: [
          { key: "Access-Control-Allow-Credentials", value: "true" },
          { key: "Access-Control-Allow-Origin", value: "*" },
          {
            key: "Access-Control-Allow-Methods",
            value: "GET,OPTIONS,PATCH,DELETE,POST,PUT",
          },
          {
            key: "Access-Control-Allow-Headers",
            value:
              "X-CSRF-Token, X-Requested-With, Accept, Accept-Version, Content-Length, Content-MD5, Content-Type, Date, X-Api-Version",
          },
        ],
      },
    ];
  },
  // Add rewrites for proxying download requests to the backend
  async rewrites() {
    return [
      {
        source: "/download/:path*",
        destination: "http://localhost:5000/download/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
