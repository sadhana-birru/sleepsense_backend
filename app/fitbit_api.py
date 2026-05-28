import requests
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from .models import FitbitSleepData
from .fitbit_auth import FitbitOAuth

class FitbitAPI:
    BASE_URL = "https://api.fitbit.com/1.2/user/-"
    
    @staticmethod
    def get_sleep_data(access_token: str, target_date: date) -> Optional[Dict[str, Any]]:
        """Fetch sleep data for a specific date using the correct endpoint"""
        url = f"{FitbitAPI.BASE_URL}/sleep/date/{target_date.strftime('%Y-%m-%d')}.json"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Check if sleep data exists
            if "sleep" not in data or not data["sleep"]:
                return None
                
            return data
            
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch sleep data: {str(e)}"
            )
    
    @staticmethod
    def get_sleep_data_range(access_token: str, start_date: date, end_date: date) -> Dict[str, Any]:
        """Fetch sleep data for a date range using version 1.2"""
        url = f"{FitbitAPI.BASE_URL}/sleep/date/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}.json"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
            
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch sleep data range: {str(e)}"
            )
    
    @staticmethod
    def save_sleep_data(db: Session, user_id: int, sleep_data: Dict[str, Any], target_date: date):
        """Save sleep data to database"""
        # Check if data already exists for this date
        existing_data = db.query(FitbitSleepData).filter(
            FitbitSleepData.user_id == user_id,
            FitbitSleepData.date == target_date
        ).first()
        
        # IST Helper
        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        
        if existing_data:
            # Update existing record
            existing_data.sleep_data = sleep_data
            existing_data.created_at = ist_now
        else:
            # Create new record
            fitbit_sleep_data = FitbitSleepData(
                user_id=user_id,
                date=target_date,
                sleep_data=sleep_data,
                created_at=ist_now
            )
            db.add(fitbit_sleep_data)
        
        db.commit()
        return True
    
    @staticmethod
    def get_cached_sleep_data(db: Session, user_id: int, target_date: date) -> Optional[Dict[str, Any]]:
        """Get cached sleep data from database"""
        cached_data = db.query(FitbitSleepData).filter(
            FitbitSleepData.user_id == user_id,
            FitbitSleepData.date == target_date
        ).first()
        
        if cached_data:
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            # Check if data is fresh (less than 24 hours old)
            if ist_now - cached_data.created_at < timedelta(hours=24):
                return cached_data.sleep_data
        
        return None
    
    @staticmethod
    def sync_sleep_data(db: Session, user_id: int, target_date: date) -> Optional[Dict[str, Any]]:
        """Sync sleep data from Fitbit API"""
        # Get valid access token
        access_token = FitbitOAuth.get_valid_access_token(db, user_id)
        
        # Fetch fresh data from Fitbit
        sleep_data = FitbitAPI.get_sleep_data(access_token, target_date)
        
        if sleep_data:
            # Save to database
            FitbitAPI.save_sleep_data(db, user_id, sleep_data, target_date)
            return sleep_data
        
        return None
    
    @staticmethod
    def sync_sleep_data_range(db: Session, user_id: int, start_date: date, end_date: date) -> Dict[str, Any]:
        """Sync sleep data for a date range"""
        # Get valid access token
        access_token = FitbitOAuth.get_valid_access_token(db, user_id)
        
        # Fetch fresh data from Fitbit
        range_data = FitbitAPI.get_sleep_data_range(access_token, start_date, end_date)
        
        # Save each day's data
        if "sleep" in range_data:
            for sleep_entry in range_data["sleep"]:
                sleep_date = datetime.strptime(sleep_entry["dateOfSleep"], "%Y-%m-%d").date()
                FitbitAPI.save_sleep_data(db, user_id, sleep_entry, sleep_date)
        
        return range_data
    
    @staticmethod
    def get_sleep_summary(db: Session, user_id: int, target_date: date) -> Optional[Dict[str, Any]]:
        """Get processed sleep summary for a specific date"""
        # Try to get cached data first
        cached_data = FitbitAPI.get_cached_sleep_data(db, user_id, target_date)
        
        if cached_data:
            return FitbitAPI._process_sleep_data(cached_data)
        
        # If no cached data, sync from Fitbit
        fresh_data = FitbitAPI.sync_sleep_data(db, user_id, target_date)
        
        if fresh_data:
            return FitbitAPI._process_sleep_data(fresh_data)
        
        return None
    
    @staticmethod
    def _process_sleep_data(sleep_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw Fitbit sleep data into a standardized format"""
        if not sleep_data or "sleep" not in sleep_data or not sleep_data["sleep"]:
            return None
        
        # Get the main sleep entry (usually the first one)
        main_sleep = sleep_data["sleep"][0]
        
        # Extract sleep stages from levels.summary if available, otherwise from main entry
        sleep_stages = {
            "deep": 0,
            "light": 0, 
            "rem": 0,
            "wake": 0
        }
        
        if "levels" in main_sleep and "summary" in main_sleep["levels"]:
            stages_summary = main_sleep["levels"]["summary"]
            sleep_stages = {
                "deep": stages_summary.get("deep", {}).get("minutes", 0),
                "light": stages_summary.get("light", {}).get("minutes", 0),
                "rem": stages_summary.get("rem", {}).get("minutes", 0),
                "wake": stages_summary.get("wake", {}).get("minutes", 0)
            }
        
        # Extract key metrics
        processed_data = {
            "date": main_sleep.get("dateOfSleep"),
            "total_minutes_asleep": main_sleep.get("minutesAsleep", 0),
            "total_time_in_bed": main_sleep.get("timeInBed", 0),
            "sleep_efficiency": main_sleep.get("efficiency", 0),
            "sleep_stages": sleep_stages,
            "sleep_start_time": main_sleep.get("startTime"),
            "sleep_end_time": main_sleep.get("endTime"),
            "is_main_sleep": main_sleep.get("isMainSleep", True),
            "data_source": "fitbit"
        }
        
        # Add top-level summary if available
        if "summary" in sleep_data:
            summary = sleep_data["summary"]
            processed_data.update({
                "total_sleep_records": summary.get("totalSleepRecords", 0),
                "total_minutes_asleep_summary": summary.get("totalMinutesAsleep", 0),
                "total_sleep_time_summary": summary.get("totalTimeInBed", 0)
            })
            
            # Override sleep stages with summary data if available
            if "stages" in summary:
                summary_stages = summary["stages"]
                processed_data["sleep_stages"] = {
                    "deep": summary_stages.get("deep", 0),
                    "light": summary_stages.get("light", 0),
                    "rem": summary_stages.get("rem", 0),
                    "wake": summary_stages.get("wake", 0)
                }
        
        return processed_data
    
    @staticmethod
    def get_available_dates(db: Session, user_id: int) -> list:
        """Get list of dates for which Fitbit sleep data is available"""
        dates = db.query(FitbitSleepData.date).filter(
            FitbitSleepData.user_id == user_id
        ).order_by(FitbitSleepData.date.desc()).all()
        
        return [date_obj[0] for date_obj in dates]
    
    @staticmethod
    def delete_sleep_data(db: Session, user_id: int, target_date: date) -> bool:
        """Delete sleep data for a specific date"""
        deleted_count = db.query(FitbitSleepData).filter(
            FitbitSleepData.user_id == user_id,
            FitbitSleepData.date == target_date
        ).delete()
        
        db.commit()
        return deleted_count > 0
