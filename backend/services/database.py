"""
PostgreSQL Database Service for Chat History Persistence

Connection: intelligentparsing-ngxp-dev.cimrdaj1f7u6.us-east-1.rds.amazonaws.com
Database: ocr_rag_system
Schema: rag

Tables:
- rag.users
- rag.chats
- rag.chat_documents
- rag.messages
- rag.pdf_page_cache
"""

import os
import uuid
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ocr-chatbot.database")

# Database Configuration
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "intelligentparsing-ngxp-dev.cimrdaj1f7u6.us-east-1.rds.amazonaws.com"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "ocr_rag_system"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "options": "-c search_path=rag,public"
}

# Connection pool (min 1, max 10 connections)
_connection_pool: Optional[pool.ThreadedConnectionPool] = None


def get_connection_pool() -> pool.ThreadedConnectionPool:
    """Get or create the connection pool."""
    global _connection_pool
    if _connection_pool is None:
        try:
            _connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                **DB_CONFIG
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise
    return _connection_pool


@contextmanager
def get_db_connection():
    """Context manager for database connections from pool."""
    conn = None
    try:
        conn = get_connection_pool().getconn()
        yield conn
    finally:
        if conn:
            get_connection_pool().putconn(conn)


@contextmanager
def get_db_cursor(commit: bool = True):
    """Context manager for database cursor with auto-commit."""
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()


def generate_chat_id() -> str:
    """Generate unique chat ID."""
    return f"chat_{uuid.uuid4().hex[:12]}"


def generate_message_id() -> str:
    """Generate unique message ID."""
    return f"msg_{uuid.uuid4().hex[:12]}"


# ============================================================================
# USER FUNCTIONS
# ============================================================================

def get_or_create_user(user_id: str, email: str = None, full_name: str = None) -> Dict[str, Any]:
    """Get existing user or create new one."""
    with get_db_cursor() as cursor:
        # Try to get existing user
        cursor.execute(
            "SELECT * FROM users WHERE user_id = %s",
            [user_id]
        )
        user = cursor.fetchone()

        if user:
            return dict(user)

        # Create new user - email is NOT NULL in schema, so use fallback if not provided
        actual_email = email if email else f"{user_id}@abbvienet.com"
        actual_name = full_name if full_name else user_id

        cursor.execute("""
            INSERT INTO users (user_id, email, full_name, created_at)
            VALUES (%s, %s, %s, NOW())
            RETURNING *
        """, [user_id, actual_email, actual_name])

        return dict(cursor.fetchone())


# ============================================================================
# CHAT FUNCTIONS
# ============================================================================

def create_chat(user_id: str, title: str = "New Chat") -> Dict[str, Any]:
    """Create a new chat for a user."""
    chat_id = generate_chat_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO chats (chat_id, user_id, title, message_count, created_at, updated_at)
            VALUES (%s, %s, %s, 0, NOW(), NOW())
            RETURNING *
        """, [chat_id, user_id, title])

        chat = dict(cursor.fetchone())
        logger.info(f"Created chat {chat_id} for user {user_id}")
        return chat


def get_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    """Get a chat by ID."""
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            "SELECT * FROM chats WHERE chat_id = %s",
            [chat_id]
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_user_chats(user_id: str, include_archived: bool = False) -> List[Dict[str, Any]]:
    """Get all chats for a user, sorted by updated_at DESC."""
    with get_db_cursor(commit=False) as cursor:
        if include_archived:
            cursor.execute("""
                SELECT c.*,
                       (SELECT document_name FROM chat_documents cd
                        WHERE cd.chat_id = c.chat_id
                        ORDER BY upload_order DESC LIMIT 1) as latest_document
                FROM chats c
                WHERE c.user_id = %s
                ORDER BY c.updated_at DESC
            """, [user_id])
        else:
            cursor.execute("""
                SELECT c.*,
                       (SELECT document_name FROM chat_documents cd
                        WHERE cd.chat_id = c.chat_id
                        ORDER BY upload_order DESC LIMIT 1) as latest_document
                FROM chats c
                WHERE c.user_id = %s AND c.is_archived = FALSE
                ORDER BY c.updated_at DESC
            """, [user_id])

        return [dict(row) for row in cursor.fetchall()]


def update_chat(chat_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Update chat fields. Accepts: title, summary, active_document_id, is_archived, metadata."""
    allowed_fields = {'title', 'summary', 'active_document_id', 'is_archived', 'metadata'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return get_chat(chat_id)

    set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
    values = list(updates.values()) + [chat_id]

    with get_db_cursor() as cursor:
        cursor.execute(f"""
            UPDATE chats
            SET {set_clause}, updated_at = NOW()
            WHERE chat_id = %s
            RETURNING *
        """, values)

        result = cursor.fetchone()
        return dict(result) if result else None


def delete_chat(chat_id: str, user_id: str) -> bool:
    """Delete a chat and all its messages (CASCADE). Verify ownership first."""
    with get_db_cursor() as cursor:
        # Verify ownership
        cursor.execute(
            "SELECT user_id FROM chats WHERE chat_id = %s",
            [chat_id]
        )
        chat = cursor.fetchone()

        if not chat or chat['user_id'] != user_id:
            logger.warning(f"Delete failed: user {user_id} doesn't own chat {chat_id}")
            return False

        # Delete chat (messages cascade automatically due to ON DELETE CASCADE)
        cursor.execute(
            "DELETE FROM chats WHERE chat_id = %s",
            [chat_id]
        )

        logger.info(f"Deleted chat {chat_id}")
        return True


# ============================================================================
# MESSAGE FUNCTIONS (with sequence_num locking to prevent race conditions)
# ============================================================================

def save_message(
    chat_id: str,
    role: str,
    content: str,
    document_id: str = None,
    message_type: str = "text",
    references: Dict = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Save a message with race-condition-safe sequence numbering.
    Uses FOR UPDATE lock to prevent duplicate sequence numbers.
    """
    message_id = generate_message_id()

    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Lock the chat row to prevent race condition
            cursor.execute(
                "SELECT message_count FROM chats WHERE chat_id = %s FOR UPDATE",
                [chat_id]
            )
            result = cursor.fetchone()

            if not result:
                raise ValueError(f"Chat {chat_id} not found")

            sequence_num = result['message_count'] + 1

            # Build optional fields
            extra_fields = []
            extra_values = []

            if kwargs.get('attached_file_name'):
                extra_fields.extend(['attached_file_name', 'attached_file_size'])
                extra_values.extend([kwargs['attached_file_name'], kwargs.get('attached_file_size')])

            if kwargs.get('generated_file_url'):
                extra_fields.extend(['generated_file_url', 'generated_file_name', 'generated_file_metadata'])
                extra_values.extend([
                    kwargs['generated_file_url'],
                    kwargs.get('generated_file_name'),
                    kwargs.get('generated_file_metadata')
                ])

            # Build the INSERT query
            # Note: "references" is a reserved keyword in PostgreSQL, so we quote it
            base_fields = 'message_id, chat_id, document_id, role, content, sequence_num, message_type, "references", created_at'
            base_values = [message_id, chat_id, document_id, role, content, sequence_num, message_type,
                          psycopg2.extras.Json(references) if references else None]

            if extra_fields:
                fields = f"{base_fields}, {', '.join(extra_fields)}"
                placeholders = ", ".join(["%s"] * (len(base_values) + len(extra_values) + 1))  # +1 for NOW()
                values = base_values + extra_values
            else:
                fields = base_fields
                placeholders = ", ".join(["%s"] * len(base_values)) + ", NOW()"
                values = base_values

            cursor.execute(f"""
                INSERT INTO messages ({fields})
                VALUES ({placeholders})
                RETURNING *
            """, values + [datetime.now()] if extra_fields else values)

            message = dict(cursor.fetchone())

            # Update chat message_count
            cursor.execute("""
                UPDATE chats
                SET message_count = %s, updated_at = NOW()
                WHERE chat_id = %s
            """, [sequence_num, chat_id])

            conn.commit()
            logger.info(f"Saved message {message_id} (seq={sequence_num}) to chat {chat_id}")
            return message

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save message: {e}")
            raise
        finally:
            cursor.close()


def get_messages(chat_id: str, include_summarized: bool = True) -> List[Dict[str, Any]]:
    """Get all messages for a chat in order."""
    with get_db_cursor(commit=False) as cursor:
        if include_summarized:
            cursor.execute("""
                SELECT * FROM messages
                WHERE chat_id = %s
                ORDER BY sequence_num ASC
            """, [chat_id])
        else:
            cursor.execute("""
                SELECT * FROM messages
                WHERE chat_id = %s AND is_summarized = FALSE
                ORDER BY sequence_num ASC
            """, [chat_id])

        return [dict(row) for row in cursor.fetchall()]


def get_recent_messages(chat_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Get the last N unsummarized messages for Claude context."""
    with get_db_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT * FROM messages
            WHERE chat_id = %s AND is_summarized = FALSE
            ORDER BY sequence_num DESC
            LIMIT %s
        """, [chat_id, limit])

        # Reverse to get chronological order
        messages = [dict(row) for row in cursor.fetchall()]
        return list(reversed(messages))


def get_unsummarized_messages_up_to(chat_id: str, max_sequence: int) -> List[Dict[str, Any]]:
    """Get unsummarized messages up to a sequence number (for summarization)."""
    with get_db_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT * FROM messages
            WHERE chat_id = %s
              AND sequence_num <= %s
              AND is_summarized = FALSE
            ORDER BY sequence_num ASC
        """, [chat_id, max_sequence])

        return [dict(row) for row in cursor.fetchall()]


def mark_messages_summarized(chat_id: str, up_to_sequence: int) -> int:
    """Mark messages as summarized up to a given sequence number."""
    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE messages
            SET is_summarized = TRUE
            WHERE chat_id = %s AND sequence_num <= %s
        """, [chat_id, up_to_sequence])

        return cursor.rowcount


# ============================================================================
# CHAT DOCUMENT FUNCTIONS
# ============================================================================

def add_document_to_chat(
    chat_id: str,
    document_id: str,
    document_name: str,
    page_count: int = None,
    file_size: int = None,
    file_path: str = None,
    weaviate_source: str = None,  # Kept for API compatibility but not stored
    process_id: str = None,
    document_type: str = None,
    processing_status: str = 'completed',
    extraction_done: bool = True
) -> Dict[str, Any]:
    """
    Add a document to a chat and update active_document_id.

    Args:
        chat_id: The chat session ID
        document_id: Unique document identifier (UUID)
        document_name: Original filename
        page_count: Number of pages in PDF
        file_size: File size in bytes
        file_path: Storage path for the file
        weaviate_source: Legacy parameter (ignored, kept for API compatibility)
        process_id: Weaviate filter key for RAG search (same as document_id if not provided)
        document_type: Type of document (e.g., 'coa', 'hbr')
        processing_status: Status of processing ('pending', 'processing', 'completed', 'failed')
        extraction_done: Whether extraction completed successfully

    Note: process_id is used for Weaviate hybrid search filtering.
    If not provided, it defaults to document_id for backwards compatibility.
    """
    # Default process_id to document_id if not provided
    actual_process_id = process_id if process_id else document_id

    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            # Get current max upload_order for this chat
            cursor.execute("""
                SELECT COALESCE(MAX(upload_order), 0) as max_order
                FROM chat_documents
                WHERE chat_id = %s
            """, [chat_id])

            max_order = cursor.fetchone()['max_order']
            new_order = max_order + 1

            # Insert document with process_id for Weaviate filtering
            # Note: weaviate_source column removed from schema, using process_id instead
            cursor.execute("""
                INSERT INTO chat_documents
                (chat_id, document_id, document_name, upload_order, page_count, file_size,
                 file_path, process_id, document_type, processing_status, extraction_done, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING *
            """, [chat_id, document_id, document_name, new_order, page_count, file_size,
                  file_path, actual_process_id, document_type, processing_status, extraction_done])

            doc = dict(cursor.fetchone())

            # Update active_document_id in chat
            cursor.execute("""
                UPDATE chats
                SET active_document_id = %s, updated_at = NOW()
                WHERE chat_id = %s
            """, [document_id, chat_id])

            conn.commit()
            logger.info(f"Added document {document_id} (process_id={actual_process_id}) to chat {chat_id} (order={new_order})")
            return doc

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add document to chat: {e}")
            raise
        finally:
            cursor.close()


def get_chat_documents(chat_id: str) -> List[Dict[str, Any]]:
    """Get all documents for a chat in upload order."""
    with get_db_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT * FROM chat_documents
            WHERE chat_id = %s
            ORDER BY upload_order ASC
        """, [chat_id])

        return [dict(row) for row in cursor.fetchall()]


def get_document_by_id(document_id: str) -> Optional[Dict[str, Any]]:
    """Get a document by its document_id."""
    with get_db_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT * FROM chat_documents
            WHERE document_id = %s
        """, [document_id])

        result = cursor.fetchone()
        return dict(result) if result else None


def get_process_id_for_document(document_id: str) -> Optional[str]:
    """
    Get the Weaviate process_id for a given document_id.
    Used for RAG search filtering.

    Returns:
        The process_id string, or None if document not found
    """
    with get_db_cursor(commit=False) as cursor:
        cursor.execute("""
            SELECT process_id FROM chat_documents
            WHERE document_id = %s
        """, [document_id])

        result = cursor.fetchone()
        if result:
            # Return process_id, or document_id as fallback (backwards compatibility)
            return result.get('process_id') or document_id
        return None


def get_active_document_process_id(chat_id: str) -> Optional[str]:
    """
    Get the process_id for the active document in a chat.
    This is used to filter Weaviate search to the current document.

    Returns:
        The process_id string, or None if no active document
    """
    with get_db_cursor(commit=False) as cursor:
        # Join chats with chat_documents to get process_id of active document
        cursor.execute("""
            SELECT cd.process_id, cd.document_id, cd.document_name
            FROM chats c
            JOIN chat_documents cd ON c.active_document_id = cd.document_id
            WHERE c.chat_id = %s
        """, [chat_id])

        result = cursor.fetchone()
        if result:
            # Return process_id, or document_id as fallback
            return result.get('process_id') or result.get('document_id')
        return None


def update_document_extraction(
    chat_id: str,
    document_id: str,
    extraction_done: bool = True,
    extraction_prompt: str = None,
    extraction_result_url: str = None
) -> Optional[Dict[str, Any]]:
    """Update document extraction status."""
    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE chat_documents
            SET extraction_done = %s,
                extraction_prompt = COALESCE(%s, extraction_prompt),
                extraction_result_url = COALESCE(%s, extraction_result_url)
            WHERE chat_id = %s AND document_id = %s
            RETURNING *
        """, [extraction_done, extraction_prompt, extraction_result_url, chat_id, document_id])

        result = cursor.fetchone()
        return dict(result) if result else None


# ============================================================================
# SUMMARIZATION FUNCTIONS
# ============================================================================

def save_chat_summary(chat_id: str, summary: str) -> Optional[Dict[str, Any]]:
    """Save or update chat summary. Also updates summary_updated_at timestamp."""
    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE chats
            SET summary = %s, summary_updated_at = NOW(), updated_at = NOW()
            WHERE chat_id = %s
            RETURNING *
        """, [summary, chat_id])

        result = cursor.fetchone()
        return dict(result) if result else None


def get_chat_context(chat_id: str, recent_limit: int = 20) -> Dict[str, Any]:
    """
    Get complete context for Claude:
    - Chat info (including summary)
    - Last N unsummarized messages
    - All documents in chat
    """
    with get_db_cursor(commit=False) as cursor:
        # Get chat with summary
        cursor.execute("SELECT * FROM chats WHERE chat_id = %s", [chat_id])
        chat = cursor.fetchone()

        if not chat:
            return None

        chat = dict(chat)

        # Get recent unsummarized messages
        cursor.execute("""
            SELECT * FROM messages
            WHERE chat_id = %s AND is_summarized = FALSE
            ORDER BY sequence_num DESC
            LIMIT %s
        """, [chat_id, recent_limit])

        recent_messages = list(reversed([dict(row) for row in cursor.fetchall()]))

        # Get all documents
        cursor.execute("""
            SELECT * FROM chat_documents
            WHERE chat_id = %s
            ORDER BY upload_order ASC
        """, [chat_id])

        documents = [dict(row) for row in cursor.fetchall()]

        return {
            "chat": chat,
            "summary": chat.get("summary"),
            "recent_messages": recent_messages,
            "documents": documents,
            "active_document_id": chat.get("active_document_id")
        }


# ============================================================================
# PDF PAGE CACHE FUNCTIONS
# ============================================================================

def cache_pdf_page(
    document_id: str,
    page_num: int,
    image_path: str,
    width: int = None,
    height: int = None,
    file_size: int = None
) -> Dict[str, Any]:
    """Cache a PDF page image."""
    with get_db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO pdf_page_cache
            (document_id, page_num, image_path, width, height, file_size, created_at, last_accessed)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (document_id, page_num)
            DO UPDATE SET
                image_path = EXCLUDED.image_path,
                width = EXCLUDED.width,
                height = EXCLUDED.height,
                file_size = EXCLUDED.file_size,
                last_accessed = NOW()
            RETURNING *
        """, [document_id, page_num, image_path, width, height, file_size])

        return dict(cursor.fetchone())


def get_cached_page(document_id: str, page_num: int) -> Optional[Dict[str, Any]]:
    """Get cached PDF page, update last_accessed."""
    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE pdf_page_cache
            SET last_accessed = NOW()
            WHERE document_id = %s AND page_num = %s
            RETURNING *
        """, [document_id, page_num])

        result = cursor.fetchone()
        return dict(result) if result else None


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def test_connection() -> bool:
    """Test database connection."""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT 1")
            logger.info("Database connection test successful")
            return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


def close_pool():
    """Close the connection pool (call on app shutdown)."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Database connection pool closed")


# ============================================================================
# EXTRACTION SCHEMA FUNCTIONS
# ============================================================================

def generate_schema_id() -> str:
    """Generate unique schema ID."""
    return f"schema_{uuid.uuid4().hex[:12]}"


def ensure_extraction_schemas_table():
    """Create extraction_schemas table if it doesn't exist."""
    with get_db_cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extraction_schemas (
                schema_id VARCHAR PRIMARY KEY,
                user_id VARCHAR NOT NULL REFERENCES users(user_id),
                name VARCHAR NOT NULL,
                description TEXT,
                document_type VARCHAR DEFAULT 'general',
                parameters JSONB NOT NULL DEFAULT '[]'::jsonb,
                is_shared BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        logger.info("extraction_schemas table ensured")


def create_extraction_schema(
    user_id: str,
    name: str,
    parameters: list,
    description: str = None,
    document_type: str = "general",
    is_shared: bool = False
) -> Dict[str, Any]:
    """Create a new extraction schema for a user."""
    schema_id = generate_schema_id()

    with get_db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO extraction_schemas
            (schema_id, user_id, name, description, document_type, parameters, is_shared, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING *
        """, [schema_id, user_id, name, description, document_type,
              psycopg2.extras.Json(parameters), is_shared])

        schema = dict(cursor.fetchone())
        logger.info(f"Created extraction schema {schema_id} for user {user_id}")
        return schema


def get_user_schemas(user_id: str, include_shared: bool = True) -> List[Dict[str, Any]]:
    """Get all schemas for a user (own + shared)."""
    with get_db_cursor(commit=False) as cursor:
        if include_shared:
            cursor.execute("""
                SELECT * FROM extraction_schemas
                WHERE user_id = %s OR is_shared = TRUE
                ORDER BY updated_at DESC
            """, [user_id])
        else:
            cursor.execute("""
                SELECT * FROM extraction_schemas
                WHERE user_id = %s
                ORDER BY updated_at DESC
            """, [user_id])

        return [dict(row) for row in cursor.fetchall()]


def get_schema(schema_id: str) -> Optional[Dict[str, Any]]:
    """Get a schema by ID."""
    with get_db_cursor(commit=False) as cursor:
        cursor.execute(
            "SELECT * FROM extraction_schemas WHERE schema_id = %s",
            [schema_id]
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def update_schema(schema_id: str, user_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Update schema fields. Verifies ownership first."""
    allowed_fields = {'name', 'description', 'document_type', 'parameters', 'is_shared'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return get_schema(schema_id)

    with get_db_cursor() as cursor:
        # Verify ownership
        cursor.execute(
            "SELECT user_id FROM extraction_schemas WHERE schema_id = %s",
            [schema_id]
        )
        schema = cursor.fetchone()
        if not schema or schema['user_id'] != user_id:
            logger.warning(f"Update failed: user {user_id} doesn't own schema {schema_id}")
            return None

        # Handle JSONB field
        set_parts = []
        values = []
        for k, v in updates.items():
            if k == 'parameters':
                set_parts.append(f"{k} = %s")
                values.append(psycopg2.extras.Json(v))
            else:
                set_parts.append(f"{k} = %s")
                values.append(v)

        set_clause = ", ".join(set_parts)
        values.append(schema_id)

        cursor.execute(f"""
            UPDATE extraction_schemas
            SET {set_clause}, updated_at = NOW()
            WHERE schema_id = %s
            RETURNING *
        """, values)

        result = cursor.fetchone()
        return dict(result) if result else None


def delete_schema(schema_id: str, user_id: str) -> bool:
    """Delete a schema. Verifies ownership first."""
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT user_id FROM extraction_schemas WHERE schema_id = %s",
            [schema_id]
        )
        schema = cursor.fetchone()
        if not schema or schema['user_id'] != user_id:
            return False

        cursor.execute(
            "DELETE FROM extraction_schemas WHERE schema_id = %s",
            [schema_id]
        )
        logger.info(f"Deleted schema {schema_id}")
        return True
