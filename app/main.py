
# from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import RedirectResponse
# from fastapi.security import OAuth2PasswordBearer

# from contextlib import asynccontextmanager
# from dotenv import load_dotenv

# import os
# import json
# import tempfile
# from datetime import date, timedelta
# from typing import Optional

# from sqlalchemy.orm import Session

# # Load env FIRST
# load_dotenv()

# GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
# if GOOGLE_CLIENT_ID:
#     print(f"GOOGLE_CLIENT_ID loaded: {GOOGLE_CLIENT_ID[:5]}...{GOOGLE_CLIENT_ID[-5:]}")
# else:
#     print("WARNING: GOOGLE_CLIENT_ID not found!")

# # Local imports (keep here but safe)
# from . import models, database, auth
# from .schemas import UserCreate, UserLogin, Token, GoogleLoginRequest
# from .api import generate_report_logic
# from .fitbit_auth import FitbitOAuth
# from .fitbit_api import FitbitAPI
# from .data_merger import DataMerger

# from google.oauth2 import id_token
# from google.auth.transport import requests as google_requests


# # -------------------------
# # LIFESPAN (FIXED STARTUP)
# # -------------------------
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     print("SleepSense AI Backend starting...")

#     # SAFE DB INIT (moved here from global scope)
#     models.Base.metadata.create_all(bind=database.engine)

#     yield

#     print("Shutting down...")


# # -------------------------
# # FASTAPI APP (ONLY ONE)
# # -------------------------
# app = FastAPI(
#     title="SleepSense AI API",
#     lifespan=lifespan
# )

# # CORS
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


# # -------------------------
# # AUTH HELPERS
# # -------------------------
# def get_current_user(
#     token: str = Depends(oauth2_scheme),
#     db: Session = Depends(database.get_db)
# ):
#     from jose import jwt

#     credentials_exception = HTTPException(
#         status_code=401,
#         detail="Could not validate credentials"
#     )

#     try:
#         payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
#         email = payload.get("sub")
#         if email is None:
#             raise credentials_exception
#     except Exception:
#         raise credentials_exception

#     user = db.query(models.User).filter(models.User.email == email).first()
#     if user is None:
#         raise credentials_exception

#     return user


# # -------------------------
# # ROOT
# # -------------------------
# @app.get("/")
# def root():
#     return {"status": "SleepSense AI Backend Running"}


# # -------------------------
# # AUTH ROUTES
# # -------------------------
# @app.post("/api/register", response_model=Token)
# def register_user(user: UserCreate, db: Session = Depends(database.get_db)):
#     db_user = db.query(models.User).filter(models.User.email == user.email).first()
#     if db_user:
#         raise HTTPException(status_code=400, detail="Email already registered")

#     hashed_password = auth.get_password_hash(user.password)

#     new_user = models.User(
#         name=user.name,
#         email=user.email,
#         hashed_password=hashed_password,
#         age=user.age
#     )

#     db.add(new_user)
#     db.commit()
#     db.refresh(new_user)

#     access_token = auth.create_access_token(data={"sub": new_user.email})

#     return {
#         "access_token": access_token,
#         "token_type": "bearer",
#         "name": new_user.name,
#         "email": new_user.email
#     }


# @app.post("/api/login", response_model=Token)
# def login_user(user: UserLogin, db: Session = Depends(database.get_db)):
#     db_user = db.query(models.User).filter(models.User.email == user.email).first()

#     if not db_user or not auth.verify_password(user.password, db_user.hashed_password):
#         raise HTTPException(status_code=401, detail="Incorrect email or password")

#     access_token = auth.create_access_token(data={"sub": db_user.email})

#     return {
#         "access_token": access_token,
#         "token_type": "bearer",
#         "name": db_user.name,
#         "email": db_user.email
#     }


# # -------------------------
# # GOOGLE LOGIN
# # -------------------------
# @app.post("/api/auth/google", response_model=Token)
# def google_auth(request: GoogleLoginRequest, db: Session = Depends(database.get_db)):
#     try:
#         idinfo = id_token.verify_oauth2_token(
#             request.credential,
#             google_requests.Request(),
#             GOOGLE_CLIENT_ID
#         )

#         email = idinfo["email"]
#         name = idinfo.get("name", email.split("@")[0])

#         db_user = db.query(models.User).filter(models.User.email == email).first()

#         if not db_user:
#             db_user = models.User(
#                 name=name,
#                 email=email,
#                 hashed_password=auth.get_password_hash(os.urandom(24).hex()),
#                 age=25
#             )
#             db.add(db_user)
#             db.commit()
#             db.refresh(db_user)

#         access_token = auth.create_access_token(data={"sub": db_user.email})

#         return {
#             "access_token": access_token,
#             "token_type": "bearer",
#             "name": db_user.name,
#             "email": db_user.email
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # -------------------------
# # ANALYZE
# # -------------------------
# @app.post("/api/analyze")
# async def analyze_data(
#     data: str = Form(...),
#     audio: UploadFile = File(None),
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(database.get_db)
# ):
#     try:
#         parsed_data = json.loads(data)

#         merged_data = DataMerger.get_merged_data_for_analysis(
#             db, current_user.id, parsed_data
#         )

#         user_input = {
#             **parsed_data.get("demographics", {}),
#             **merged_data
#         }

#         smartwatch = parsed_data.get("smartwatch", {})
#         if smartwatch.get("has_smartwatch"):
#             user_input["deep_sleep_percent"] = smartwatch.get("deep_sleep_percent")
#             user_input["rem_sleep_percent"] = smartwatch.get("rem_sleep_percent")
#             user_input["sleep_efficiency"] = smartwatch.get("sleep_efficiency")

#         text_message = parsed_data.get("text_message", "")

#         audio_path = None
#         if audio:
#             temp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
#             temp.write(await audio.read())
#             temp.close()
#             audio_path = temp.name

#         report = generate_report_logic(user_input, text_message, audio_path)

#         # cleanup
#         if audio_path and os.path.exists(audio_path):
#             os.remove(audio_path)

#         return report

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # -------------------------
# # HISTORY ROUTE
# # -------------------------
# @app.get("/api/history")
# def get_user_history(current_user: models.User = Depends(get_current_user), db: Session = Depends(database.get_db)):
#     reports = db.query(models.Report).filter(models.Report.user_id == current_user.id).order_by(models.Report.created_at.desc()).all()
    
#     formatted_reports = []
#     for r in reports:
#          formatted_reports.append({
#              "id": r.id,
#              "created_at": r.created_at.isoformat(),
#              "physical_score": r.physical_score,
#              "mental_score": r.mental_score,
#              "vocal_score": r.vocal_score,
#              "overall_score": r.overall_score,
#              "status": r.status,
#              "advice": r.advice
#          })
#     return formatted_reports

# # -------------------------
# # FITBIT ROUTES
# # -------------------------
# @app.get("/api/auth/fitbit/connect")
# def connect_fitbit(current_user: models.User = Depends(get_current_user)):
#     return {"auth_url": FitbitOAuth.get_authorization_url(current_user.id)}

# @app.get("/api/auth/fitbit/callback")
# def fitbit_callback(
#     code: str,
#     state: Optional[str] = None,
#     db: Session = Depends(database.get_db)
# ):
#     """Handle Fitbit OAuth callback"""
#     if not state:
#         raise HTTPException(
#             status_code=400,
#             detail="Missing state parameter (user session lost)"
#         )

#     try:
#         user_id = int(state) if state else None
        
#         # Verify user exists
#         user = db.query(models.User).filter(models.User.id == user_id).first()
#         if not user:
#             raise HTTPException(
#                 status_code=404,
#                 detail="User not found"
#             )
        
#         # Exchange authorization code for tokens
#         token_data = FitbitOAuth.exchange_code_for_tokens(code)
        
#         # Save Fitbit account information
#         fitbit_account = FitbitOAuth.save_fitbit_account(
#             db, user_id, token_data
#         )

#         # Redirect to frontend with success message
#         return RedirectResponse(
#             url=f"http://localhost:5173?fitbit_connected=true&user_id={user_id}",
#             status_code=302
#         )
        
#     except Exception as e:
#         # Redirect to frontend with error message
#         return RedirectResponse(
#             url=f"http://localhost:5173?fitbit_error={str(e)}",
#             status_code=302
#         )

# @app.post("/api/auth/fitbit/disconnect")
# def disconnect_fitbit(
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(database.get_db)
# ):
#     """Disconnect Fitbit account"""
#     try:
#         FitbitOAuth.disconnect_fitbit(db, current_user.id)
#         return {"message": "Fitbit account disconnected successfully"}
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

# @app.get("/api/auth/fitbit/status")
# def fitbit_status(
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(database.get_db)
# ):
#     """Check Fitbit connection status"""
#     is_connected = FitbitOAuth.is_fitbit_connected(db, current_user.id)
    
#     if is_connected:
#         fitbit_account = db.query(models.FitbitAccount).filter(models.FitbitAccount.user_id == current_user.id).first()
#         available_dates = FitbitAPI.get_available_dates(db, current_user.id)
        
#         return {
#             "connected": True,
#             "fitbit_user_id": fitbit_account.fitbit_user_id,
#             "connected_at": fitbit_account.created_at.isoformat(),
#             "available_dates": [d.isoformat() for d in available_dates]
#         }
#     else:
#         return {"connected": False}

# # Fitbit Data Routes
# @app.get("/api/fitbit/sleep/{target_date}")
# def get_fitbit_sleep_data(
#     target_date: date,
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(database.get_db)
# ):
#     """Get Fitbit sleep data for a specific date"""
#     try:
#         sleep_summary = FitbitAPI.get_sleep_summary(db, current_user.id, target_date)
#         return sleep_summary
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

# @app.get("/api/fitbit/sleep/range/{start_date}/{end_date}")
# def get_fitbit_sleep_range(
#     start_date: date,
#     end_date: date,
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(database.get_db)
# ):
#     """Get Fitbit sleep data for a date range"""
#     try:
#         range_data = FitbitAPI.sync_sleep_data_range(db, current_user.id, start_date, end_date)
#         return range_data
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

# @app.post("/api/fitbit/sync")
# def sync_fitbit_data(
#     target_date: Optional[date] = None,
#     current_user: models.User = Depends(get_current_user),
#     db: Session = Depends(database.get_db)
# ):
#     """Manually sync Fitbit data"""
#     try:
#         if target_date:
#             # Sync specific date
#             sleep_data = FitbitAPI.sync_sleep_data(db, current_user.id, target_date)
#             return {"message": f"Synced data for {target_date.isoformat()}", "data": sleep_data}
#         else:
#             # Sync last 7 days by default
#             end_date = date.today()
#             start_date = end_date - timedelta(days=7)
#             range_data = FitbitAPI.sync_sleep_data_range(db, current_user.id, start_date, end_date)
#             return {"message": f"Synced data from {start_date.isoformat()} to {end_date.isoformat()}", "data": range_data}
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

import os
import json
import tempfile
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from sqlalchemy.orm import Session

# Load env FIRST
load_dotenv()

# -------------------------
# ENV VARIABLES
# -------------------------
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
FRONTEND_URL = os.getenv("FRONTEND_URL")

if GOOGLE_CLIENT_ID:
    print(f"GOOGLE_CLIENT_ID loaded: {GOOGLE_CLIENT_ID[:5]}...{GOOGLE_CLIENT_ID[-5:]}")
else:
    print("WARNING: GOOGLE_CLIENT_ID not found!")

if not FRONTEND_URL:
    print("WARNING: FRONTEND_URL not set in environment variables!")

# -------------------------
# LOCAL IMPORTS
# -------------------------
from . import models, database, auth
from .schemas import UserCreate, UserLogin, Token, GoogleLoginRequest
from .api import generate_report_logic
from .fitbit_auth import FitbitOAuth
from .fitbit_api import FitbitAPI
from .data_merger import DataMerger

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests


# -------------------------
# LIFESPAN
# -------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("SleepSense AI Backend starting...")

    models.Base.metadata.create_all(bind=database.engine)

    yield

    print("Shutting down...")


# -------------------------
# FASTAPI APP
# -------------------------
app = FastAPI(
    title="SleepSense AI API",
    lifespan=lifespan
)

# -------------------------
# CORS (UPDATED FOR VERCEL)
# -------------------------
origins = []

if FRONTEND_URL:
    origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


# -------------------------
# AUTH HELPERS
# -------------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db)
):
    from jose import jwt

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials"
    )

    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception

    return user


# -------------------------
# ROOT
# -------------------------
@app.get("/")
def root():
    return {"status": "SleepSense AI Backend Running"}


# -------------------------
# AUTH ROUTES
# -------------------------
@app.post("/api/register", response_model=Token)
def register_user(user: UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()

    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = auth.get_password_hash(user.password)

    new_user = models.User(
        name=user.name,
        email=user.email,
        hashed_password=hashed_password,
        age=user.age
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = auth.create_access_token(data={"sub": new_user.email})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "name": new_user.name,
        "email": new_user.email
    }


@app.post("/api/login", response_model=Token)
def login_user(user: UserLogin, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()

    if not db_user or not auth.verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = auth.create_access_token(data={"sub": db_user.email})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "name": db_user.name,
        "email": db_user.email
    }


# -------------------------
# GOOGLE LOGIN
# -------------------------
@app.post("/api/auth/google", response_model=Token)
def google_auth(request: GoogleLoginRequest, db: Session = Depends(database.get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            request.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )

        email = idinfo["email"]
        name = idinfo.get("name", email.split("@")[0])

        db_user = db.query(models.User).filter(models.User.email == email).first()

        if not db_user:
            db_user = models.User(
                name=name,
                email=email,
                hashed_password=auth.get_password_hash(os.urandom(24).hex()),
                age=25
            )
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

        access_token = auth.create_access_token(data={"sub": db_user.email})

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "name": db_user.name,
            "email": db_user.email
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# ANALYZE (MAIN AI ENDPOINT)
# -------------------------
@app.post("/api/analyze")
async def analyze_data(
    data: str = Form(...),
    audio: UploadFile = File(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    try:
        parsed_data = json.loads(data)

        merged_data = DataMerger.get_merged_data_for_analysis(
            db, current_user.id, parsed_data
        )

        user_input = {
            **parsed_data.get("demographics", {}),
            **merged_data
        }

        smartwatch = parsed_data.get("smartwatch", {})
        if smartwatch.get("has_smartwatch"):
            user_input["deep_sleep_percent"] = smartwatch.get("deep_sleep_percent")
            user_input["rem_sleep_percent"] = smartwatch.get("rem_sleep_percent")
            user_input["sleep_efficiency"] = smartwatch.get("sleep_efficiency")

        text_message = parsed_data.get("text_message", "")

        audio_path = None
        if audio:
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            temp.write(await audio.read())
            temp.close()
            audio_path = temp.name

        # CALL YOUR HF-BASED PIPELINE
        report = generate_report_logic(user_input, text_message, audio_path)

        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

        return report

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# HISTORY
# -------------------------
@app.get("/api/history")
def get_user_history(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    reports = db.query(models.Report).filter(
        models.Report.user_id == current_user.id
    ).order_by(models.Report.created_at.desc()).all()

    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "physical_score": r.physical_score,
            "mental_score": r.mental_score,
            "vocal_score": r.vocal_score,
            "overall_score": r.overall_score,
            "status": r.status,
            "advice": r.advice
        }
        for r in reports
    ]


# -------------------------
# FITBIT REDIRECT FIXED
# -------------------------
@app.get("/api/auth/fitbit/callback")
def fitbit_callback(
    code: str,
    state: Optional[str] = None,
    db: Session = Depends(database.get_db)
):
    try:
        user_id = int(state) if state else None

        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        token_data = FitbitOAuth.exchange_code_for_tokens(code)

        FitbitOAuth.save_fitbit_account(db, user_id, token_data)

        frontend = FRONTEND_URL or "http://localhost:5173"
        return RedirectResponse(
            url=f"{frontend}?fitbit_connected=true&user_id={user_id}",
            status_code=302
        )

    except Exception as e:
        return RedirectResponse(
            url=f"{FRONTEND_URL}?fitbit_error={str(e)}",
            status_code=302
        )