# -*- coding: utf-8 -*-
r"""
ЛУПОВЫЙ режим для Mount & Blade II Bannerlord (без фрагментации).

Для каждого MP3:
  - берёт LOOP_COUNT лучших по score точек лупа (непохожих друг на друга);
  - loop_01 — лучший («идеальный») луп: к нему привязаны intro и outro;
  - loop_02.., loop_03.. — альтернативные лупы;
  - intro  = [начало трека .. начало лупа 1];
  - outro  = несколько проходов лупа 1 + натуральный хвост, добитый до ~1–1.5 мин;
  - продление лупов до 4–8 мин — опционально (по умолчанию ВЫКЛ).

Маскировка стыков повторов (и в outro): КРОССФЕЙД всегда + слои 0/1:
  USE_DUCK, USE_DIFFUSION (трещётка-тремоло), USE_BRIDGE (по умолчанию ВЫКЛ).
Когда продление выключено, loop_0N — это «сырой» луп (игра зацикливает его сама).

Структура: bm_<держава>_NNN/{intro.ogg, loop_01.ogg.., outro.ogg, <имя>.txt}
ЗАПУСК:  .\.venv\Scripts\python.exe batch_loops.py
"""

import os
import re
import sys
import math
import random
import shutil
import subprocess

# ==================== БАЗА / ЯЗЫК ====================

def app_dir():
    """Папка, ОТКУДА реально запущен инструмент. В exe (PyInstaller) __file__ ведёт
    во временную распаковку _MEIxxxx, поэтому там берём папку самого exe."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# Язык интерфейса: авто по локали Windows, с возможностью выбора при запуске.
LANG = "en"

TR = {
    'choose_lang': {"en": 'Language / Язык:  [1] English   [2] Русский', "ru": 'Language / Язык:  [1] English   [2] Русский'},
    'root_not_found': {"en": 'ModuleSounds folder was not found next to the tool.', "ru": 'Папка ModuleSounds не найдена рядом с инструментом.'},
    'root_hint': {"en": 'Put the tool in the mod root (next to ModuleSounds), or type the full path to the mod folder (or to ModuleSounds itself):', "ru": 'Положи инструмент в корень мода (рядом с ModuleSounds) или введи полный путь до папки мода (или до самой ModuleSounds):'},
    'path_prompt': {"en": 'Path: ', "ru": 'Путь: '},
    'path_empty': {"en": 'Empty. Type a path or close the window (Ctrl+C).', "ru": 'Пусто. Введи путь или закрой окно (Ctrl+C).'},
    'path_bad': {"en": 'No ModuleSounds at this path: {p}. Try again.', "ru": 'По этому пути нет ModuleSounds: {p}. Попробуй ещё раз.'},
    'modulesounds': {"en": 'ModuleSounds: {p}', "ru": 'ModuleSounds: {p}'},
    'struct_full': {"en": 'Folder structure is complete.', "ru": 'Структура папок полная.'},
    'struct_missing': {"en": 'WARNING: folder structure is INCOMPLETE. Missing:', "ru": 'ВНИМАНИЕ: структура папок НЕПОЛНАЯ. Отсутствуют:'},
    'struct_missing2': {"en": 'The tool will process what exists. You can create the rest later.', "ru": 'Инструмент обработает то, что есть. Недостающие папки можно создать позже.'},
    'menu_title': {"en": '===== DMS Music Cutter =====', "ru": '===== DMS Нарезка музыки ====='},
    'menu_1': {"en": '[1] Cut everything (faction folders + ambient + VS)', "ru": '[1] Нарезать всё (папки держав + ambient + VS)'},
    'menu_2': {"en": '[2] Cut faction/ambient folders only', "ru": '[2] Нарезать только папки держав/ambient'},
    'menu_3': {"en": '[3] Cut VS folder only', "ru": '[3] Нарезать только папку VS'},
    'menu_0': {"en": '[0] Exit', "ru": '[0] Выход'},
    'menu_prompt': {"en": 'Choose (0-3): ', "ru": 'Выбор (0-3): '},
    'menu_bad': {"en": 'Unknown choice. Type 0, 1, 2 or 3.', "ru": 'Неизвестный выбор. Введи 0, 1, 2 или 3.'},
    'ffmpeg_missing': {"en": 'ERROR: ffmpeg/ffprobe not found. Put ffmpeg.exe and ffprobe.exe next to this tool.', "ru": 'ОШИБКА: ffmpeg/ffprobe не найдены. Положи ffmpeg.exe и ffprobe.exe рядом с инструментом.'},
    'pml_missing': {"en": 'ERROR: the looping engine (pymusiclooper) is unavailable in this build.', "ru": 'ОШИБКА: движок нарезки (pymusiclooper) недоступен в этой сборке.'},
    'folder': {"en": '>>> Folder: {f}', "ru": '>>> Папка: {f}'},
    'no_new': {"en": '  No new audio files.', "ru": '  Новых аудиофайлов нет.'},
    'new_count': {"en": '  New files: {n}', "ru": '  Новых файлов: {n}'},
    'cutting': {"en": '  [{i}/{n}] Cutting: {name}', "ru": '  [{i}/{n}] Режу: {name}'},
    'working': {"en": '      working... (analysing loop points, please wait)', "ru": '      работаю... (анализ точек лупа, подождите)'},
    'done_file': {"en": '      done -> {out}', "ru": '      готово -> {out}'},
    'skipped_file': {"en": '      skipped: {name}', "ru": '      пропущено: {name}'},
    'all_done': {"en": 'All done. You can close the window.', "ru": 'Готово. Можно закрыть окно.'},
    'press_enter': {"en": 'Press Enter to exit...', "ru": 'Нажми Enter для выхода...'},
    'vs_none': {"en": '  No VS folder — skipped.', "ru": '  Папки VS нет — пропуск.'},
    'vs_bad_name': {"en": "  [VS] name not recognised, skipped: '{f}'", "ru": "  [VS] имя не распознано, пропуск: '{f}'"},
}


def t(key, **kw):
    txt = TR.get(key, {}).get(LANG) or TR.get(key, {}).get("en") or key
    return txt.format(**kw) if kw else txt


def detect_system_lang():
    """RU, если система русская; иначе EN."""
    try:
        import locale
        try:
            loc = (locale.getlocale()[0] or "")
        except Exception:
            loc = ""
        if not loc:
            loc = os.environ.get("LANG", "")
        if str(loc).lower().startswith("ru"):
            return "ru"
    except Exception:
        pass
    try:
        import ctypes
        # 0x419 = русская раскладка/локаль
        if ctypes.windll.kernel32.GetUserDefaultUILanguage() == 0x419:
            return "ru"
    except Exception:
        pass
    return "en"


def choose_language():
    global LANG
    LANG = detect_system_lang()          # авто по системе
    print(TR["choose_lang"]["en"])
    try:
        sel = input("[1/2] (Enter = auto): ").strip()
    except EOFError:
        sel = ""
    if sel == "1":
        LANG = "en"
    elif sel == "2":
        LANG = "ru"
    # иначе оставляем авто-определённый


# ==================== НАСТРОЙКИ ====================
# Путь к ModuleSounds определяется АВТОМАТИЧЕСКИ (см. resolve_root в конце файла):
# положи batch_loops.py в корень мода (Modules/DMS_BattleMusicMod/, рядом с папкой
# ModuleSounds) или прямо в ModuleSounds — путь найдётся сам. Если не нашёлся,
# скрипт спросит полный путь. Здесь заполняется в main().
ROOT_DIR = None
EXCLUDE_DIRS = {"transitions", "vs", "tavernmusic"}   # vs — отдельным проходом; таверны не режем

LOOP_COUNT = 3               # сколько лупов делать (loop_01..loop_0N), по score
DIVERSITY_GAP_SEC = 5.0      # насколько лупы должны отличаться (старт ИЛИ длина), сек
MIN_LOOP_BODY_SEC = 55.0      # отбрасывать слишком короткие лупы

# --- Продление лупов ---
EXTEND_LOOPS = 0             # 0 = выкл (сырой луп, игра зацикливает сама), 1 = вкл
EXTEND_MIN_SEC = 240         # 4 минуты
EXTEND_MAX_SEC = 480         # 8 минут

# --- Outro ---
OUTRO_TARGET_SEC = 75        # к чему стремиться (~1–1.5 мин); если хвост уже длиннее — оставляем

# --- Слои маскировки стыка (0 = выкл, 1 = вкл). Кроссфейд всегда включён. ---
USE_DUCK = 1
USE_BRIDGE = 0               # мост выключен
USE_DIFFUSION = 1

CROSSFADE_MS = 45            # длина кроссфейда, если диффузия выкл (мс)
DUCK_MS = 150                # длина провала/подъёма громкости (мс)
DUCK_FLOOR = 0.1             # до какой доли громкости проседает duck

# слой диффузии (тремоло-волна):
DIFFUSION_DURATION_MS = 777  # продолжительность зоны (= длина кроссфейда при вкл диффузии)
DIFFUSION_WAVELENGTH_MS = 70 # длина волны тремоло (меньше = чаще «зубцы» трещётки)
DIFFUSION_DEPTH = 0.8        # глубина провалов волны (0..1; 1 = до тишины)

# слой моста (если включат):
BRIDGE_SOURCE = "folder"
TRANSITIONS_DIR = None   # строится в main() после resolve_root()
BRIDGE_PEAK = 1.0
BRIDGE_FADE_MS = 5
BRIDGE_MS = 300

# --- Поиск кандидатов ---
MIN_DURATION_MULTIPLIER = 0.20

def _find_tool(name):
    """Ищет ffmpeg/ffprobe рядом с инструментом (app_dir), потом в PATH."""
    base = app_dir()
    for cand in (os.path.join(base, name + ".exe"),
                 os.path.join(base, "ffmpeg", name + ".exe"),
                 os.path.join(base, "bin", name + ".exe")):
        if os.path.isfile(cand):
            return cand
    return name

FFMPEG = _find_tool("ffmpeg")
FFPROBE = _find_tool("ffprobe")
PROCESSED_FILE = "processed.txt"
OGG_QUALITY = "6"

# ==================== VS-РЕЖИМ ====================
# Кладёшь сырые mp3 прямо в ModuleSounds/VS/ с именами вида "KHvsWE 2 - ...mp3".
# Скрипт сам разложит их в подпапки bm_<a>_VS_<b>_NNN (имя пары — алфавитно,
# как ждёт TrackLibrary.VsPairKey), нарезав intro/loop/outro тем же движком.
VS_DIR_NAME = "VS"           # имя папки VS внутри ROOT_DIR (регистр как в моде)
VS_MIN_PER_PAIR = 3          # минимум треков на пару (для отчёта о недостающих)

# 2 буквы аббревиатуры -> папочное имя державы (как в остальных папках мода).
# Империи: одна буква W/E (западная/восточная-южная), плюс N — северная.
ABBR_TO_NATION = {
    "BA": "battania",
    "ST": "sturgia",
    "KH": "khuzait",
    "AS": "aserai",
    "VL": "vlandia",
    "NO": "nordving",
    "NE": "northern_empire",
    "WE": "western_empire",
    "SE": "southern_empire",   # на случай, если появятся файлы с SE как отдельной аббревиатурой
}

# Полный список держав для отчёта «сколько пар осталось».
ALL_NATIONS = ["aserai", "battania", "khuzait", "nordving",
               "northern_empire", "southern_empire", "sturgia",
               "vlandia", "western_empire"]

# Имя пары в аббревиатуре: 2 буквы + "vs" + 2 буквы (регистр любой), напр. "KHvsWE".
# Вторая аббревиатура может слипаться с номером/текстом ("STvsNE2", "WEvsAS 1"),
# поэтому границу слова не требуем — просто берём ровно 2 буквы.
VS_NAME_RE = re.compile(r"^\s*([A-Za-z]{2})\s*vs\s*([A-Za-z]{2})", re.IGNORECASE)
# ==================================================


CHILD_ENV = dict(os.environ)
CHILD_ENV["PYTHONUTF8"] = "1"
CHILD_ENV["PYTHONIOENCODING"] = "utf-8"
# Внутрипроцессный движок предпочтителен (единственный надёжный путь в exe).
# CLI-подпроцесс оставлен как запасной для запуска из .py с установленным Python.
_PML_API = None
def _load_pml_api():
    global _PML_API
    if _PML_API is not None:
        return _PML_API
    try:
        from pymusiclooper.core import MusicLooper
        _PML_API = MusicLooper
    except Exception:
        _PML_API = False
    return _PML_API

# CLI только когда НЕ заморожены (обычный python) — в exe sys.executable это сам exe.
PML = None
if not getattr(sys, "frozen", False):
    PML = [sys.executable, "-m", "pymusiclooper"]
AUDIO_EXTS = (".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus")


def run(cmd, description="", check=True, quiet=False):
    if not quiet:
        print(f"\n>> {description}: {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=CHILD_ENV)
    if check and r.returncode != 0:
        if r.stdout:
            print(r.stdout)
        if r.stderr:
            print(r.stderr)
        raise RuntimeError(f"Команда вернула код {r.returncode}")
    return r


def ffprobe_value(path, entries, stream=False):
    cmd = [FFPROBE, "-v", "error"]
    cmd += (["-select_streams", "a:0", "-show_entries", entries] if stream
            else ["-show_entries", entries])
    cmd += ["-of", "default=noprint_wrappers=1:nokey=1", path]
    return run(cmd, "ffprobe", check=True, quiet=True).stdout.strip().splitlines()[0].strip()


def get_duration(path):
    return float(ffprobe_value(path, "format=duration"))


def get_sample_rate(path):
    return int(ffprobe_value(path, "stream=sample_rate", stream=True))


# ---------------- кандидаты ----------------

def export_points(mp3_path):
    # Предпочтительно: внутрипроцессный API (работает и в exe).
    api = _load_pml_api()
    if api:
        try:
            # pymusiclooper 3.x: конструктор принимает filepath; параметры анализа
            # передаются в find_loop_pairs. LoopPair.loop_start/loop_end — в сэмплах.
            ml = api(filepath=mp3_path)
            pairs = ml.find_loop_pairs(min_duration_multiplier=MIN_DURATION_MULTIPLIER)
            out = []
            for lp in pairs:
                try:
                    sv = float(ml.samples_to_seconds(lp.loop_start))
                    ev = float(ml.samples_to_seconds(lp.loop_end))
                    sc = float(getattr(lp, "score", 0.0) or 0.0)
                except Exception:
                    continue
                if ev > sv:
                    out.append((sv, ev, sc, "seconds"))
            if out:
                return out
            # API отработал, но точек нет — это НЕ ошибка, вернём пусто (будет fallback).
            return []
        except Exception as ex:
            msg = str(ex)
            if "loop" in msg.lower() and "found" in msg.lower():
                # "No loop points found" — штатная ситуация, не ошибка.
                return []
            print(f"      (API-движок не смог, пробую CLI: {ex})")

    # Запасной путь: CLI-подпроцесс (только при запуске из .py).
    if not PML:
        raise RuntimeError("pymusiclooper API unavailable and no CLI in exe build")
    base = PML + ["export-points", "--path", mp3_path, "--alt-export-top=-1",
                  "--min-duration-multiplier", str(MIN_DURATION_MULTIPLIER)]
    res = run(base + ["--fmt", "seconds"], "export-points (seconds)", check=False)
    mode = "seconds"
    if res.returncode != 0:
        res = run(base, "export-points (samples)", check=False)
        mode = "samples"
        if res.returncode != 0:
            blob = (res.stdout or "") + (res.stderr or "")
            if "loop" in blob.lower() and "found" in blob.lower():
                return []   # точек нет — штатно, будет fallback
            raise RuntimeError("export-points завершился с ошибкой")
    out = []
    num_re = re.compile(r"^-?\d+(?:\.\d+)?$")
    for line in res.stdout.splitlines():
        pp = line.split()
        if len(pp) < 3 or not (num_re.match(pp[0]) and num_re.match(pp[1])):
            continue
        try:
            sv = float(pp[0]); ev = float(pp[1]); sc = float(pp[-1])
        except ValueError:
            continue
        if ev > sv:
            out.append((sv, ev, sc, mode))
    return out


def enrich(cands, total_sec, sr):
    res = []
    for sv, ev, sc, mode in cands:
        if mode == "seconds":
            ss = int(round(sv * sr)); es = int(round(ev * sr)); length = ev - sv
        else:
            ss = int(round(sv)); es = int(round(ev)); length = (ev - sv) / sr
        res.append({"start": ss, "end": es, "len_sec": length,
                    "fraction": length / total_sec if total_sec else 0.0, "score": sc})
    return res


def pick_loops(enriched, sr):
    """Лучшие по score, непохожие; [0] = самый высокий score (идеальный для intro/outro)."""
    pool = [c for c in enriched if c["len_sec"] >= MIN_LOOP_BODY_SEC] or enriched
    chosen = []
    for c in sorted(pool, key=lambda x: x["score"], reverse=True):
        ok = True
        for d in chosen:
            if (abs(c["start"] - d["start"]) / sr < DIVERSITY_GAP_SEC and
                    abs(c["len_sec"] - d["len_sec"]) < DIVERSITY_GAP_SEC):
                ok = False; break
        if ok:
            chosen.append(c)
        if len(chosen) >= LOOP_COUNT:
            break
    return chosen


# ---------------- ffmpeg примитивы ----------------

def cut_samples(src, out_wav, start_sample, end_sample):
    af = f"atrim=start_sample={start_sample}:end_sample={end_sample},asetpts=PTS-STARTPTS"
    run([FFMPEG, "-y", "-i", src, "-af", af, "-c:a", "pcm_s16le", out_wav], "cut", quiet=True)


def cut_seconds(src, out_wav, ss, to):
    af = f"atrim={ss:.6f}:{to:.6f},asetpts=PTS-STARTPTS"
    run([FFMPEG, "-y", "-i", src, "-af", af, "-c:a", "pcm_s16le", out_wav], "cut_sec", quiet=True)


def concat_plain(a_wav, b_wav, out_wav):
    run([FFMPEG, "-y", "-i", a_wav, "-i", b_wav, "-filter_complex",
         "[0:a][1:a]concat=n=2:v=0:a=1[out]", "-map", "[out]",
         "-c:a", "pcm_s16le", out_wav], "concat", quiet=True)


def encode_ogg(in_wav, out_ogg):
    run([FFMPEG, "-y", "-i", in_wav, "-ar", "44100", "-c:a", "libvorbis",
         "-q:a", OGG_QUALITY, out_ogg], "encode", quiet=True)


def layered_join(a_wav, b_wav, out_wav, temp_dir, tag, bridge_file):
    """Кроссфейд (перемешивание) + опциональные слои: duck, diffusion, bridge."""
    La = get_duration(a_wav); Lb = get_duration(b_wav)
    overlap = CROSSFADE_MS / 1000.0
    if USE_DIFFUSION:
        overlap = max(overlap, DIFFUSION_DURATION_MS / 1000.0)
    overlap = max(0.005, min(overlap, La * 0.5, Lb * 0.5))

    chains = []
    ain, bin_ = "[0:a]", "[1:a]"
    if USE_DUCK:
        duck = min(DUCK_MS / 1000.0, La * 0.4, Lb * 0.4)
        F = DUCK_FLOOR; t0 = La - duck
        chains.append(f"[0:a]volume=eval=frame:"
                      f"volume='if(lt(t,{t0:.6f}),1,pow({F},(t-{t0:.6f})/{duck:.6f}))'[a]")
        chains.append(f"[1:a]volume=eval=frame:"
                      f"volume='if(lt(t,{duck:.6f}),pow({F},1-t/{duck:.6f}),1)'[b]")
        ain, bin_ = "[a]", "[b]"
    chains.append(f"{ain}{bin_}acrossfade=d={overlap:.6f}:c1=tri:c2=tri[ab]")
    cur = "[ab]"
    ablen = La + Lb - overlap

    if USE_DIFFUSION:
        center = La - overlap / 2.0
        zs = center - overlap / 2.0
        ze = center + overlap / 2.0
        lam = max(0.005, DIFFUSION_WAVELENGTH_MS / 1000.0)
        D = DIFFUSION_DEPTH
        PI = "3.14159265"
        expr = (f"if(between(t,{zs:.6f},{ze:.6f}),"
                f"1-{D}*(0.5-0.5*cos(2*{PI}*(t-{zs:.6f})/{overlap:.6f}))"
                f"*(0.5-0.5*cos(2*{PI}*(t-{center:.6f})/{lam:.6f})),1)")
        chains.append(f"{cur}volume=eval=frame:volume='{expr}'[abd]")
        cur = "[abd]"

    inputs = ["-i", a_wav, "-i", b_wav]
    do_bridge = USE_BRIDGE and not (BRIDGE_SOURCE == "folder" and not bridge_file)
    if do_bridge:
        if BRIDGE_SOURCE == "folder":
            brlen = get_duration(bridge_file)
            brlen_eff = min(brlen, ablen * 0.9)
            if brlen_eff < brlen - 1e-3:
                bwav = os.path.join(temp_dir, f"{tag}_br.wav")
                cut_seconds(bridge_file, bwav, 0.0, brlen_eff)
            else:
                bwav = bridge_file; brlen_eff = brlen
            fade = min(BRIDGE_FADE_MS / 1000.0, brlen_eff * 0.3)
            env = (f"afade=t=in:st=0:d={fade:.6f},"
                   f"afade=t=out:st={brlen_eff - fade:.6f}:d={fade:.6f},volume={BRIDGE_PEAK}")
        else:
            brlen_eff = min(BRIDGE_MS / 1000.0, La * 0.5, Lb * 0.5)
            bwav = os.path.join(temp_dir, f"{tag}_br.wav")
            if BRIDGE_SOURCE == "outgoing":
                cut_seconds(a_wav, bwav, max(0.0, La - brlen_eff), La)
            else:
                cut_seconds(b_wav, bwav, 0.0, brlen_eff)
            env = f"volume=eval=frame:volume='{BRIDGE_PEAK}*sin(3.14159265*t/{brlen_eff:.6f})'"
        seam_center = La - overlap / 2.0
        delay = max(0.0, min(seam_center - brlen_eff / 2.0, ablen - brlen_eff))
        delay_ms = int(round(delay * 1000))
        inputs += ["-i", bwav]
        chains.append(f"[2:a]{env},adelay={delay_ms}|{delay_ms}[brg]")
        chains.append(f"{cur}[brg]amix=inputs=2:normalize=0[out]")
    else:
        chains.append(f"{cur}anull[out]")

    run([FFMPEG, "-y"] + inputs + ["-filter_complex", ";".join(chains),
         "-map", "[out]", "-c:a", "pcm_s16le", out_wav], "join", quiet=True)


def repeat_masked(body_wav, n, temp_dir, tag, bridge_file):
    """n копий тела подряд, каждая обёртка end->start маскируется слоями."""
    if n <= 1:
        out = os.path.join(temp_dir, f"{tag}_r0.wav")
        shutil.copyfile(body_wav, out)
        return out
    result = os.path.join(temp_dir, f"{tag}_r0.wav")
    shutil.copyfile(body_wav, result)
    for i in range(1, n):
        nxt = os.path.join(temp_dir, f"{tag}_r{i}.wav")
        layered_join(result, body_wav, nxt, temp_dir, f"{tag}_{i}", bridge_file)
        if "_r0" not in result and os.path.exists(result):
            os.remove(result)
        result = nxt
    return result


# ---------------- обработка трека ----------------

def list_transition_files():
    if not os.path.isdir(TRANSITIONS_DIR):
        return []
    return [os.path.join(TRANSITIONS_DIR, f) for f in os.listdir(TRANSITIONS_DIR)
            if f.lower().endswith(AUDIO_EXTS)]


def maybe_bridge(temp_dir, sr, tag, transition_files):
    if not (USE_BRIDGE and transition_files):
        return None
    chosen = random.choice(transition_files)
    bf = os.path.join(temp_dir, f"{tag}_bridge.wav")
    run([FFMPEG, "-y", "-i", chosen, "-ar", str(sr), "-ac", "2",
         "-c:a", "pcm_s16le", bf], f"bridge<-{os.path.basename(chosen)}", quiet=True)
    return bf


def process_mp3(mp3_path, target_dir):
    base = os.path.splitext(os.path.basename(mp3_path))[0]
    work_dir = os.path.dirname(mp3_path)
    temp_dir = os.path.join(work_dir, f"_temp_{base}")
    os.makedirs(temp_dir, exist_ok=True)

    print(f"\n--- Обработка: {mp3_path} ---")
    try:
        total_sec = get_duration(mp3_path)
        sr = get_sample_rate(mp3_path)
        total_samples = int(round(total_sec * sr))
        print(f"Длительность: {total_sec:.2f} сек, sr: {sr} Гц")

        cand = export_points(mp3_path)
        used_fallback = False
        loops = []
        if cand:
            enriched = enrich(cand, total_sec, sr)
            loops = pick_loops(enriched, sr)
        if not loops:
            # FALLBACK: чистой точки зацикливания нет (или её не выбрать по нашим
            # правилам) — не бросаем трек, а берём его ЦЕЛИКОМ как один луп. Игра
            # зациклит его сама; лучше «сырой» луп, чем пропущенный трек.
            used_fallback = True
            loops = [{
                "start": 0,
                "end": total_samples,
                "len_sec": total_sec,
                "fraction": 1.0,
                "score": 0.0,
            }]
            print("  Точек зацикливания не найдено — беру трек целиком как loop_01 "
                  "(fallback).")
        if not used_fallback:
            print(f"Кандидатов: {len(enriched)} -> выбрано лупов: {len(loops)} "
                  f"(хотели {LOOP_COUNT}); слои duck={USE_DUCK} diffusion={USE_DIFFUSION} bridge={USE_BRIDGE}")
        for i, lp in enumerate(loops, 1):
            print(f"  loop_{i:02d}: {lp['len_sec']:.1f}с (доля {lp['fraction']:.0%}, score {lp['score']:.3f})")

        transition_files = list_transition_files() if (USE_BRIDGE and BRIDGE_SOURCE == "folder") else []
        os.makedirs(target_dir, exist_ok=True)

        primary = loops[0]
        pS = max(0, primary["start"]); pE = min(total_samples, primary["end"])
        body1 = os.path.join(temp_dir, "body1.wav")
        cut_samples(mp3_path, body1, pS, pE)
        body1_len = primary["len_sec"]

        # ---- intro = [0, начало лупа 1] ----
        intro_ogg = os.path.join(target_dir, "intro.ogg")
        if pS > int(0.05 * sr):
            tmp = os.path.join(temp_dir, "intro.wav")
            cut_samples(mp3_path, tmp, 0, pS); encode_ogg(tmp, intro_ogg)
        else:
            run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                 "-t", "0.5", "-c:a", "libvorbis", "-q:a", OGG_QUALITY, intro_ogg], "silence", quiet=True)

        # ---- лупы ----
        info = [f"original_mp3: {os.path.basename(mp3_path)}",
                f"loops: {len(loops)}  extend: {EXTEND_LOOPS}",
                f"layers: duck={USE_DUCK} bridge={USE_BRIDGE} diffusion={USE_DIFFUSION}",
                f"crossfade_ms={CROSSFADE_MS} duck_ms={DUCK_MS} duck_floor={DUCK_FLOOR}",
                f"diffusion dur={DIFFUSION_DURATION_MS} wave={DIFFUSION_WAVELENGTH_MS} depth={DIFFUSION_DEPTH}"]

        for i, lp in enumerate(loops, 1):
            s = max(0, lp["start"]); e = min(total_samples, lp["end"])
            body = os.path.join(temp_dir, f"body_{i}.wav")
            cut_samples(mp3_path, body, s, e)
            loop_ogg = os.path.join(target_dir, f"loop_{i:02d}.ogg")
            if EXTEND_LOOPS:
                target = random.randint(EXTEND_MIN_SEC, EXTEND_MAX_SEC)
                n = max(1, math.ceil(target / lp["len_sec"]))
                bf = maybe_bridge(temp_dir, sr, f"l{i}", transition_files)
                rep = repeat_masked(body, n, temp_dir, f"l{i}", bf)
                encode_ogg(rep, loop_ogg)
                fin = get_duration(loop_ogg)
                print(f"[loop_{i:02d}] продлён: {n} повтор(ов) -> {fin:.0f}с")
                info.append(f"loop_{i:02d}: len={lp['len_sec']:.1f}s score={lp['score']:.3f} extended={fin:.0f}s")
            else:
                encode_ogg(body, loop_ogg)
                print(f"[loop_{i:02d}] сырой луп {lp['len_sec']:.1f}с (игра зациклит сама)")
                info.append(f"loop_{i:02d}: len={lp['len_sec']:.1f}s score={lp['score']:.3f} raw")

        # ---- outro = m проходов лупа 1 + натуральный хвост, ~1–1.5 мин ----
        tail_start = pE
        tail_len = (total_samples - tail_start) / sr
        tail_wav = None
        if tail_len > 0.05:
            tail_wav = os.path.join(temp_dir, "tail.wav")
            cut_samples(mp3_path, tail_wav, tail_start, total_samples)
        m = max(1, round((OUTRO_TARGET_SEC - max(0.0, tail_len)) / body1_len))
        bf = maybe_bridge(temp_dir, sr, "outro", transition_files)
        bodies = repeat_masked(body1, m, temp_dir, "outro", bf)
        outro_ogg = os.path.join(target_dir, "outro.ogg")
        if tail_wav:
            outro_wav = os.path.join(temp_dir, "outro_full.wav")
            concat_plain(bodies, tail_wav, outro_wav)
            encode_ogg(outro_wav, outro_ogg)
        else:
            encode_ogg(bodies, outro_ogg)
        outro_len = get_duration(outro_ogg)
        print(f"[outro] {m} проход(ов) лупа 1 + хвост {tail_len:.0f}с = {outro_len:.0f}с")
        info.append(f"outro: bodies={m} tail={tail_len:.0f}s total={outro_len:.0f}s")

        with open(os.path.join(target_dir, f"{base}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(info) + "\n")

        print(f"OK: {len(loops)} лупов + intro/outro в {target_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return True
    except Exception as e:
        print(f"  ОШИБКА при обработке {base}: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False


# ---------------- VS-режим ----------------

def parse_vs_name(filename):
    """'KHvsWE 2 - ...mp3' -> ('khuzait', 'western_empire') или None.
    Пара нормализуется алфавитно, как VsPairKey в моде (nationA <= nationB)."""
    m = VS_NAME_RE.match(os.path.splitext(filename)[0])
    if not m:
        return None
    a_ab, b_ab = m.group(1).upper(), m.group(2).upper()
    a = ABBR_TO_NATION.get(a_ab)
    b = ABBR_TO_NATION.get(b_ab)
    if not a or not b or a == b:
        return None
    return tuple(sorted((a, b)))   # алфавитно: ('battania','sturgia') и т.п.


def vs_pair_prefix(nation_a, nation_b):
    """Префикс подпапки без номера: bm_<a>_VS_<b> (a,b уже алфавитно)."""
    return f"bm_{nation_a}_VS_{nation_b}"


def scan_existing_vs(vs_dir):
    """Считает уже нарезанные пары: {('a','b'): count} по подпапкам bm_*_VS_*_NNN."""
    counts = {}
    if not os.path.isdir(vs_dir):
        return counts
    pat = re.compile(r"^bm_(.+?)_VS_(.+?)_(\d{3})$", re.IGNORECASE)
    for item in os.listdir(vs_dir):
        if not os.path.isdir(os.path.join(vs_dir, item)):
            continue
        m = pat.match(item)
        if not m:
            continue
        pair = tuple(sorted((m.group(1).lower(), m.group(2).lower())))
        counts[pair] = counts.get(pair, 0) + 1
    return counts


def stage_vs_sources(vs_dir):
    """Раскладывает сырые mp3 из корня VS/ по подпапкам пар.
    Возвращает список (mp3_path, pair, prefix) готовых к нарезке.
    Файлы, имя которых не распозналось, пропускаются с предупреждением."""
    staged = []
    if not os.path.isdir(vs_dir):
        print(f"  Папки {vs_dir} нет — VS пропущен.")
        return staged
    loose_mp3 = [f for f in os.listdir(vs_dir)
                 if f.lower().endswith(".mp3")
                 and os.path.isfile(os.path.join(vs_dir, f))]
    for fname in sorted(loose_mp3):
        pair = parse_vs_name(fname)
        if pair is None:
            print(f"  [VS] не распознано имя, пропуск: '{fname}'")
            continue
        prefix = vs_pair_prefix(*pair)
        staged.append((os.path.join(vs_dir, fname), pair, prefix))
    return staged


def process_vs(root_dir):
    """Обрабатывает все сырые mp3 в ROOT_DIR/VS/ и печатает отчёт по парам."""
    vs_dir = os.path.join(root_dir, VS_DIR_NAME)
    if not os.path.isdir(vs_dir):
        # регистронезависимый фолбэк, как в моде
        for item in os.listdir(root_dir):
            p = os.path.join(root_dir, item)
            if os.path.isdir(p) and item.lower() == VS_DIR_NAME.lower():
                vs_dir = p
                break

    print(f"\n>>> VS-папка: {vs_dir}")
    processed = load_processed(vs_dir) if os.path.isdir(vs_dir) else set()
    staged = stage_vs_sources(vs_dir)
    new_staged = [(mp3, pair, pfx) for (mp3, pair, pfx) in staged
                  if os.path.splitext(os.path.basename(mp3))[0] not in processed]

    if not new_staged:
        print("  Новых VS mp3 нет.")
    else:
        print(f"  Новых VS mp3: {len(new_staged)}")
        for mp3_path, pair, prefix in new_staged:
            base_name = os.path.splitext(os.path.basename(mp3_path))[0]
            num = next_subfolder_number(vs_dir, prefix)
            subfolder = os.path.join(vs_dir, f"{prefix}_{num:03d}")
            print(f"\n--- [{pair[0]} vs {pair[1]}] {os.path.basename(mp3_path)}"
                  f" -> {os.path.basename(subfolder)}")
            if process_mp3(mp3_path, subfolder):
                processed.add(base_name)
                save_processed(vs_dir, processed)
                print(f"  В processed: {base_name}")
            else:
                if os.path.isdir(subfolder):
                    shutil.rmtree(subfolder, ignore_errors=True)
                print(f"  Пропущен: {os.path.basename(mp3_path)}")


# ---------------- учёт / main ----------------

def load_processed(folder_path):
    p = os.path.join(folder_path, PROCESSED_FILE)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_processed(folder_path, processed):
    with open(os.path.join(folder_path, PROCESSED_FILE), "w", encoding="utf-8") as f:
        for name in sorted(processed):
            f.write(name + "\n")


def next_subfolder_number(folder_path, prefix):
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d{{3}})$")
    existing = {int(m.group(1)) for item in os.listdir(folder_path)
                if os.path.isdir(os.path.join(folder_path, item))
                for m in [pattern.match(item)] if m}
    n = 1
    while n in existing:
        n += 1
    return n


def preflight():
    try:
        run([FFMPEG, "-version"], "ffmpeg", quiet=True)
        run([FFPROBE, "-version"], "ffprobe", quiet=True)
    except Exception:
        print(t("ffmpeg_missing"))
        input(t("press_enter"))
        sys.exit(1)
    # Движок: сначала внутрипроцессный API, потом CLI.
    if _load_pml_api():
        return
    if PML:
        res = run(PML + ["--version"], "pymusiclooper", check=False, quiet=True)
        if res.returncode == 0:
            return
    print(t("pml_missing"))
    input(t("press_enter"))
    sys.exit(1)


# Папки, которые мод ожидает внутри ModuleSounds (для проверки полноты структуры).
EXPECTED_DIRS = ["aserai", "battania", "khuzait", "nordving", "northern_empire",
                 "southern_empire", "sturgia", "vlandia", "western_empire",
                 "bandits", "ambient", "VS"]


def resolve_root():
    """Находит папку ModuleSounds: от расположения скрипта (сама папка или до 3
    уровней вверх — т.е. корень мода тоже подходит). Если не нашлось, просит
    пользователя ввести полный путь до папки мода или до ModuleSounds."""
    def as_modulesounds(path):
        path = os.path.abspath(path)
        if os.path.basename(path).lower() == "modulesounds" and os.path.isdir(path):
            return path
        cand = os.path.join(path, "ModuleSounds")
        return cand if os.path.isdir(cand) else None

    probe = app_dir()
    for _ in range(4):
        got = as_modulesounds(probe)
        if got:
            return got
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent

    # Не нашли рядом — спросим у пользователя.
    print(t("root_not_found"))
    print(t("root_hint"))
    while True:
        raw = input(t("path_prompt")).strip().strip('"')
        if not raw:
            print(t("path_empty"))
            continue
        got = as_modulesounds(raw)
        if got:
            return got
        print(t("path_bad", p=raw))


def check_structure(root_dir):
    """Предупреждает, если структура папок неполная (мод ждёт EXPECTED_DIRS)."""
    present = {d.lower() for d in os.listdir(root_dir)
               if os.path.isdir(os.path.join(root_dir, d))}
    missing = [d for d in EXPECTED_DIRS if d.lower() not in present]
    if missing:
        print(t("struct_missing"))
        for d in missing:
            print(f"  - {d}")
        print(t("struct_missing2"))
    else:
        print(t("struct_full"))


def cut_faction_folders():
    """Нарезает папки держав + ambient (всё, кроме VS/transitions/tavernmusic)."""
    for folder_name in sorted(os.listdir(ROOT_DIR)):
        folder_path = os.path.join(ROOT_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue
        if folder_name.lower() in EXCLUDE_DIRS:
            continue
        print(t("folder", f=folder_name))
        processed = load_processed(folder_path)
        all_mp3 = [f for f in os.listdir(folder_path) if f.lower().endswith(".mp3")]
        new_files = [f for f in all_mp3 if os.path.splitext(f)[0] not in processed]
        if not new_files:
            print(t("no_new"))
            continue
        print(t("new_count", n=len(new_files)))
        prefix = f"bm_{folder_name}"
        for i, mp3_file in enumerate(new_files, 1):
            mp3_path = os.path.join(folder_path, mp3_file)
            base_name = os.path.splitext(mp3_file)[0]
            num = next_subfolder_number(folder_path, prefix)
            subfolder = os.path.join(folder_path, f"{prefix}_{num:03d}")
            print(t("cutting", i=i, n=len(new_files), name=mp3_file))
            print(t("working")); sys.stdout.flush()
            if process_mp3(mp3_path, subfolder):
                processed.add(base_name)
                save_processed(folder_path, processed)
                print(t("done_file", out=os.path.basename(subfolder)))
            else:
                if os.path.isdir(subfolder):
                    shutil.rmtree(subfolder, ignore_errors=True)
                print(t("skipped_file", name=mp3_file))
            sys.stdout.flush()


def menu():
    while True:
        print(t("menu_title"))
        print(t("menu_1")); print(t("menu_2")); print(t("menu_3")); print(t("menu_0"))
        try:
            choice = input(t("menu_prompt")).strip()
        except EOFError:
            choice = "0"
        if choice == "1":
            cut_faction_folders(); process_vs(ROOT_DIR)
        elif choice == "2":
            cut_faction_folders()
        elif choice == "3":
            process_vs(ROOT_DIR)
        elif choice == "0":
            return
        else:
            print(t("menu_bad")); continue
        print(t("all_done"))


def main():
    global ROOT_DIR, TRANSITIONS_DIR
    choose_language()
    ROOT_DIR = resolve_root()
    TRANSITIONS_DIR = os.path.join(ROOT_DIR, "transitions")
    print(t("modulesounds", p=ROOT_DIR))
    check_structure(ROOT_DIR)
    preflight()
    menu()
    input(t("press_enter"))


if __name__ == "__main__":
    main()
