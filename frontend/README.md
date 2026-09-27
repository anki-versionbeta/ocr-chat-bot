# OCR Chatbot Frontend

This is the frontend for the OCR Chatbot application, which analyzes Paperbatch Records and Certificates of Analysis documents.

## Claude Integration

The application integrates with Claude 3.7 Sonnet via a custom API endpoint. The agent is specifically designed to only answer questions related to Paperbatch Records and Certificates of Analysis.

### How It Works

1. **Agent Service**: The Claude agent is implemented in `src/services/agent.ts`. It:

   - Maintains conversation history
   - Enforces domain constraints through system prompts
   - Handles document analysis
   - Communicates with the Claude API

2. **File Handling**: Document processing utilities are in `src/services/fileUtils.ts`. In production, this would:

   - Extract text from various document types
   - Send files to backend OCR services
   - Support various document formats

3. **Dashboard Integration**: The chat interface in `src/app/dashboard/page.tsx` integrates the agent by:
   - Sending user messages to the Claude agent
   - Processing file uploads
   - Displaying responses and loading states

### Configuration

The Claude API is configured through environment variables:

- `NEXT_PUBLIC_CLAUDE_API_KEY`: API key for Claude
- `NEXT_PUBLIC_CLAUDE_API_URL`: Claude API endpoint

### System Prompt

The agent uses a carefully crafted system prompt that:

- Restricts the agent to only discuss Paperbatch Records and COA documents
- Provides domain-specific knowledge about these document types
- Guides the agent to provide appropriate responses
- Prevents the agent from answering questions outside its domain

## Getting Started

1. Install dependencies:

   ```bash
   npm install
   ```

2. Create a `.env.local` file with your Claude API credentials:

   ```
   NEXT_PUBLIC_CLAUDE_API_KEY=REDACTED
   NEXT_PUBLIC_CLAUDE_API_URL=your_api_url
   ```

3. Run the development server:
   ```bash
   npm run dev
   ```

## Production Deployment

For production, ensure that:

1. Environment variables are properly set in your hosting environment
2. Backend OCR services are properly configured and accessible
3. API endpoints are secured with appropriate authentication
