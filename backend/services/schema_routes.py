"""
Extraction Schema API Routes

Endpoints:
- GET    /api/schemas              - List user's schemas
- POST   /api/schemas              - Create schema
- GET    /api/schemas/{schema_id}  - Get schema
- PATCH  /api/schemas/{schema_id}  - Update schema
- DELETE /api/schemas/{schema_id}  - Delete schema
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

from .database import (
    get_or_create_user,
    create_extraction_schema,
    get_user_schemas,
    get_schema,
    update_schema,
    delete_schema,
    ensure_extraction_schemas_table
)

logger = logging.getLogger("ocr-chatbot.schema_routes")

router = APIRouter(prefix="/api", tags=["schemas"])

# Ensure table exists on module load
try:
    ensure_extraction_schemas_table()
    logger.info("Extraction schemas table ready")
except Exception as e:
    logger.warning(f"Could not ensure extraction_schemas table: {e}")


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ParameterDefinition(BaseModel):
    name: str
    type: str = "string"  # string, number, date, boolean
    hint: Optional[str] = None
    required: bool = True
    unit: Optional[str] = None


class CreateSchemaRequest(BaseModel):
    name: str
    description: Optional[str] = None
    document_type: str = "general"
    parameters: List[ParameterDefinition]
    is_shared: bool = False


class UpdateSchemaRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    document_type: Optional[str] = None
    parameters: Optional[List[ParameterDefinition]] = None
    is_shared: Optional[bool] = None


# ============================================================================
# HELPER
# ============================================================================

def get_user_id(request: Request) -> str:
    """Extract user_id from request headers or use default."""
    user_id = request.headers.get("x-user-id", "default_user")
    get_or_create_user(user_id)
    return user_id


# ============================================================================
# ROUTES
# ============================================================================

@router.get("/schemas")
async def list_schemas(request: Request):
    """List all schemas for the current user (own + shared)."""
    user_id = get_user_id(request)

    try:
        schemas = get_user_schemas(user_id)
        return {
            "schemas": schemas,
            "count": len(schemas)
        }
    except Exception as e:
        logger.error(f"Error listing schemas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schemas")
async def create_schema(request: Request, body: CreateSchemaRequest):
    """Create a new extraction schema."""
    user_id = get_user_id(request)

    try:
        schema = create_extraction_schema(
            user_id=user_id,
            name=body.name,
            parameters=[p.dict() for p in body.parameters],
            description=body.description,
            document_type=body.document_type,
            is_shared=body.is_shared
        )
        return schema
    except Exception as e:
        logger.error(f"Error creating schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schemas/{schema_id}")
async def get_schema_by_id(schema_id: str):
    """Get a schema by ID."""
    try:
        schema = get_schema(schema_id)
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
        return schema
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/schemas/{schema_id}")
async def update_schema_endpoint(schema_id: str, request: Request, body: UpdateSchemaRequest):
    """Update a schema (owner only)."""
    user_id = get_user_id(request)

    try:
        updates = body.dict(exclude_none=True)
        if 'parameters' in updates:
            updates['parameters'] = [p.dict() if hasattr(p, 'dict') else p for p in updates['parameters']]

        schema = update_schema(schema_id, user_id, **updates)
        if not schema:
            raise HTTPException(status_code=403, detail="Not authorized to update this schema")
        return schema
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/schemas/{schema_id}")
async def delete_schema_endpoint(schema_id: str, request: Request):
    """Delete a schema (owner only)."""
    user_id = get_user_id(request)

    try:
        success = delete_schema(schema_id, user_id)
        if not success:
            raise HTTPException(status_code=403, detail="Not authorized to delete this schema")
        return {"success": True, "deleted": schema_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))
