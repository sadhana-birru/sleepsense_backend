from pydantic import BaseModel, Field
from typing import Optional

class DemographicData(BaseModel):
    age: int = Field(..., ge=15, le=120, description="Age of the user (15-120)")
    gender: int = Field(..., ge=0, le=2, description="0=Female, 1=Male, 2=Other")
    occupation: int = Field(..., ge=0, le=10, description="Occupation code (0-10)")

class BiometricData(BaseModel):
    work_hours: float = Field(..., ge=0, le=24, description="Daily work hours")
    sleep_duration: float = Field(..., ge=0, le=24, description="Total sleep hours")
    sleep_latency: int = Field(..., ge=0, le=300, description="Minutes to fall asleep")
    wake_count: int = Field(..., ge=0, le=20, description="Number of times woken up")
    bedtime_num: int = Field(..., ge=0, le=1440, description="Bedtime in minutes from midnight")
    waketime_num: int = Field(..., ge=0, le=1440, description="Waketime in minutes from midnight")
    stress_level_num: int = Field(..., ge=0, le=2, description="0=Low, 1=Med, 2=High")

class SmartwatchData(BaseModel):
    has_smartwatch: bool = Field(False, description="Whether advanced smartwatch data is provided")
    deep_sleep_percent: Optional[float] = Field(None, ge=0, le=100)
    rem_sleep_percent: Optional[float] = Field(None, ge=0, le=100)
    sleep_efficiency: Optional[float] = Field(None, ge=0, le=100)

class ReportRequest(BaseModel):
    demographics: DemographicData
    biometrics: BiometricData
    smartwatch: SmartwatchData
    text_message: str = Field(..., min_length=1, description="Mental check-in text")
    # Note: Audio file is handled via Form/File upload in FastAPI, so it's not strictly in this JSON body if using multipart/form-data.
    # We will likely accept JSON strings + a FileUpload in the endpoint.

class UserCreate(BaseModel):
    name: str = Field(..., min_length=2)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=6)
    age: int = Field(..., ge=15, le=120)

class UserLogin(BaseModel):
    email: str
    password: str

class GoogleLoginRequest(BaseModel):
    credential: str

class Token(BaseModel):
    access_token: str
    token_type: str
    name: Optional[str] = None
    email: Optional[str] = None

class ReportResponse(BaseModel):
    id: int
    created_at: str
    physical_score: float
    mental_score: float
    vocal_score: float
    overall_score: float
    status: str
    advice: str
