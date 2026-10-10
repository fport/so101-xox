# Kullanım notları

[English](../operations.md) · **Türkçe**

Donanım, Hugging Face'teki dataset'ler ve eğitim için günlük notlar: oturumun başında neye bakılır, dataset repolarının komutları ve şimdiye kadar karşılaşılan tuzaklar. Portlar ve kamera index'leri verinin kaydedildiği düzene ait. Bütün komutlar repo kökünden, `.venv` ortamında çalıştırılır (`uv sync`, sonra `source .venv/bin/activate`).

## Donanım

| | |
|---|---|
| Follower | `/dev/cu.usbmodem5AB01794851`, id `follower`, ~12,5 V |
| Leader | `/dev/cu.usbmodem5A7C1232561`, id `leader`, ~5,5 V |
| Kalibrasyon | `calibration/{follower,leader}.json` (2026-09-13), `--robot.calibration_dir=calibration` |
| Kamera `top` | OpenCV index `0`, 640×480 @ 30, kolun karşısından tahtaya bakıyor |
| Kamera `wrist` | OpenCV index `1`, 640×480 @ 30, bilekte |

Port adları kablo yeniden takılınca değişebilir: `ls /dev/cu.usbmodem*`. Hangisinin hangisi olduğu voltajdan anlaşılır.

Kamera index'leri de değişebilir: eskiden bilek 0, üst 1'di; 2026-10-06'da ilk denemede üst 1'e kaydı. MacBook kamerası ve iPhone (Süreklilik Kamerası) da listeye giriyor. Her oturumun başında aşağıdaki kontrolü yap.

## Hugging Face

Dataset'ler `fport` hesabında, **public** (2026-10-10 kararı; kayıt sırasında private tutulması planlanmıştı). Adlandırma, daha önce yapılmış açık bir SO-101 XOX projesinin `tic-tac-toe-so101-<parça>-clean-vN` düzeninde:

| Repo | İçerik |
|---|---|
| `fport/tic-tac-toe-so101-x-round1` | Tur 1 ham kaydı (pilot): 46 bölüm, 9 blok × 5 + #45 (#15'in tekrarı). Yerelde `data/tic-tac-toe-so101-x-round1`. |
| `fport/tic-tac-toe-so101-x-round1-clean-v1` | Tur 1'in temiz hâli (2026-10-10): ham #15 silindi, 45 bölüm, hücre başına 5. Numaralar kayar: ham #16–#45 → temiz #15–#44. Yerelde `data/tic-tac-toe-so101-x-round1-clean-v1`. |
| `fport/tic-tac-toe-so101-x-round2` … | Sonraki turların ham kayıtları (henüz yok) |
| `fport/tic-tac-toe-so101-x-clean-v1` | Eğitim seti: temizlenmiş turların birleşimi (henüz yok) |

Ham repolara kayıttan sonra dokunulmaz. Temizleme ve birleştirme her zaman yeni bir `-clean-vN` reposu üretir; bir şey ters giderse ham kayıt elde kalır. O'lar gelince aynı düzen `-o-` / `-xo-` ile devam eder.

**Bir kere:** `hf auth login` (yazma izinli token), kontrol için `hf auth whoami`.

**Aynı tura bölüm eklemek:** Kayıt komutu ([`recording.md`](recording.md)) + `--resume=true`, `--dataset.num_episodes` = eklenecek bölüm sayısı. Kayıt bitince lerobot dataset'in tamamını HF'e kendisi yükler. Yerel kopya şart; başka bir bilgisayardaysan önce indir:

```bash
hf download fport/tic-tac-toe-so101-x-round1 --repo-type dataset --local-dir data/tic-tac-toe-so101-x-round1
```

**Yeni tur:** Komutta `--dataset.repo_id` ve `--dataset.root`'u `-round2` yap, `--resume` olmadan başlat. `--dataset.private=true --dataset.no_stamp=true` hep kalsın.

**Elle yükleme** (kayıt yüklemeden kapandıysa):

```bash
hf upload fport/tic-tac-toe-so101-x-round1 data/tic-tac-toe-so101-x-round1 . --repo-type dataset --private
```

**Kötü bölümleri silip temiz kopya çıkarmak** (numaralar örnek):

```bash
lerobot-edit-dataset \
  --repo_id=fport/tic-tac-toe-so101-x-round1 --root=data/tic-tac-toe-so101-x-round1 \
  --new_repo_id=fport/tic-tac-toe-so101-x-round1-clean-v1 --new_root=data/tic-tac-toe-so101-x-round1-clean-v1 \
  --operation.type=delete_episodes --operation.episode_indices="[3, 17]"
hf upload fport/tic-tac-toe-so101-x-round1-clean-v1 data/tic-tac-toe-so101-x-round1-clean-v1 . --repo-type dataset --private
hf repos tag create fport/tic-tac-toe-so101-x-round1-clean-v1 v3.0 --repo-type dataset
```

**Turları birleştirmek:**

```bash
lerobot-edit-dataset \
  --new_repo_id=fport/tic-tac-toe-so101-x-clean-v1 --new_root=data/tic-tac-toe-so101-x-clean-v1 \
  --operation.type=merge \
  --operation.repo_ids="['fport/tic-tac-toe-so101-x-round1-clean-v1', 'fport/tic-tac-toe-so101-x-round2-clean-v1']" \
  --operation.roots="['data/tic-tac-toe-so101-x-round1-clean-v1', 'data/tic-tac-toe-so101-x-round2-clean-v1']"
hf upload fport/tic-tac-toe-so101-x-clean-v1 data/tic-tac-toe-so101-x-clean-v1 . --repo-type dataset --private
hf repos tag create fport/tic-tac-toe-so101-x-clean-v1 v3.0 --repo-type dataset
```

**Yanlış görev etiketini düzeltmek** (yerinde değiştirir; önce klasörü yedekle):

```bash
lerobot-edit-dataset --repo_id=fport/tic-tac-toe-so101-x-round1 --root=data/tic-tac-toe-so101-x-round1 \
  --operation.type=modify_tasks \
  --operation.episode_tasks='{"22": "put the red X in the middle left cell"}'
```

Sonra HF'e: `python -c "from lerobot.datasets.lerobot_dataset import LeRobotDataset as D; D('fport/tic-tac-toe-so101-x-round1', root='data/tic-tac-toe-so101-x-round1').push_to_hub(private=True)"` (repo zaten varsa görünürlüğü değiştirmez, `v3.0` etiketini son commit'e taşır).

- `lerobot-edit-dataset --push_to_hub=true` **kullanma**: private ayarı olmadan yüklüyor, kişisel hesapta repo public açılır. Yüklemeyi yukarıdaki gibi `hf upload --private` ile yap.
- `v3.0` etiketi LeRobot'un dataset'i Hub'dan sürümüyle bulması için gerekli. `lerobot-record` bunu kendisi ekliyor, elle yüklemede yukarıdaki komut ekliyor.
- **Public yapmak** (temizlenmiş sürüm hazır olunca): `hf repos settings fport/<repo> --repo-type dataset --public` (`--no-private` hiçbir şeyi değiştirmiyor), ya da HF'te repo sayfası → Settings.
- **Repo adı değiştirmek:** `hf repos move fport/<eski> fport/<yeni> --repo-type dataset`. Yerel klasörü de aynı ada taşı.

## Eğitim (Colab)

[`notebooks/train_smolvla_round1.ipynb`](../../notebooks/train_smolvla_round1.ipynb): tur 1 temiz setiyle SmolVLA, A100'de 20k adım (80 GB A100'de 3 sa 45 dk ölçüldü). Colab'da File → Upload notebook ile aç, Runtime'ı A100 yap, Secrets'e yazma izinli `HF_TOKEN` ekle, hücreleri sırayla çalıştır. Model `fport/smolvla-tic-tac-toe-so101-x-round1-20k` (önce private, 2026-10-11'den beri public) olarak yüklenir; ara checkpoint'ler repoda `checkpoints/<adım>/` altında.

## Her oturumun başında (kablolar çıkarıldıysa)

1. **Yerler:** Kol tabanı, tahta ve `top` kamera bant işaretlerinde mi? Kamera açısı değişirse kayıtlar birbirini tutmaz. En kolayı kamerayı ve standını hiç oynatmamak, kabloyu Mac tarafından çıkarmak.
2. **Güç:** Follower'ın 12 V adaptörü takılı mı?
3. **Portlar:** `ls /dev/cu.usbmodem*` çıktısında `5AB01794851` (follower) ve `5A7C1232561` (leader) olmalı. Adlar USB çipinin seri numarasından geliyor, genelde değişmez. Değiştiyse komutlardaki portları güncelle.
4. **Kameralar:** `lerobot-find-cameras opencv` çalıştır, `outputs/captured_images/` içindeki resimlere bak. `top` hâlâ 0, `wrist` hâlâ 1 mi? Index'ler takma sırasına göre yer değiştirebilir; iPhone yakındaysa Continuity Camera da listeye girebilir. Yeni `top` karesini [`reference_top.png`](../reference_top.png) (2026-10-06, pilot kaydının başı) ile karşılaştır: tahta ve yuvalar karede aynı yerde mi? `outputs/` git'e gitmez, MacBook kamerasının karesi orada kalabilir.
5. **Kalibrasyon:** Bir şey yapma. Kablo çıkarmak kalibrasyonu bozmaz; sadece bir motor sökülüp takılırsa yeniden gerekir.
6. **Işık:** Pilot boyunca hep aynı ışık: aynı lambalar, perde aynı durumda.

## Bilinen tuzaklar

- `--robot.max_relative_target` verme: 2 değerinde dirsek yerçekimine karşı kilitlendi.
- Teleop ya da kayıt açıkken aynı porttan başka bir şey okuma, bağlantı düşer.
- Kalibrasyon sorusunda ENTER (dosyayı kullan). `c` yeniden kalibre eder.
- `lerobot-find-cameras` macOS kamera izni ister, kendi terminalinden çalıştır.
- torchcodec bu Mac'teki FFmpeg ile yüklenmiyor: eğitim ve okumada `--dataset.video_backend=pyav`.
- Kayıtta `--dataset.streaming_encoding=true --dataset.encoder_threads=2` bölüm arası donmayı kaldırıyor.
- Rerun'daki `Exceeded gRPC proxy server memory limit` ve kaydın başındaki `Record loop is running slower` uyarısı zararsız (bölüm 0'da 25 sn'de 750 kare kaydedildi, kayıp yok).
