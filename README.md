# MVM Yavaşlar — Netsis Stok Kontrol

Netsis'in MS SQL Server üzerindeki **kendi tablolarını** kullanan, Python/Tkinter tabanlı masaüstü uygulaması. Başka bir veri tabanı oluşturmaz.

## Mevcut işlevler

- `dbo.TBLSTSABIT` üzerinden stok kodu/adı, grup, KOD_1, KOD_2, `ALIS_FIAT1`, `SATIS_FIAT1` okumak.
- Varsa `BARKOD1/2/3` üzerinden stok kodu/adı/barkod aramak. Farklı kurulumlarda barkod alanları opsiyoneldir.
- Alış fiyatı sıfır, satış fiyatı sıfır, zarar, düşük **brüt kâr marjı**, %100+ **maliyet kârı** filtreleri.
- Seçili ürünlere yüzde bazlı alış/satış fiyat önerisi, isteğe bağlı bir sonraki `…,90` fiyatına **yukarı** yuvarlama.
- Değişikliklerin sadece arayüzde **önizlenmesi**; açık izin + ayrı onay olmadan SQL'e yazılmaz.
- Sadece önizlemedeki ve gerçekten değişen satırları, aynı transaction içinde, eski fiyatla eşleşme kontrolüyle güncellemek.
- Başarılı kayıt sonrası kullanıcının yerel klasörüne işlem günlükleri (`~/.mvm-stok-kontrol/price_audit.jsonl`).

> Uyarı: `ALIS_FIAT1` ve `SATIS_FIAT1` Netsis stok kartı *liste fiyatlarıdır*. **Son alış BF / son satış BF**, hareket ve iskonto sonrası net fiyat ile aynı kavram değildir. Satış hareketleri için `TBLSTHAR`; bakiye için `TBLSTOKPH`; ek barkod kayıtları için `TBLSTOKBAR` sonraki aşamalarda ayrıca doğrulanmalıdır.

## Windows kurulumu

1. Python 3.11+ ve **Microsoft ODBC Driver 17 for SQL Server** kurun. ODBC 18 varsa `NETSIS_DRIVER` değerini buna göre değiştirin.
2. Depoyu indirin, terminalde klasöre geçin: `python -m pip install -r requirements.txt`.
3. `.env.example` dosyasını `.env` adıyla kopyalayıp **kendi ortamınızda** `NETSIS_SERVER` ve `NETSIS_DATABASE` ayarlarını girin.
4. Mümkünse `NETSIS_AUTH=windows` ve kısıtlı erişimli Windows hesabı kullanın. SQL doğrulaması gerekiyorsa `NETSIS_AUTH=sql`, `NETSIS_USER` ve `NETSIS_PASSWORD` değerlerini **yalnızca yerel `.env` dosyasında** ayarlayın.
5. **İlk deneme:** `NETSIS_WRITE_ENABLED=0` bırakın ve `python stokyonetim.py` çalıştırın. Bağlantı, stok adları ve fiyatları Netsis ekranlarıyla karşılaştırın.
6. Test ortamında tablo ve veri eşleşmeleri doğrulanıp SQL hesabına gerekli sınırlı UPDATE yetkisi verildikten sonra yazma gerekliyse `NETSIS_WRITE_ENABLED=1` ayarlayın. Ekrandaki ikinci onay yine zorunludur.

## Güvenlik

- Önceki yayınlanmış sürümde SQL bağlantı parolası kaynak koda gömülmüştü. **Bu parola açığa çıkmış kabul edilmeli ve SQL Server'da derhal değiştirilmelidir.** Yeni dosyada kaldırılmış olması Git geçmişindeki eski commit'i silmez.
- Açık kaynak depoya hiçbir gerçek `.env` dosyası, şifre, sunucu erişim sırrı veya müşteri verisi koymayın. Parola rotasyonu, sunucuda yetki sınırlandırması ve geçmişin dikkatli temizliği ayrıca gereklidir.
- Üretim ortamında doğrudan fiyat yazma, Netsis'in kullandığı iş kuralları, döviz/KDV, şube ve fiyat seviyelerine bağlı olabilir. **Tedarikçi / Netsis uzmanı onayı ve yedekli test veri tabanında doğrulama olmadan yazma modunu açmayın.**
- Günlük JSONL dosyası yerel denetim izidir, SQL tarafında değiştirilemez bir denetim kaydı yerine geçmez. Kayıt hatası durumunda önce Netsis stok kartını yeniden okuyun; işlemi körlemesine tekrar göndermeyin.
- Yalnızca görüntülenen stok fiyatlarına göre hesaplanan **birim** kâr yüzdeleri raporlanır; stok miktarıyla çarpılmış envanter değeri değildir.

## Testler

```powershell
python -m unittest discover -s tests -v
```

Testler gerçek Netsis bağlantısı olmadan hesaplama ve SQL transaction kontrolünü sınar. Entegrasyon testi, firmanızın SQL altyapısına bağlanılarak ayrıca yapılmalıdır.

## Yol haritası

1. [x] Kod içindeki sabit bağlantı kimlik bilgilerini kaldır, salt okunur varsayılan oluştur.
2. [x] Yalnızca onaylanan değişikliklere atomik UPDATE / eşzamanlılık kontrolü.
3. [x] Netsis `TBLSTSABIT` veri erişimi, alım/satım fiyatı okuma.
4. [x] Seçim filtreleri, % kâr / brüt marj ayrımı, fiyat önizlemesi.
5. [x] Mevcut Tkinter ekranını yeniden düzenle, geçerli SQL modunu göster.
6. [x] Yerel işlem geçmişi + birim testleri.
7. [ ] Canlı Netsis **salt-okunur** bağlantı testi: tablo şeması, barkod, fiyatlar ve ürün sayıları.
8. [ ] `TBLSTHAR` ile son alış BF / son satış BF, `TBLSTOKPH` stok bakiye ve `TBLSTOKBAR` ek barkod senaryoları.
9. [ ] Veri doğrulamasından sonra test SQL ortamında yazma pilotu; Netsis tarafındaki iş kuralları doğrulanmalı.
10. [ ] İsteğe bağlı PySide6 arayüzü, Excel raporu ve Windows paketleme.
