# Google OAuth Setup Guide

## Required Environment Variables

Add these to your `.env` file:

```env
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
REDIRECT_URI=http://localhost:8080/auth/callback

# Session Security (will auto-generate if not provided)
SECRET_KEY=your_secret_key_here
```

## Setting Up Google OAuth

1. **Go to Google Cloud Console**
   - Visit https://console.cloud.google.com/
   - Create a new project or select existing one

2. **Enable Google+ API**
   - Go to "APIs & Services" > "Library"
   - Search for "Google+ API" and enable it

3. **Create OAuth 2.0 Credentials**
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client IDs"
   - Choose "Web application"
   - Add authorized redirect URIs:
     - `http://localhost:8080/auth/callback` (for local development)
     - `https://yourdomain.com/auth/callback` (for production)

4. **Configure OAuth Consent Screen**
   - Go to "APIs & Services" > "OAuth consent screen"
   - Fill in required fields (app name, user support email, etc.)
   - Add your email to test users if using external user type

5. **Copy Credentials**
   - Copy the Client ID and Client Secret
   - Add them to your `.env` file

## Installation

Install the new dependencies:

```bash
pip install -r requirements.txt
```

## How It Works

- Users accessing `/` are redirected to `/login` if not authenticated
- Login page provides Google OAuth button
- After successful authentication, users are redirected back to main app
- User info is stored in session and displayed in top-right corner
- Logout button clears session and redirects to login

## Protected Routes

The following routes now require authentication:
- `/` - Main chat interface
- `/debug/` - Debug interface  
- `/chat/{handle}` - Chat API endpoint
- All other existing routes remain as before

## Testing

1. Start your server: `python main.py`
2. Visit `http://localhost:8080`
3. You should be redirected to login page
4. Click "Continue with Google"
5. Complete OAuth flow
6. You should be redirected back to main app

## Troubleshooting

- Make sure redirect URI in Google Console matches your REDIRECT_URI env var
- Check that Google+ API is enabled
- Verify OAuth consent screen is properly configured
- Check server logs for detailed error messages 