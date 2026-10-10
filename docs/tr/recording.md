# Kayıt protokolü

[English](../recording.md) · **Türkçe**

Bölüm bölüm tahta dizilimleri: [`rounds/`](rounds/). Her tur `scripts/recording_plan.py` ile üretilir (Türkçesi `--lang tr` ile).

## Bir kerelik hazırlık

- **Alma yuvası:** Robotun X aldığı tek yer, X grubunun robota en yakın sırasında tahta tarafındaki yuva. X'in dış hatlarını bantla çiz; her bölümde X oraya aynı açıyla konur. Pick sabit olunca politika asıl olarak place kısmını öğrenir (PDF Faz 0). Oyunda da robot hamlesini yapınca sıradaki X'i oraya insan koyar. Kolun arkasından bakınca:

  ```
  X'ler (robotun sağı)
  [ ] [ ]   uzak
  [ ] [ ]
  [A] [ ]   robota yakın   (A = alma yuvası, tahtaya yakın olan)
  ```
- **Depo:** Kalan 5 X ve 6 O. Tahtaya koyacağın taşları depodan al.
- **Yön:** Hücre adları robotun bakışına göre. Tur dosyasındaki tahtalar da kolun arkasından görüldüğü gibi çizili; tahtayı masaya bakarak kur. `top` kamerası kolun karşısında, görüntüsü 180° ters:

  ```
              (robot)
  bottom right | bottom center | bottom left
  middle right | middle center | middle left
  top right    | top center    | top left
              (top kamera)
  ```
- **Işık:** Tur boyunca aynı. Işık değişimi sonraki turlarda kontrollü eklenecek.
- **Sen ve leader:** İki kameranın da dışında, kolun arkasında.

## Her bölüm

1. **Başlangıç:** Kol dinlenme pozunda. Tahtada plandaki taşlar, alma yuvasında bir X, hedef hücre (`*`) boş.
2. **Kayıt:** "Recording episode N" sesi gelince hemen hareket et. X'i al, hedef hücrenin ortasına bırak, gripper'ı aç, kolu dinlenme pozuna getir, **→** bas. Duyduğun N plandaki # ile aynı olmalı. → tuşuna "Reset the environment" sesinden önce bas: süre dolup reset başladıysa → bu sefer reseti atlar ve sıradaki bölüm hazır olmadan başlar (2026-10-06'da böyle oldu).
3. **Reset** (en fazla 90 sn, hazır olunca **→**): Bıraktığın X'i ve tahtadaki taşları kaldır, sıradaki bölümün tahtasını kur, alma yuvasına X koy.
4. **Bozuk bölüm** (düşürdü, yanlış hücre, taşa çarptı, takıldı): Bölüm sırasında ya da hemen ardından gelen resette **←**. Aynı numara yeniden kaydedilir.
5. Bloğun son bölümünden sonra reset yok. Komut kendisi biter ve dataset'i HF'e (private) yükler.

**Esc'ye basma:** Yarım kalan bölüm kaydedilir. Blok yarıda kalırsa dur ve haber ver, numaraları birlikte düzeltelim.

## Örnek: Blok 1 baştan sona

`--dataset.single_task` cümlesi bu 5 bölümün etiketi; komutta hazır yazılı, sen bir şey yapmıyorsun. Blok içindeki 5 tahtanın hepsinde `*` aynı hücrede (Blok 1'de `middle right`). Değişen tek şey tahtadaki diğer taşlar. Kolu leader ile sen yönetiyorsun, follower taklit ediyor.

Hücre adları: `top` = robottan uzak satır, `bottom` = robota yakın satır; `left` = robotun solu (O'ların tarafı), `right` = robotun sağı (X'lerin tarafı).

| # | Tahtaya X | Tahtaya O |
|---|---|---|
| 0 | top center, bottom left | top right, middle left, bottom right |
| 1 | top center, top right, middle left | middle center, bottom center, bottom right |
| 2 | top left, top right, middle center, bottom center | top center, middle left, bottom left, bottom right |
| 3 | yok | top right |
| 4 | middle center | top center, top right |

1. **Komuttan önce:** Tahtayı #0'a göre kur, alma yuvasına bir X koy. İki kolu da dinlenme pozuna getir; komut açılınca follower leader'ın pozuna atlar. Kayıt komut açılır açılmaz başlıyor, o yüzden her şey önceden hazır olmalı.
2. **`lerobot-record` komutunu çalıştır** (aşağıda "Komut" bölümünde). `lerobot-teleoperate` değil: o kolu oynatır ama hiçbir şey kaydetmez. Kalibrasyon sorarsa ENTER.
3. **"Recording episode 0":** Rerun'da `top` ve `wrist` doğru mu, bir bakışta kontrol et. Sonra leader ile X'i alma yuvasından al, `middle right` hücresinin ortasına bırak, gripper'ı aç, kolu dinlenme pozuna getir, **→** bas.
4. **"Reset the environment":** Robotun koyduğu X'i alıp alma yuvasına geri koy. Tahtayı #1'e çevir, kol dinlenme pozunda kalsın, **→** bas.
5. **"Recording episode 1":** Aynı hareket. #2, #3 ve #4 için de 3–4. adımları tekrarla.
6. **#4'ten sonra** reset yok. Komut kendisi kapanır, dataset'i HF'e yükler.

Bir bölüm bozulursa (X düştü, yanlış yere gitti, taşa çarptı): **←** bas. Reset gelir; aynı tahtayı yeniden kur, aynı numara tekrar kaydedilir.

## Komut

Her blok bir çağrı. Değişen tek şey `--dataset.single_task` (tur dosyasında yazılı). İlk bloktan sonraki her çağrıya `--resume=true` eklenir.

```bash
cd ~/www/so101-xox && source .venv/bin/activate
lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/cu.usbmodem5AB01794851 --robot.id=follower --robot.calibration_dir=calibration \
  --robot.cameras="{ top: {type: opencv, index_or_path: 0, width: 640, height: 480, fps: 30}, wrist: {type: opencv, index_or_path: 1, width: 640, height: 480, fps: 30}}" \
  --teleop.type=so101_leader --teleop.port=/dev/cu.usbmodem5A7C1232561 --teleop.id=leader --teleop.calibration_dir=calibration \
  --dataset.repo_id=fport/tic-tac-toe-so101-x-round1 \
  --dataset.root=data/tic-tac-toe-so101-x-round1 \
  --dataset.single_task="put the red X in the middle right cell" \
  --dataset.num_episodes=5 --dataset.episode_time_s=40 --dataset.reset_time_s=90 \
  --dataset.streaming_encoding=true --dataset.encoder_threads=2 \
  --dataset.push_to_hub=true --dataset.private=true --dataset.no_stamp=true \
  --display_data=true
```

`--dataset.private=true` şart: verilmezse kişisel hesapta dataset public açılır. `--dataset.no_stamp=true` da şart: verilmezse lerobot repo adının sonuna tarih ekler (2026-10-06'daki ilk kayıt `fport/so101-xox_20261006_225957` olarak gitti, elle taşındı). Repo adları ve sonradan veri ekleme: [`operations.md`](operations.md) içindeki "Hugging Face" bölümü.

Komut yarıda kesilirse o ana kadar kaydedilen bölümler saklanır ve HF'e yüklenir. Kalanlar için aynı komut + `--resume=true`, `--dataset.num_episodes` = kalan bölüm sayısı.
