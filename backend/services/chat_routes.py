"""
Chat API Routes for FastAPI

Endpoints:
- POST   /api/chats              - Create new chat
- GET    /api/chats              - List user's chats
- GET    /api/chats/{chat_id}    - Get chat with messages
- DELETE /api/chats/{chat_id}    - Delete chat
- PATCH  /api/chats/{chat_id}    - Update chat (rename, archive)
- POST   /api/chats/{chat_id}/messages - Send message and get response
- GET    /api/chats/{chat_id}/messages - Get chat messages
- POST   /api/chats/{chat_id}/documents - Add document to chat
"""

import logging
import threading
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .database import (
    get_or_create_user,
    create_chat,
    get_chat,
    get_user_chats,
    update_chat,
    delete_chat,
    save_message,
    get_messages,
    get_recent_messages,
    get_chat_context,
    add_document_to_chat,
    get_chat_documents,
    update_document_extraction
)
from .summarization import maybe_summarize, generate_chat_title

logger = logging.getLogger("ocr-chatbot.chat_routes")

# Create router
router = APIRouter(prefix="/api", tags=["chats"])

# Iliad API configuration for summarization
ILIAD_URL = "https://api-epic.ir-gateway.abbvienet.com/iliad"
ILIAD_API_KEY = REDACTED


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class CreateChatRequest(BaseModel):
    title: Optional[str] = "New Chat"


class UpdateChatRequest(BaseModel):
    title: Optional[str] = None
    is_archived: Optional[bool] = None


class SendMessageRequest(BaseModel):
    content: str
    document_id: Optional[str] = None  # Override active document


class AddDocumentRequest(BaseModel):
    document_id: str
    document_name: str
    page_count: Optional[int] = None
    file_size: Optional[int] = None
    file_path: Optional[str] = None
    weaviate_source: Optional[str] = None
    process_id: Optional[str] = None  # Phase 4: Weaviate filter key for RAG search
    document_type: Optional[str] = None  # e.g., 'coa', 'hbr'
    processing_status: Optional[str] = 'completed'  # Default to completed since we save after extraction
    extraction_done: Optional[bool] = True  # Default to True since we save after extraction completes


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_current_user_info(request: Request) -> dict:
    """Extract user info from session. Returns dict with user_id, email."""
    if hasattr(request, 'session') and request.session.get('authenticated'):
        return {
            'user_id': request.session.get('username', 'anonymous'),
            'email': request.session.get('email'),
            'authenticated': True
        }
    return {
        'user_id': 'anonymous',
        'email': None,
        'authenticated': False
    }


# ============================================================================
# CHAT ENDPOINTS
# ============================================================================

@router.post("/chats")
async def create_new_chat(request: Request, body: CreateChatRequest):
    """Create a new chat for the current user."""
    try:
        user_info = get_current_user_info(request)
        user_id = user_info['user_id']
        email = user_info['email']

        # Ensure user exists in database (pass email from LDAP session)
        get_or_create_user(user_id, email=email, full_name=user_id)

        # Create chat
        chat = create_chat(user_id, body.title)

        logger.info(f"Created chat {chat['chat_id']} for user {user_id}")

        return {
            "success": True,
            "chat": {
                "chat_id": chat['chat_id'],
                "title": chat['title'],
                "message_count": chat['message_count'],
                "created_at": chat['created_at'].isoformat() if chat['created_at'] else None
            }
        }

    except Exception as e:
        logger.error(f"Error creating chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chats")
async def list_user_chats(request: Request, include_archived: bool = False):
    """List all chats for the current user."""
    try:
        user_id = get_current_user_info(request)['user_id']

        chats = get_user_chats(user_id, include_archived)

        return {
            "success": True,
            "chats": [
                {
                    "chat_id": c['chat_id'],
                    "title": c['title'],
                    "message_count": c['message_count'],
                    "latest_document": c.get('latest_document'),
                    "is_archived": c.get('is_archived', False),
                    "updated_at": c['updated_at'].isoformat() if c['updated_at'] else None,
                    "created_at": c['created_at'].isoformat() if c['created_at'] else None
                }
                for c in chats
            ]
        }

    except Exception as e:
        logger.error(f"Error listing chats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chats/{chat_id}")
async def get_chat_details(chat_id: str, request: Request):
    """Get chat details including messages and documents."""
    try:
        user_id = get_current_user_info(request)['user_id']

        # Get full chat context
        context = get_chat_context(chat_id)

        if not context:
            raise HTTPException(status_code=404, detail="Chat not found")

        chat = context['chat']

        # Verify ownership
        if chat['user_id'] != user_id and user_id != 'anonymous':
            raise HTTPException(status_code=403, detail="Access denied")

        # Get all messages for display
        messages = get_messages(chat_id)

        return {
            "success": True,
            "chat": {
                "chat_id": chat['chat_id'],
                "title": chat['title'],
                "message_count": chat['message_count'],
                "active_document_id": chat.get('active_document_id'),
                "summary": chat.get('summary'),
                "is_archived": chat.get('is_archived', False),
                "created_at": chat['created_at'].isoformat() if chat['created_at'] else None,
                "updated_at": chat['updated_at'].isoformat() if chat['updated_at'] else None
            },
            "documents": [
                {
                    "document_id": d['document_id'],
                    "document_name": d['document_name'],
                    "upload_order": d['upload_order'],
                    "extraction_done": d.get('extraction_done', False),
                    "is_active": d['document_id'] == chat.get('active_document_id'),
                    "process_id": d.get('process_id'),  # Phase 4: For RAG search filtering
                    "document_type": d.get('document_type')
                }
                for d in context['documents']
            ],
            "messages": [
                {
                    "message_id": m['message_id'],
                    "role": m['role'],
                    "content": m['content'],
                    "message_type": m.get('message_type', 'text'),
                    "document_id": m.get('document_id'),
                    "references": m.get('references'),
                    "is_summarized": m.get('is_summarized', False),
                    "created_at": m['created_at'].isoformat() if m['created_at'] else None
                }
                for m in messages
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/chats/{chat_id}")
async def update_chat_details(chat_id: str, request: Request, body: UpdateChatRequest):
    """Update chat title or archive status."""
    try:
        user_id = get_current_user_info(request)['user_id']

        # Get chat to verify ownership
        chat = get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        if chat['user_id'] != user_id and user_id != 'anonymous':
            raise HTTPException(status_code=403, detail="Access denied")

        # Build update dict
        updates = {}
        if body.title is not None:
            updates['title'] = body.title
        if body.is_archived is not None:
            updates['is_archived'] = body.is_archived

        if updates:
            updated_chat = update_chat(chat_id, **updates)
        else:
            updated_chat = chat

        return {
            "success": True,
            "chat": {
                "chat_id": updated_chat['chat_id'],
                "title": updated_chat['title'],
                "is_archived": updated_chat.get('is_archived', False),
                "updated_at": updated_chat['updated_at'].isoformat() if updated_chat['updated_at'] else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chats/{chat_id}")
async def delete_user_chat(chat_id: str, request: Request):
    """Delete a chat and all its messages."""
    try:
        user_id = get_current_user_info(request)['user_id']

        success = delete_chat(chat_id, user_id)

        if not success:
            raise HTTPException(status_code=404, detail="Chat not found or access denied")

        return {"success": True, "message": "Chat deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MESSAGE ENDPOINTS
# ============================================================================

@router.get("/chats/{chat_id}/messages")
async def get_chat_messages(chat_id: str, request: Request, include_summarized: bool = True):
    """Get all messages for a chat."""
    try:
        user_id = get_current_user_info(request)['user_id']

        # Verify chat exists and user has access
        chat = get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        if chat['user_id'] != user_id and user_id != 'anonymous':
            raise HTTPException(status_code=403, detail="Access denied")

        messages = get_messages(chat_id, include_summarized)

        return {
            "success": True,
            "chat_id": chat_id,
            "message_count": len(messages),
            "messages": [
                {
                    "message_id": m['message_id'],
                    "role": m['role'],
                    "content": m['content'],
                    "message_type": m.get('message_type', 'text'),
                    "document_id": m.get('document_id'),
                    "references": m.get('references'),
                    "sequence_num": m.get('sequence_num'),
                    "is_summarized": m.get('is_summarized', False),
                    "created_at": m['created_at'].isoformat() if m['created_at'] else None
                }
                for m in messages
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages for chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chats/{chat_id}/messages")
async def send_chat_message(
    chat_id: str,
    request: Request,
    body: SendMessageRequest
):
    """
    Send a message to a chat and get AI response.

    This endpoint:
    1. Saves the user message
    2. Auto-generates title if first meaningful message
    3. Returns the saved message

    Note: Claude response is handled separately by the frontend/agent
    """
    try:
        user_id = get_current_user_info(request)['user_id']

        # Verify chat exists
        chat = get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        if chat['user_id'] != user_id and user_id != 'anonymous':
            raise HTTPException(status_code=403, detail="Access denied")

        # Use provided document_id or fall back to active document
        document_id = body.document_id or chat.get('active_document_id')

        # 1. Save user message
        user_message = save_message(
            chat_id=chat_id,
            role="user",
            content=body.content,
            document_id=document_id,
            message_type="text"
        )

        logger.info(f"Saved user message {user_message['message_id']} to chat {chat_id}")

        # 2. Auto-generate title if chat still has default title
        # Strategy: Generate title from FIRST MEANINGFUL message (Option-1 - Industry Standard)
        # - Only generates once (when title is "New Chat" or empty)
        # - Skips greetings/filler messages (will retry on next message)
        # - User can manually rename anytime
        current_title = chat.get('title', 'New Chat')
        should_generate_title = current_title in ['New Chat', '', None]

        if should_generate_title:
            try:
                def generate_title_async():
                    try:
                        title = generate_chat_title(body.content, ILIAD_URL, ILIAD_API_KEY)
                        if title and title != "New Chat":
                            update_chat(chat_id, title=title)
                            logger.info(f"Auto-generated title for chat {chat_id}: '{title}'")
                        else:
                            logger.info(f"Skipped title generation for chat {chat_id} - message not meaningful")
                    except Exception as e:
                        logger.warning(f"Failed to auto-generate title: {e}")

                # Run title generation in background thread (non-blocking)
                title_thread = threading.Thread(target=generate_title_async, daemon=True)
                title_thread.start()
            except Exception as e:
                logger.warning(f"Failed to start title generation: {e}")

        # 3. Check if summarization needed (will be done in background later)
        # For now, we return and let the main chat endpoint handle Claude call

        return {
            "success": True,
            "user_message": {
                "message_id": user_message['message_id'],
                "role": "user",
                "content": user_message['content'],
                "sequence_num": user_message.get('sequence_num'),
                "created_at": user_message['created_at'].isoformat() if user_message['created_at'] else None
            },
            "chat": {
                "chat_id": chat_id,
                "message_count": user_message.get('sequence_num', chat['message_count'] + 1)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message to chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SaveAssistantMessageRequest(BaseModel):
    content: str
    document_id: Optional[str] = None
    references: Optional[List[dict]] = None  # Phase 5: bbox references for PDF highlighting


@router.post("/chats/{chat_id}/messages/assistant")
async def save_assistant_message(chat_id: str, request: Request, body: SaveAssistantMessageRequest):
    """
    Save an assistant message to a chat.
    Used by frontend to persist AI responses.
    """
    try:
        user_id = get_current_user_info(request)['user_id']

        # Verify chat exists
        chat = get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        if chat['user_id'] != user_id and user_id != 'anonymous':
            raise HTTPException(status_code=403, detail="Access denied")

        # Use provided document_id or fall back to active document
        document_id = body.document_id or chat.get('active_document_id')

        # Save assistant message with references (Phase 5: for PDF highlighting)
        assistant_message = save_message(
            chat_id=chat_id,
            role="assistant",
            content=body.content,
            document_id=document_id,
            message_type="text",
            references=body.references  # Phase 5: bbox data for highlighting
        )

        logger.info(f"Saved assistant message {assistant_message['message_id']} to chat {chat_id}")

        # Get current chat state including any existing summary
        current_chat = get_chat(chat_id)
        current_summary = current_chat.get('summary') if current_chat else None
        current_message_count = current_chat.get('message_count', 0) if current_chat else 0

        # Summarization trigger logic:
        # - Messages 1-30: No summary, send all 30 messages
        # - After 30: TRIGGER - summarize 1-30, then send summary + last 30 messages
        # - After 60: TRIGGER - summarize 31-60, combine with old summary
        # - After 90: TRIGGER - summarize 61-90, combine with old summary
        #
        # Trigger when: message_count > 30 AND message_count crosses a 30 boundary (32, 62, 92...)
        # Since we check AFTER assistant message is saved, trigger at 32, 62, 92...
        SUMMARIZE_INTERVAL = 30

        should_check_summarization = False
        if current_message_count > 30 and current_message_count % SUMMARIZE_INTERVAL == 2:
            # 32 % 30 == 2, 62 % 30 == 2, 92 % 30 == 2
            should_check_summarization = True
            logger.info(f"Summarization TRIGGER at {current_message_count} messages")

        # Run summarization in background thread so it doesn't block the response
        if should_check_summarization:
            import threading
            def run_summarization():
                try:
                    new_summary = maybe_summarize(chat_id, ILIAD_URL, ILIAD_API_KEY)
                    if new_summary:
                        logger.info(f"Background summarization completed for chat {chat_id}")
                except Exception as e:
                    logger.warning(f"Background summarization failed for chat {chat_id}: {e}")

            summarization_thread = threading.Thread(target=run_summarization, daemon=True)
            summarization_thread.start()
            logger.info(f"Started background summarization thread for chat {chat_id}")
        else:
            logger.info(f"Skipping summarization: {current_message_count} messages (triggers at 31, 61, 91...)")

        return {
            "success": True,
            "assistant_message": {
                "message_id": assistant_message['message_id'],
                "role": "assistant",
                "content": assistant_message['content'],
                "sequence_num": assistant_message.get('sequence_num'),
                "created_at": assistant_message['created_at'].isoformat() if assistant_message['created_at'] else None
            },
            "current_summary": current_summary  # Return current summary for agent context
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving assistant message to chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DOCUMENT ENDPOINTS
# ============================================================================

@router.post("/chats/{chat_id}/documents")
async def add_document(chat_id: str, request: Request, body: AddDocumentRequest):
    """Add a document to a chat."""
    try:
        user_id = get_current_user_info(request)['user_id']

        # Verify chat exists and user has access
        chat = get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        if chat['user_id'] != user_id and user_id != 'anonymous':
            raise HTTPException(status_code=403, detail="Access denied")

        # Add document (Phase 4: includes process_id for RAG search)
        doc = add_document_to_chat(
            chat_id=chat_id,
            document_id=body.document_id,
            document_name=body.document_name,
            page_count=body.page_count,
            file_size=body.file_size,
            file_path=body.file_path,
            weaviate_source=body.weaviate_source,
            process_id=body.process_id,
            document_type=body.document_type,
            processing_status=body.processing_status,
            extraction_done=body.extraction_done
        )

        return {
            "success": True,
            "document": {
                "id": doc['id'],
                "document_id": doc['document_id'],
                "document_name": doc['document_name'],
                "upload_order": doc['upload_order'],
                "created_at": doc['created_at'].isoformat() if doc['created_at'] else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding document to chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chats/{chat_id}/documents")
async def list_chat_documents(chat_id: str, request: Request):
    """List all documents in a chat."""
    try:
        user_id = get_current_user_info(request)['user_id']

        # Verify chat exists and user has access
        chat = get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        if chat['user_id'] != user_id and user_id != 'anonymous':
            raise HTTPException(status_code=403, detail="Access denied")

        documents = get_chat_documents(chat_id)

        return {
            "success": True,
            "chat_id": chat_id,
            "active_document_id": chat.get('active_document_id'),
            "documents": [
                {
                    "document_id": d['document_id'],
                    "document_name": d['document_name'],
                    "upload_order": d['upload_order'],
                    "page_count": d.get('page_count'),
                    "extraction_done": d.get('extraction_done', False),
                    "is_active": d['document_id'] == chat.get('active_document_id'),
                    "created_at": d['created_at'].isoformat() if d['created_at'] else None
                }
                for d in documents
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing documents for chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/chats/{chat_id}/documents/{document_id}")
async def update_document_status(
    chat_id: str,
    document_id: str,
    request: Request,
    extraction_done: bool = None,
    extraction_prompt: str = None,
    extraction_result_url: str = None
):
    """Update document extraction status."""
    try:
        user_id = get_current_user_info(request)['user_id']

        # Verify chat exists and user has access
        chat = get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        if chat['user_id'] != user_id and user_id != 'anonymous':
            raise HTTPException(status_code=403, detail="Access denied")

        doc = update_document_extraction(
            chat_id=chat_id,
            document_id=document_id,
            extraction_done=extraction_done,
            extraction_prompt=extraction_prompt,
            extraction_result_url=extraction_result_url
        )

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "success": True,
            "document": {
                "document_id": doc['document_id'],
                "extraction_done": doc['extraction_done'],
                "extraction_result_url": doc.get('extraction_result_url')
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document {document_id} in chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONTEXT ENDPOINT (for debugging/testing)
# ============================================================================

@router.get("/chats/{chat_id}/context")
async def get_claude_context(chat_id: str, request: Request):
    """
    Get the context that would be sent to Claude.
    Useful for debugging and testing.
    """
    try:
        user_id = get_current_user_info(request)['user_id']

        context = get_chat_context(chat_id)
        if not context:
            raise HTTPException(status_code=404, detail="Chat not found")

        chat = context['chat']
        if chat['user_id'] != user_id and user_id != 'anonymous':
            raise HTTPException(status_code=403, detail="Access denied")

        return {
            "success": True,
            "context": {
                "chat_id": chat_id,
                "summary": context.get('summary'),
                "recent_messages_count": len(context['recent_messages']),
                "recent_messages": [
                    {
                        "role": m['role'],
                        "content": m['content'][:200] + "..." if len(m['content']) > 200 else m['content']
                    }
                    for m in context['recent_messages']
                ],
                "documents": [
                    {
                        "document_id": d['document_id'],
                        "document_name": d['document_name'],
                        "is_active": d['document_id'] == context['active_document_id']
                    }
                    for d in context['documents']
                ],
                "active_document_id": context['active_document_id']
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting context for chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
