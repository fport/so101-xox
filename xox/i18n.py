"""Terminal messages of the game in English and Turkish.

English is the default; `--lang tr` or XOX_LANG=tr selects Turkish. The same texts are reused for
the dashboard's event log and for `game.jsonl`.
"""

import os

MESSAGES = {
    "board_far_side": {
        "en": "          far from robot (top)",
        "tr": "          robottan uzak (top)",
    },
    "board_not_reported": {
        "en": "Claude did not report the board with the tool",
        "tr": "Claude tahtayı araçla bildirmedi",
    },
    "slot_empty": {
        "en": "The pick slot is empty: put an X in the slot, the arm is waiting.",
        "tr": "Alma yuvası boş: yuvaya bir X koy, kol bekliyor.",
    },
    "your_turn": {
        "en": "Your turn: place your O, the camera will see it. "
        "(Type the cell name to enter it by hand; Enter = read now.)",
        "tr": "Senin sıran: O'nu koy, kamera görecek. (Elle girmek için hücre adını yaz; Enter = şimdi oku.)",
    },
    "not_allowed": {
        "en": "Not allowed. Empty cells: {cells}",
        "tr": "Olmaz. Boş hücreler: {cells}",
    },
    "read_failed_type": {
        "en": "Could not read the board ({error}). You can type the cell name by hand.",
        "tr": "Tahta okunamadı ({error}). Hücre adını elle yazabilirsin.",
    },
    "camera_o": {
        "en": "Camera: O is in the {cell} cell.",
        "tr": "Kamera: O {cell} hücresinde.",
    },
    "no_single_o": {
        "en": "I could not see exactly one new O (the board I saw is above). Waiting; Enter = read again.",
        "tr": "Tek bir yeni O göremedim (gördüğüm tahta yukarıda). Bekliyorum; Enter = tekrar oku.",
    },
    "read_failed": {
        "en": "Could not read the board ({error}).",
        "tr": "Tahta okunamadı ({error}).",
    },
    "x_landed": {
        "en": "Did the X land in the {cell} cell?",
        "tr": "X {cell} hücresine kondu mu?",
    },
    "camera_x": {
        "en": "Camera: X is in the {cell} cell.",
        "tr": "Kamera: X {cell} hücresinde.",
    },
    "x_not_seen": {
        "en": "I could not see the X in the {cell} cell. Fix it by hand, then press Enter: ",
        "tr": "X'i {cell} hücresinde göremedim. Elle düzelt, sonra Enter: ",
    },
    "yes_no": {
        "en": "[y/n]",
        "tr": "[e/h]",
    },
    "loading_policy": {
        "en": "Loading policy: {model}",
        "tr": "Politika yükleniyor: {model}",
    },
    "task_sentence": {
        "en": "\nTask sentence: {task}",
        "tr": "\nGörev cümlesi: {task}",
    },
    "dry_run": {
        "en": "dry run, the arm was not moved",
        "tr": "kuru çalışma, kol oynatılmadı",
    },
    "confirm_move": {
        "en": "Is there an X in the X slots and is the target cell empty? The arm will move.",
        "tr": "X yuvalarında X var, hedef hücre boş mu? Kol hareket edecek.",
    },
    "not_confirmed": {
        "en": "the operator did not confirm",
        "tr": "operatör onaylamadı",
    },
    "stopped_ctrl_c": {
        "en": "the operator stopped it with Ctrl+C",
        "tr": "operatör Ctrl+C ile durdurdu",
    },
    "returned_to_rest": {
        "en": "The arm returned to the rest pose; the move took {seconds:.0f} s.",
        "tr": "Kol dinlenme pozuna döndü, hamle {seconds:.0f} sn sürdü.",
    },
    "time_ran_out": {
        "en": "Time ran out ({seconds:.0f} s); the arm did not return to the rest pose.",
        "tr": "Süre doldu ({seconds:.0f} sn); kol dinlenme pozuna dönmedi.",
    },
    "closing": {
        "en": "Closing cuts the torque. If the arm is not in the rest pose, hold it by hand, then press Enter: ",
        "tr": "Kapatınca tork kesilir. Kol dinlenme pozunda değilse elinle tut, sonra Enter: ",
    },
    "log_folder": {
        "en": "Log: {folder}",
        "tr": "Kayıt: {folder}",
    },
    "move_not_played": {
        "en": "The move was not played: {reason}",
        "tr": "Hamle oynanmadı: {reason}",
    },
    "no_api_key": {
        "en": "ANTHROPIC_API_KEY is not set. Add a line ANTHROPIC_API_KEY=... to the file {path}.",
        "tr": "ANTHROPIC_API_KEY tanımlı değil. {path} dosyasına ANTHROPIC_API_KEY=... satırı ekle.",
    },
    "arm_plays_soon": {
        "en": "The arm plays in 2 s: {cell} (Ctrl+C stops it)",
        "tr": "Kol 2 sn sonra oynuyor: {cell} (Ctrl+C durdurur)",
    },
    "put_x_by_hand": {
        "en": "Put the X in the {cell} cell by hand, then press Enter: ",
        "tr": "X'i elle {cell} hücresine koy, sonra Enter: ",
    },
    "claude_failed": {
        "en": "\nThe Claude call failed, the game stopped: {error}",
        "tr": "\nClaude çağrısı başarısız, oyun durdu: {error}",
    },
    "claude_no_move": {
        "en": "Claude did not make a move, the game stopped.",
        "tr": "Claude hamle yapmadı, oyun durdu.",
    },
    "move_cancelled": {
        "en": "The move was cancelled, the game stopped.",
        "tr": "Hamle iptal edildi, oyun durdu.",
    },
    "your_move": {
        "en": "Your move (O), e.g. top left: ",
        "tr": "Senin hamlen (O), ör. top left: ",
    },
    "winner": {
        "en": "Winner: {winner}",
        "tr": "Kazanan: {winner}",
    },
    "draw": {
        "en": "Draw.",
        "tr": "Berabere.",
    },
    "arm_accuracy": {
        "en": "Arm accuracy: {hits}/{total}",
        "tr": "Kol isabeti: {hits}/{total}",
    },
    "hit": {
        "en": "hit",
        "tr": "tuttu",
    },
    "missed": {
        "en": "missed",
        "tr": "ıskaladı",
    },
    "ctrl_c": {
        "en": "\nCtrl+C: the arm was stopped.",
        "tr": "\nCtrl+C: kol durduruldu.",
    },
    "wrong_venv": {
        "en": "This script runs in the .venv-strands environment; a different Python is being used right now.\n"
        "Run it like this: {python} scripts/strands_game.py ...",
        "tr": "Bu betik .venv-strands ortamında çalışır, şu an başka bir Python kullanılıyor.\n"
        "Şöyle çalıştır: {python} scripts/strands_game.py ...",
    },
    # --- stop, dashboard and event-log texts ---
    "stopped": {
        "en": "the operator stopped it",
        "tr": "operatör durdurdu",
    },
    "stop_pressed": {
        "en": "\nStop was pressed on the dashboard: the arm was stopped.",
        "tr": "\nDashboard'da Durdur'a basıldı: kol durduruldu.",
    },
    "dashboard_url": {
        "en": "Dashboard: {url}",
        "tr": "Dashboard: {url}",
    },
    "dashboard_failed": {
        "en": "The dashboard could not start on port {port} ({error}). "
        "The game goes on without it; --dashboard-port picks another port.",
        "tr": "Dashboard {port} portunda başlatılamadı ({error}). "
        "Oyun dashboard olmadan devam ediyor; --dashboard-port ile başka bir port seçebilirsin.",
    },
    "claude_picked": {
        "en": "Claude picked the {cell} cell.",
        "tr": "Claude {cell} hücresini seçti.",
    },
    "slot_filled": {
        "en": "There is an X in the pick slot.",
        "tr": "Alma yuvasında X var.",
    },
    "x_missing": {
        "en": "Camera: no X in the {cell} cell.",
        "tr": "Kamera: {cell} hücresinde X yok.",
    },
    "x_fixed_by_hand": {
        "en": "The X was put in the {cell} cell by hand.",
        "tr": "X {cell} hücresine elle kondu.",
    },
    "operator_says": {
        "en": "Operator: {cell} {verdict}.",
        "tr": "Operatör: {cell} {verdict}.",
    },
    "o_typed": {
        "en": "O entered by hand: {cell}.",
        "tr": "O elle girildi: {cell}.",
    },
    # --- the eval command ---
    "eval_plan": {
        "en": "Evaluation: {total} moves, {trials} per cell on {cells} cells (seed {seed}).",
        "tr": "Değerlendirme: {total} hamle, {cells} hücrede hücre başına {trials} (seed {seed}).",
    },
    "eval_order": {
        "en": "Order: {order}",
        "tr": "Sıra: {order}",
    },
    "eval_clear_board": {
        "en": "Clear the board (no X and no O on it), leave the arm in the rest pose and put one X in the "
        "pick slot. Then press Enter: ",
        "tr": "Tahtayı boşalt (üstünde X ya da O kalmasın), kolu dinlenme pozunda bırak ve alma yuvasına "
        "bir X koy. Sonra Enter: ",
    },
    "eval_reference": {
        "en": "Taking the reference picture of the empty board: keep your hands out of the camera's view.",
        "tr": "Boş tahtanın referans karesi alınıyor: ellerini kameranın görüş alanından çek.",
    },
    "eval_not_empty": {
        "en": "The board is not empty: the camera sees a red piece in {cells}. Take it off and start again.",
        "tr": "Tahta boş değil: kamera {cells} hücresinde kırmızı bir taş görüyor. Onu kaldırıp yeniden başlat.",
    },
    "eval_rules": {
        "en": "After each result line: take the X off the board and put it back in the pick slot (not before "
        "the line, the camera is still measuring). The arm starts by itself 2 s after the board is empty, "
        "the slot has an X and nothing moves.\n"
        "Ctrl+C or Stop on the dashboard ends the run; the results so far are kept.",
        "tr": "Her sonuç satırından sonra: X'i tahtadan al ve alma yuvasına geri koy (satırdan önce değil, "
        "kamera o sırada ölçüyor). Tahta boşalıp yuvada X olunca ve görüntü durunca kol 2 sn sonra "
        "kendiliğinden başlar.\n"
        "Ctrl+C ya da dashboard'daki Durdur çalışmayı bitirir; o ana kadarki sonuçlar saklanır.",
    },
    "eval_take_x": {
        "en": "Waiting: there is still a red piece on the board ({where}). Take it off.",
        "tr": "Bekliyorum: tahtada hâlâ kırmızı bir taş var ({where}). Onu kaldır.",
    },
    "eval_start": {
        "en": "[{n}/{total}] {cell}: the arm plays in 2 s (Ctrl+C stops it)",
        "tr": "[{n}/{total}] {cell}: kol 2 sn sonra oynuyor (Ctrl+C durdurur)",
    },
    "eval_landed": {
        "en": "X in {landed}, {dx:+.0f}, {dy:+.0f} px from the centre of {cell} "
        "({fx:+.2f}, {fy:+.2f} of a cell), {pixels} red px",
        "tr": "X {landed} hücresinde, {cell} merkezinden {dx:+.0f}, {dy:+.0f} px "
        "({fx:+.2f}, {fy:+.2f} hücre), {pixels} kırmızı px",
    },
    "eval_near_gripper": {
        "en": " (next to the resting gripper: the centre is less exact)",
        "tr": " (duran tutucunun yanında: merkez daha az kesin)",
    },
    "eval_at_edge": {
        "en": " (at the edge of the board: part of the X may be outside)",
        "tr": " (tahtanın kenarında: X'in bir kısmı dışarıda olabilir)",
    },
    "eval_none": {
        "en": "no X seen on the board ({pixels} new red px)",
        "tr": "tahtada X görülmedi ({pixels} yeni kırmızı px)",
    },
    "eval_several": {
        "en": "{count} red pieces on the board, cannot tell which one is new",
        "tr": "tahtada {count} kırmızı taş var, hangisinin yeni olduğu anlaşılmıyor",
    },
    "eval_timing": {
        "en": "left rest after {leave} s, {seconds} s in all, largest jump {jump}°, {ended}",
        "tr": "{leave} sn'de dinlenme pozundan ayrıldı, toplam {seconds} sn, en büyük sıçrama {jump}°, {ended}",
    },
    "eval_returned": {
        "en": "returned to rest",
        "tr": "dinlenme pozuna döndü",
    },
    "eval_timeout": {
        "en": "time ran out",
        "tr": "süre doldu",
    },
    "eval_table": {
        "en": "Hits per cell (hits/moves):",
        "tr": "Hücre başına isabet (isabet/hamle):",
    },
    "eval_total": {
        "en": "Hits: {hits}/{done}. {done} of the {total} planned moves were played.",
        "tr": "İsabet: {hits}/{done}. Planlanan {total} hamlenin {done} tanesi oynandı.",
    },
    "eval_saved": {
        "en": "Results: {folder}",
        "tr": "Sonuçlar: {folder}",
    },
    "eval_no_results": {
        "en": "No results in {path}.",
        "tr": "{path} içinde sonuç yok.",
    },
}

LANG = os.environ.get("XOX_LANG", "en").strip().lower()
if LANG not in ("en", "tr"):
    LANG = "en"


def set_language(lang: str) -> None:
    """Selects the language `t()` answers in (the `--lang` flag ends up here)."""
    global LANG
    LANG = lang


def t(key: str, **fmt) -> str:
    """Message `key` in the selected language."""
    return MESSAGES[key][LANG].format(**fmt)


def yes(question: str) -> bool:
    """Asks a yes/no question; accepts e/evet/y/yes in either language."""
    return input(f"{question} {t('yes_no')} ").strip().lower() in ("e", "evet", "y", "yes")
