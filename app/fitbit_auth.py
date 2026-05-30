import os
import requests
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from .models import FitbitAccount, User
from .database import get_db
from dotenv import load_dotenv

load_dotenv()

FITBIT_CLIENT_ID = os.getenv("FITBIT_CLIENT_ID")
FITBIT_CLIENT_SECRET = os.getenv("FITBIT_CLIENT_SECRET")
FITBIT_REDIRECT_URI = os.getenv("FITBIT_REDIRECT_URI", "http://localhost:8000/api/auth/fitbit/callback")

FITBIT_AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
FITBIT_TOKEN_URL = "https://api.fitbit.com/oauth2/token"

class FitbitOAuth:
    @staticmethod
    def get_authorization_url(user_id: int):
        """Generate Fitbit OAuth authorization URL"""
        params = {
            "client_id": FITBIT_CLIENT_ID,
            "redirect_uri": FITBIT_REDIRECT_URI,
            "response_type": "code",
            "scope": "sleep",
            "expires_in": 604800,  # 7 days
            "state": str(user_id),  # Use user_id as state parameter
        }
        
        from urllib.parse import urlencode

        query_string = urlencode(params)
        return f"{FITBIT_AUTH_URL}?{query_string}"
    
    @staticmethod
    def exchange_code_for_tokens(code: str):
        """Exchange authorization code for access and refresh tokens"""
        import base64
        
        # Fitbit requires Basic Authentication with client_id:client_secret
        auth_string = f"{FITBIT_CLIENT_ID}:{FITBIT_CLIENT_SECRET}"
        auth_header = base64.b64encode(auth_string.encode()).decode()
        
        data = {
            "grant_type": "authorization_code",
            "redirect_uri": FITBIT_REDIRECT_URI,
            "code": code,
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_header}",
        }
        
        try:
            print(f"Making token exchange request to: {FITBIT_TOKEN_URL}")
            print(f"Request data: {data}")
            response = requests.post(FITBIT_TOKEN_URL, data=data, headers=headers)
            print(f"Response status: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")
            
            if response.status_code != 200:
                print(f"Response body: {response.text}")
            
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            # Add more detailed error information
            error_detail = f"Failed to exchange code for tokens: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                print(f"Error response status: {e.response.status_code}")
                print(f"Error response body: {e.response.text}")
                try:
                    error_json = e.response.json()
                    if 'errors' in error_json:
                        error_detail += f" - {error_json['errors']}"
                except:
                    pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail
            )
    
    @staticmethod
    def refresh_access_token(refresh_token: str):
        """Refresh access token using refresh token"""
        import base64
        
        # Fitbit requires Basic Authentication with client_id:client_secret
        auth_string = f"{FITBIT_CLIENT_ID}:{FITBIT_CLIENT_SECRET}"
        auth_header = base64.b64encode(auth_string.encode()).decode()
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "expires_in": 604800,  # 7 days
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_header}",
        }
        
        try:
            response = requests.post(FITBIT_TOKEN_URL, data=data, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            # Add more detailed error information
            error_detail = f"Failed to refresh token: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_json = e.response.json()
                    if 'errors' in error_json:
                        error_detail += f" - {error_json['errors']}"
                except:
                    pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail
            )
    
    @staticmethod
    def save_fitbit_account(db: Session, user_id: int, token_data: dict):
        """Save or update Fitbit account information"""
        # Calculate token expiration time
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        # Check if Fitbit account already exists for this user
        fitbit_account = db.query(FitbitAccount).filter(FitbitAccount.user_id == user_id).first()
        
        if fitbit_account:
            # Update existing account
            fitbit_account.access_token = token_data["access_token"]
            fitbit_account.refresh_token = token_data["refresh_token"]
            fitbit_account.token_expires_at = expires_at
            fitbit_account.fitbit_user_id = token_data.get("user_id")
        else:
            # Create new account
            fitbit_account = FitbitAccount(
                user_id=user_id,
                fitbit_user_id=token_data.get("user_id"),
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                token_expires_at=expires_at
            )
            db.add(fitbit_account)
        
        db.commit()
        db.refresh(fitbit_account)
        return fitbit_account
    
    @staticmethod
    def get_valid_access_token(db: Session, user_id: int):
        """Get valid access token, refresh if necessary"""
        fitbit_account = db.query(FitbitAccount).filter(FitbitAccount.user_id == user_id).first()
        
        if not fitbit_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fitbit account not connected"
            )
        
        # Check if token is expired or will expire within 5 minutes
        if datetime.utcnow() >= fitbit_account.token_expires_at - timedelta(minutes=5):
            # Refresh the token
            token_data = FitbitOAuth.refresh_access_token(fitbit_account.refresh_token)
            
            # Update the account with new tokens
            expires_in = token_data.get("expires_in", 3600)
            fitbit_account.access_token = token_data["access_token"]
            fitbit_account.refresh_token = token_data["refresh_token"]
            fitbit_account.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            db.commit()
            db.refresh(fitbit_account)
        
        return fitbit_account.access_token
    
    @staticmethod
    def disconnect_fitbit(db: Session, user_id: int):
        """Disconnect Fitbit account for user"""
        fitbit_account = db.query(FitbitAccount).filter(FitbitAccount.user_id == user_id).first()
        
        if not fitbit_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fitbit account not connected"
            )
        
        db.delete(fitbit_account)
        db.commit()
        
        return True
    
    @staticmethod
    def is_fitbit_connected(db: Session, user_id: int):
        """Check if user has connected Fitbit account"""
        fitbit_account = db.query(FitbitAccount).filter(FitbitAccount.user_id == user_id).first()
        return fitbit_account is not None
