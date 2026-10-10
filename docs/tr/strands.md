# Strands Robots + Claude ile oyun katmanı

[English](../strands.md) · **Türkçe**

Kaynak: [GitHub](https://github.com/strands-labs/robots), [doküman](https://strands-labs.github.io/robots/). Kurulu sürüm: `strands-robots 0.5.3`, `strands-agents 1.59.0`.

Durum (2026-10-10): ortam kuruldu, betik yazıldı, sahte kolla (görüntüler gerçek bir koşudan oynatılarak) art arda iki hamle denendi. Gerçek kolda `move` iki kez çalıştı ve ikisi de tuttu (`top left`, `bottom left`); aynı akşam kolda Claude ile iki oyun oynandı, altı kol hamlesi, hepsi doğru hücrede, iki oyun da sonuna kadar oynanmadı ([`plan.md`](plan.md)).

Durum (2026-10-11): oyun kodu `scripts/strands_game.py` dosyasından `xox` paketine taşındı, `play` yerel bir dashboard'u sürüyor, ilk Ctrl+C kolu durduruyor ve dördüncü bir komut, `eval`, hücre başına değerlendirme yapıyor. Bunların hepsi sahte kol, sahte kameralar ve sahte bir Claude ile denendi; hiçbiri henüz gerçek kolda çalıştırılmadı.

## Mimari

```
Claude (Strands Agent)  →  hücre seçer: place_x("top left")
kod                     →  birebir eğitim cümlesi: "put the red X in the top left cell"
Strands Robot + politika →  SmolVLA kolu oynatır
```

Claude kolu doğrudan sürmez, sadece hücre seçer. Politika yalnızca eğitimde gördüğü 9 cümleyi anlar; cümleyi kod üretir ([`method.md`](method.md)). Claude'a Strands'in ham `so101` aracı verilmiyor, çünkü o araç serbest metin ve serbest `policy_config` alıyor. Onun yerine tek parametreli `place_x(cell)` aracı var; dolu ya da bilinmeyen hücreyi reddediyor.

## Kod nerede

Oyun, repo kökündeki `xox` paketi. `scripts/strands_game.py` ince bir sarmalayıcı: repo kökünü import yoluna ekleyip paketi çağırıyor; repo kökünden çalıştırılan `python -m xox <komut>` aynı program.

| Dosya | İçinde ne var |
|---|---|
| `xox/board.py` | Hücre adları, görev cümlesi, tahtanın terminal çizimi, kazanan |
| `xox/vision.py` | Üst kameranın oyuna söyledikleri: alma yuvası, değişen hücre ve hareket için piksel kontrolleri, Claude'un tahta okuması ve `eval` için konma ölçümü |
| `xox/arm.py` | Strands robotu ve SmolVLA politikası, hamle başına kayıt, kameralar |
| `xox/game.py` | `play` döngüsü: ajan, `place_x` aracı, dashboard durumu, `game.jsonl`, Durdur ve Ctrl+C |
| `xox/evaluate.py` | `eval` komutu |
| `xox/cli.py` | Dört komut ve bayrakları |
| `xox/i18n.py` | İngilizce ve Türkçe terminal mesajları |
| `xox/state.py` | Oyun döngüsü ile dashboard arasında paylaşılan oyun durumu |
| `xox/dashboard/` | Yerel web sayfası ve sunucusu; `python -m xox.dashboard --demo` onu tek başına çalıştırır |

## Kurulum

Ayrı ortam, repodaki `.venv`'e dokunmaz:

```bash
cd ~/www/so101-xox
uv venv .venv-strands --python 3.12
source .venv-strands/bin/activate
uv pip install "strands-robots[lerobot,smolvla]" "strands-agents[anthropic]"
```

`strands-robots doctor` üç şeyde FAIL veriyor, üçü de bize lazım değil: `mujoco` (simülasyon), `torchcodec` (video çözme), simülasyon duman testi.

## Kullanım

```bash
cd ~/www/so101-xox && source .venv-strands/bin/activate   # ya da doğrudan .venv-strands/bin/python ile çağır

# 1. Ajan yok, tek hamle (Strands bağlantısını dener); kol oynamadan önce onay ister
python scripts/strands_game.py move "middle center"

# 2. Claude X, sen O (anahtar repo kökündeki .env dosyasından okunur: ANTHROPIC_API_KEY=...)
python scripts/strands_game.py play

# 3. Yalnızca üst kameradan tahtayı okur; kol oynamaz (anahtar bunda da gerekir)
python scripts/strands_game.py board

# 4. Kolda hücre başına değerlendirme, Claude ve anahtar olmadan (aşağıda "Hücre başına değerlendirme")
python scripts/strands_game.py eval

# Sarmalayıcı betik olmadan aynı program
python -m xox play
```

Seçenekler komut adından sonra yazılır:

| Bayrak | Komut | Ne yapar |
|---|---|---|
| `--model` | hepsi | HF repo ya da yerel checkpoint klasörü |
| `--port` | hepsi | follower portu |
| `--top`, `--wrist` | hepsi | kamera index'leri |
| `--duration` | hepsi | hamle başına en çok saniye, varsayılan 45 |
| `--device` | hepsi | varsayılan `mps` |
| `--dry-run` | hepsi | kolu oynatmaz, yalnızca akışı gösterir |
| `--lang en\|tr` | hepsi | terminal mesajlarının dili, varsayılan `en`; `XOX_LANG=tr` ortam değişkeni de olur |
| `--claude` | `play`, `board` | Claude model adı |
| `--first x\|o` | `play` | kim başlar |
| `--confirm` | `play` | kamera algılaması yerine her adımda sorar |
| `--no-dashboard`, `--dashboard-port`, `--no-open` | `play`, `eval` | aşağıda "Dashboard" |
| `--image`, `--save` | `board` | kamera yerine bir görüntü dosyasını okur; Claude'a gönderilen kırpımı yazar |
| `--trials`, `--cells`, `--seed`, `--report` | `eval` | aşağıda "Hücre başına değerlendirme" |

İlk yedisini her komut kabul eder; `board` bunlardan yalnızca `--top` ve `--lang` bayraklarını kullanır.

**Bir hamle.** Kol hücreye gidip dinlenme pozuna dönünce (omuz ve dirsek başlangıca 8° içinde, 1,5 sn boyunca) kod hamleyi süre dolmadan bitirir; dönmezse `--duration` (varsayılan 45 sn) dolunca biter. `move` kol oynamadan önce onay ister. `play` hamleden önce sormaz (aşağıda "Otomatik oyun"); yalnızca hamleden sonraki kamera kontrolü başarısız olursa sorar. `--confirm` ile ilk günkü gibi davranır: her hamleden önce sorar, hamleden sonra X'in hücreye konup konmadığını sorar, O hamlesini de sen terminale yazarsın. Oyunun sonunda isabet sayısını yazar. `--dry-run` ile `play` kolu oynatmaz, dashboard başlatmaz, kayıt yazmaz; O hamlelerini sen yazarsın.

**Dashboard.** `play` ve `eval` yerel bir web sayfası başlatır, adresini yazar (varsayılan `http://127.0.0.1:8765/`) ve tarayıcıda açar. Sayfa iki kamerayı, tahtayı, sıranın kimde olduğunu, Claude'un cümlesini, hamle listesini, olayları ve bir Durdur düğmesini gösterir; İngilizce ile Türkçe arasında değiştirilebilir. `--dashboard-port` başka bir port seçer (0 = boş olan herhangi biri), `--no-open` tarayıcıyı açmaz, `--no-dashboard` sayfayı başlatmaz. Port doluysa bir mesaj yazılır ve oyun dashboard olmadan devam eder. `move` ve `board` dashboard başlatmaz. `python -m xox.dashboard --demo` sayfayı tek başına, hazır yazılmış sahte bir oyunla çalıştırır (kendi bayrakları: `--host`, `--port`, `--speed` ve bir hamlenin kayıtlı kareleri için `--frames DIR`; kayıtlı kare yoksa yer tutucu kareler çizer). Dashboard şimdiye kadar yalnızca sahte kolla ve bu yeniden oynatmayla çalıştırıldı.

**Durdurmak.** `play` ve `eval` sırasında ilk Ctrl+C kolu hemen durdurur: bir sinyal işleyicisi durdurma işaretini verir ve kesmeyi başka hiçbir şey görmeden robota durmasını söyler. Strands, bir araç çalışırken gelen ilk Ctrl+C'yi yutuyor; işleyici yokken kol hamlesini bitiriyordu. Bu, sahte kolla denendi; gerçek kolda henüz denenmedi. Dashboard'daki Durdur düğmesi çalışmayı aynı yoldan bitirir. `--confirm` modunda oyunun bitmesi için terminaldeki bir sorunun yine de cevaplanması gerekir. `move` komutunda Ctrl+C kolu durdurur. Kol bağlandıysa, bağlantı kapatılmadan önce terminal her seferinde Enter ister: kapatınca tork kesilir, bu yüzden kol dinlenme pozunda değilse elinle tut.

**Kayıtlar.** Her çalıştırma için bir `outputs/strands_logs/<zaman>/` klasörü açılır. Her hamlenin bunun içinde kendi klasörü olur, `moveNN_<hücre>/`: komutlar ve parça başına bir gözlem (`steps.jsonl`) ile `top` / `wrist` kareleri. `play` için hamle klasörlerinin yanına `game.jsonl` yazılır: olay başına bir satır (aşamalar, Claude'un seçimi ve cümlesi, her hamle ve ardındaki tahta, durdurma). `eval` kendi klasörüne yazar, aşağıya bak.

## Otomatik oyun (2026-10-10)

`play` artık soru sormuyor (eski davranış: `--confirm`). Bir tur şöyle işliyor:

1. Claude hücreyi seçer.
2. Kod üst kameradan alma yuvasına bakar (`SLOT_BOX` içinde kırmızı var mı). Boşsa "yuvaya X koy" der ve bekler; X görünüp görüntü 1 sn kıpırdamayınca 2 sn sayıp kolu oynatır.
3. Kol dinlenmeye dönünce Claude tahtayı okur: X hedef hücredeyse isabet sayılır, değilse elle düzeltmen istenir.
4. Sıra sende: O'nu koyarsın. Kod kareleri yerelde karşılaştırır (API çağrısı yok); bir hücre değişip görüntü durulunca Claude'a okutur ve tek yeni O'yu hamlen sayar. Bulamazsa beklemeye devam eder; Enter tekrar okutur, hücre adı yazmak elle girer. O'yu kol daha dönerken koyarsan 3. adımdaki doğrulama okuması onu zaten görür ve beklemeden oradan alınır. 30 sn boyunca değişiklik görülmezse Claude tahtayı yine de okur.

Yerel eşikler gerçek karelerden ölçüldü: aynı sahnede hücre farkı ~2, yeni taşta 16–22 (8 hücrede ölçüldü; eşik 8); kol ya da el oynarken blok farkı 25–54, dururken ~2 (eşik 6); yuvada X varken kırmızı oranı 0,045–0,30 (16 kare), boşken 0,00 (eşik 0,015). Dinlenen tutucunun altındaki bir hücre, tutucu farklı bir pozda durunca yeni taş olmadan 30'a kadar çıktı; tetiklenen okumada kararı yine Claude'un vermesinin sebebi bu.

Oyun başına Claude görüntü okuması: kol hamlesi başına bir (doğrulama) ve O hamlesi başına bir; beş hamlelik sahte oyunda 9.

Denenenler: yerel algılama gerçek karelerle; tam akış sahte kol + sahte ajan + sahte okumayla (soru sorulmadan bitiyor). Gerçek kolda (2026-10-10 22:58) bir otomatik oyun oynandı: üç kol hamlesi, üçü de doğru hücrede doğrulandı, bitmeden durduruldu; erken O kısayolu ve 30 sn'lik yeniden bakma bundan sonra eklendi ve yalnızca sahte kolla çalıştı. Bilinen zayıflık: `bottom center` hücresi dinlenen tutucunun altında kalıyor, oradaki X doğrulamada "göremedim" diyebilir.

## Tahtayı kameradan okuma (2026-10-10)

Oyunda O hamlesi artık yazılmak zorunda değil: kod `top` kamerasından kare alır (yukarıdaki otomatik oyunda kendiliğinden; Enter hemen okutur), robotun bakışına çevirir (180°), ızgaraya kırpar (`BOARD_BOX`) ve Claude'a gösterir; Claude 9 hücreyi `report_board` aracıyla bildirir. Kod bunu bildiği tahtayla karşılaştırır: tam bir yeni O varsa ve geri kalan her şey aynıysa kabul eder, değilse sorar ya da elle yazdırır. Hücre adını yazmak hâlâ mümkün.

```bash
.venv-strands/bin/python scripts/strands_game.py board            # kolu oynatmadan tahtayı oku
.venv-strands/bin/python scripts/strands_game.py board --image outputs/live/top_4.png
```

- Gerçek koşulardan 8 kare (boş tahta, 1–4 taş, biri tutucunun yarı kapattığı X) ikişer kez okutuldu: 16/16 tam doğru, okuma başına 3–8 sn (`claude-opus-5-5`).
- Denenmeyen: `bottom center` hücresindeki taş. Dinlenme pozunda tutucu o hücrenin büyük kısmını kapatıyor.
- `claude-opus-5-5` zorunlu araç seçimini (`tool_choice` `tool` / `any`) kabul etmiyor; araç serbest bırakıldı, bildirmezse elle girişe düşülüyor.
- `BOARD_BOX` sabit; kamera ya da tahta oynarsa `board --save kirpim.png` ile bakıp güncellenir.
- Canlı kameradan okuma denendi (2026-10-10 22:10): 5 taşlı tahta (2 O, 3 X, biri tutucunun yanında) tam doğru okundu.

## Hücre başına değerlendirme: `eval` (2026-10-11)

`eval` koldan her hücreyi birkaç kez ister ve X'in nereye konduğuna üst kameradan karar verir. Claude da API anahtarı da kullanmaz. Yalnızca sahte kol ve montaj karelerle denendi; gerçek kolda henüz çalıştırılmadı, dolayısıyla ondan gelen bir sonuç yok.

```bash
python scripts/strands_game.py eval                                  # her hücre 3 kez
python scripts/strands_game.py eval --trials 10                      # her hücre 10 kez
python scripts/strands_game.py eval --cells "top left" "top right"   # yalnızca bu hücreler
python scripts/strands_game.py eval --dry-run --trials 2             # planı ve kuralları yazar, hiçbir şey açmaz
python scripts/strands_game.py eval --report outputs/eval/<zaman>    # daha önceki bir çalışmanın tablosunu yazar
```

- `--trials`: hücre başına hamle sayısı, varsayılan 3.
- `--cells`: yalnızca bu hücreler.
- `--seed`: karıştırılmış hamle sırasının tohumu, varsayılan 0. Aynı tohum aynı sırayı verir.
- `--report RUN`: yalnızca daha önceki bir çalışmanın tablosunu yazar, klasöründen ya da `results.jsonl` dosyasından; kol kullanılmaz.
- Bütün komutların ortak bayrakları ve üç dashboard bayrağı `play`'deki gibi çalışır.

**Operatörün yapacakları.**

1. Tahtayı boşalt (üstünde X ya da O kalmasın), kolu dinlenme pozunda bırak, alma yuvasına bir X koy ve Enter'a bas. Kod boş tahtanın referans karesini alır; ellerini kameranın görüş alanından çek. Tahtada kırmızı bir taş görürse başlamaz.
2. Tahta boşalıp yuvada X olunca ve hiçbir şey kıpırdamayınca kol 2 sn sonra kendiliğinden başlar.
3. Kol dönünce bir sonuç satırı yazılır: isabet ya da ıska, X'in bulunduğu hücre, istenen hücrenin merkezinden sapması ve hamlenin süreleri.
4. Her sonuç satırından sonra X'i tahtadan al ve alma yuvasına geri koy. Satırdan önce değil: kamera o sırada hâlâ ölçüyor.
5. Ctrl+C ya da dashboard'daki Durdur çalışmayı bitirir ve o ana kadarki sonuçları saklar. Sonunda hücre başına isabet tablosu yazılır.

**Çıktı.** Bir çalışmanın her şeyi `outputs/eval/<zaman>/` altına gider:

| Dosya | İçerik |
|---|---|
| `results.jsonl` | Hamle başına bir satır, çalışma ilerledikçe eklenir |
| `summary.json` | Ayarlar, eşikler, hücre başına isabet ve her alanın anlamı; her hamleden sonra yeniden yazılır |
| `reference.jpg` | Çalışmanın başladığı boş tahta |
| `before_NN.jpg`, `after_NN.jpg` | NN. hamleden önceki ve sonraki üst kamera karesi |
| `moveNN_<hücre>/` | Kolun o hamle için kendi kaydı (`steps.jsonl`, `top` / `wrist` kareleri) |
| `events.jsonl` | Terminalin ve dashboard'un gösterdikleri |

**Konma nasıl değerlendiriliyor.** Kod, tahta kutusunun (`BOARD_BOX`) içinde, boş tahtanın referans karesine göre yeni olan kırmızıyı arar; kenar gürültüsüne karşı referanstaki kırmızı önce birkaç piksel genişletilir (`REFERENCE_MARGIN`). Tutucunun turuncu parçası aynı kırmızı kuralından geçiyor, alt sıranın üstünde duruyor ve hiçbir zaman tam aynı yerde durmuyor; bu yüzden referansı çıkarmak yetmiyor: yalnızca en az 1100 yeni kırmızı pikselden oluşan bir öbek (`MIN_PIECE_PIXELS`) taş sayılır. Kayıtlı karelerde bir X, kol dinlenirken 1650–2060, kol bir kısmını hâlâ örterken en az 1340 kırmızı piksel gösteriyor; tutucunun turuncu parçası 490–610 gösteriyor ve bunun 690'a kadarı bir referansa göre yeni çıkıyor. Taşın merkezinin bulunduğu hücre, X'in konduğu hücredir; bu, istenen hücreyse hamle isabettir. İstenen hücrenin merkezinden sapma piksel ve hücre genişliği cinsinden bildirilir.

**Sınırlar, kodda yazdığı hâliyle.**

- Yalnızca boş tahta. Referans boş tahtadır ve her hamle ondan başlar; oyundaki gibi üstünde başka taşlar olan başlangıç tahtaları kapsanmıyor.
- `near_gripper`, taş tutucunun referansta durduğu yere 40 px (`GRIPPER_REACH`) içinde olduğunda işaretlenir. O zaman taşın bir kısmı gizlenmiş ya da tutucunun bir kısmı taşla birlikte sayılmış olabilir, merkez de daha az kesindir. Dinlenen tutucu `bottom center` ve `bottom right` hücrelerini kısmen örtüyor.
- `touches_edge`, taş tahta kutusunun kenarına değdiğinde işaretlenir: bir kısmı dışarıda kalmış olabilir, merkez daha az kesindir.
- Yeterince büyük bir öbek yoksa sonuç `none`, birden fazla varsa `several` olur; ikisi de ıska sayılır.
- X'in merkezi ölçülür, dönüklüğü ölçülmez.
- Eşikler kayıtlı karelerden geliyor. Koldaki bir çalışmada nasıl dayanacakları henüz bilinmiyor.

## Denenenler (kol olmadan)

| Ne | Sonuç |
|---|---|
| Politika Strands üzerinden yükleniyor mu | Evet. `create_policy("lerobot_local", embodiment="so101_real", device="mps", obs_rename_override=...)` |
| Kayıtlı karede tahmin (15k ve son model) | 50 adımlık parça, 0,35 sn. Kayıttaki hareketle ortalama fark 0,4–1,6°, `lerobot` yolundakiyle aynı seviye. Bu eğitim verisi; kolda başarıyı göstermez. |
| `Robot(...)` kurulumu | Kuruluyor, kalibrasyon dosyasını buluyor, bağlantıyı ilk harekete bırakıyor. |
| Sahte portla tam yol | Politika yükleniyor, porta gelince düzgün hata veriyor. |
| Oyun döngüsü | Sahte ajanla kuru modda: dolu hücre, bilinmeyen hücre ve aynı turda ikinci hamle reddediliyor, kazanan bulunuyor. |
| Claude ile gerçek çağrı | Kuru modda tam oyun oynandı (2026-10-10, `claude-opus-5-5`): her turda `place_x`'i bir kez çağırdı, engelledi ve kazandı. |

## Yanlışlıkla gerçek kolda koşu (2026-10-10 21:28)

Sahte kol testi yazarken yama tutmadı ve betik varsayılan portla gerçek kola bağlandı; onay sorusuna test girdisi "e" dedi. Kol 45 sn tork altında kaldı ve politika komut gönderdi. Hedef hücrede (`middle center`) önceki koşudan X durduğu için model "iş bitmiş" gördü: komutlar dinlenme pozundan en çok 5° (bilek) oynadı, kol yerinden kalkmadı. Kayıt: `outputs/strands_gunluk/20261010-212846` (klasörün o günkü adı; yeni kayıtlar `outputs/strands_logs/` altına yazılır).

Ders: kol olmadan yapılan her test `--port /dev/cu.YOK` ile çalıştırılır. Yan bulgular: Strands döngüsünde adım aralığı 35 ms (~28,5 Hz), parça başına ~2,15 sn; hedef hücre doluyken model yerinde kalıyor.

## Öğrenilenler

- **Kamera adları:** `so101_real` embodiment'ı `front` / `wrist` bekliyor ve `observation.images.image`'e çeviriyor. Bizim checkpoint `camera1` / `camera2` istiyor; `obs_rename_override={"top": "...camera1", "wrist": "...camera2", "front": None}` ile çözüldü.
- **Kontrol hızı:** Varsayılan 50 Hz. Veri 30 fps, bu yüzden `control_frequency=30.0` veriliyor.
- **`calibration_dir`:** `Path` olmalı, metin verince `lerobot` hata veriyor.
- **`max_relative_target`:** Sürücü kendiliğinden uygulamıyor, vermezsen kapalı. Vermiyoruz (dirseği kilitliyor, [`operations.md`](operations.md) "Bilinen tuzaklar").
- **Cihaz:** `device="mps"` açıkça verilmeli; Strands CUDA yoksa CPU'ya düşüyor.
- **Süreç yeniden başlıyor:** macOS'ta `import strands_robots`, `torchcodec` için süreci baştan başlatıyor; betik soruları iki kez soruyordu. `STRANDS_ROBOTS_NO_DYLD_SHIM=1` ile kapatıldı.
- **Onay kapısı:** Strands'in kapısı yalnızca ajan aracı yolunda (`execute` / `start`). Biz `robot.run_policy(...)` çağırıyoruz, o kapıdan geçmiyor; onayı kod kendi soruyor: `move` komutunda her zaman, `play` komutunda yalnızca `--confirm` ile.
- **Kapanış:** `cleanup()` bağlantıyı kesince tork kapanıyor. Kayıtlarda kol başladığı dinlenme pozuna dönüyor, politika da dönmeli; kod kapatmadan önce Enter istiyor ki kol orada değilse elle tutulabilsin.

## Açık sorular (kolda görülecek)

- Döngü senkron: her 50 adımda (1,7 sn) yeni parça için ~0,4 sn duruyor. Bu, kolda iyi çalışan `lerobot-rollout --inference.type=sync` ile aynı davranış (2026-10-10); kuyruklu ayar kolu sıçratıyordu.
- Döngü her adımdan sonra 1/30 sn uyuyor ve yazma süresini düşmüyor; gerçek hız 30 Hz'in biraz altında kalır.
- 2026-10-10'da cevaplandı: hamle artık sabit süre koşmuyor; kol dinlenmeye dönünce bitiyor, kolda hamle başına 17–28 sn ölçüldü.
- macOS'ta kamera index kayması aynen geçerli; her oturumda `lerobot-find-cameras`.

## Sıra

1. Model önce düz `lerobot-rollout` ile kolda denenir (komut [`plan.md`](plan.md)'de). Politikanın tek başına ne yaptığını bilmeden Strands'e geçersek hata politikada mı köprüde mi ayıramayız.
2. `strands_game.py move` ile tek hamle.
3. `strands_game.py play` ile Claude.
4. Tahta okuma ve minimax.
5. `strands_game.py eval` ile hücre başına değerlendirme.

## Strands'in bizim kullanmadığımız kısımları

Simülasyon (MuJoCo, Isaac), kayıt ve `verify-dataset`, bölüm etiketleme, eğitim sarmalayıcıları, filo ağı, Strands'in kendi tarayıcı panosu, ROS 2 köprüleri. `play`'in açtığı dashboard bu projenin kendi kodu (`xox/dashboard/`), Strands ile gelen pano değil; Strands panosunun burada anıldığı işi, kameraları tek ekranda görmeyi, artık o yapıyor. İleride işe yarayabilecek: `verify-dataset` (tur 2 kayıtlarını kontrol).
