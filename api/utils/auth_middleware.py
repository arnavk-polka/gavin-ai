from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from config import logger

def require_auth(request: Request):
    """
    Check if user is authenticated. Raise HTTPException if not.
    For use in API endpoints.
    """
    if not request.session.get('authenticated'):
        logger.warning(f"Unauthenticated API access attempt from {request.client.host}")
        raise HTTPException(status_code=401, detail="Authentication required")
    return True

def require_auth_redirect(request: Request):
    """
    Check if user is authenticated. Return redirect response if not.
    For use in page routes.
    """
    if not request.session.get('authenticated'):
        logger.info(f"Redirecting unauthenticated user from {request.url.path} to login")
        return RedirectResponse(url="/login", status_code=302)
    return None

def get_current_user(request: Request):
    """
    Get current authenticated user info from session.
    Returns None if not authenticated.
    """
    if request.session.get('authenticated'):
        return request.session.get('user')
    return None

def is_authenticated(request: Request) -> bool:
    """
    Simple check if user is authenticated.
    """
    return bool(request.session.get('authenticated')) 