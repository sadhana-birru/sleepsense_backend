import sys
import os
sys.path.append('.')
from app.auth import create_access_token
from app.database import SessionLocal
from app.models import User
db = SessionLocal()
user = db.query(User).first()
if user:
    token = create_access_token(data={"sub": user.email})
    print(token)
else:
    print("No users found")
