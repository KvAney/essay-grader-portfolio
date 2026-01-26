import motor
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

# 1. Initialize Client
client = AsyncIOMotorClient(settings.MONGO_URL)

# 2. Get the Database (Use this for Health Checks)
db = client.get_database("essayEval") 

# 3. Get the Collection (Use this for Insert/Find)
essay_collection = db.get_collection("essay_collection")