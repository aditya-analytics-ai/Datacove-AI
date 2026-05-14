"""
pagination.py - Standardized pagination for list endpoints.

Provides unified pagination parameters and response wrapping for all list endpoints.
Enables consistent limit/offset/sorting across the API.

Usage:
    from utils.pagination import PaginationParams, paginate_response
    
    # In a route:
    @router.get("/items")
    async def list_items(
        pagination: PaginationParams = Depends(),
    ):
        items = get_all_items()
        total = len(items)
        
        # Apply pagination
        start = pagination.offset
        end = start + pagination.limit
        paginated_items = items[start:end]
        
        return paginate_response(
            items=paginated_items,
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
        )

Non-breaking: New utility providing opt-in standardization. Existing routes unaffected.
"""

from typing import Generic, TypeVar, List, Optional, Any, Dict
from pydantic import BaseModel, Field
from fastapi import Query

T = TypeVar("T")


class PaginationParams(BaseModel):
    """
    Standardized pagination parameters for list endpoints.
    
    Query parameters:
        limit: Maximum items per page (1-1000, default 50)
        offset: Starting position (default 0)
        sort_by: Field to sort by (optional)
        sort_order: 'asc' or 'desc' (default 'asc')
    """
    
    limit: int = Query(
        default=50,
        ge=1,
        le=1000,
        description="Items per page (1-1000)"
    )
    offset: int = Query(
        default=0,
        ge=0,
        description="Starting position (0-indexed)"
    )
    sort_by: Optional[str] = Query(
        default=None,
        description="Field to sort by (e.g., 'created_at', 'name')"
    )
    sort_order: str = Query(
        default="asc",
        pattern="^(asc|desc)$",
        description="Sort order: 'asc' or 'desc'"
    )
    
    @property
    def skip(self) -> int:
        """Alias for offset (SQLAlchemy compatibility)."""
        return self.offset
    
    @property
    def take(self) -> int:
        """Alias for limit (some ORM compatibility)."""
        return self.limit
    
    def get_slice(self) -> tuple:
        """Get (offset, limit) tuple for database queries."""
        return (self.offset, self.limit)


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standardized paginated response wrapper.
    
    Fields:
        items: List of paginated items
        total: Total count of all items
        limit: Items per page
        offset: Current page offset
        page: Current page number (calculated)
        pages: Total number of pages (calculated)
        has_next: Whether next page exists
        has_prev: Whether previous page exists
    """
    
    items: List[T]
    total: int
    limit: int
    offset: int
    
    @property
    def page(self) -> int:
        """Calculate current page number (1-indexed)."""
        return (self.offset // max(self.limit, 1)) + 1
    
    @property
    def pages(self) -> int:
        """Calculate total number of pages."""
        return (self.total + max(self.limit, 1) - 1) // max(self.limit, 1)
    
    @property
    def has_next(self) -> bool:
        """Check if next page exists."""
        return self.offset + self.limit < self.total
    
    @property
    def has_prev(self) -> bool:
        """Check if previous page exists."""
        return self.offset > 0


def paginate_response(
    items: List[Any],
    total: int,
    limit: int,
    offset: int,
    **extra_fields,
) -> Dict[str, Any]:
    """
    Create standardized paginated response.
    
    Args:
        items: List of items for this page
        total: Total count of all items
        limit: Items per page
        offset: Current page offset
        **extra_fields: Additional fields to include in response
        
    Returns:
        Dict with pagination metadata and items
        
    Example:
        return paginate_response(
            items=dataset_list[start:end],
            total=len(dataset_list),
            limit=pagination.limit,
            offset=pagination.offset,
            query_time_ms=elapsed_ms,
        )
    """
    
    # Calculate pagination metadata
    page = (offset // max(limit, 1)) + 1
    pages = (total + max(limit, 1) - 1) // max(limit, 1)
    has_next = offset + limit < total
    has_prev = offset > 0
    
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": page,
        "pages": pages,
        "has_next": has_next,
        "has_prev": has_prev,
        **extra_fields,
    }


def get_pagination_params(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: Optional[str] = Query(None),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
) -> PaginationParams:
    """
    Create pagination params from query strings.
    Use this as a dependency in routes that don't access request body.
    
    Example:
        @router.get("/items")
        async def list_items(
            pagination: PaginationParams = Depends(get_pagination_params)
        ):
            ...
    """
    return PaginationParams(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


class CursorPaginationParams(BaseModel):
    """
    Cursor-based pagination for efficient large dataset pagination.
    Better than offset pagination for very large results.
    
    Fields:
        cursor: Opaque cursor string (base64 encoded ID + position)
        limit: Items to return
        direction: 'next' or 'prev'
    """
    
    cursor: Optional[str] = Query(None, description="Pagination cursor")
    limit: int = Query(20, ge=1, le=500, description="Items per page")
    direction: str = Query("next", pattern="^(next|prev)$")


def decode_cursor(cursor: Optional[str]) -> Optional[Dict[str, Any]]:
    """Decode cursor string (implement based on your ID scheme)."""
    if not cursor:
        return None
    
    try:
        import base64
        import json
        decoded = base64.b64decode(cursor).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return None


def encode_cursor(data: Dict[str, Any]) -> str:
    """Encode cursor from dict."""
    import base64
    import json
    encoded = base64.b64encode(json.dumps(data).encode("utf-8"))
    return encoded.decode("utf-8")
