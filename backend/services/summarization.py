"""
Chat Summarization Service

Strategy: Threshold-based summarization
- Trigger when message_count > 30
- Keep last 20 messages fresh
- Summarize older messages into chats.summary
- Use Claude for intelligent summarization
"""

import logging
import threading
import requests
from typing import Dict, Any, List, Optional

from .database import (
    get_chat,
    get_unsummarized_messages_up_to,
    mark_messages_summarized,
    save_chat_summary
)

logger = logging.getLogger("ocr-chatbot.summarization")

# Configuration
SUMMARIZE_INTERVAL = 30   # Summarize every 30 messages (at 31, 61, 91...)
MAX_SUMMARY_TOKENS = REDACTED

# Simple lock to prevent concurrent summarizations of same chat
_summarization_locks: Dict[str, threading.Lock] = {}


def get_summarization_lock(chat_id: str) -> threading.Lock:
    """Get or create a lock for a specific chat."""
    if chat_id not in _summarization_locks:
        _summarization_locks[chat_id] = threading.Lock()
    return _summarization_locks[chat_id]


def maybe_summarize(chat_id: str, iliad_url: str, iliad_api_key: str) -> Optional[str]:
    """
    Summarize messages in batches of 30.

    Logic:
    - At message 31: summarize messages 1-30
    - At message 61: summarize messages 31-60 (combined with existing summary)
    - At message 91: summarize messages 61-90 (combined with existing summary)

    Returns the new summary if created, None otherwise.
    Thread-safe: Uses lock to prevent concurrent summarizations.
    """
    logger.info(f"Starting summarization for chat {chat_id}")

    chat = get_chat(chat_id)
    if not chat:
        logger.warning(f"Chat {chat_id} not found for summarization")
        return None

    message_count = chat.get('message_count', 0)
    logger.info(f"Chat {chat_id} has {message_count} messages")

    # Calculate which batch to summarize
    # At 31: summarize 1-30 (batch 1)
    # At 61: summarize 31-60 (batch 2)
    # At 91: summarize 61-90 (batch 3)
    batch_number = (message_count - 1) // SUMMARIZE_INTERVAL  # 31->1, 61->2, 91->3
    start_seq = (batch_number - 1) * SUMMARIZE_INTERVAL + 1   # 1, 31, 61
    end_seq = batch_number * SUMMARIZE_INTERVAL               # 30, 60, 90

    logger.info(f"Summarizing batch {batch_number}: messages {start_seq}-{end_seq}")

    # Get unsummarized messages in this range
    messages_to_summarize = get_unsummarized_messages_up_to(chat_id, end_seq)
    # Filter to only messages >= start_seq
    messages_to_summarize = [m for m in messages_to_summarize if m.get('sequence_num', 0) >= start_seq]

    logger.info(f"Found {len(messages_to_summarize) if messages_to_summarize else 0} messages to summarize")

    if not messages_to_summarize:
        logger.info("No messages to summarize in this batch")
        return None

    # Try to acquire lock (non-blocking)
    lock = get_summarization_lock(chat_id)
    if not lock.acquire(blocking=False):
        logger.info(f"Summarization already in progress for chat {chat_id}")
        return None

    try:
        logger.info(f"Processing {len(messages_to_summarize)} messages for summarization")

        # Get existing summary for context (to combine with new batch)
        existing_summary = chat.get('summary', '')

        # Generate new summary (combines existing + new batch)
        new_summary = generate_summary(
            messages_to_summarize,
            existing_summary,
            iliad_url,
            iliad_api_key
        )

        if new_summary:
            # Save summary to chat
            save_chat_summary(chat_id, new_summary)

            # Mark messages as summarized
            count = mark_messages_summarized(chat_id, end_seq)
            logger.info(f"Marked messages up to {end_seq} as summarized in chat {chat_id}")

            return new_summary
        else:
            logger.warning(f"Summary generation failed for chat {chat_id}")
            return None

    except Exception as e:
        logger.error(f"Summarization error for chat {chat_id}: {e}")
        return None

    finally:
        lock.release()


def generate_summary(
    messages: List[Dict[str, Any]],
    existing_summary: str,
    iliad_url: str,
    iliad_api_key: str
) -> Optional[str]:
    """
    Generate a summary of messages using Claude.
    Incorporates existing summary for continuity.
    """
    # Format messages for prompt
    message_text = ""
    for msg in messages:
        role = msg.get('role', 'user').capitalize()
        content = msg.get('content', '')
        # Truncate very long messages
        if len(content) > 500:
            content = content[:500] + "..."
        message_text += f"[{role}]: {content}\n\n"

    logger.info(f"Message text for summarization (first 500 chars): {message_text[:500]}")

    # Build prompt - keep it simple and direct
    prompt = f"""You are summarizing a chat conversation for context preservation.

{f"EXISTING SUMMARY (incorporate this):{chr(10)}{existing_summary}{chr(10)}{chr(10)}" if existing_summary else ""}CONVERSATION TO SUMMARIZE:
{message_text}

INSTRUCTIONS:
- Create a brief summary (2-4 sentences) of what was discussed
- If documents were mentioned (COA, HBR, PDF), note the document types
- If specific data was mentioned (batch numbers, dates, values), include them
- If it's just casual conversation (greetings, etc.), say "General conversation with greetings"

SUMMARY:"""

    try:
        api_url = f"{iliad_url}/api/v1/chat/claude-4.5-haiku"
        logger.info(f"Calling summarization API: {api_url}")
        logger.info(f"Summarizing {len(messages)} messages, prompt length: {len(prompt)} chars")

        response = requests.post(
            api_url,
            json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,  # Lower temperature for consistent summaries
                "max_tokens": MAX_SUMMARY_TOKENS
            },
            headers={"x-api-key": iliad_api_key},
            timeout=30
        )

        logger.info(f"Summarization API response status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Summary API full response: {result}")

            # Try different response formats
            summary = None
            if 'completion' in result:
                completion = result['completion']
                logger.info(f"Completion object: {completion}")
                if isinstance(completion, dict):
                    summary = completion.get('content', '')
                    # Also try 'text' key
                    if not summary:
                        summary = completion.get('text', '')
                elif isinstance(completion, str):
                    summary = completion
            elif 'choices' in result:
                # OpenAI format
                choices = result.get('choices', [])
                if choices:
                    summary = choices[0].get('message', {}).get('content', '')
            elif 'content' in result:
                summary = result.get('content', '')
            elif 'text' in result:
                summary = result.get('text', '')

            # If summary is empty string, it's still a failure
            if not summary or summary.strip() == '':
                logger.error(f"Empty summary returned from API. Full response: {result}")
                # For conversations with minimal content, create a basic summary
                if message_text.strip():
                    # Include existing summary if available
                    if existing_summary:
                        summary = f"{existing_summary} Additional {len(messages)} messages continued the conversation."
                    else:
                        summary = f"Conversation with {len(messages)} messages. Topics discussed: general chat."
                    logger.info(f"Created fallback summary: {summary}")
                else:
                    # If no new content but we have existing summary, keep it
                    if existing_summary:
                        return existing_summary
                    return None

            logger.info(f"Generated summary length: {len(summary)} chars")

            # Safety check: if summary too long, condense it
            if len(summary) > 2000:  # Rough character limit
                summary = condense_summary(summary, iliad_url, iliad_api_key)

            return summary
        else:
            logger.error(f"Summary generation failed: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Summary generation error: {e}")
        return None


def condense_summary(long_summary: str, iliad_url: str, iliad_api_key: str) -> str:
    """Condense a summary that's too long."""
    prompt = f"""This summary is too long. Condense it to under 300 words while keeping the most important information:

{long_summary}

Condensed summary:"""

    try:
        response = requests.post(
            f"{iliad_url}/api/v1/chat/claude-4.5-haiku",
            json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500
            },
            headers={"x-api-key": iliad_api_key},
            timeout=20
        )

        if response.status_code == 200:
            result = response.json()
            return result.get('completion', {}).get('content', long_summary[:1500])
        else:
            # Fallback: just truncate
            return long_summary[:1500] + "..."

    except Exception as e:
        logger.error(f"Summary condensation error: {e}")
        return long_summary[:1500] + "..."


def is_meaningful_message(message: str) -> bool:
    """
    Check if a message is meaningful enough to generate a title from.
    Filters out greetings, filler messages, and very short inputs.
    """
    # Normalize: lowercase, strip whitespace
    msg = message.lower().strip()

    # Too short to be meaningful
    if len(msg) < 10:
        return False

    # Common greetings and filler phrases to skip
    skip_patterns = [
        "hi", "hello", "hey", "hii", "hiii",
        "hi there", "hello there", "hey there",
        "good morning", "good afternoon", "good evening",
        "help", "help me", "can you help",
        "please help", "i need help",
        "test", "testing", "just testing",
        "ok", "okay", "k",
        "thanks", "thank you", "thx",
        "yes", "no", "yeah", "nope",
        "hmm", "hmmm", "um", "umm",
        "what", "why", "how", "when", "where",  # Single word questions
        "explain", "tell me", "show me",  # Too vague
        "?", "...", "."
    ]

    # Check exact matches
    if msg in skip_patterns:
        return False

    # Check if starts with greeting followed by short content
    greeting_prefixes = ["hi ", "hello ", "hey ", "hi, ", "hello, ", "hey, "]
    for prefix in greeting_prefixes:
        if msg.startswith(prefix):
            remaining = msg[len(prefix):].strip()
            if len(remaining) < 15:  # Greeting + very short follow-up
                return False

    return True


def generate_chat_title(first_message: str, iliad_url: str, iliad_api_key: str) -> str:
    """
    Generate a short, meaningful title from the first user message.

    Strategy (Option-1 - Industry Standard):
    - Generate title ONCE from first meaningful message
    - Never regenerate automatically
    - User can manually rename anytime

    Returns "New Chat" if message is not meaningful enough.
    """
    # Check if message is meaningful enough to generate title
    if not is_meaningful_message(first_message):
        logger.info(f"Message not meaningful enough for title: '{first_message[:50]}...'")
        return "New Chat"  # Will try again on next message

    # Optimized prompt for consistent, high-quality titles
    prompt = f"""You generate chat titles for a conversation sidebar.

Create a single, stable title based on this user message:
"{first_message[:300]}"

Rules:
- Compress the main topic into 3-6 words
- Use Title Case (e.g., "RAG With Neo4j")
- Focus on the KEY TOPIC or ACTION requested
- Do NOT use punctuation, emojis, or filler words (how, please, can you, I want)
- Prefer concrete nouns over verbs
- If about a specific technology/product, include its name
- If about code/programming, mention the language or framework

Examples:
- "How to design RAG using Neo4j?" → "RAG Design With Neo4j"
- "Can you help me fix this Python error?" → "Python Error Debugging"
- "I want to analyze COA documents" → "COA Document Analysis"
- "explain batch number extraction from PDF" → "PDF Batch Number Extraction"

Return ONLY the title text, nothing else."""

    try:
        response = requests.post(
            f"{iliad_url}/api/v1/chat/claude-4.5-haiku",
            json={
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,  # Lower temperature for consistency
                "max_tokens": 25
            },
            headers={"x-api-key": iliad_api_key},
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            title = result.get('completion', {}).get('content', 'New Chat')

            # Clean up the title
            title = title.strip().strip('"').strip("'").strip()

            # Remove common prefixes LLM might add
            for prefix in ["Title:", "Chat Title:", "title:"]:
                if title.lower().startswith(prefix.lower()):
                    title = title[len(prefix):].strip()

            # Limit length
            if len(title) > 50:
                title = title[:47] + "..."

            # If title is empty or just whitespace, return default
            if not title or title.lower() == "new chat":
                return "New Chat"

            logger.info(f"Generated title: '{title}' from message: '{first_message[:50]}...'")
            return title
        else:
            logger.warning(f"Title generation API failed: {response.status_code}")
            return "New Chat"

    except Exception as e:
        logger.error(f"Title generation error: {e}")
        return "New Chat"
