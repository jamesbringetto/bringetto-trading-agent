"""API authentication middleware."""

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from agent.config.settings import get_settings

# API key header - clients must send: X-API-Key: <your_secret_key>
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """
    Dependency that validates the API key.

    Usage:
        @router.get("/protected")
        async def protected_route(api_key: str = Depends(require_api_key)):
            return {"status": "authenticated"}
    """
    settings = get_settings()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Include 'X-API-Key' header.",
        )

    if api_key != settings.api_secret_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return api_key
