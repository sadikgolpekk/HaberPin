import asyncio
import httpx
from bs4 import BeautifulSoup
import re
import os
from datetime import datetime, timedelta
from database import news_collection
from models import NewsModel
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from dotenv import load_dotenv

# ── Concurrency Controls ────────────────────────────────────────────────────
# Nominatim API: max 1 request/second (usage policy)
nominatim_semaphore = asyncio.Semaphore(1)
# Scraper: max 5 concurrent article requests to avoid IP bans
scraper_semaphore = asyncio.Semaphore(5)

# Load API key and init model
load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

try:
    print("Loading SentenceTransformer model... (This might take a moment on first run)")
    embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
except Exception as e:
    print(f"Warning: Could not load sentence transformer model: {e}")
    embedding_model = None


# ═══════════════════════════════════════════════════════════════════
# 1) ANAHTAR KELİME SÖZLÜĞÜ VE ÖNCELİK SIRASI
# ═══════════════════════════════════════════════════════════════════
KEYWORD_SOZLUK = {
    "Trafik Kazası": [
        "trafik kazası", "zincirleme kaza", "çarpışma", "kaza yaptı", "otomobil çarptı",
        "araç devrildi", "kamyon çarptı", "motosiklet kazası", "tır kazası", "yol kazası",
        "ölümlü kaza", "maddi hasarlı", "trafik kazasında", "feci kaza", "kafa kafaya çarpıştı",
        "bariyerlere çarptı", "takla attı", "kazada yaralandı",
        "otobanda kaza", "karayolunda kaza", "otoyolunda kaza", "kavşakta kaza",
        "araç devrildi", "tıkanıklık", "kilometrelerce kuyruk",
        "liman yolu kapandı", "yol kapandı", "trafik durdu",
    ],
    "Yangın": [
        "yangın", "alev aldı", "tutuştu", "itfaiye", "ev yandı", "fabrika yandı",
        "araç yandı", "orman yangını", "koru yangını", "yangın çıktı", "alevler",
        "yangına müdahale", "kül oldu", "yangın söndürme", "alevlere teslim",
        "dumandan etkilendi", "yangında hayatını kaybetti",
    ],
    "Elektrik Kesintisi": [
        "elektrik kesintisi", "elektrik arızası", "elektrik verilmeyecek",
        "elektrik kesildi", "elektrik yok", "dedaş", "trafo arızası",
        "enerji kesintisi", "enerji arızası", "planlı kesinti", "sedaş",
        "elektriksiz kalacak", "trafo patladı",
    ],
    "Hırsızlık": [
        "hırsızlık", "çalındı", "soygun", "kapkaç", "gasp", "hırsız",
        "araç çalıntı", "hırsızlık şüphelisi", "evden hırsızlık", "işyerinden hırsızlık",
        "cüzdan çalındı", "silahlı soygun", "soyguncu", "hırsızlık yapan",
        "çaldığı", "gaspçı", "kapkaççı", "kablo çaldı", "çalan hırsız",
    ],
    "Kültürel Etkinlikler": [
        "konser", "festival", "sergi", "tiyatro", "sinema", "müze",
        "kültür merkezi", "sempozyum", "fuar", "kermes", "şenlik",
        "etkinlik", "gösteri", "sahne aldı", "performans sergiledi",
    ],
}

ONCELIK_SIRASI = [
    "Trafik Kazası",
    "Yangın",
    "Elektrik Kesintisi",
    "Hırsızlık",
    "Kültürel Etkinlikler",
]

# ═══════════════════════════════════════════════════════════════════
# 2) BAĞLAMSAL NEGATİF KALIPLAR  (Katman 1)
# ═══════════════════════════════════════════════════════════════════
HUKUKI_BAGLAMLAR = [
    "duruşma", "duruşması", "dava", "davası", "mahkeme", "mahkemesi",
    "soruşturma", "soruşturması", "savcılık", "savcılığı", "kovuşturma",
    "beraat", "tutuklandı", "tutuklama", "gözaltı", "gözaltına",
    "sanık", "sanığı", "müşteki", "şüpheli", "ifade verdi", "karar verildi",
    "hüküm", "ceza aldı", "ceza verildi", "temyiz", "yargıtay", "istinaf",
    "hapis", "hapis cezası", "tahliye", "serbest bırakıldı", "aklandı",
    "iddia makamı", "iddianame", "bilirkişi raporu", "keşif yapıldı",
    "yargılama", "yargılanıyor", "hakim", "hakimi", "yaşam desteği"
]

RAPOR_BAGLAMLAR = [
    "rapor", "raporu", "raporda", "raporunda",
    "istatistik", "istatistiği", "istatistikleri",
    "anma", "anma töreni", "yıldönümü", "yıl dönümü",
    "tarihi", "tarihinde yaşanan", "geçmiş yıl",
]

BAGLAMSAL_NEGATIFLER = {
    "Trafik Kazası": HUKUKI_BAGLAMLAR + RAPOR_BAGLAMLAR,
    "Yangın":        HUKUKI_BAGLAMLAR + RAPOR_BAGLAMLAR,
    "Hırsızlık":     HUKUKI_BAGLAMLAR + RAPOR_BAGLAMLAR,
    "Elektrik Kesintisi": [],
    "Kültürel Etkinlikler": [],
}

# ═══════════════════════════════════════════════════════════════════
# 3) SEMANTİK PROTOTİP CÜMLELERİ  (Katman 2)
# ═══════════════════════════════════════════════════════════════════
PROTOTIP_CUMLELER = {
    "Trafik Kazası": [
        "Otomobil ile kamyon çarpıştı, 3 kişi yaralandı",
        "D-100 karayolunda zincirleme trafik kazası meydana geldi",
        "Motosiklet sürücüsü kaza sonucu hayatını kaybetti",
        "Araç bariyerlere çarparak takla attı, sürücü hastaneye kaldırıldı",
        "Trafik kazasında 2 kişi hayatını kaybetti 5 kişi yaralandı",
        "Otobanda feci kaza 2 ölü kilometrelerce trafik kuyruğu oluştu",
        "Liman yolu kapandı araçlar saatlerce beklemek zorunda kaldı",
    ],
    "Yangın": [
        "Apartmanda çıkan yangını itfaiye ekipleri söndürdü",
        "Fabrikada başlayan yangın büyük maddi hasara yol açtı",
        "Ormanlık alanda çıkan yangına havadan ve karadan müdahale ediliyor",
        "Araç alev aldı sürücü son anda kurtuldu",
        "Evde çıkan yangında bir kişi dumandan etkilendi",
    ],
    "Elektrik Kesintisi": [
        "Planlı bakım çalışması nedeniyle elektrik kesintisi uygulanacak",
        "Trafo arızası nedeniyle mahallede saatlerce elektrik kesildi",
        "SEDAŞ duyurdu yarın bu ilçelerde elektrik verilmeyecek",
        "Fırtına sonrası elektrik hatlarında arıza meydana geldi",
        "Enerji kesintisi nedeniyle vatandaşlar mağdur oldu",
    ],
    "Hırsızlık": [
        "İş yerinden hırsızlık yapan şüpheli güvenlik kamerasına yakalandı",
        "Park halindeki araçtan hırsızlık yapıldı",
        "Kapkaççıyı vatandaşlar yakalayarak polise teslim etti",
        "Evden altın ve para çalan hırsız tutuklandı",
        "Silahlı soygun girişimi polis tarafından önlendi",
        "Kablo çalan hırsızlar suçüstü yakalandı",
    ],
    "Kültürel Etkinlikler": [
        "Kocaeli Büyükşehir Belediyesi konser düzenledi binlerce kişi katıldı",
        "Uluslararası film festivali bu hafta başlıyor",
        "Resim sergisi sanat severlerle buluştu",
        "Şehir tiyatrosu yeni sezon oyunlarını açıkladı",
        "Kültür merkezinde çocuklar için atölye çalışması yapıldı",
    ],
}

# ═══════════════════════════════════════════════════════════════════
# 4) GENEL NEGATİF (siyasi/eylem) FİLTRESİ
# ═══════════════════════════════════════════════════════════════════
SIYASI_NEGATIFLER = [
    "eylem ", "protesto", "siyaset", "hukuksuzluk",
    "yürüyüş", "miting", "seçim kampanyası", "parti kongre",
    "genel kurul", "meclis oturumu", "kanun teklifi",
]

# ── Lokasyonlar ve Kaynaklar ──────────────────────────────────────────────
DISTRICTS = {
    "İzmit": (40.7654, 29.9408),
    "Gebze": (40.8028, 29.4307),
    "Derince": (40.7570, 29.8329),
    "Darıca": (40.7736, 29.3900),
    "Gölcük": (40.7180, 29.8214),
    "Körfez": (40.7634, 29.7380),
    "Kartepe": (40.7051, 30.0163),
    "Başiskele": (40.7161, 29.9231),
    "Karamürsel": (40.6908, 29.6133),
    "Kandıra": (41.0667, 30.1500),
    "Dilovası": (40.7850, 29.5408),
    "Çayırova": (40.8242, 29.3789)
}
DEFAULT_LOCATION = ("Kocaeli", 40.8533, 29.8815)

SOURCES = [
    {"name": "Çağdaş Kocaeli", "url": "https://www.cagdaskocaeli.com.tr"},
    {"name": "Özgür Kocaeli", "url": "https://www.ozgurkocaeli.com.tr"},
    {"name": "Ses Kocaeli", "url": "https://www.seskocaeli.com"},
    {"name": "Yeni Kocaeli", "url": "https://www.yenikocaeli.com"},
    {"name": "Bizim Yaka", "url": "https://www.bizimyaka.com"}
]

# ── Şehir Dışı Haber Filtresi: Kocaeli dışındaki 80 il ─────────────────────
DIGER_ILLER = [
    "adana", "adıyaman", "afyonkarahisar", "ağrı", "aksaray", "amasya",
    "ankara", "antalya", "ardahan", "artvin", "aydın", "balıkesir",
    "bartın", "batman", "bayburt", "bilecik", "bingöl", "bitlis",
    "bolu", "burdur", "bursa", "çanakkale", "çankırı", "çorum",
    "denizli", "diyarbakır", "düzce", "edirne", "elazığ", "erzincan",
    "erzurum", "eskişehir", "gaziantep", "giresun", "gümüşhane",
    "hakkari", "hatay", "iğdır", "ısparta", "istanbul",
    "izmir", "kahramanmaraş", "karabük", "karaman", "kars", "kastamonu",
    "kayseri", "kırıkkale", "kırklareli", "kırşehir", "kilis",
    "konya", "kütahya", "malatya", "manisa", "mardin", "mersin",
    "muğla", "muş", "nevşehir", "niğde", "ordu", "osmaniye",
    "rize", "sakarya", "samsun", "siirt", "sinop", "sivas",
    "şanlıurfa", "şırnak", "tekirdağ", "tokat", "trabzon",
    "tunceli", "uşak", "van", "yalova", "yozgat", "zonguldak",
]

def clean_text(text: str) -> str:
    """Removes HTML tags, extra whitespace, and normalizes text."""
    if not text:
        return ""
    text = BeautifulSoup(text, "html.parser").get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_publish_date(soup: BeautifulSoup) -> datetime:
    """Attempts to extract the real publication date from HTML meta/time tags and JSON-LD."""
    import json
    try:
        # 1. Try application/ld+json schemas (used by Cagdas Kocaeli, Ozgur Kocaeli)
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            if not script.string: continue
            try:
                data = json.loads(script.string)
                
                # Sometime json-ld is a list, sometimes a dict
                items = data if isinstance(data, list) else [data]
                
                for item in items:
                    if isinstance(item, dict) and 'datePublished' in item:
                        # ISO format often has +03:00 which fromisoformat handles
                        dt_str = item['datePublished'].replace('Z', '+00:00')
                        return datetime.fromisoformat(dt_str)
            except:
                pass

        # 2. Common SEO meta tags
        meta_pub = soup.find('meta', property='article:published_time') or \
                   soup.find('meta', attrs={'name': 'published_time'}) or \
                   soup.find('meta', property='og:article:published_time')
        if meta_pub and meta_pub.get('content'):
            return datetime.fromisoformat(meta_pub['content'].replace('Z', '+00:00'))
            
        # 3. Standard HTML5 time tag
        time_tag = soup.find('time')
        if time_tag and time_tag.get('datetime'):
            return datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00'))
            
    except Exception as e:
        print(f"Date extraction error: {e}")
        pass
    
    # Fallback to scrape time
    return datetime.now()

# ═══════════════════════════════════════════════════════════════════
# 5) PROTOTİP EMBEDDİNG'LERİ
# ═══════════════════════════════════════════════════════════════════
_prototip_embeddingleri = {}

def _prototip_emb_getir() -> dict:
    global _prototip_embeddingleri
    if _prototip_embeddingleri:
        return _prototip_embeddingleri
    if embedding_model is None:
        return {}
    for tur, cumleler in PROTOTIP_CUMLELER.items():
        vecs = embedding_model.encode(cumleler, normalize_embeddings=True)
        ortalama = np.mean(vecs, axis=0)
        norm = np.linalg.norm(ortalama)
        if norm > 0:
            ortalama = ortalama / norm
        _prototip_embeddingleri[tur] = ortalama
    return _prototip_embeddingleri

# ═══════════════════════════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR VE ANA SINIFLANDIRMA
# ═══════════════════════════════════════════════════════════════════

def _cumlelere_bol(metin: str) -> list[str]:
    cumleler = re.split(r'[.!?\n]+', metin)
    return [c.strip() for c in cumleler if c.strip()]

def _anahtar_kelime_baglam_kontrol(cumle: str, anahtar: str, tur: str) -> bool:
    negatifler = BAGLAMSAL_NEGATIFLER.get(tur, [])
    if not negatifler:
        return False
    cumle_lower = cumle.lower()
    for negatif in negatifler:
        if negatif in cumle_lower:
            return True
    return False

# Olumsuzluk (negation) kalıpları: anahtar kelimenin yakınında geçerse o eşleşme geçersiz sayılır
OLUMSUZLUK_KALIPLARI = ["değil", "değildir", "değilmiş", "olmadı", "değildi", "yok "]

def _olumsuzluk_kontrol(cumle_lower: str, anahtar: str) -> bool:
    """Anahtar kelimenin yakınında olumsuzluk ifadesi var mı kontrol eder.
    Örn: 'bu bir kaza değil' -> True (kaza kelimesi olumsuz bağlamda)"""
    idx = cumle_lower.find(anahtar)
    if idx == -1:
        return False
    # Anahtar kelimeden sonraki 20 karaktere bak
    sonrasi = cumle_lower[idx + len(anahtar):idx + len(anahtar) + 20]
    # Anahtar kelimeden önceki 15 karaktere bak  
    oncesi = cumle_lower[max(0, idx - 15):idx]
    for kalip in OLUMSUZLUK_KALIPLARI:
        if kalip in sonrasi or kalip in oncesi:
            return True
    return False

def _keyword_skor_hesapla(baslik: str, icerik: str) -> dict[str, float]:
    skorlar = {tur: 0.0 for tur in ONCELIK_SIRASI}
    baslik_lower = baslik.lower()
    baslik_cumleleri = _cumlelere_bol(baslik)
    icerik_cumleleri = _cumlelere_bol(icerik)
    for tur in ONCELIK_SIRASI:
        for anahtar in KEYWORD_SOZLUK[tur]:
            if anahtar in baslik_lower:
                baglam_negatif = _anahtar_kelime_baglam_kontrol(baslik_lower, anahtar, tur)
                olumsuz = _olumsuzluk_kontrol(baslik_lower, anahtar)
                if not baglam_negatif and not olumsuz:
                    skorlar[tur] += 3.0
            for cumle in icerik_cumleleri:
                cumle_lower = cumle.lower()
                if anahtar in cumle_lower:
                    baglam_negatif = _anahtar_kelime_baglam_kontrol(cumle_lower, anahtar, tur)
                    olumsuz = _olumsuzluk_kontrol(cumle_lower, anahtar)
                    if not baglam_negatif and not olumsuz:
                        skorlar[tur] += 1.0
    return skorlar

def _semantik_skor_hesapla(baslik: str, icerik: str) -> dict[str, float]:
    skorlar = {tur: 0.0 for tur in ONCELIK_SIRASI}
    if embedding_model is None:
        return skorlar
    prototip_embs = _prototip_emb_getir()
    if not prototip_embs:
        return skorlar
    haber_metin = f"{baslik} {icerik[:400]}"
    try:
        haber_emb = embedding_model.encode(haber_metin, normalize_embeddings=True)
    except Exception:
        return skorlar
    for tur, prototip_emb in prototip_embs.items():
        skor = float(np.dot(haber_emb, prototip_emb))
        skorlar[tur] = max(0.0, skor)
    return skorlar

def _hukuki_baglam_yoğunluk(metin: str) -> int:
    metin_lower = metin.lower()
    return sum(1 for h in HUKUKI_BAGLAMLAR if h in metin_lower)

def classify_news(baslik: str, icerik: str) -> str | None:
    tam_metin = (baslik + " " + icerik).lower()
    negatif_sayisi = sum(1 for n in SIYASI_NEGATIFLER if n in tam_metin)
    if negatif_sayisi >= 2:
        return None

    hukuki_yogunluk = _hukuki_baglam_yoğunluk(tam_metin)
    metin_hukuki = hukuki_yogunluk >= 3

    keyword_skorlar = _keyword_skor_hesapla(baslik, icerik)
    
    # ── BAĞLAMSAL CEZA VE BAŞLIK ÖNCELİĞİ (İtfaiye Anomalisi Çözümü) ──
    baslik_lower = baslik.lower()
    kaza_kelimeleri = ["kaza", "çarpış", "şarampole", "devrildi", "zincirleme", "direksiyon hakimiyetini"]
    yangin_belirteci = ["alev", "yandı", "söndür", "kül oldu", "duman"]
    
    # Eğer kaza ihtimali varsa ve kesin yangın kelimeleri yoksa Yangın puanını sıfırla, Kazayı destekle
    # AMA: kaza kelimesi olumsuz bağlamdaysa ("kaza değil") bu desteği VERME
    kaza_olumlu = any(k in tam_metin for k in kaza_kelimeleri) and not _olumsuzluk_kontrol(tam_metin, "kaza")
    if kaza_olumlu and not any(y in tam_metin for y in yangin_belirteci):
        keyword_skorlar["Yangın"] = 0.0
        keyword_skorlar["Trafik Kazası"] += 5.0
        
    # Sadece başlığa bakılarak yapılan katı desteklemeler (negation kontrollü)
    if any(k in baslik_lower for k in ["kaza", "çarpış"]) and not _olumsuzluk_kontrol(baslik_lower, "kaza"):
        keyword_skorlar["Trafik Kazası"] += 5.0
    if any(k in baslik_lower for k in ["yangın", "alev"]):
        keyword_skorlar["Yangın"] += 5.0

    max_keyword = max(keyword_skorlar.values())

    if metin_hukuki and max_keyword < 3.0:
        return None

    semantik_skorlar = _semantik_skor_hesapla(baslik, icerik)
    
    # Semantik tarafta da hala inatla itfaiye yüzünden yangın yüksekse, aynı cezayı semantiğe de uygula
    if any(k in tam_metin for k in kaza_kelimeleri) and not any(y in tam_metin for y in yangin_belirteci):
        if "Yangın" in semantik_skorlar:
            semantik_skorlar["Yangın"] = 0.0

    if max_keyword > 0:
        keyword_norm = {tur: skor / max_keyword for tur, skor in keyword_skorlar.items()}
    else:
        keyword_norm = {tur: 0.0 for tur in ONCELIK_SIRASI}

    KEYWORD_AGIRLIK = 0.4
    SEMANTIK_AGIRLIK = 0.6

    hibrit_skorlar = {}
    for tur in ONCELIK_SIRASI:
        kw = keyword_norm.get(tur, 0.0)
        sem = semantik_skorlar.get(tur, 0.0)
        hibrit_skorlar[tur] = (kw * KEYWORD_AGIRLIK) + (sem * SEMANTIK_AGIRLIK)

    en_iyi_tur = max(hibrit_skorlar, key=hibrit_skorlar.get)
    en_iyi_skor = hibrit_skorlar[en_iyi_tur]

    if keyword_skorlar[en_iyi_tur] < 1.0:
        if semantik_skorlar.get(en_iyi_tur, 0) < 0.65:
            return None

    if embedding_model is not None and semantik_skorlar.get(en_iyi_tur, 0) < 0.25:
        return None

    if en_iyi_skor < 0.20:
        return None

    print(f"   🤖 [3-Katman Hibrit] '{baslik[:40]}' → {en_iyi_tur} (Skor: {en_iyi_skor:.3f}, Semantik: {semantik_skorlar.get(en_iyi_tur, 0):.3f})")
    return en_iyi_tur

def extract_location(text: str, title: str = "") -> tuple[str, float, float]:
    """Find the matched district by checking title first, then counting frequencies in text.
    Also use regex to find specific Mahalle/Sokak/Cadde names."""
    title_lower = title.lower()
    full_text = f"{title}. {text}"
    
    # ── Şehir Dışı Filtre: Başka il geçiyor mu ve Kocaeli ilçesi var mı? ──
    combined_lower = full_text.lower()
    baska_il_gecti = any(il in combined_lower for il in DIGER_ILLER)
    kocaeli_ilcesi_gecti = any(ilce.lower() in combined_lower for ilce in DISTRICTS)
    
    if baska_il_gecti and not kocaeli_ilcesi_gecti:
        bulunan_il = next((il for il in DIGER_ILLER if il in combined_lower), "?")
        print(f"      ⛔ Şehir dışı haber tespit edildi ({bulunan_il.title()}), Kocaeli ilçesi bulunamadı. Reddedildi.")
        return None, 0, 0
    
    # 1. Extract district first to have a valid fallback and city context
    best_district = None
    best_lat = DEFAULT_LOCATION[1]
    best_lng = DEFAULT_LOCATION[2]
    
    for district, coords in DISTRICTS.items():
        if district.lower() in title_lower:
            best_district = district
            best_lat, best_lng = coords
            break
            
    if not best_district:
        text_lower = text.lower()
        counts = {}
        for district, coords in DISTRICTS.items():
            cnt = text_lower.count(district.lower())
            if cnt > 0:
                counts[district] = cnt
        if counts:
            best_district = max(counts, key=counts.get)
            best_lat, best_lng = DISTRICTS[best_district]
            
    # 2. Extract Specific Neighborhood/Street using Regex
    specific_location = None
    
    # Pattern A: Proper noun + location suffix (handles Turkish suffixed forms like Caddesinde, Mahallesinde)
    # Requires first letter to be CAPITAL to avoid catching random words like 'gecesi'
    regex_patterns = [
        # "Ömerağa Mahallesi", "Cumhuriyet Caddesinde", "Tavşantepe Mevkiinde"
        r"([A-ZÇŞĞÜÖİ][a-zçşğüöıA-ZÇŞĞÜÖİ]*(?:\s+[A-ZÇŞĞÜÖİ][a-zçşğüöıA-ZÇŞĞÜÖİ]*)*)\s+(Mahallesi|Mah\.|Sokağı|Sok\.|Caddesi|Cad\.|Bulvarı|Blv\.|Kavşağı|Mevkii|Mevkisi|Yolu|Köprüsü|Otoyolu|Karayolu)\w*",
        # "D-100 karayolu", "D100 karayolu", "TEM Otoyolu", "Kuzey Marmara Otoyolu"
        r"((?:D[- ]?100|TEM|O-?[1-4]|Kuzey\s+Marmara))\s*(karayolu|otoyolu|bağlantı yolu)\w*",
        # "Ankara Caddesi üzerinde" — city/district name + Caddesi
        r"([A-ZÇŞĞÜÖİ][a-zçşğüöıA-ZÇŞĞÜÖİ]+)\s+(Caddesi|Caddesinde|Caddesindeki|Sokağı|Sokağında|Bulvarı|Bulvarında)\w*",
    ]
    
    for pattern in regex_patterns:
        match = re.search(pattern, full_text)
        if match:
            # group(1) is the name (e.g., "Ömerağa", "D-100"), group(2) is the type (e.g., "Mahallesi", "karayolu")
            name_part = match.group(1).strip()
            type_part = match.group(2).strip()
            # Clean up the type part to a base form (e.g. "Caddesinde" -> "Caddesi", "Mahallesinde" -> "Mahallesi")
            if type_part.startswith("Mah"): type_part = "Mahallesi"
            elif type_part.startswith("Cad"): type_part = "Caddesi"
            elif type_part.startswith("Sok"): type_part = "Sokağı"
            elif type_part.startswith("Blv") or type_part.startswith("Bulvar"): type_part = "Bulvarı"
            elif type_part.startswith("Mevki"): type_part = "Mevkii"
            elif type_part.startswith("Kavşa"): type_part = "Kavşağı"
            
            specific_location = f"{name_part} {type_part}"
            break
        
    # 3. Construct the detailed location string
    if specific_location and best_district:
        konum_metin = f"{specific_location}, {best_district}, Kocaeli"
    elif specific_location:
        konum_metin = f"{specific_location}, Kocaeli"
    elif best_district:
        konum_metin = f"{best_district}, Kocaeli"
    else:
        # If no district or specific location is found, return None to reject the article
        print(f"      -> Konum bulunamadı, sadece 'Kocaeli' yeterli değil.")
        konum_metin = None
        
    return konum_metin, best_lat, best_lng

# ── Geocode Cache: aynı konum için tekrar API çağrısı yapılmamasını sağlar ────
_geocode_cache: dict[str, tuple[float, float]] = {}

async def geocode_location(client: httpx.AsyncClient, text_query: str) -> tuple[float, float]:
    """Uses Nominatim (OpenStreetMap) Geocoding API to parse real coordinates.
    Rate-limited to 1 request/second per Nominatim usage policy.
    Results are cached to avoid duplicate API calls for the same location."""
    # Check cache first (PDF requirement: avoid duplicate API calls for same location)
    if text_query in _geocode_cache:
        print(f"   ✓ Geocode cache hit: {text_query}")
        return _geocode_cache[text_query]
    
    async with nominatim_semaphore:
        try:
            url = "https://nominatim.openstreetmap.org/search"
            # text_query format is typically "Neighborhood, District, Kocaeli"
            # so we only need to append ", Turkey"
            search_string = f"{text_query}, Turkey"
            print(f"   🌍 Nominatim API Text Search: '{search_string}'")
            
            params = {
                "q": search_string,
                "format": "json",
                "limit": 1
            }
            headers = {
                "User-Agent": "KocaeliHaberHaritasi/1.0 (Student Project)"
            }
            response = await client.get(url, params=params, headers=headers, timeout=10.0)
            data = response.json()
            if len(data) > 0:
                result = (float(data[0]['lat']), float(data[0]['lon']))
                _geocode_cache[text_query] = result
                print(f"   ✅ API Başarılı: {search_string} -> {result}")
                return result
            else:
                # Cache negative results too to avoid retrying
                print(f"   ❌ API Sonuç Bulamadı: {search_string} -> Null fallback uygulanacak")
                _geocode_cache[text_query] = (None, None)
        except Exception as e:
            print(f"   ⚠️ Geocoding failed for {text_query}: {e}")
        finally:
            # Respect Nominatim rate limit: wait 1.1 seconds between requests
            await asyncio.sleep(1.1)
    return None, None

async def scrape_article(client: httpx.AsyncClient, link: str, source_name: str) -> str:
    """Scrapes a single article link. Returns a string status code for detailed tracking.
    Concurrency is controlled by scraper_semaphore to avoid overwhelming news sites."""
    async with scraper_semaphore:
        try:
            # Check if URL belongs to an opinion piece / author column
            if '/yazar' in link.lower() or '/makale' in link.lower() or 'kose-yazisi' in link.lower():
                return "OPINION_PIECE"
                
            # Check if URL exists in DB first to save bandwidth
            existing = await news_collection.find_one({"link": link})
            if existing:
                return "ALREADY_DB"
                
            response = await client.get(link, timeout=10.0)
            if response.status_code != 200:
                if response.status_code in [403, 503]:
                    print(f"   🚫 Cloudflare/Bot Engeli ({response.status_code}): {link}")
                else:
                    print(f"   ⚠️ HTTP Hata ({response.status_code}) - Atlanıyor: {link}")
                return "HTTP_ERROR"
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 0. Check if page is actually an article using OpenGraph meta tags
            og_type = soup.find('meta', property='og:type')
            if og_type and og_type.get('content', '').lower() not in ['article', 'news']:
                print(f"   ⏭️ Not an article page (og:type={og_type.get('content')}): {link}")
                return "NOT_ARTICLE"
            
            title_tag = soup.find('h1')
            title = clean_text(title_tag.text) if title_tag else ""
            
            if not title:
                return "MISSING_TITLE"
                
            # Try to find the main article container to avoid headers/footers
            article_node = soup.find('article')
            if not article_node:
                # Common class names for article bodies in Turkish news sites
                article_node = soup.find(class_=re.compile(r'(haber-detay|haber-icerik|post-content|article-content|detay|icerik|news-body)', re.I))
            
            p_tags = article_node.find_all('p') if article_node else soup.find_all('p')
            
            valid_p = []
            for p in p_tags:
                text = p.get_text(separator=' ').strip()
                # Skip very short paragraphs or stock/currency tickers
                if len(text) < 40: continue
                if any(curr in text for curr in ["$ Dolar", "€ Euro", "£ Sterlin", "BIST", "ALTIN", "Borsa"]): continue
                # Skip legal disclaimers and comment section generic warnings
                if any(bad in text.lower() for bad in ["topluluk kuralları", "yorum yazarak", "sorumluluğu tek başınıza", "kabul etmiş bulunuyor", "uyarı: bu içeriğe"]): continue
                valid_p.append(text)
                
            # Only take the first 3 valid paragraphs for summary
            content = clean_text(" ".join(valid_p[:3]))
            
            category = classify_news(title, content)
            if not category:
                return "NLP_FAIL"
                
            # ------------------------
            # 1. Deduplication via NLP Embedding (Cosine Similarity >= 0.90)
            # ------------------------
            full_text = f"{title}. {content}"
            if embedding_model:
                new_embedding = embedding_model.encode([full_text])[0]
                
                # Fetch recent news to compare
                three_days_ago = datetime.now() - timedelta(days=3)
                recent_news = await news_collection.find({"yayin_tarihi": {"$gte": three_days_ago}}).to_list(length=1000)
                
                for news in recent_news:
                    if 'embedding' in news and news['embedding']:
                        sim = cosine_similarity([new_embedding], [news['embedding']])[0][0]
                        if sim >= 0.80:
                            # PDF requirement was 0.90, user wants to test 0.80
                            existing_sources = news.get('kaynaklar') or [news.get('kaynak_site', '')]
                            existing_details = news.get('kaynaklar_detay') or [{"name": news.get('kaynak_site', ''), "url": news.get('link', '')}]
                            
                            if source_name not in existing_sources:
                                existing_sources.append(source_name)
                                existing_details.append({"name": source_name, "url": link})
                                
                                await news_collection.update_one(
                                    {'_id': news['_id']},
                                    {'$set': {
                                        'kaynaklar': existing_sources,
                                        'kaynaklar_detay': existing_details
                                    }}
                                )
                                print(f"Source merged ({sim:.2f}): '{source_name}' added to '{news.get('baslik','')[:50]}'")
                            else:
                                print(f"Duplicate (already from same source, {sim:.2f}) -> Skipping: {title}")
                            return "MERGED"
            else:
                new_embedding = []
                
            # ------------------------
            # 2. Geocoding
            # ------------------------
            konum_metin, default_lat, default_lng = extract_location(content, title)
            
            if konum_metin is None:
                # Out of city rejection triggered (e.g., Istanbul)
                print(f"Skipped: Şehir dışı haber tespit edildi ({title})")
                return "GEOCODE_FAIL"
            
            geo_lat, geo_lng = await geocode_location(client, konum_metin)
            
            # PDF Requirement: Geocoding başarısız olursa kayıt işlenmemelidir.
            if geo_lat is None or geo_lng is None:
                print(f"Skipped: Geocoding API koordinat bulamadı ({konum_metin})")
                return "GEOCODE_FAIL"
                
            enlem = geo_lat
            boylam = geo_lng

            # 3. Extract Real Publication Date
            yayin_tarihi = extract_publish_date(soup)
            
            # PDF Requirement: "sadece son 3 güne ait haberleri işlemelidir"
            # If the article is older than 3 days, discard it.
            now = datetime.now()
            if yayin_tarihi.tzinfo:
                now = datetime.now(yayin_tarihi.tzinfo)
                
            if yayin_tarihi < now - timedelta(days=3):
                print(f"Eski haber (3 günden eski) atlanıyor: {yayin_tarihi.strftime('%Y-%m-%d')} - {title[:40]}")
                return "OLD_NEWS"
                
            # Prepare document
            news_doc = {
                "haber_turu": category,
                "baslik": title,
                "icerik": content,
                "konum_metin": konum_metin,
                "enlem": enlem,
                "boylam": boylam,
                "yayin_tarihi": yayin_tarihi,
                "kaynak_site": source_name,
                "link": link,
                "kaynaklar": [source_name],   # starts as single-item list; grows if duplicates found
                "embedding": new_embedding.tolist() if len(new_embedding) > 0 else []
            }
            
            await news_collection.insert_one(news_doc)
            print(f"✅ Kaydedildi [{category}]: {title[:60]} → {konum_metin}")
            return "SAVED"
        except Exception as e:
            print(f"Error scraping article {link}: {repr(e)}")
            return "ERROR"

async def scrape_source(client: httpx.AsyncClient, source: dict) -> dict:
    """Scrapes multiple pages of the source to find article links."""
    stats = {
        "source": source['name'],
        "total_links": 0,
        "processed": 0,
        "SAVED": 0,
        "ALREADY_DB": 0,
        "NLP_FAIL": 0,
        "MERGED": 0,
        "GEOCODE_FAIL": 0,
        "OLD_NEWS": 0,
        "HTTP_ERROR": 0,
        "NOT_ARTICLE": 0,
        "OTHER_FAIL": 0
    }
    try:
        response = await client.get(source['url'], timeout=15.0)
        if response.status_code != 200:
            stats["HTTP_ERROR"] = 1
            return stats
            
        soup = BeautifulSoup(response.content, 'html.parser')
        links = set()
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            # Heuristic for news links: contains 'haber' and looks like a specific page
            if 'haber' in href or re.search(r'\d+', href):
                # Resolve relative URLs
                if href.startswith('/'):
                    full_link = f"{source['url']}{href}"
                elif href.startswith('http'):
                    full_link = href
                    # Make sure we don't scrape external ads or share links (Facebook/Twitter)
                    base_domain = source['url'].replace('https://www.', '').replace('https://', '').replace('http://', '')
                    if not re.match(r'^https?://(www\.)?' + re.escape(base_domain), full_link):
                        continue
                else:
                    continue
                    
                # Temiz bir url için fragmentları (#) temizle
                full_link = full_link.split('#')[0]
                links.add(full_link)
        
        stats["total_links"] = len(links)
        
        # Process all news links found on the homepage
        # Filter out category pages, tags, author pages, and advertisements
        ignore_patterns = ['basin_ilan', 'ilan.gov.tr', '/kategori/', '/etiket/', '-haberleri', '/author/', '/yazar/']
        filtered_links = set(l for l in links if not any(pattern in l.lower() for pattern in ignore_patterns))
        
        # Sadece yeterince uzun, mantıklı url'leri denemek
        filtered_links = [l for l in filtered_links if len(l.split('/')) > 3]
        
        stats["processed"] = len(filtered_links)
        
        print(f"\\n--- 📰 BOTA BAŞLANIYOR: {source['name']} ({stats['processed']} taze link test edilecek) ---")
        for link in filtered_links:
            # İşlemleri sırayla yap ki site yorulup IP ban Atmasın (Rate Limit Koruması)
            res = await scrape_article(client, link, source['name'])
            
            if res in stats:
                stats[res] += 1
            elif res in ["OPINION_PIECE", "MISSING_TITLE", "ERROR", "NOT_ARTICLE"]:
                stats["OTHER_FAIL"] += 1
                
            await asyncio.sleep(1.0)  # 1.0s gecikme ekleyerek IP engellemelerini (403 Ban) önleriz
            
    except Exception as e:
        print(f"Error scraping source {source['name']}: {repr(e)}")
        stats["OTHER_FAIL"] += 1
        
    return stats

async def run_scraper():
    """Main function to trigger scraping for all sources and generate a report."""
    # Provide a typical user agent
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    all_stats = []
    
    # Disable SSL verification to avoid CERTIFICATE_VERIFY_FAILED from some local news sites
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, verify=False) as client:
        # Siteleri de sırayla tarayarak hem kendi PC'mizi hem RAM'i hem hedef siteleri rahatlatalım
        for source in SOURCES:
            stats = await scrape_source(client, source)
            all_stats.append(stats)
    
    # Raporu Tablo Halinde Bastır
    total_saved = sum(s["SAVED"] for s in all_stats)
    
    print("\\n" + "="*80)
    print(" 📊 HABER ÇEKİMİ (SCRAPING) SONUÇ RAPORU ".center(80, " "))
    print("="*80)
    print(f"{'KAYNAK':<18} | {'BAKILAN':<8} | {'ZATEN VAR':<10} | {'NLP ELEDİ':<10} | {'KONUM YOK':<10} | {'BİRLEŞTİ':<9} | {'EKLENEN':<8}")
    print("-" * 80)
    
    for s in all_stats:
        print(f"{s['source']:<18} | {s['processed']:<8} | {s['ALREADY_DB']:<10} | {s['NLP_FAIL']:<10} | {s['GEOCODE_FAIL']:<10} | {s['MERGED']:<9} | {s['SAVED']:<8}")
        
    print("-" * 80)
    print(f"🔥 TOPLAM YENİ KAYIT: {total_saved} (Elenenler NLP ve Konum filtreleri sayesinde haritayı çöpten korudu!)")
    print("="*80 + "\\n")
    
    return total_saved
