from fastapi import APIRouter, HTTPException
from database import client, news_collection
from services.scraper import run_scraper

router = APIRouter()

@router.get("/test-db", response_description="Test MongoDB connection")
async def test_db_connection():
    try:
        # Ping the database to check connection
        await client.admin.command('ping')
        return {"status": "success", "message": "Successfully connected to MongoDB!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

@router.post("/scrape", response_description="Trigger web scraping from news sources")
async def scrape_news_endpoint():
    try:
        inserted_count = await run_scraper()
        return {
            "status": "success", 
            "message": f"Scraping completed. {inserted_count} new articles classified and saved.",
            "inserted": inserted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

@router.delete("/", response_description="Clear all news from database")
async def clear_news_endpoint():
    try:
        result = await news_collection.delete_many({})
        return {
            "status": "success",
            "message": f"System cleared. Deleted {result.deleted_count} old articles."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear database: {str(e)}")

@router.get("/", response_description="Get scraped news for the map")
async def get_news(
    haber_turu: str = None,
    ilce: str = None,
    tarih_baslangic: str = None,
    tarih_bitis: str = None
):
    query = {}
    
    if haber_turu:
        query["haber_turu"] = haber_turu
        
    if ilce:
        # Regex search for the district name in location text
        query["konum_metin"] = {"$regex": ilce, "$options": "i"}
        
    if tarih_baslangic or tarih_bitis:
        query["yayin_tarihi"] = {}
        from datetime import datetime, time
        if tarih_baslangic:
            query["yayin_tarihi"]["$gte"] = datetime.fromisoformat(tarih_baslangic)
        if tarih_bitis:
            # Add time 23:59:59 to include the whole day
            end_date = datetime.fromisoformat(tarih_bitis)
            end_date_full = datetime.combine(end_date.date(), time(23, 59, 59))
            query["yayin_tarihi"]["$lte"] = end_date_full
            
    try:
        # Limit to 1000 to prevent huge payloads for mapping
        news_cursor = news_collection.find(query).sort("yayin_tarihi", -1).limit(1000)
        news_list = []
        async for doc in news_cursor:
            doc["_id"] = str(doc["_id"])
            if "embedding" in doc: # Dont send huge vectors to frontend
                del doc["embedding"] 
            news_list.append(doc)
            
        return {"status": "success", "data": news_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database fetch failed: {str(e)}")
