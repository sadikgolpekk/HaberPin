# Kentsel Haber İzleme ve Harita Tabanlı Görselleştirme Sistemi: Kocaeli İli Örneği

## Özet

Bu proje, Kocaeli ilindeki yerel haber kaynaklarından otomatik olarak veri toplayan, toplanan haberleri Doğal Dil İşleme (NLP) teknikleri kullanarak analiz edip kategorize eden ve bu olayları interaktif bir harita üzerinde görselleştiren kapsamlı bir web uygulamasıdır. Günümüz şehirleşme dinamikleri ve artan nüfus yoğunluğu bağlamında, kentsel olayların (trafik kazaları, yangınlar, altyapı arızaları, asayiş olayları ve kültürel etkinlikler) anlık olarak takip edilmesi elzem hale gelmiştir. Bu sistem, dağınık haldeki yerel haber bilgilerini tek bir platformda toplayarak şehir sakinlerinin ve ilgili kurumların yaşadıkları çevreye dair bilgilere hızlı, bütüncül ve doğru biçimde erişmesini sağlamayı hedeflemektedir.


<img width="1584" height="778" alt="image" src="https://github.com/user-attachments/assets/c4d18d92-8379-4d03-998b-7ff41fc9756c" />



## Özellikler

- **Otomatik Haber Toplama (Web Scraping):** Kocaeli'de faaliyet gösteren 5 ana yerel haber platformundan (Özgür Kocaeli, Çağdaş Kocaeli, Bizim Yaka, Ses Kocaeli ve Yeni Kocaeli) gerçek zamanlı olarak haber verilerini toplar. `httpx` ve `BeautifulSoup4` kütüphaneleri kullanılarak yüksek performanslı ve asenkron bir veri toplama mekanizması geliştirilmiştir [1].

- **Gelişmiş Doğal Dil İşleme (NLP ) ile Kategorizasyon:** Toplanan haber metinlerini, özel olarak tasarlanmış hibrit bir sınıflandırma algoritması kullanarak 5 ana kategoriye ayırır: Trafik Kazası, Yangın, Elektrik Kesintisi, Hırsızlık ve Kültürel Etkinlikler. Bu algoritma, klasik sözlük tabanlı yaklaşımların dezavantajlarını gidermek amacıyla `Sentence-Transformers` (SBERT) tabanlı semantik analiz ve bağlamsal filtreleme katmanlarını içerir [1].

- **Konum Tabanlı Görselleştirme (Geocoding):** Haberlerde geçen olay yerlerini (ilçe, mahalle, önemli bina, cadde vb.) Google Geocoding API aracılığıyla enlem-boylam koordinatlarına dönüştürür ve bu konumları Google Haritalar üzerinde işaretler. `Nominatim` geocoding servisi de desteklenmektedir [1].

- **İnteraktif Harita Arayüzü:** Kullanıcıların harita üzerinde olayları görmesini, kategorilere, ilçelere ve zaman aralıklarına göre filtrelemesini sağlayan dinamik bir arayüz sunar. `MarkerClusterer` kütüphanesi ile yoğun bölgelerdeki işaretçiler gruplandırılır [1].

- **Gerçek Zamanlı Güncellemeler:** Sistem, her tetiklendiğinde son 3 günlük zaman dilimini kapsayacak şekilde otomatik arşiv taraması yaparak verileri güncel tutar.

- **Tekilleştirme ve Gölge Kayıt Temizleme:** Benzerlik analizi ve ağırlıklı hibrit skorlama yöntemleri kullanılarak aynı olaya ait farklı haber kaynaklarından gelen verilerin tekilleştirilmesi sağlanır, böylece harita üzerinde gereksiz tekrarın önüne geçilir [1].

- **Kullanıcı Dostu ve Duyarlı Arayüz:** `Tailwind CSS` ile modern ve duyarlı bir kullanıcı arayüzü geliştirilmiştir. Frontend, harici bir framework bağımlılığı olmaksızın (Vanilla JS) geliştirilerek düşük kaynak tüketimi ve yüksek render hızı hedeflenmiştir [1].


<img width="1595" height="790" alt="image" src="https://github.com/user-attachments/assets/c6ebd3b1-7352-4a8c-80c3-35ac9a4c21d4" />


## Teknoloji Yığını (Tech Stack)

Projenin mimari tasarımı, yüksek veri işleme hızı ve ölçeklenebilirlik hedefleri doğrultusunda modüler bir yapıda kurgulanmıştır. Geliştirme sürecinde modern ve performans odaklı teknolojiler tercih edilmiştir.

<img width="508" height="357" alt="image" src="https://github.com/user-attachments/assets/2ed0c311-c29b-4bac-bf53-f5461aa96cb2" />




## Kurulum

Projeyi yerel ortamınızda çalıştırmak için aşağıdaki adımları izleyin:

1. **Depoyu Klonlayın:**

   ```bash
   git clone https://github.com/kullanici_adiniz/kocaeli-haber-haritasi.git
   cd kocaeli-haber-haritasi
   ```

1. **Ortam Değişkenlerini Ayarlayın:**Proje kök dizininde `.env` adında bir dosya oluşturun ve aşağıdaki değişkenleri ekleyin:

   ```
   MONGODB_URL="mongodb://localhost:27017/"
   GOOGLE_MAPS_API_KEY="YOUR_GOOGLE_MAPS_API_KEY"
   ```
  - `MONGODB_URL`: MongoDB veritabanınızın bağlantı URL'si. Yerel bir MongoDB kurulumu kullanıyorsanız `mongodb://localhost:27017/` yeterli olacaktır.
  - `GOOGLE_MAPS_API_KEY`: Google Cloud Console'dan alacağınız Google Haritalar JavaScript API'si ve Geocoding API'si için API anahtarı. Bu anahtarın doğru şekilde yapılandırıldığından emin olun.

1. **Bağımlılıkları Yükleyin:**

   ```bash
   pip install -r requirements.txt
   ```

1. **Uygulamayı Çalıştırın:**

   ```bash
   uvicorn main:app --reload
   ```

   Uygulama varsayılan olarak `http://127.0.0.1:8000` adresinde çalışacaktır.


<img width="728" height="290" alt="image" src="https://github.com/user-attachments/assets/b0b399cc-a98e-40f0-948d-32a6483cad3e" />

## Kullanım

Uygulama çalıştıktan sonra tarayıcınızda `http://127.0.0.1:8000` adresine giderek ana arayüze erişebilirsiniz.

- **Haberleri Çek:** Sol üst köşedeki "Haberleri Çek" butonuna tıklayarak yeni haberleri toplayabilir ve veritabanına kaydedebilirsiniz.

- **Haritayı Temizle:** "Haritayı Temizle" butonu ile mevcut haberleri veritabanından silebilirsiniz.

- **Filtreleme:** Sol kenar çubuğundaki filtreleri kullanarak haberleri kategoriye, ilçeye veya son 3 günlük zaman dilimine göre filtreleyebilirsiniz.

- **Harita Etkileşimi:** Harita üzerindeki işaretçilere tıklayarak haber detaylarını (başlık, içerik özeti, tarih, kaynak linkleri ) görüntüleyebilirsiniz.



## Katkıda Bulunma

Katkılarınız memnuniyetle karşılanır! Lütfen bir `issue` açın veya bir `pull request` gönderin.

## Lisans

Bu proje MIT Lisansı altında lisanslanmıştır. Daha fazla bilgi için `LICENSE` dosyasına bakın.

## İletişim

Sorularınız veya geri bildirimleriniz için lütfen iletişime geçin:

- Sadık Gölpek

- Abdullah Önder

---

**Not:** Projenin tam işlevselliği için Google Maps API anahtarınızın doğru yapılandırıldığından ve MongoDB sunucunuzun çalıştığından emin olun. Ayrıca, `scraper.py` dosyasındaki `embedding_model` yüklemesi ilk çalıştırmada biraz zaman alabilir. Bu, `paraphrase-multilingual-MiniLM-L12-v2` modelinin indirilmesinden kaynaklanmaktadır.

