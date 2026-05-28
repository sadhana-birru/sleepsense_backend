from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from .models import FitbitSleepData
from .fitbit_api import FitbitAPI

class DataMerger:
    @staticmethod
    def merge_sleep_data(user_data: Dict[str, Any], fitbit_data: Optional[Dict[str, Any]], target_date: date) -> Dict[str, Any]:
        """
        Merge user manual data with Fitbit data based on priority rules.
        Priority: Manual entry > Fitbit data > Default values
        """
        merged_data = {}
        
        # Start with Fitbit data as base if available
        if fitbit_data:
            merged_data.update(DataMerger._format_fitbit_for_form(fitbit_data))
        
        # Override with user manual entries (highest priority)
        if user_data:
            merged_data.update(user_data)
        
        # Add metadata about data sources
        merged_data['_metadata'] = {
            'date': target_date.isoformat(),
            'fitbit_available': bool(fitbit_data),
            'manual_entry': bool(user_data),
            'data_sources': DataMerger._get_field_sources(user_data, fitbit_data),
            'merged_at': (datetime.utcnow() + timedelta(hours=5, minutes=30)).isoformat()
        }
        
        return merged_data
    
    @staticmethod
    def _format_fitbit_for_form(fitbit_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Fitbit data format to form data format"""
        if not fitbit_data:
            return {}
        
        formatted = {}
        
        # Map Fitbit fields to form fields
        if 'total_minutes_asleep' in fitbit_data:
            formatted['sleep_duration'] = round(fitbit_data['total_minutes_asleep'] / 60, 1)
        
        if 'sleep_stages' in fitbit_data:
            stages = fitbit_data['sleep_stages']
            if 'wake' in stages:
                formatted['wake_count'] = max(1, round(stages['wake'] / 15))  # Estimate wake count
            if 'deep' in stages:
                formatted['deep_sleep_percent'] = round((stages['deep'] / fitbit_data['total_minutes_asleep']) * 100)
            if 'rem' in stages:
                formatted['rem_sleep_percent'] = round((stages['rem'] / fitbit_data['total_minutes_asleep']) * 100)
        
        if 'sleep_efficiency' in fitbit_data:
            formatted['sleep_efficiency'] = fitbit_data['sleep_efficiency']
        
        # Convert sleep times to minutes since midnight
        if 'sleep_start_time' in fitbit_data:
            start_time = datetime.fromisoformat(fitbit_data['sleep_start_time'].replace('Z', '+00:00'))
            formatted['bedtime_num'] = start_time.hour * 60 + start_time.minute
        
        if 'sleep_end_time' in fitbit_data:
            end_time = datetime.fromisoformat(fitbit_data['sleep_end_time'].replace('Z', '+00:00'))
            formatted['waketime_num'] = end_time.hour * 60 + end_time.minute
        
        # Set smartwatch data flag
        formatted['has_smartwatch'] = True
        
        return formatted
    
    @staticmethod
    def _get_field_sources(user_data: Dict[str, Any], fitbit_data: Dict[str, Any]) -> Dict[str, str]:
        """Determine the source of each field"""
        sources = {}
        
        # Define which fields to track
        trackable_fields = [
            'sleep_duration', 'sleep_latency', 'wake_count', 
            'bedtime_num', 'waketime_num', 'deep_sleep_percent',
            'rem_sleep_percent', 'sleep_efficiency'
        ]
        
        for field in trackable_fields:
            if user_data and field in user_data:
                sources[field] = 'manual'
            elif fitbit_data and DataMerger._field_in_fitbit_data(field, fitbit_data):
                sources[field] = 'fitbit'
            else:
                sources[field] = 'default'
        
        return sources
    
    @staticmethod
    def _field_in_fitbit_data(field: str, fitbit_data: Dict[str, Any]) -> bool:
        """Check if a field is available in Fitbit data"""
        formatted = DataMerger._format_fitbit_for_form(fitbit_data)
        return field in formatted and formatted[field] is not None
    
    @staticmethod
    def get_merged_data_for_analysis(db: Session, user_id: int, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get merged data for analysis based on form data source preference
        """
        metadata = form_data.get('metadata', {})
        data_source = metadata.get('dataSource', 'manual')
        target_date = date.today()
        
        # Get Fitbit data if needed
        fitbit_data = None
        if data_source in ['fitbit', 'mixed']:
            try:
                fitbit_data = FitbitAPI.get_sleep_summary(db, user_id, target_date)
            except Exception:
                fitbit_data = None
        
        # Extract user biometric data from form
        user_biometrics = form_data.get('biometrics', {})
        user_smartwatch = form_data.get('smartwatch', {})
        
        # Combine user data
        user_data = {**user_biometrics, **user_smartwatch}
        
        # Merge data based on source
        if data_source == 'manual':
            return user_data
        elif data_source == 'fitbit' and fitbit_data:
            merged = DataMerger.merge_sleep_data({}, fitbit_data, target_date)
            return {k: v for k, v in merged.items() if not k.startswith('_')}
        elif data_source == 'mixed':
            merged = DataMerger.merge_sleep_data(user_data, fitbit_data, target_date)
            return {k: v for k, v in merged.items() if not k.startswith('_')}
        else:
            return user_data
    
    @staticmethod
    def create_data_source_report(db: Session, user_id: int, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a report showing data sources and merging information
        """
        metadata = form_data.get('metadata', {})
        data_source = metadata.get('dataSource', 'manual')
        target_date = date.today()
        
        # Get Fitbit data availability
        fitbit_available = False
        if data_source in ['fitbit', 'mixed']:
            try:
                fitbit_data = FitbitAPI.get_sleep_summary(db, user_id, target_date)
                fitbit_available = fitbit_data is not None
            except Exception:
                fitbit_available = False
        
        return {
            'data_source': data_source,
            'fitbit_available': fitbit_available,
            'manual_entry_used': data_source in ['manual', 'mixed'],
            'fitbit_data_used': data_source in ['fitbit', 'mixed'] and fitbit_available,
            'merging_applied': data_source == 'mixed',
            'date': target_date.isoformat()
        }
