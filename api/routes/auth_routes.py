import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from config import logger, google_oauth
import httpx

auth_router = APIRouter()

@auth_router.get("/login")
async def login(request: Request):
    """Initiate Google OAuth login"""
    if not google_oauth:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    from config import REDIRECT_URI
    # Use the configured redirect URI instead of generating it dynamically
    return await google_oauth.authorize_redirect(request, REDIRECT_URI)

@auth_router.get("/callback")
async def auth_callback(request: Request):
    """Handle Google OAuth callback"""
    if not google_oauth:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    try:
        # Get the authorization token
        token = await google_oauth.authorize_access_token(request)
        
        # Get user info from Google API
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {token["access_token"]}'}
            )
            if resp.status_code != 200:
                raise Exception(f"Failed to get user info: {resp.status_code} {resp.text}")
            user_info = resp.json()
        
        # Store user info in session
        request.session['user'] = {
            'id': user_info.get('id'),
            'email': user_info.get('email'),
            'name': user_info.get('name'),
            'picture': user_info.get('picture'),
            'verified_email': user_info.get('verified_email', False)
        }
        request.session['authenticated'] = True
        
        logger.info(f"User {user_info.get('email')} authenticated successfully")
        
        # Redirect to main application
        return RedirectResponse(url="/")
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        # Clear any partial session data
        request.session.pop('user', None)
        request.session.pop('authenticated', None)
        return RedirectResponse(url="/login?error=oauth_failed")

@auth_router.get("/logout")
async def logout(request: Request):
    """Logout user and clear session"""
    request.session.clear()
    logger.info("User logged out")
    return RedirectResponse(url="/login")

@auth_router.get("/user")
async def get_user(request: Request):
    """Get current user info (API endpoint)"""
    if not request.session.get('authenticated'):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return request.session.get('user', {}) 