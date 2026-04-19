from motor.motor_asyncio import AsyncIOMotorClient
import os

# Default to local MongoDB, can be overridden by environment variable
MONGO_DETAILS = os.getenv("MONGODB_URL", "mongodb://localhost:27017")

client = AsyncIOMotorClient(MONGO_DETAILS)
database = client.kocaeli_haber_haritasi
news_collection = database.get_collection("news")
