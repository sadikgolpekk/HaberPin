// =============================================
//  Kocaeli Haber Haritası — app.js
// =============================================

let map;
let markers = [];
let markerCluster = null;
let infowindow = null;

// ─── Utility ───────────────────────────────────────────────────────────────────
function seededJitter(id, axis) {
    const seed = id + (axis || '');
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
        hash = ((hash << 5) - hash) + seed.charCodeAt(i);
        hash |= 0;
    }
    return ((hash % 1000) / 1000 - 0.5) * 0.0001;   // ≈ ±5 m (Max zoomda ayırır, sokağı bile bozmaz)
}

// ─── Harita Başlatma ─────────────────────────────────────────────────────────
function initMap() {
    map = new google.maps.Map(document.getElementById("map"), {
        center: { lat: 40.8533, lng: 29.8815 },
        zoom: 10,
        mapTypeId: 'roadmap',
        styles: [{ featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] }]
    });

    infowindow = new google.maps.InfoWindow({ maxWidth: 420 });

    // Close popup on map background click
    map.addListener('click', () => infowindow.close());

    fetchNewsAndRender();
}

// ─── Marker İkonu ────────────────────────────────────────────────────────────
function getMarkerConfig(category) {
    const config = {
        'Trafik Kazası': { color: '#dc2626', emoji: '🚗' }, // Kırmızı
        'Yangın': { color: '#ea580c', emoji: '🔥' }, // Turuncu
        'Elektrik Kesintisi': { color: '#1f2937', emoji: '⚡' }, // Siyah
        'Hırsızlık': { color: '#7e22ce', emoji: '🕵️' }, // Mor
        'Kültürel Etkinlikler': { color: '#059669', emoji: '🎵' }, // Yeşil
    };
    return config[category] || { color: '#3b82f6', emoji: '📰' };
}

// ─── Global Function for Konuma Git Button ─────────────────────────────────────
window.zoomToLocation = function (lat, lng) {
    if (map) {
        map.setZoom(16);
        map.panTo({ lat, lng });
    }
};

// ─── Popup HTML ──────────────────────────────────────────────────────────────
function buildPopupHtml(news) {
    const date = new Date(news.yayin_tarihi).toLocaleString('tr-TR', {
        day: '2-digit', month: 'long', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
    const raw = (news.icerik || '').replace(/<[^>]*>/g, '').trim();
    const summary = raw.length > 200 ? raw.substring(0, 200) + '…' : raw;

    const config = getMarkerConfig(news.haber_turu);
    const badgeColor = config.color;

    // Build sources section — may be multi-source per PDF requirement
    const details = news.kaynaklar_detay || [{ name: news.kaynak_site, url: news.link }];

    // Create multiple "Habere Git" links if there are multiple sources
    const linksHtml = details.map(d => `
        <a href="${d.url}" target="_blank" rel="noopener"
           style="flex:1; text-align:center; padding:7px 0; background:#2563eb; color:#fff;
                  border-radius:6px; text-decoration:none; font-size:12px; font-weight:600; white-space:nowrap; text-overflow:ellipsis; overflow:hidden;">
          Habere Git (${d.name}) ↗
        </a>
    `).join('');

    return `
      <div style="font-family:'Segoe UI',Arial,sans-serif; padding:8px 4px; max-width:400px;">
        <span style="display:inline-block; background:${badgeColor}; color:#fff;
                     padding:2px 10px; border-radius:12px; font-size:11px;
                     font-weight:700; margin-bottom:8px; letter-spacing:0.5px;
                     box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
          ${config.emoji} ${news.haber_turu}
        </span>
        <h3 style="margin:0 0 8px; font-size:14px; font-weight:700; color:#1e293b; line-height:1.4;">
          ${news.baslik}
        </h3>
        ${summary ? `<p style="margin:0 0 8px; font-size:12px; color:#475569; line-height:1.5;">${summary}</p>` : ''}
        <p style="margin:0 0 3px; font-size:11px; color:#64748b;">📅 ${date}</p>
        ${news.konum_metin ? `<p style="margin:0 0 3px; font-size:11px; color:#64748b;">📍 ${news.konum_metin}</p>` : ''}
        
        <div style="display:flex; flex-direction:column; gap:6px; margin-top:12px;">
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
                ${linksHtml}
            </div>
            <a href="https://www.google.com/maps/search/?api=1&query=${news.enlem},${news.boylam}" target="_blank" rel="noopener"
               style="width:100%; text-align:center; padding:7px 0; background:#f1f5f9; color:#334155;
                      border:1px solid #cbd5e1; border-radius:6px; text-decoration:none; font-size:13px; font-weight:600; transition:0.2s; box-sizing:border-box;">
              Konuma Git 📍
            </a>
        </div>
      </div>`;
}

// ─── Haritayı Temizle ─────────────────────────────────────────────────────────
function clearMapData() {
    infowindow?.close();
    if (markerCluster) { markerCluster.clearMarkers(); markerCluster = null; }
    markers.forEach(m => m.setMap(null));
    markers = [];
}

// ─── Haberleri Çek ve Haritaya Ekle ──────────────────────────────────────────
async function fetchNewsAndRender() {
    showStatus("Haberler yükleniyor…", true);

    const params = new URLSearchParams();
    const cat = document.getElementById('filter-category').value;
    const dist = document.getElementById('filter-district').value;
    const timeframe = document.getElementById('filter-timeframe').value;

    if (cat) params.append('haber_turu', cat);
    if (dist) params.append('ilce', dist);

    if (timeframe !== "") {
        // Calculate the specific date based on selected dropdown value (0=Today, 1=Yesterday, etc)
        const targetDate = new Date();
        targetDate.setDate(targetDate.getDate() - parseInt(timeframe, 10));

        // Format as YYYY-MM-DD
        const dateStr = targetDate.toISOString().split('T')[0];

        // Both start and end date point to the same day
        params.append('tarih_baslangic', dateStr);
        params.append('tarih_bitis', dateStr);
    }

    try {
        const res = await fetch(`/api/news?${params}`);
        const result = await res.json();
        clearMapData();

        if (result.status !== 'success' || result.data.length === 0) {
            showStatus("Bu kriterlere uygun haber bulunamadı.", false);
            const container = document.getElementById('latest-news-list');
            if(container) container.innerHTML = '<p class="text-xs text-gray-500 py-2">Haber bulunamadı.</p>';
            return;
        }

        result.data.forEach(news => {
            if (!news.enlem || !news.boylam) return;

            // 0.00005'lik mikro kaydırma (yaklaşık 5 metre). 
            // Denize düşürmez ama iki farklı haber tam aynı adresteyse max zoom'da ayrılmalarını sağlar.
            const lat = news.enlem + seededJitter(news._id, 'lat');
            const lng = news.boylam + seededJitter(news._id, 'lng');

            const config = getMarkerConfig(news.haber_turu);

            const marker = new google.maps.Marker({
                position: { lat, lng },
                map: map,
                title: news.baslik,
                icon: {
                    path: "M0-48c-9.8 0-17.7 7.8-17.7 17.4 0 15.5 17.7 30.6 17.7 30.6s17.7-15.4 17.7-30.6c0-9.6-7.9-17.4-17.7-17.4z",
                    fillColor: config.color,
                    fillOpacity: 1,
                    strokeWeight: 1.5,
                    strokeColor: "#ffffff",
                    scale: 1,
                    labelOrigin: new google.maps.Point(0, -26)
                },
                label: {
                    text: config.emoji,
                    fontSize: "16px",
                    className: "marker-emoji"
                },
                optimized: true
            });

            // Single global infowindow — auto-closes previous when new one opens
            marker.addListener('click', () => {
                infowindow.setContent(buildPopupHtml(news));
                infowindow.open({ anchor: marker, map });
            });

            markers.push(marker);
        });

        // ─── MarkerClusterer ──────────────────────────────────────────────────
        try {
            const Lib = window.markerClusterer;
            const Klass = Lib?.MarkerClusterer;
            if (Klass) {
                // Remove direct map so clusterer controls visibility
                markers.forEach(m => m.setMap(null));
                markerCluster = new Klass({
                    map,
                    markers,
                    onClusterClick: (evt, cluster, gmap) => {
                        const bounds = cluster.bounds;
                        if (bounds) gmap.fitBounds(bounds);
                    }
                });
            }
            // If clusterer not available, markers already set to map above
        } catch (e) {
            console.warn("MarkerClusterer failed:", e);
        }

        showStatus(`${result.data.length} haber haritada gösteriliyor.`, false);
        renderLatestNews(result.data);
    } catch (err) {
        console.error("fetchNewsAndRender:", err);
        showStatus("Haberler yüklenirken hata oluştu.", false);
    }
}

// ─── Son Haberler (Sidebar) ───────────────────────────────────────────────────
function renderLatestNews(newsList) {
    const container = document.getElementById('latest-news-list');
    if (!container) return;

    // Sort by yayin_tarihi descending
    const sorted = [...newsList].sort((a, b) => new Date(b.yayin_tarihi) - new Date(a.yayin_tarihi));
    
    // Take top 4
    const topNews = sorted.slice(0, 4);

    if (topNews.length === 0) {
        container.innerHTML = '<p class="text-xs text-gray-500 py-2">Haber bulunamadı.</p>';
        return;
    }

    const html = topNews.map(news => {
        const config = getMarkerConfig(news.haber_turu);
        const date = new Date(news.yayin_tarihi).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' });
        const locationParts = news.konum_metin ? news.konum_metin.split(',').slice(0, 2).map(p=>p.trim()).join(', ') : 'Kocaeli';
        const metaText = `${locationParts} - ${date}`;

        return `
            <div class="py-3 flex items-center cursor-pointer hover:bg-gray-50 transition border-b border-gray-100 last:border-0" onclick="window.zoomToLocation(${news.enlem}, ${news.boylam})">
                <div class="w-10 h-10 rounded-lg flex items-center justify-center text-xl text-white shadow-sm shrink-0 mr-3" style="background-color: ${config.color}; line-height:0;">
                    ${config.emoji}
                </div>
                <div class="flex-1 min-w-0">
                    <h4 class="text-[13px] font-semibold text-gray-800 leading-tight mb-1 truncate">${news.baslik}</h4>
                    <p class="text-[11px] text-gray-500 truncate mt-0.5">${metaText}</p>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// ─── Durum Mesajı ─────────────────────────────────────────────────────────────
function showStatus(msg, loading) {
    const div = document.getElementById('status-message');
    const text = document.getElementById('status-text');
    const spin = div.querySelector('.fa-spinner');
    div.classList.remove('hidden');
    text.innerText = msg;
    spin?.classList.toggle('hidden', !loading);
    if (!loading) setTimeout(() => div.classList.add('hidden'), 5000);
}

// ─── Event Listeners ──────────────────────────────────────────────────────────
document.getElementById('filter-form').addEventListener('submit', e => {
    e.preventDefault();
    fetchNewsAndRender();
});

document.getElementById('btn-reset').addEventListener('click', () => {
    document.getElementById('filter-form').reset();
    fetchNewsAndRender();
});

document.getElementById('btn-scrape').addEventListener('click', async () => {
    const btn = document.getElementById('btn-scrape');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Çekiliyor…';
    btn.disabled = true;
    try {
        const res = await fetch('/api/news/scrape', { method: 'POST' });
        const data = await res.json();

        if (data.status === 'success') {
            Swal.fire({ title: 'Başarılı!', text: data.message || 'Tamamlandı.', icon: 'success', confirmButtonColor: '#3b82f6' });
        } else {
            Swal.fire({ title: 'Hata!', text: data.message || 'Bir sorun oluştu.', icon: 'error', confirmButtonColor: '#ef4444' });
        }
        fetchNewsAndRender();
    } catch {
        Swal.fire({ title: 'Hata!', text: 'Scraping sırasında bağlantı hatası oluştu.', icon: 'error', confirmButtonColor: '#ef4444' });
    } finally {
        btn.innerHTML = '<i class="fas fa-sync-alt mr-2"></i> Yeni Haberleri Çek';
        btn.disabled = false;
    }
});

document.getElementById('btn-clear').addEventListener('click', async () => {
    const result = await Swal.fire({
        title: 'Veritabanı Sıfırlansın Mı?',
        text: 'Haritadaki tüm haberler MongoDB veritabanından kalıcı olarak silinecek!',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#ef4444',
        cancelButtonColor: '#6b7280',
        confirmButtonText: '<i class="fas fa-trash-alt"></i> Evet, Temizle',
        cancelButtonText: 'İptal'
    });

    if (!result.isConfirmed) return;

    const btn = document.getElementById('btn-clear');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Temizleniyor…';
    btn.disabled = true;

    try {
        const res = await fetch('/api/news', { method: 'DELETE' });
        const data = await res.json();
        Swal.fire({ title: 'Temizlendi!', text: data.message || 'Veritabanı başarıyla sıfırlandı.', icon: 'success', confirmButtonColor: '#3b82f6' });
        fetchNewsAndRender(); // This will clear the map
    } catch {
        Swal.fire({ title: 'Hata!', text: 'Temizleme sırasında bir hata oluştu.', icon: 'error', confirmButtonColor: '#ef4444' });
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
});
