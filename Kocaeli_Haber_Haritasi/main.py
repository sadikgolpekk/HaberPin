import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from routes.news import router as news_router
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Kocaeli Haber Haritası API",
    description="Backend API for Kocaeli news map application with MongoDB",
    version="1.0.0"
)

# Mount static files (css, js)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates for HTML rendering
templates = Jinja2Templates(directory="static")

# Include the news router under /api/news
app.include_router(news_router, prefix="/api/news", tags=["news"])

@app.get("/")
async def serve_frontend(request: Request):
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    return templates.TemplateResponse("index.html", {"request": request, "api_key": api_key})
