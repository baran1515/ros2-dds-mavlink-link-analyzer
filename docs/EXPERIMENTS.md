# Deney Metodolojisi

## 1. Amaç
Gecikme, jitter ve paket kaybı altında; otonom araç ile yer birimleri arasındaki haberleşmenin
**sürekliliğini** (kesinti süresi, veri tazeliği) ve **güvenilirliğini** (uygulama seviyesi kayıp)
farklı DDS QoS ayarları ve mesaj profilleri için karşılaştırmak.

## 2. Ölçüm Yöntemi

### RTT
`probe_sender` her `Probe` mesajına gönderim zamanını yazar; `probe_echo` mesajı değiştirmeden geri yollar.
`RTT = alım_zamanı − gönderim_zamanı` aynı saatle ölçülür → saat senkronizasyonu gerekmez.

### Kayıp
Cevabı `timeout_s` (1 s) içinde gelmeyen probe **kayıp** sayılır. Zaman aşımından sonra gelen cevaplar
**geç gelen** olarak ayrıca sayılır (RELIABLE QoS'ta yeniden iletimle gelen eski veriyi gösterir).

### Jitter
RFC 3550 §6.4.1: `J ← J + (|D| − J)/16`, `D` = ardışık iki paketin geçiş süreleri farkı.

### Telemetri sürekliliği
`telemetry_monitor`: ArduPilot konusunun alım hızı ve **varışlar arası en uzun boşluk** (veri kesintisi).

## 3. Prosedür
1. Ortam: tek makine, `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`, `CYCLONEDDS_URI=config/cyclonedds_lo.xml`.
2. Her koşu öncesi `netem.sh clear` ve doğrulama (`netem.sh show`).
3. Profil uygulanır (`--port 7400-7450`), koşu 60 s sürer, ilk 5 s analiz dışıdır.
4. Her kombinasyon için CSV `results/<profil>__<qos>__<hız>_<boyut>.csv`.
5. `analyze_results.py` → tablo + `summary.png`.

## 4. Hipotezler (deneyle doğrulanacak)

| # | Hipotez | Ölçüt |
|---|---|---|
| H1 | Kayıplı profillerde RELIABLE, uygulama seviyesi kaybı BEST_EFFORT'tan düşük tutar | `loss_pct` |
| H2 | RELIABLE, kayıp arttıkça RTT kuyruğunu (p95/max) uzatır (yeniden iletim + head-of-line) | `rtt_p95_ms`, `rtt_max_ms` |
| H3 | RELIABLE + depth 1, yüksek hızda en güncel veriyi korurken kuyruk birikmesini sınırlar | `late`, `rtt_p95_ms` |
| H4 | Burst kayıp, aynı ortalama kayıptaki uniform kayıptan daha uzun kesintiler üretir | telemetri `gap_max_ms` |
| H5 | Büyük yük (512 B) + yüksek hız (100 Hz), `bad` profilinde kuyrukları doldurur | `loss_pct`, `late` |

## 5. Sonuç Şablonu

`python3 scripts/analyze_results.py results/` çıktısı buraya eklenir:

| Ağ profili | QoS | Gönderilen | Kayıp [%] | Geç gelen | RTT p50 [ms] | RTT p95 [ms] | RTT max [ms] | Jitter [ms] |
|---|---|---|---|---|---|---|---|---|
| ideal | reliable_d10 | | | | | | | |
| ... | | | | | | | | |

## 6. Yorumlama Notları
* `lo` üzerinde netem her pakete bir kez uygulanır; RTT ≈ 2 × tek yön gecikme + işlem süresi.
* `late` > 0 ve yüksek `rtt_max_ms`, verinin geldiğini ama **eskimiş** olduğunu gösterir; kontrol döngüsü
  için bu, kayıp kadar zararlı olabilir.
* Tek makinede CPU yükü sonuçları etkiler; koşular sırasında başka yük çalıştırılmamalıdır.

## 7. Geçerlilik Sınırları
* netem, gerçek RF kanalının (çok yollu sönümlenme, girişim, menzile bağlı SNR) basitleştirilmiş modelidir.
* Tüm düğümler tek makinededir; gerçek bir dağıtık kurulumda saat, ağ yığını ve donanım farklılıkları eklenir.
