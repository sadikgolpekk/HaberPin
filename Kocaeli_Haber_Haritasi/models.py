from pydantic import BaseModel, Field
from typing import Literal, List, Optional
from datetime import datetime

class NewsModel(BaseModel):
    haber_turu: Literal[
        'Trafik Kazası', 
        'Yangın', 
        'Elektrik Kesintisi', 
        'Hırsızlık', 
        'Kültürel Etkinlikler'
    ] = Field(..., description="Type of the news event")
    baslik: str = Field(..., description="Title of the news")
    icerik: str = Field(..., description="Content/description of the news")
    konum_metin: str = Field(..., description="Textual description of the location")
    enlem: float = Field(..., description="Latitude coordinate")
    boylam: float = Field(..., description="Longitude coordinate")
    yayin_tarihi: datetime = Field(..., description="Publication date and time")
    kaynak_site: str = Field(..., description="Primary source website")
    link: str = Field(..., description="URL link to the original news")
    kaynaklar: Optional[List[str]] = Field(default=None, description="All sources that published this news")

    model_config = {
        "json_schema_extra": {
            "example": {
                "haber_turu": "Trafik Kazası",
                "baslik": "D100 Karayolunda Zincirleme Kaza",
                "icerik": "Kocaeli D100 karayolunda 3 aracın karıştığı kaza meydana geldi.",
                "konum_metin": "İzmit, Kocaeli",
                "enlem": 40.7654,
                "boylam": 29.9408,
                "yayin_tarihi": "2026-03-10T10:00:00",
                "kaynak_site": "Kocaeli Gündem",
                "link": "https://example.com/haber1"
            }
        }
    }
