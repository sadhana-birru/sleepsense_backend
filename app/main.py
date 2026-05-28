from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
import tempfile
import json
import io
from datetime import date, datetime, timedelta

from .api import load_models, generate_report_logic
from .api import load_models, generate_report_logic
from typing import Optional
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from .schemas import ReportRequest, UserCreate, UserLogin, Token, GoogleLoginRequest
from . import models, database, auth
from .fitbit_auth import FitbitOAuth
from .fitbit_api import FitbitAPI
from .data_merger import DataMerger
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
if not GOOGLE_CLIENT_ID:
    print("WARNING: GOOGLE_CLIENT_ID not found in environment variables!")
else:
    print(f"GOOGLE_CLIENT_ID loaded: {GOOGLE_CLIENT_ID[:5]}...{GOOGLE_CLIENT_ID[-5:]}")

# Create the database tables
models.Base.metadata.create_all(bind=database.engine)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
        if email is None: raise credentials_exception
    except Exception:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None: raise credentials_exception
    return user

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load models when the application starts
    print("Loading models...")
    load_models()
    yield
    print("Shutting down...")

app = FastAPI(title="SleepSense AI API", lifespan=lifespan)

# Setup CORS to allow React frontend (Vite defaults to port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "SleepSense AI Backend Running"}

@app.post("/api/register", response_model=Token)
def register_user(user: UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(name=user.name, email=user.email, hashed_password=hashed_password, age=user.age)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    access_token = auth.create_access_token(data={"sub": new_user.email})
    return {"access_token": access_token, "token_type": "bearer", "name": new_user.name, "email": new_user.email}

@app.post("/api/login", response_model=Token)
def login_user(user: UserLogin, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if not db_user or not auth.verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
        
    access_token = auth.create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer", "name": db_user.name, "email": db_user.email}

@app.post("/api/auth/google", response_model=Token)
def google_auth(request: GoogleLoginRequest, db: Session = Depends(database.get_db)):
    try:
        # Verify the Google Token
        idinfo = id_token.verify_oauth2_token(
            request.credential, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )

        # ID token is valid. Get user information from it.
        email = idinfo['email']
        name = idinfo.get('name', email.split('@')[0])
        
        # Check if user exists
        db_user = db.query(models.User).filter(models.User.email == email).first()
        
        if not db_user:
            # Create a new user if they don't exist
            # For Google users, we might not have a password or age initially.
            # We can set a dummy password or allow nullable password in models.
            # For now, let's set a random password and a default age if required.
            db_user = models.User(
                name=name,
                email=email,
                hashed_password=auth.get_password_hash(os.urandom(24).hex()), # Random password
                age=25 # Default age, user can update later
            )
            db.add(db_user)
            db.commit()
            db.refresh(db_user)
            
        # Create access token
        access_token = auth.create_access_token(data={"sub": db_user.email})
        return {
            "access_token": access_token, 
            "token_type": "bearer", 
            "name": db_user.name, 
            "email": db_user.email
        }
        
    except ValueError:
        # Invalid token
        raise HTTPException(status_code=401, detail="Invalid Google token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
def get_user_history(current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
    reports = db.query(models.Report).filter(models.Report.user_id == current_user.id).order_by(models.Report.created_at.desc()).all()
    
    formatted_reports = []
    for r in reports:
         formatted_reports.append({
             "id": r.id,
             "created_at": r.created_at.isoformat(),
             "physical_score": r.physical_score,
             "mental_score": r.mental_score,
             "vocal_score": r.vocal_score,
             "overall_score": r.overall_score,
             "status": r.status,
             "advice": r.advice
         })
    return formatted_reports

@app.post("/api/analyze")
async def analyze_data(
    data: str = Form(..., description="JSON stringified demographic, biometric, and text data"),
    audio: UploadFile = File(None, description="Audio file for vocal sentiment analysis"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    try:
        # Parse the JSON string from Form data
        parsed_data = json.loads(data)
        
        # Get merged data based on data source preference
        merged_data = DataMerger.get_merged_data_for_analysis(db, current_user.id, parsed_data)
        
        # Flatten the data for the logic function
        user_input = {**parsed_data.get('demographics', {}), **merged_data}
        
        # Add smartwatch data if provided
        smartwatch = parsed_data.get('smartwatch', {})
        if smartwatch.get('has_smartwatch'):
            user_input['deep_sleep_percent'] = smartwatch.get('deep_sleep_percent')
            user_input['rem_sleep_percent'] = smartwatch.get('rem_sleep_percent')
            user_input['sleep_efficiency'] = smartwatch.get('sleep_efficiency')
            
        text_message = parsed_data.get('text_message', "")
        
        audio_path = None
        if audio:
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            audio_content = await audio.read()
            temp.write(audio_content)
            temp.close()
            audio_path = temp.name

        # Call the core ML inference function
        report = generate_report_logic(user_input, text_message, audio_path)
        
        # Add data source information to the report
        data_source_report = DataMerger.create_data_source_report(db, current_user.id, parsed_data)
        report['data_sources'] = data_source_report
        
        # Save to database
        db_report = models.Report(
            user_id=current_user.id,
            physical_score=report["physical_score"],
            mental_score=report["mental_score"],
            vocal_score=report["vocal_score"],
            overall_score=report["overall_score"],
            status=report["status"],
            advice=report["advice"]
        )
        db.add(db_report)
        db.commit()
        db.refresh(db_report)
        
        # Clean up temporary file
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

        return report

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'data' field.")
    except Exception as e:
        if 'audio_path' in locals() and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        raise HTTPException(status_code=500, detail=str(e))

# Fitbit Authentication Routes
@app.get("/api/auth/fitbit/connect")
def connect_fitbit(current_user: models.User = Depends(get_current_user)):
    """Initiate Fitbit OAuth flow"""
    auth_url = FitbitOAuth.get_authorization_url(current_user.id)
    return {"auth_url": auth_url}

@app.get("/api/auth/fitbit/callback")
def fitbit_callback(
    code: str,
    state: Optional[str] = None,
    db: Session = Depends(database.get_db)
):
    """Handle Fitbit OAuth callback"""
    if not state:
        raise HTTPException(
            status_code=400,
            detail="Missing state parameter (user session lost)"
        )

    try:
        user_id = int(state) if state else None
        
        # Verify user exists
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # Exchange authorization code for tokens
        token_data = FitbitOAuth.exchange_code_for_tokens(code)
        
        # Save Fitbit account information
        fitbit_account = FitbitOAuth.save_fitbit_account(
            db, user_id, token_data
        )

        # Redirect to frontend with success message
        return RedirectResponse(
            url=f"http://localhost:5173?fitbit_connected=true&user_id={user_id}",
            status_code=302
        )
        
    except Exception as e:
        # Redirect to frontend with error message
        return RedirectResponse(
            url=f"http://localhost:5173?fitbit_error={str(e)}",
            status_code=302
        )

@app.post("/api/auth/fitbit/disconnect")
def disconnect_fitbit(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Disconnect Fitbit account"""
    try:
        FitbitOAuth.disconnect_fitbit(db, current_user.id)
        return {"message": "Fitbit account disconnected successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/auth/fitbit/status")
def fitbit_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Check Fitbit connection status"""
    is_connected = FitbitOAuth.is_fitbit_connected(db, current_user.id)
    
    if is_connected:
        fitbit_account = db.query(models.FitbitAccount).filter(models.FitbitAccount.user_id == current_user.id).first()
        available_dates = FitbitAPI.get_available_dates(db, current_user.id)
        
        return {
            "connected": True,
            "fitbit_user_id": fitbit_account.fitbit_user_id,
            "connected_at": fitbit_account.created_at.isoformat(),
            "available_dates": [d.isoformat() for d in available_dates]
        }
    else:
        return {"connected": False}

# Fitbit Data Routes
@app.get("/api/fitbit/sleep/{target_date}")
def get_fitbit_sleep_data(
    target_date: date,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Get Fitbit sleep data for a specific date"""
    try:
        sleep_summary = FitbitAPI.get_sleep_summary(db, current_user.id, target_date)
        return sleep_summary
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/fitbit/sleep/range/{start_date}/{end_date}")
def get_fitbit_sleep_range(
    start_date: date,
    end_date: date,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Get Fitbit sleep data for a date range"""
    try:
        range_data = FitbitAPI.sync_sleep_data_range(db, current_user.id, start_date, end_date)
        return range_data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/fitbit/sync")
def sync_fitbit_data(
    target_date: Optional[date] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Manually sync Fitbit data"""
    try:
        if target_date:
            # Sync specific date
            sleep_data = FitbitAPI.sync_sleep_data(db, current_user.id, target_date)
            return {"message": f"Synced data for {target_date.isoformat()}", "data": sleep_data}
        else:
            # Sync last 7 days by default
            end_date = date.today()
            start_date = end_date - timedelta(days=7)
            range_data = FitbitAPI.sync_sleep_data_range(db, current_user.id, start_date, end_date)
            return {"message": f"Synced data from {start_date.isoformat()} to {end_date.isoformat()}", "data": range_data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
