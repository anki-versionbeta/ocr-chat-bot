# OCR Chatbot

A powerful application for extracting and analyzing data from Certificate of Analysis (CoA) documents using OCR and AI.

## Features

- Upload PDF files directly through the chat interface
- Extract structured data using AWS Textract OCR
- Analyze content using Claude 3.7 Sonnet
- View extracted information in a clear, formatted display

## Prerequisites

- **Python 3.7+** for the backend
- **Node.js 14+** for the frontend
- AWS credentials (for Textract API)
- Claude API key (for LLM analysis)

## Quick Start

### Windows

1. Clone this repository to your local machine
2. Run the automatic starter script:

   ```
   start_all.bat
   ```

   This will start both the backend and frontend servers in separate windows.

3. Open your browser and navigate to:
   ```
   http://localhost:3000
   ```

### Manual Setup

#### Backend Setup

1. Navigate to the backend directory:

   ```
   cd backend
   ```

2. Install dependencies:

   ```
   python install_dependencies.py
   ```

3. Start the backend server:
   ```
   python app.py
   ```
   The backend will run on http://localhost:5000

#### Frontend Setup

1. Navigate to the frontend directory:

   ```
   cd frontend
   ```

2. Install dependencies:

   ```
   npm install
   ```

3. Start the frontend development server:
   ```
   npm run dev
   ```
   The frontend will run on http://localhost:3000

## Usage

1. Open the application in your browser
2. Click the upload button in the chat interface
3. Select a Certificate of Analysis PDF file
4. Wait for the processing to complete
5. View the extracted data in the chat

## Troubleshooting

If you encounter any issues with the application:

1. Check that both backend and frontend servers are running
2. Ensure all dependencies are installed correctly
3. Verify your AWS credentials for Textract
4. Check the console logs for any error messages

## License

This project is proprietary and confidential.

## Contact

For support or questions, please contact the development team.
