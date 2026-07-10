#!/usr/bin/env python3
"""
Phonics Dictation Trainer V3 — Web Edition
===========================================
Web interface for mobile phone access.
Uses the same TTS engine as the terminal version.
"""
import requests, base64, json, os, sys, time, random, shutil, tempfile, subprocess, hashlib
from dataclasses import dataclass, field
from collections import defaultdict
from flask import Flask, request, jsonify, send_file, send_from_directory
import pronouncing

# ── API Config ──────────────────────────────────────────────────────────────

VOLC_API_KEY = "7ac606a7-4e1f-4a0a-b0d4-6c7d45bd7ff4"
TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
SPEAKER = "en_female_myra_cmb_uranus_bigtts"

app = Flask(__name__)

# ── Static directory for serving phoneme WAV files ─────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PHONEME_DIR = os.path.join(BASE_DIR, "phonemes")
TTS_CACHE_DIR = os.path.join(BASE_DIR, "tts_cache")
os.makedirs(TTS_CACHE_DIR, exist_ok=True)

# ── ARPAbet mapping ────────────────────────────────────────────────────────

ARPABET_TO_WAV = {
    "AA": "AA_single.wav",
    "AE": "AE_single.wav",
    "AH": "AH_single.wav",
    "AO": "AO.wav",
    "AR": "AR.wav",
    "AW": "AW_single.wav",
    "AY": "AY_single.wav",
    "B": "B_single.wav",
    "CH": "CH.wav",
    "D": "D_single.wav",
    "DH": "DH_single.wav",
    "EH": "EH_single.wav",
    "ER": "ER_single.wav",
    "EY": "EY_single.wav",
    "F": "F_single.wav",
    "G": "G_single.wav",
    "HH": "HH.wav",
    "IH": "IH_single.wav",
    "IY": "IY_single.wav",
    "JH": "JH.wav",
    "K": "K_single.wav",
    "KS": "KS.wav",
    "KW": "KW.wav",
    "L": "L.wav",
    "M": "M.wav",
    "N": "N.wav",
    "NG": "NG.wav",
    "OW": "OW_single.wav",
    "OY": "OY_single.wav",
    "P": "P_single.wav",
    "R": "R.wav",
    "S": "S.wav",
    "SH": "SH.wav",
    "T": "T_single.wav",
    "TH": "TH.wav",
    "UH": "UH_single.wav",
    "UW": "UW_single.wav",
    "V": "V.wav",
    "W": "W.wav",
    "WH": "WH.wav",
    "Y": "Y.wav",
    "Z": "Z.wav",
    "ZH": "ZH.wav",
}

ARPABET_TO_WAV_REPEAT = {
    "AA": "AA_repeat.wav",
    "AE": "AE_repeat.wav",
    "AH": "AH_repeat.wav",
    "AW": "AW_repeat.wav",
    "AY": "AY_repeat.wav",
    "B": "B_repeat.wav",
    "D": "D_repeat.wav",
    "EH": "EH_repeat.wav",
    "ER": "ER_repeat.wav",
    "EY": "EY_repeat.wav",
    "F": "F_repeat.wav",
    "G": "G_repeat.wav",
    "IH": "IH_repeat.wav",
    "IY": "IY_repeat.wav",
    "K": "K_repeat.wav",
    "OW": "OW_repeat.wav",
    "OY": "OY_repeat.wav",
    "P": "P_repeat.wav",
    "T": "T_repeat.wav",
    "UH": "UH_repeat.wav",
    "UW": "UW_repeat.wav",
}

ARPABET_TO_ESPEAK = {
    "AA": "a", "AE": "ae", "AH": "uh", "AO": "ao", "AW": "aw",
    "AY": "ay", "EH": "eh", "ER": "er", "EY": "ey", "IH": "ih",
    "IY": "iy", "OW": "ow", "OY": "oy", "UH": "uu", "UW": "uw",
    "B": "b", "CH": "ch", "D": "d", "DH": "dh", "F": "f",
    "G": "g", "HH": "h", "JH": "j", "K": "k", "L": "l",
    "M": "m", "N": "n", "NG": "ng", "P": "p", "R": "r",
    "S": "s", "SH": "sh", "T": "t", "TH": "th", "V": "v",
    "W": "w", "Y": "y", "Z": "z", "ZH": "zh",
}

ESPEAK_EXE = shutil.which("espeak-ng") or shutil.which("espeak")

# Pronunciation overrides — some words in CMUdict list the wrong pronunciation first
PRONUNCIATION_OVERRIDES = {
    "wind": 1,  # /wɪnd/ (the wind blows), not /waɪnd/ (wind up)
    "live": 1,  # /lɪv/ (to live), not /laɪv/ (live music)
}


# ── CMU Dictionary helpers ─────────────────────────────────────────────────

def get_phoneme_list(word):
    """Get ARPAbet phoneme sequence for a word from CMUdict."""
    word = word.lower().strip()
    phones = pronouncing.phones_for_word(word)
    if not phones:
        return None
    # Use override index if this word has one (fixes homograph issues)
    idx = PRONUNCIATION_OVERRIDES.get(word, 0)
    if idx >= len(phones):
        idx = 0
    result = []
    for ph in phones[idx].split():
        clean = ph.rstrip("012")
        espeak_ph = ARPABET_TO_ESPEAK.get(clean)
        if espeak_ph:
            result.append((espeak_ph, clean))
    return result


# ── Volcengine TTS (cached) ────────────────────────────────────────────────

def _call_volc_tts(word, speech_rate=0):
    payload = {
        "req_params": {
            "speaker": SPEAKER,
            "text": word,
            "audio_params": {"format": "mp3", "sample_rate": 24000, "speech_rate": speech_rate},
        }
    }
    headers = {
        "X-Api-Key": VOLC_API_KEY,
        "X-Api-Resource-Id": "seed-tts-2.0",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(TTS_URL, headers=headers, json=payload, timeout=30, stream=True)
        resp.raise_for_status()
        chunks = []
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                ch = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = ch.get("code", 0)
            if code != 0 and code != 20000000:
                return None
            d = ch.get("data", "")
            if d:
                chunks.append(base64.b64decode(d))
        if not chunks:
            return None
        return b"".join(chunks)
    except requests.exceptions.RequestException:
        return None


def get_tts_audio(word, speed=1.0):
    """Get cached TTS audio for a word. Returns (path, exists).
    For slow speeds, generates at normal speed then uses ffmpeg
    rubberband filter for high-quality time-stretching."""
    if speed < 1.0:
        # Generate at normal speed for quality, then slow with ffmpeg
        normal_path, ok = get_tts_audio(word, 1.0)
        if not ok:
            return None, False
        slow_key = hashlib.md5(f"{word}:slow:{speed}:rubberband".encode()).hexdigest()
        slow_path = os.path.join(TTS_CACHE_DIR, f"{slow_key}.mp3")
        if os.path.exists(slow_path):
            return slow_path, True
        # Use ffmpeg rubberband for high-quality time stretching
        # rubberband preserves pitch better than atempo at extreme ratios
        ratio = max(0.5, speed)
        # For very slow speeds, cascade rubberband for best quality
        if ratio < 0.7:
            # Chain: 0.8 * 0.875 = 0.7, 0.8 * 0.625 = 0.5, etc.
            ret = subprocess.run(
                ["ffmpeg", "-y", "-i", normal_path,
                 "-filter:a", f"rubberband=tempo={ratio}",
                 "-q:a", "2", slow_path],
                capture_output=True, timeout=30
            )
        else:
            ret = subprocess.run(
                ["ffmpeg", "-y", "-i", normal_path,
                 "-filter:a", f"rubberband=tempo={ratio}",
                 "-q:a", "2", slow_path],
                capture_output=True, timeout=30
            )
        if ret.returncode == 0 and os.path.exists(slow_path):
            return slow_path, True
        # Fallback to original slow generation
        speech_rate = int((speed - 1.0) * 100)
    else:
        speech_rate = int((speed - 1.0) * 100)

    key = hashlib.md5(f"{word}:{speech_rate}".encode()).hexdigest()
    path = os.path.join(TTS_CACHE_DIR, f"{key}.mp3")
    if os.path.exists(path):
        return path, True
    audio = _call_volc_tts(word, speech_rate)
    if not audio:
        return None, False
    with open(path, "wb") as f:
        f.write(audio)
    return path, True


def get_phoneme_audio(arpabet_phoneme, repeat=False):
    """Get phoneme WAV file path, or generate via espeak-ng if missing.
    If repeat=True, uses the repeated version (for error correction)."""
    if repeat:
        wav = ARPABET_TO_WAV_REPEAT.get(arpabet_phoneme)
        if wav:
            wav_path = os.path.join(PHONEME_DIR, wav)
            if os.path.exists(wav_path):
                return wav_path, "wav"
    wav = ARPABET_TO_WAV.get(arpabet_phoneme)
    if wav:
        wav_path = os.path.join(PHONEME_DIR, wav)
        if os.path.exists(wav_path):
            return wav_path, "wav"

    # Fallback: espeak-ng
    espeak_name = ARPABET_TO_ESPEAK.get(arpabet_phoneme)
    if espeak_name and ESPEAK_EXE:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            subprocess.run(
                [ESPEAK_EXE, "-v", "en-us", "-s", "140", "-p", "50",
                 "-w", tmp.name, "[[" + espeak_name + "]]"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
            )
            if os.path.getsize(tmp.name) > 1000:
                return tmp.name, "wav"
        except Exception:
            pass
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return None, None


# ── Word data ────────────────────────────────────────────────────────────────

BEGINNER = [
    "cat","bat","hat","mat","rat","sat","fat","pat",
    "can","man","pan","fan","van","ran",
    "map","tap","nap","gap","bad","dad","pad","sad",
    "bed","red","fed","led","hen","pen","ten","men",
    "jet","net","pet","wet",
    "big","pig","dig","wig","bin","pin","tin","win",
    "fit","hit","sit","bit","lip","tip","rip","zip",
    "dog","log","fog","hog","hop","mop","top","pop",
    "pot","hot","dot","not","box","fox",
    "bug","jug","mug","rug","bus","cup","pup",
    "sun","run","fun","bun","hut","nut","cut",
    "a","the","is","I","to","has","you",
    "and","said","go","he","she","was",
    "they","are","have","do","of","for",
]

INTERMEDIATE = [
    "mask","hand","flag","plan","flat","camp",
    "slip","spill","wind","swim","list","milk",
    "drop","frog","spot","pond","stop",
    "drum","plug","jump","hunt","dust",
    "tent","belt","nest","desk","step",
    "ship","shop","fish","shell","dish","cash","rush",
    "that","them","then","this","than",
    "thin","thick","bath","moth","path",
    "chin","chip","chop","rich","lunch","much",
    "whip","whale","wheel","phone","photo","graph",
    "king","ring","wing","song","lung","bang",
    "sink","pink","tank","bank","wink","trunk",
    "cliff","puff","hill","bell","miss","buzz",
    "ball","tall","toll","bull","full",
    "duck","neck","lock","rock","sock","pick",
    "cake","lake","gate","cape","game","late","name",
    "kite","pine","bike","bite","line","lime","side",
    "bone","rope","home","nose","rose","joke","hope",
    "tube","mule","cute","flute","tune","rude",
    "face","lace","rice","mice","nice","space","place",
    "cage","page","rage","huge","stage",
    "there","their","where","what","why","who","when",
    "some","come","one","once","wash",
    "mother","father","give","live","done","gone",
]

ADVANCED = [
    "car","star","park","dark","yard","farm",
    "fork","storm","corn","more","shore",
    "her","sister","brother","dinner","tiger","paper",
    "bird","girl","dirt","shirt","fur","turn","burn",
    "word","world","work",
    "rain","train","paint","play","day","clay",
    "tree","green","seat","beach","key","monkey",
    "boat","coat","road","snow","blow","toe",
    "pie","tie","light","night","high","fight",
    "book","look","foot","wood","good","push",
    "moon","spoon","food","pool","cool","room",
    "grew","flew","juice","fruit","blue","clue",
    "saw","straw","draw","haul","sauce","caught",
    "head","bread","heavy","sweat","water",
    "coin","point","soil","boy","toy","joy",
    "out","house","mouse","cow","town","brown",
    "knee","knit","write","wrong","lamb","comb",
    "bigger","tallest","faster","slowly","softly",
    "helpful","playful","unhappy","rewrite","refill",
    "running","hopped","baked","dried","babies",
    "action","station","picture","nature","mixture",
    "answer","neighbor","beautiful","thought","though",
    "could","should","would",
]

LEVELS = {
    "1": {"name": "Beginner", "subtitle": "Alphabet & CVC Basics",
          "words": BEGINNER,
          "subs": [
              {"id": "1a", "name": "Short A", "words_idx": [0,23]},
              {"id": "1b", "name": "Short E", "words_idx": [24,35]},
              {"id": "1c", "name": "Short I", "words_idx": [36,51]},
              {"id": "1d", "name": "Short O", "words_idx": [52,65]},
              {"id": "1e", "name": "Short U", "words_idx": [66,79]},
              {"id": "1f", "name": "Heart Words", "words_idx": [80,97]},
          ]},
    "2": {"name": "Intermediate", "subtitle": "Blends, Digraphs & Silent E",
          "words": INTERMEDIATE,
          "subs": [
              {"id": "2a", "name": "Blends", "words_idx": [0,14]},
              {"id": "2b", "name": "Digraphs", "words_idx": [15,44]},
              {"id": "2c", "name": "FLSZ & ck", "words_idx": [45,57]},
              {"id": "2d", "name": "Silent e", "words_idx": [58,81]},
              {"id": "2e", "name": "Soft c/g", "words_idx": [82,93]},
              {"id": "2f", "name": "Heart Words", "words_idx": [94,106]},
          ]},
    "3": {"name": "Advanced", "subtitle": "R-Controlled, Vowels & Morphology",
          "words": ADVANCED,
          "subs": [
              {"id": "3a", "name": "R-Controlled", "words_idx": [0,18]},
              {"id": "3b", "name": "Vowel Teams", "words_idx": [19,44]},
              {"id": "3c", "name": "Diphthongs", "words_idx": [45,66]},
              {"id": "3d", "name": "Silent Letters", "words_idx": [67,74]},
              {"id": "3e", "name": "Suffixes & Affixes", "words_idx": [75,89]},
              {"id": "3f", "name": "Advanced Patterns", "words_idx": [90,104]},
          ]},
}

HEART_WORDS = [
    "the","a","and","is","to","of","in","I","you","it",
    "he","she","was","we","they","are","have","has","had",
    "said","do","does","done","go","going","come","came",
    "like","see","look","make","made","give","live","there",
    "where","what","when","why","who","which","how","many",
    "some","any","very","every","your","our","their","its",
    "could","would","should","because","people","know","new",
    "call","find","first","long","more","most","other","over",
    "part","place","right","same","such","tell","thing","time",
    "under","water","way","write","word","work","world","year",
]


# ── Session state (in-memory) ──────────────────────────────────────────────

WEB_SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(WEB_SESSIONS_DIR, exist_ok=True)


@dataclass
class WebSession:
    level_key: str
    words: list
    all_words: list = field(init=False)
    error_bank: list = field(default_factory=list)
    speed_mode: str = "normal"
    letter_errors: dict = field(default_factory=lambda: defaultdict(lambda: {"wrong": 0, "correct": 0}))
    round_num: int = 0
    total_attempts: int = 0
    total_correct: int = 0
    total_errors: int = 0
    words_this_round: int = 0
    correct_this_round: int = 0
    incorrect_this_round: int = 0
    word_index: int = 0
    current_word: str = ""

    def __post_init__(self):
        seen = set()
        combined = []
        for w in self.words:
            wl = w.lower()
            if wl not in seen:
                seen.add(wl)
                combined.append(wl)
        self.all_words = combined

    def pick_word(self):
        if self.error_bank and random.random() < 0.8:
            return random.choice(self.error_bank)
        weak = [l for l, s in self.letter_errors.items()
                if s["wrong"] > s["correct"] and s["wrong"] >= 2]
        if weak and random.random() < 0.5:
            candidates = [w for w in self.all_words
                          if any(l in w.lower() for l in weak) and w not in self.error_bank]
            if candidates:
                return random.choice(candidates)
        return random.choice(self.all_words)

    def log_error(self, word, attempt):
        word = word.lower().strip()
        attempt = attempt.lower().strip()
        ml = min(len(word), len(attempt))
        for i in range(ml):
            if attempt[i] != word[i]:
                self.letter_errors[word[i]]["wrong"] += 1
            else:
                self.letter_errors[word[i]]["correct"] += 1
        if len(word) > len(attempt):
            for j in range(len(attempt), len(word)):
                self.letter_errors[word[j]]["wrong"] += 1

    def save_log(self):
        """Save error log to a JSON file for persistence."""
        weak = [(l, s) for l, s in self.letter_errors.items()
                if s["wrong"] > s["correct"] and s["wrong"] >= 2]
        log = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "level": self.level_key,
            "total_attempts": self.total_attempts,
            "total_correct": self.total_correct,
            "total_errors": self.total_errors,
            "error_bank": list(self.error_bank),
            "weak_letters": {l: s for l, s in weak[:10]},
        }
        log_path = os.path.join(WEB_SESSIONS_DIR, f"log_{time.strftime('%Y%m%d')}.json")
        existing = []
        if os.path.exists(log_path):
            try:
                with open(log_path) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = []
        existing.append(log)
        with open(log_path, "w") as f:
            json.dump(existing, f, indent=2)
        return True

    def highlight_errors(self, correct, attempt):
        correct = correct.lower().strip()
        attempt = attempt.lower().strip()
        chars = []
        errors = 0
        ml = min(len(correct), len(attempt))
        for i in range(ml):
            if attempt[i] == correct[i]:
                chars.append({"char": attempt[i], "correct": True})
            else:
                chars.append({"char": attempt[i], "correct": False})
                errors += 1
        if len(attempt) > len(correct):
            for c in attempt[len(correct):]:
                chars.append({"char": c, "correct": False, "extra": True})
                errors += 1
        if len(correct) > len(attempt):
            for c in correct[len(attempt):]:
                chars.append({"char": c, "correct": False, "missing": True})
                errors += 1
        return chars, errors

    def get_summary(self):
        t = self.correct_this_round + self.incorrect_this_round
        pct = round(self.correct_this_round / max(t, 1) * 100, 1)
        weak = [(l, s) for l, s in self.letter_errors.items()
                if s["wrong"] > s["correct"] and s["wrong"] >= 2]
        weak.sort(key=lambda x: -x[1]["wrong"])
        cp = round(self.total_correct / max(self.total_attempts, 1) * 100, 1)
        return {
            "round": self.round_num,
            "total": t,
            "correct": self.correct_this_round,
            "incorrect": self.incorrect_this_round,
            "accuracy": pct,
            "error_bank": self.error_bank[:10],
            "error_bank_total": len(self.error_bank),
            "weak_letters": [l for l, _ in weak[:5]],
            "all_time_correct": self.total_correct,
            "all_time_errors": self.total_errors,
            "all_time_attempts": self.total_attempts,
            "all_time_accuracy": cp,
        }


# Session store
sessions = {}


# ── Flask Routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "phonics_web.html")


@app.route("/phonemes/<path:filename>")
def serve_phoneme(filename):
    return send_from_directory(PHONEME_DIR, filename)


@app.route("/tts_cache/<path:filename>")
def serve_tts_cache(filename):
    return send_from_directory(TTS_CACHE_DIR, filename)


# ── API Routes ─────────────────────────────────────────────────────────────

@app.route("/api/levels")
def api_levels():
    result = {}
    for k, v in LEVELS.items():
        subs = [{"id": s["id"], "name": s["name"]} for s in v.get("subs", [])]
        result[k] = {"name": v["name"], "subtitle": v["subtitle"],
                     "count": len(v["words"]), "subs": subs}
    result["heart"] = {"name": "Heart Words", "subtitle": "Sight words frequency practice",
                       "count": len(HEART_WORDS), "subs": []}
    return jsonify(result)


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json() or {}
    level_key = data.get("level", "1")
    speed_mode = data.get("speed", "normal")
    sub_id = data.get("sub", None)  # optional sub-category

    if level_key == "heart":
        # Heart words mode
        random.shuffle(HEART_WORDS)
        words = [w.lower() for w in HEART_WORDS]
    elif level_key in LEVELS:
        if sub_id:
            # Filter to sub-category words
            info = LEVELS[level_key]
            selected = None
            for s in info.get("subs", []):
                if s["id"] == sub_id:
                    start, end = s["words_idx"]
                    selected = [w.lower() for w in info["words"][start:end]]
                    break
            if not selected:
                selected = [w.lower() for w in info["words"]]
            words = selected
        else:
            words = []
            seen = set()
            for w in LEVELS[level_key]["words"]:
                wl = w.lower()
                if wl not in seen:
                    seen.add(wl)
                    words.append(wl)
    else:
        return jsonify({"error": "Invalid level"}), 400

    session_id = hashlib.sha256(str(time.time() + random.random()).encode()).hexdigest()[:12]
    sessions[session_id] = WebSession(
        level_key=level_key,
        words=words,
        speed_mode=speed_mode,
    )

    sess = sessions[session_id]
    sess.round_num = 1
    sess.words_this_round = min(10 if level_key == "heart" else 10 + 2 * int(level_key), len(words))
    sess.word_index = 0
    sess.correct_this_round = 0
    sess.incorrect_this_round = 0
    sess.current_word = sess.pick_word()

    return jsonify({
        "session_id": session_id,
        "level": "Heart Words" if level_key == "heart" else LEVELS[level_key]["name"],
        "speed": speed_mode,
        "words_this_round": sess.words_this_round,
        "round": sess.round_num,
    })


@app.route("/api/word", methods=["POST"])
def api_word():
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400

    word = sess.current_word
    phonemes = get_phoneme_list(word)
    phoneme_names = [p for _, p in phonemes] if phonemes else []
    phoneme_audios = []
    for _, arp in (phonemes or []):
        audio_path, fmt = get_phoneme_audio(arp)
        if audio_path:
            # For espeak-generated temp files, we need to serve them differently
            if audio_path.startswith(tempfile.gettempdir()):
                # Copy to cache dir for serving
                cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                if not os.path.exists(cache_path):
                    shutil.copy2(audio_path, cache_path)
                phoneme_audios.append(f"/tts_cache/{cache_name}")
            else:
                phoneme_audios.append(f"/phonemes/{os.path.basename(audio_path)}")
        else:
            phoneme_audios.append(None)

    # Generate TTS audio URL
    tts_path, tts_ok = get_tts_audio(word, 1.0)
    tts_url = f"/tts_cache/{os.path.basename(tts_path)}" if tts_ok else None

    # Slow TTS
    tts_slow_path, tts_slow_ok = get_tts_audio(word, 0.5)
    tts_slow_url = f"/tts_cache/{os.path.basename(tts_slow_path)}" if tts_slow_ok else None

    return jsonify({
        "word": word,
        "phoneme_names": phoneme_names,
        "phoneme_audios": phoneme_audios,
        "tts_url": tts_url,
        "tts_slow_url": tts_slow_url,
        "word_index": sess.word_index + 1,
        "words_this_round": sess.words_this_round,
    })


@app.route("/api/check", methods=["POST"])
def api_check():
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    attempt = data.get("attempt", "").strip().lower()
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400

    word = sess.current_word
    chars, errors = sess.highlight_errors(word, attempt)

    result = {
        "word": word,
        "chars": chars,
        "errors": errors,
        "correct": errors == 0,
    }

    if errors == 0:
        sess.total_attempts += 1
        sess.total_correct += 1
        sess.correct_this_round += 1
        for ch in word.lower():
            sess.letter_errors[ch]["correct"] += 1
        if word in sess.error_bank:
            sess.error_bank.remove(word)
        result["message"] = "Perfect! ✅"
        # Next word
        sess.word_index += 1
    else:
        sess.log_error(word, attempt)
        result["message"] = "Not quite. Try again! ❌"
        result["hint_phonemes"] = []
        phonemes = get_phoneme_list(word)
        if phonemes:
            arpabet_display = []
            for espeak_name, arpabet_name in phonemes:
                # On error, play the REPEAT version for reinforcement
                audio_path, fmt = get_phoneme_audio(arpabet_name, repeat=True)
                if not audio_path:
                    audio_path, fmt = get_phoneme_audio(arpabet_name, repeat=False)
                url = None
                if audio_path:
                    if audio_path.startswith(tempfile.gettempdir()):
                        cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                        cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                        if not os.path.exists(cache_path):
                            shutil.copy2(audio_path, cache_path)
                        url = f"/tts_cache/{cache_name}"
                    else:
                        url = f"/phonemes/{os.path.basename(audio_path)}"
                arpabet_display.append({"name": arpabet_name, "audio_url": url, "repeat": True})
            result["hint_phonemes"] = arpabet_display

    return jsonify(result)


@app.route("/api/retry_word", methods=["POST"])
def api_retry():
    """Get audio again for the same word (retry)."""
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400

    word = sess.current_word
    phonemes = get_phoneme_list(word)
    phoneme_names = [p for _, p in phonemes] if phonemes else []
    phoneme_audios = []
    for _, arp in (phonemes or []):
        audio_path, fmt = get_phoneme_audio(arp)
        if audio_path:
            if audio_path.startswith(tempfile.gettempdir()):
                cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                if not os.path.exists(cache_path):
                    shutil.copy2(audio_path, cache_path)
                phoneme_audios.append(f"/tts_cache/{cache_name}")
            else:
                phoneme_audios.append(f"/phonemes/{os.path.basename(audio_path)}")
        else:
            phoneme_audios.append(None)

    return jsonify({
        "word": word,
        "phoneme_names": phoneme_names,
        "phoneme_audios": phoneme_audios,
        "tts_url": f"/tts_cache/{os.path.basename(get_tts_audio(word, 1.0)[0])}",
        "tts_slow_url": f"/tts_cache/{os.path.basename(get_tts_audio(word, 0.5)[0])}",
        "speed_mode": sess.speed_mode,
    })


@app.route("/api/hint", methods=["POST"])
def api_hint():
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400

    word = sess.current_word
    phonemes = get_phoneme_list(word)
    phoneme_data = []
    if phonemes:
        for espeak_name, arpabet_name in phonemes:
            # Hint uses the repeat version too (reinforcement)
            audio_path, fmt = get_phoneme_audio(arpabet_name, repeat=True)
            if not audio_path:
                audio_path, fmt = get_phoneme_audio(arpabet_name, repeat=False)
            url = None
            if audio_path:
                if audio_path.startswith(tempfile.gettempdir()):
                    cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                    cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                    if not os.path.exists(cache_path):
                        shutil.copy2(audio_path, cache_path)
                    url = f"/tts_cache/{cache_name}"
                else:
                    url = f"/phonemes/{os.path.basename(audio_path)}"
            phoneme_data.append({"name": arpabet_name, "audio_url": url})

    return jsonify({
        "phonemes": phoneme_data,
        "tts_slow_url": f"/tts_cache/{os.path.basename(get_tts_audio(word, 0.5)[0])}",
    })


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400

    word = sess.current_word
    phonemes = get_phoneme_list(word)
    phoneme_names = [p for _, p in phonemes] if phonemes else []

    sess.total_attempts += 1
    sess.total_errors += 1
    sess.incorrect_this_round += 1
    if word not in sess.error_bank:
        sess.error_bank.append(word)
    sess.word_index += 1

    return jsonify({
        "word": word,
        "phoneme_names": phoneme_names,
    })


@app.route("/api/skip", methods=["POST"])
def api_skip():
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400

    word = sess.current_word
    sess.total_attempts += 1
    sess.total_errors += 1
    sess.incorrect_this_round += 1
    if word not in sess.error_bank:
        sess.error_bank.append(word)
    sess.word_index += 1

    return jsonify({"skipped": True})


@app.route("/api/next_word", methods=["POST"])
def api_next_word():
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400

    if sess.word_index >= sess.words_this_round:
        # Round complete
        return jsonify({"round_complete": True})

    sess.current_word = sess.pick_word()
    word = sess.current_word
    phonemes = get_phoneme_list(word)
    phoneme_names = [p for _, p in phonemes] if phonemes else []
    phoneme_audios = []
    for _, arp in (phonemes or []):
        audio_path, fmt = get_phoneme_audio(arp)
        if audio_path:
            if audio_path.startswith(tempfile.gettempdir()):
                cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                if not os.path.exists(cache_path):
                    shutil.copy2(audio_path, cache_path)
                phoneme_audios.append(f"/tts_cache/{cache_name}")
            else:
                phoneme_audios.append(f"/phonemes/{os.path.basename(audio_path)}")
        else:
            phoneme_audios.append(None)

    tts_path, tts_ok = get_tts_audio(word, 1.0)
    tts_url = f"/tts_cache/{os.path.basename(tts_path)}" if tts_ok else None
    tts_slow_path, tts_slow_ok = get_tts_audio(word, 0.5)
    tts_slow_url = f"/tts_cache/{os.path.basename(tts_slow_path)}" if tts_slow_ok else None

    return jsonify({
        "word": word,
        "phoneme_names": phoneme_names,
        "phoneme_audios": phoneme_audios,
        "tts_url": tts_url,
        "tts_slow_url": tts_slow_url,
        "word_index": sess.word_index + 1,
        "words_this_round": sess.words_this_round,
    })


@app.route("/api/summary", methods=["POST"])
def api_summary():
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400
    sess.save_log()  # persist errors to disk
    return jsonify(sess.get_summary())


@app.route("/api/next_round", methods=["POST"])
def api_next_round():
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400

    sess.round_num += 1
    if sess.level_key == "heart":
        sess.words_this_round = min(10, len(sess.all_words))
    else:
        sess.words_this_round = min(10 + 2 * int(sess.level_key), len(sess.all_words))
    sess.correct_this_round = 0
    sess.incorrect_this_round = 0
    sess.word_index = 0
    sess.current_word = sess.pick_word()

    word = sess.current_word
    phonemes = get_phoneme_list(word)
    phoneme_names = [p for _, p in phonemes] if phonemes else []
    phoneme_audios = []
    for _, arp in (phonemes or []):
        audio_path, fmt = get_phoneme_audio(arp)
        if audio_path:
            if audio_path.startswith(tempfile.gettempdir()):
                cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                if not os.path.exists(cache_path):
                    shutil.copy2(audio_path, cache_path)
                phoneme_audios.append(f"/tts_cache/{cache_name}")
            else:
                phoneme_audios.append(f"/phonemes/{os.path.basename(audio_path)}")
        else:
            phoneme_audios.append(None)

    tts_path, tts_ok = get_tts_audio(word, 1.0)
    tts_url = f"/tts_cache/{os.path.basename(tts_path)}" if tts_ok else None
    tts_slow_path, tts_slow_ok = get_tts_audio(word, 0.5)
    tts_slow_url = f"/tts_cache/{os.path.basename(tts_slow_path)}" if tts_slow_ok else None

    return jsonify({
        "round": sess.round_num,
        "word": word,
        "phoneme_names": phoneme_names,
        "phoneme_audios": phoneme_audios,
        "tts_url": tts_url,
        "tts_slow_url": tts_slow_url,
        "word_index": 1,
        "words_this_round": sess.words_this_round,
    })


@app.route("/api/errors")
def api_errors():
    """Return all saved error logs for review."""
    logs = []
    for fname in sorted(os.listdir(WEB_SESSIONS_DIR)):
        if fname.startswith("log_") and fname.endswith(".json"):
            try:
                with open(os.path.join(WEB_SESSIONS_DIR, fname)) as f:
                    logs.extend(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    # Return last 50 entries
    return jsonify(logs[-50:])


@app.route("/api/speak_custom", methods=["POST"])
def api_speak_custom():
    """Get phoneme breakdown and audio for any custom word."""
    data = request.get_json() or {}
    word = data.get("word", "").strip().lower()
    if not word:
        return jsonify({"error": "No word provided"}), 400

    phonemes = get_phoneme_list(word)
    phoneme_names = [p for _, p in phonemes] if phonemes else []
    phoneme_audios = []
    for _, arp in (phonemes or []):
        audio_path, fmt = get_phoneme_audio(arp)
        if audio_path:
            if audio_path.startswith(tempfile.gettempdir()):
                cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                if not os.path.exists(cache_path):
                    shutil.copy2(audio_path, cache_path)
                phoneme_audios.append(f"/tts_cache/{cache_name}")
            else:
                phoneme_audios.append(f"/phonemes/{os.path.basename(audio_path)}")
        else:
            phoneme_audios.append(None)

    tts_path, tts_ok = get_tts_audio(word, 1.0)
    tts_url = f"/tts_cache/{os.path.basename(tts_path)}" if tts_ok else None
    tts_slow_path, tts_slow_ok = get_tts_audio(word, 0.5)
    tts_slow_url = f"/tts_cache/{os.path.basename(tts_slow_path)}" if tts_slow_ok else None

    # Also get repeat versions for errors
    phoneme_repeat_audios = []
    for _, arp in (phonemes or []):
        audio_path, fmt = get_phoneme_audio(arp, repeat=True)
        if not audio_path:
            audio_path, fmt = get_phoneme_audio(arp, repeat=False)
        if audio_path:
            if audio_path.startswith(tempfile.gettempdir()):
                cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                if not os.path.exists(cache_path):
                    shutil.copy2(audio_path, cache_path)
                phoneme_repeat_audios.append(f"/tts_cache/{cache_name}")
            else:
                phoneme_repeat_audios.append(f"/phonemes/{os.path.basename(audio_path)}")
        else:
            phoneme_repeat_audios.append(None)

    return jsonify({
        "word": word,
        "found": phonemes is not None,
        "phoneme_names": phoneme_names,
        "phoneme_audios": phoneme_audios,
        "phoneme_repeat_audios": phoneme_repeat_audios,
        "tts_url": tts_url,
        "tts_slow_url": tts_slow_url,
    })

@app.route("/api/set_speed", methods=["POST"])
def api_set_speed():
    data = request.get_json() or {}
    session_id = data.get("session_id", "")
    speed = data.get("speed", "normal")
    sess = sessions.get(session_id)
    if not sess:
        return jsonify({"error": "Session expired or invalid"}), 400
    if speed not in ("normal", "slow", "phoneme"):
        return jsonify({"error": "Invalid speed"}), 400
    sess.speed_mode = speed
    return jsonify({"speed_mode": speed})


@app.route("/api/audio_test", methods=["GET"])
def api_audio_test():
    """Test that TTS is working."""
    tts_path, tts_ok = get_tts_audio("hello", 1.0)
    phoneme_count = sum(1 for f in os.listdir(PHONEME_DIR) if f.endswith(".wav")) if os.path.isdir(PHONEME_DIR) else 0
    espeak_ok = ESPEAK_EXE is not None
    return jsonify({
        "tts_ok": tts_ok,
        "phoneme_count": phoneme_count,
        "espeak_ok": espeak_ok,
    })


# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phonics Dictation Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()
    print(f"  ╔═══ Phonics Dictation Web ═══╗")
    print(f"  ║ http://{args.host}:{args.port} ║")
    print(f"  ╚════════════════════════════════╝")
    app.run(host=args.host, port=args.port, debug=args.debug)
