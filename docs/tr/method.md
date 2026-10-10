# Yöntem: robota XOX nasıl öğretilir

[English](../method.md) · **Türkçe**

2026-10-05 konuşmasından. İlk akla gelen planın neresi doğru, neresi düzeltilmeli.

## İlk akla gelen plan

Bir X'i alıp 9 kutuya koymayı göster, sonra 9 X'in her birini 9 kutuya tek tek koy, sonra aynısını O'lar için yap. Günün sonunda bu veriyle eğit: robot almayı ve koymayı öğrenir. Arkaya bir LLM bağla, akıllıca oynasın.

## Doğru olanlar

- **Hücre başına ayrı görev:** 9 hücre = 9 görev cümlesi.
- **O'ları da öğretmek:** Plandaki 7. adım.
- **Arkada LLM:** PDF'teki ve daha önce yapılmış açık bir SO-101 XOX projesindeki mimari de bu. LLM hücreyi seçer, robot koyar.

## Düzeltmeler

| İlk akla gelen | Gerçekte |
|---|---|
| "9 X'i tek tek 9 kutuya koyarım" | X'ler birbirinin aynısı; robot hangi X olduğuna bakmaz. Önemli olan **durum**: X nereden alınıyor, hangi hücreye gidiyor, tahtada ne var. X 6 farklı yuvadan alınırsa "yuva × hücre" = 54 durum olur, her birine veri gerekir. Tek alma yuvası bu yüzden. |
| "Her birini bir kere gösteririm" | Her durum onlarca tekrar ister. LeRobot: en az 50 bölüm, konum başına 10. Referans proje: 18 görev için 195 bölüm (görev başına ~11). |
| "Almayı ve koymayı ayrı öğrenir, sonra birleştirir" | Robot kavram öğrenmez; gördüğü durumda operatörün hareketini taklit eder. Görmediği durumda bocalar (ring-v2'de kamera açısı değişince kol dinlenme pozunda kaldı). Hep boş tahtada kaydedilirse dolu tahtada taşlara çarpar. Oyunda karşılaşacağı durumlar kayıtta olmalı. |
| "Hepsini kaydedip sonunda bir kere eğitirim" | Profesyonel iş döngüyle yürür: az kaydet, eğit, kolda dene, nerede hata yaptığına bak, tam oraya veri ekle, tekrar eğit. LeRobot: önce temel iş güvenilir çalışsın, varyasyonu sonra ekle; çok varyasyonu çok hızlı eklemek sonucu bozar. |
| "Çok veri = iyi" | Kalite sayıdan önemli. Hep aynı yol, X'i hep aynı yerinden tut, aynı hız, tereddüt yok. Kalitenin ana belirleyicisi operatörün aynı durumda hep aynı hareketi yapması (Belkhale vd.: "action divergence"). Kötü bölümler silinir. |
| "LLM bağlarsam akıllı oynar" | Akıllılık LLM'den gelir ama robot yalnızca eğitimde gördüğü cümleleri anlar; "köşeye koy" demek işe yaramaz. LLM hücreyi seçer, kod onu birebir eğitim cümlesine çevirir. LLM'ler XOX'ta kötü oynar, minimax kontrolü şart. Tahtayı görmek için de üst kameradan 9 hücreyi okuyan ayrı bir adım gerekir. |

## Profesyonel akış

1. **Sahneyi sabitle:** kamera, tahta, kol tabanı.
2. **Neyin değişeceğine karar ver:** Oyunda değişen hedef hücre ve tahtadaki taşlar, bunlar kayıtta çeşitlendirilir. Alma yeri ve ışık sabit.
3. **Pilot:** 45 bölüm. Sadece zincir testi: kayıt → HF → Colab → kolda deneme.
4. **Ana kayıt:** Hücre başına eşit sayıda (30–40), tutarlı gösterimler, kötüler silinir. Eşitlik önemli, yoksa model fazla kaydedilen hücreye kayar.
5. **Eğit ve ölç:** Eğitimde hiç görülmemiş tahta dizilimleriyle hücre başına başarı oranı.
6. **Hatalara hedefli veri:** Robot hata yapınca leader ile devral, düzeltme kaydedilir (`lerobot-rollout --strategy.type=dagger`).
7. **Kontrollü varyasyon:** O'lar, ışık, farklı alma yuvaları; her biri tek tek eklenip ölçülür.
8. **Oyun katmanı:** tahta okuma + LLM + minimax kontrolü.

## Kaynaklar

- [LeRobot: Imitation Learning on Real-World Robots](https://huggingface.co/docs/lerobot/il_robots) (kayıt ipuçları)
- [HF blog: What makes a good dataset](https://huggingface.co/blog/lerobot-datasets#what-makes-a-good-dataset)
- [Belkhale, Cui, Sadigh: Data Quality in Imitation Learning (NeurIPS 2023)](https://arxiv.org/abs/2306.02437)
- [Trossen Robotics: Robot Data Collection Best Practices](https://www.trossenrobotics.com/post/robot-data-collection-best-practices-imitation-learning)
