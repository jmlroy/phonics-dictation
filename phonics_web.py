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
    "AO": "AO_single.wav",
    "AR": "AR.wav",
    "AW": "AW_single.wav",
    "AY": "AY_single.wav",
    "B": "B_single.wav",
    "CH": "CH_single.wav",
    "D": "D_single.wav",
    "DH": "DH_single.wav",
    "EH": "EH_single.wav",
    "ER": "ER_single.wav",
    "EY": "EY_single.wav",
    "F": "F_single.wav",
    "G": "G_single.wav",
    "HH": "HH_single.wav",
    "IH": "IH_single.wav",
    "IY": "IY_single.wav",
    "JH": "JH_single.wav",
    "K": "K_single.wav",
    "KS": "KS_single.wav",
    "KW": "KW_single.wav",
    "L": "L_single.wav",
    "M": "M_single.wav",
    "N": "N_single.wav",
    "NG": "NG_single.wav",
    "OW": "OW_single.wav",
    "OY": "OY_single.wav",
    "P": "P_single.wav",
    "R": "R_single.wav",
    "S": "S_single.wav",
    "SH": "SH_single.wav",
    "T": "T_single.wav",
    "TH": "TH_single.wav",
    "UH": "UH_single.wav",
    "UW": "UW_single.wav",
    "V": "V_single.wav",
    "W": "W_single.wav",
    "WH": "WH_single.wav",
    "Y": "Y_single.wav",
    "Z": "Z_single.wav",
    "ZH": "ZH_single.wav",
}

ARPABET_TO_WAV_REPEAT = {
    "AA": "AA_repeat.wav",
    "AE": "AE_repeat.wav",
    "AH": "AH_repeat.wav",
    "AO": "AO_repeat.wav",
    "AW": "AW_repeat.wav",
    "AY": "AY_repeat.wav",
    "B": "B_repeat.wav",
    "CH": "CH_repeat.wav",
    "D": "D_repeat.wav",
    "DH": "DH_repeat.wav",
    "EH": "EH_repeat.wav",
    "ER": "ER_repeat.wav",
    "EY": "EY_repeat.wav",
    "F": "F_repeat.wav",
    "G": "G_repeat.wav",
    "HH": "HH_repeat.wav",
    "IH": "IH_repeat.wav",
    "IY": "IY_repeat.wav",
    "JH": "JH_repeat.wav",
    "K": "K_repeat.wav",
    "KS": "KS_repeat.wav",
    "KW": "KW_repeat.wav",
    "L": "L_repeat.wav",
    "M": "M_repeat.wav",
    "N": "N_repeat.wav",
    "NG": "NG_repeat.wav",
    "OW": "OW_repeat.wav",
    "OY": "OY_repeat.wav",
    "P": "P_repeat.wav",
    "R": "R_repeat.wav",
    "S": "S_repeat.wav",
    "SH": "SH_repeat.wav",
    "T": "T_repeat.wav",
    "TH": "TH_repeat.wav",
    "UH": "UH_repeat.wav",
    "UW": "UW_repeat.wav",
    "V": "V_repeat.wav",
    "W": "W_repeat.wav",
    "WH": "WH_repeat.wav",
    "Y": "Y_repeat.wav",
    "Z": "Z_repeat.wav",
    "ZH": "ZH_repeat.wav",
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


# ARPAbet to IPA mapping for display
ARPABET_TO_IPA = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ",
    "AY": "aɪ", "EH": "ɛ", "ER": "ɝ", "EY": "eɪ", "IH": "ɪ",
    "IY": "i", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ", "UW": "u",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f",
    "G": "g", "HH": "h", "JH": "dʒ", "K": "k", "L": "l",
    "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "r",
    "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "V": "v",
    "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}

# Grapheme pattens for letter-group splitting
GRAPHEME_PATTERNS = sorted([
    "tch","dge","eigh","augh","ough","igh","qu",
    "th","sh","ch","wh","ph","ck","ng","nk","kn","wr","gn","mb",
    "ee","ea","ai","ay","oa","ow","oe","ie","ei","ey","oi","oy",
    "oo","ew","ui","ue","ou","au","aw",
    "ar","or","er","ir","ur","ear",
    "bb","dd","ff","gg","ll","mm","nn","pp","rr","ss","tt","zz",
    "ci","ti","si","di","tu","ture","sure",
], key=len, reverse=True)


def split_graphemes(word):
    """Split word into grapheme groups matching phoneme boundaries."""
    w = word.lower()
    parts = []
    i = 0
    while i < len(w):
        matched = False
        for p in GRAPHEME_PATTERNS:
            if w[i:i+len(p)] == p:
                parts.append(p)
                i += len(p)
                matched = True
                break
        if not matched:
            # Check for silent e at end
            if w[i] == 'e' and i == len(w) - 1 and len(parts) > 0:
                parts[-1] += 'e'
                i += 1
            else:
                parts.append(w[i])
                i += 1
    return parts


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

    key = hashlib.md5(f"{word}:{speech_rate}:{SPEAKER}".encode()).hexdigest()
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
    # Short A (26)
    "cat","bat","hat","mat","rat","sat","fat","pat",
    "can","man","pan","fan","van","ran",
    "map","tap","nap","gap","bad","dad","pad","sad",
    "ant","cab","cap","wag",
    # Short E (18)
    "bed","red","fed","led","hen","pen","ten","men",
    "jet","net","pet","wet",
    "egg","elk","peg","leg","web","den",
    # Short I (24)
    "big","pig","dig","wig","bin","pin","tin","win",
    "fit","hit","sit","bit","lip","tip","rip","zip",
    "kit","lid","six","mix","fix","fin","dip","yam",
    # Short O (18)
    "dog","log","fog","hog","hop","mop","top","pop",
    "pot","hot","dot","not","box","fox",
    "ox","rod","sob","job",
    # Short U (19)
    "bug","jug","mug","rug","bus","cup","pup",
    "sun","run","fun","bun","hut","nut","cut",
    "gum","mud","tub","bud","hum",
    # Heart Words (28)
    "a","the","is","i","to","has","you",
    "and","said","go","he","she","was",
    "they","are","have","do","of","for",
    "we","my","all","her","his","put","say",
    "why","yes",
    # Extra CVC words (40)
    "jam","yak","ram","bib","rib","kid",
    "dim","him","sin","pit","mitt","nib",
    "cob","cog","jog",
    "vet","zoo","ax",
    "elf","ink","cub","sub",
    "mad","lad","bag","rag",
    "tag","sap",
]

INTERMEDIATE = [
    # Blends (20)
    "mask","hand","flag","plan","flat","camp",
    "slip","spill","wind","swim","list","milk",
    "drop","frog","spot","pond","stop",
    "drum","plug","jump","hunt","dust",
    "tent","belt","nest","desk","step",
    "blend","clap","crab","grab","skip","sled","snap","trap",
    # Digraphs (30)
    "ship","shop","fish","shell","dish","cash","rush",
    "that","them","then","this","than",
    "thin","thick","bath","moth","path",
    "chin","chip","chop","rich","lunch","much",
    "whip","whale","wheel","phone","photo","graph",
    "king","ring","wing","song","lung","bang",
    "sink","pink","tank","bank","wink","trunk",
    "shut","wish","bush","chat","thud","whiz",
    # FLSZ & ck (12)
    "cliff","puff","hill","bell","miss","buzz",
    "ball","tall","toll","bull","full",
    "duck","neck","lock","rock","sock","pick",
    "back","pack","kick","luck",
    # Silent e (24)
    "cake","lake","gate","cape","game","late","name",
    "kite","pine","bike","bite","line","lime","side",
    "bone","rope","home","nose","rose","joke","hope",
    "tube","mule","cute","flute","tune","rude",
    "wide","dime","nine","pole","vote","woke",
    # Soft c/g (12)
    "face","lace","rice","mice","nice","space","place",
    "cage","page","rage","huge","stage",
    "gem","city","cent",
    # Heart Words
    "there","their","where","what","why","who","when",
    "some","come","one","once","wash",
    "mother","father","give","live","done","gone",
    # Extra blend/digraph words (40)
    "cram","grim","prop","scan","skim","stun",
    "twin","trim","swan","brim","grin","trot",
    "club","glad","glum","plum","slid","slug","snip",
    "stir","trip","twig",
    "brick","clock","crack","dress","freck","press",
    "stick","track","trick","twist","brand","spend",
    "crisp","draft","frost","grunt","stamp","blast",
    "trust","swept","clamp","crept",
]

ADVANCED = [
    # R-Controlled (18)
    "car","star","park","dark","yard","farm",
    "fork","storm","corn","more","shore",
    "her","sister","brother","dinner","tiger","paper",
    "bird","girl","dirt","shirt","fur","turn","burn",
    "word","world","work",
    "card","hard","part","start","mark","bark",
    # Vowel Teams (26)
    "rain","train","paint","play","day","clay",
    "tree","green","seat","beach","key","monkey",
    "boat","coat","road","snow","blow","toe",
    "pie","tie","light","night","high","fight",
    "book","look","foot","wood","good","push",
    "moon","spoon","food","pool","cool","room",
    "grew","flew","juice","fruit","blue","clue",
    "saw","straw","draw","haul","sauce","caught",
    "head","bread","heavy","sweat","water",
    "stay","wait","mail","tail","main",
    "seed","feed","need","keep","week",
    # Diphthongs (22)
    "coin","point","soil","boy","toy","joy",
    "out","house","mouse","cow","town","brown",
    "down","how","now","loud","cloud","round",
    # Silent Letters (6)
    "knee","knit","write","wrong","lamb","comb",
    "knock","knife","wrap",
    # Suffixes & Affixes (15)
    "bigger","tallest","faster","slowly","softly",
    "helpful","playful","unhappy","rewrite","refill",
    "running","hopped","baked","dried","babies",
    # Advanced Patterns (15)
    "action","station","picture","nature","mixture",
    "answer","neighbor","beautiful","thought","though",
    "could","should","would",
    # Extra advanced words (35)
    "teach","reach","beast","cream","dream","steam",
    "cheap","clean","clear","bleed","creep","sweet",
    "float","gloat","coast","toast","roast","boost",
    "crowd","proud","shout","south","mouth","found",
    "ground","sound","bound","count","mount",
    "chair","stair","chain","brain","plain",
]
# ── Handwriting Stroke Data ────────────────────────────────────────────
# Each letter has: group, uppercase version, strokes (normalized 0-100 grid)
# stroke: [{x,y},...] sequence of points forming the pen path
# type: "down"|"up"|"curve"|"circle"|"hook"

# Handwriting groups (from Units 8-12)
HANDWRITING_GROUPS = {
    "straight_drops": {"name": "Straight Drops", "letters": ["l","t","i","j","u"]},
    "bounce_backs": {"name": "Bounce-Backs", "letters": ["n","m","r","h","b","p"]},
    "smooth_loops": {"name": "Smooth Loops", "letters": ["c","a","d","o","g","q"]},
    "slanted_vectors": {"name": "Slanted Vectors", "letters": ["v","w","x","y","k"]},
    "slippery_curves": {"name": "Slippery Curves", "letters": ["s","e","f","z"]},
}

# Stroke paths for each lowercase letter (normalized 0-100 grid)
# Each stroke is an array of {x,y} waypoints
HANDWRITING_STROKES = {
    "a": {"group": "smooth_loops", "strokes": [
        [{"x":50,"y":10},{"x":30,"y":20},{"x":20,"y":40},{"x":20,"y":60},{"x":30,"y":80},{"x":50,"y":90},{"x":70,"y":80},{"x":80,"y":60},{"x":80,"y":40},{"x":50,"y":40}],
        [{"x":50,"y":40},{"x":50,"y":70},{"x":55,"y":80},{"x":60,"y":85},{"x":70,"y":80},{"x":80,"y":70}],
    ]},
    "b": {"group": "bounce_backs", "strokes": [
        [{"x":30,"y":0},{"x":30,"y":40},{"x":30,"y":90},{"x":35,"y":95},{"x":40,"y":90}],
        [{"x":30,"y":40},{"x":40,"y":20},{"x":60,"y":15},{"x":75,"y":25},{"x":80,"y":40},{"x":80,"y":60},{"x":75,"y":75},{"x":60,"y":85},{"x":40,"y":85},{"x":30,"y":80}],
    ]},
    "c": {"group": "smooth_loops", "strokes": [
        [{"x":80,"y":20},{"x":60,"y":15},{"x":40,"y":25},{"x":25,"y":40},{"x":20,"y":60},{"x":25,"y":80},{"x":40,"y":90},{"x":60,"y":95},{"x":80,"y":90}],
    ]},
    "d": {"group": "smooth_loops", "strokes": [
        [{"x":50,"y":10},{"x":70,"y":20},{"x":80,"y":40},{"x":85,"y":60},{"x":80,"y":80},{"x":65,"y":90},{"x":50,"y":95},{"x":35,"y":85},{"x":25,"y":70},{"x":25,"y":50},{"x":35,"y":35},{"x":50,"y":25}],
        [{"x":50,"y":0},{"x":50,"y":25},{"x":55,"y":30}],
    ]},
    "e": {"group": "slippery_curves", "strokes": [
        [{"x":80,"y":40},{"x":50,"y":35},{"x":30,"y":40},{"x":20,"y":55},{"x":25,"y":75},{"x":40,"y":88},{"x":60,"y":90},{"x":75,"y":85},{"x":80,"y":75}],
        [{"x":80,"y":40},{"x":25,"y":55}],
    ]},
    "f": {"group": "slippery_curves", "strokes": [
        [{"x":55,"y":0},{"x":55,"y":80}],
        [{"x":35,"y":25},{"x":75,"y":25}],
        [{"x":55,"y":80},{"x":45,"y":90},{"x":35,"y":93},{"x":25,"y":88}],
    ]},
    "g": {"group": "smooth_loops", "strokes": [
        [{"x":45,"y":10},{"x":65,"y":18},{"x":75,"y":35},{"x":78,"y":55},{"x":70,"y":75},{"x":55,"y":85},{"x":40,"y":80},{"x":30,"y":65},{"x":28,"y":45},{"x":35,"y":28},{"x":50,"y":20}],
        [{"x":50,"y":55},{"x":55,"y":85},{"x":60,"y":100},{"x":70,"y":110},{"x":85,"y":115}],
    ]},
    "h": {"group": "bounce_backs", "strokes": [
        [{"x":25,"y":0},{"x":25,"y":90},{"x":30,"y":95},{"x":35,"y":90}],
        [{"x":25,"y":40},{"x":45,"y":20},{"x":65,"y":15},{"x":78,"y":25},{"x":82,"y":45},{"x":80,"y":65},{"x":75,"y":80},{"x":65,"y":88},{"x":55,"y":85}],
    ]},
    "i": {"group": "straight_drops", "strokes": [
        [{"x":50,"y":30},{"x":50,"y":90},{"x":52,"y":93}],
        [{"x":47,"y":15},{"x":53,"y":15}],
    ]},
    "j": {"group": "straight_drops", "strokes": [
        [{"x":65,"y":30},{"x":60,"y":80},{"x":55,"y":100},{"x":45,"y":110},{"x":30,"y":112}],
        [{"x":62,"y":15},{"x":68,"y":15}],
    ]},
    "k": {"group": "slanted_vectors", "strokes": [
        [{"x":30,"y":0},{"x":30,"y":90},{"x":32,"y":93}],
        [{"x":30,"y":45},{"x":70,"y":20}],
        [{"x":35,"y":50},{"x":70,"y":85}],
    ]},
    "l": {"group": "straight_drops", "strokes": [
        [{"x":45,"y":0},{"x":45,"y":85},{"x":48,"y":92},{"x":55,"y":95}],
        [{"x":40,"y":92},{"x":55,"y":95},{"x":60,"y":92}],
    ]},
    "m": {"group": "bounce_backs", "strokes": [
        [{"x":15,"y":40},{"x":15,"y":85},{"x":18,"y":90},{"x":22,"y":88}],
        [{"x":15,"y":40},{"x":25,"y":20},{"x":40,"y":15},{"x":50,"y":25},{"x":50,"y":60},{"x":48,"y":75},{"x":42,"y":85},{"x":35,"y":88}],
        [{"x":50,"y":40},{"x":60,"y":20},{"x":75,"y":15},{"x":85,"y":25},{"x":85,"y":60},{"x":82,"y":75},{"x":75,"y":85},{"x":65,"y":88}],
    ]},
    "n": {"group": "bounce_backs", "strokes": [
        [{"x":20,"y":40},{"x":20,"y":85},{"x":22,"y":90},{"x":26,"y":88}],
        [{"x":20,"y":40},{"x":35,"y":20},{"x":55,"y":15},{"x":70,"y":25},{"x":78,"y":45},{"x":75,"y":65},{"x":68,"y":80},{"x":58,"y":88},{"x":48,"y":85}],
    ]},
    "o": {"group": "smooth_loops", "strokes": [
        [{"x":50,"y":10},{"x":30,"y":20},{"x":20,"y":40},{"x":18,"y":60},{"x":25,"y":80},{"x":40,"y":92},{"x":60,"y":92},{"x":75,"y":80},{"x":82,"y":60},{"x":80,"y":40},{"x":70,"y":20},{"x":50,"y":10}],
    ]},
    "p": {"group": "bounce_backs", "strokes": [
        [{"x":35,"y":20},{"x":35,"y":40},{"x":35,"y":95},{"x":37,"y":100},{"x":42,"y":98}],
        [{"x":35,"y":40},{"x":45,"y":20},{"x":65,"y":15},{"x":80,"y":25},{"x":85,"y":45},{"x":80,"y":65},{"x":65,"y":78},{"x":45,"y":80},{"x":35,"y":75}],
    ]},
    "q": {"group": "smooth_loops", "strokes": [
        [{"x":50,"y":10},{"x":30,"y":22},{"x":20,"y":45},{"x":22,"y":65},{"x":35,"y":80},{"x":55,"y":85},{"x":70,"y":75},{"x":78,"y":55},{"x":72,"y":35},{"x":58,"y":22},{"x":45,"y":25}],
        [{"x":55,"y":55},{"x":65,"y":85},{"x":75,"y":100}],
    ]},
    "r": {"group": "bounce_backs", "strokes": [
        [{"x":20,"y":40},{"x":20,"y":85},{"x":22,"y":90}],
        [{"x":20,"y":40},{"x":40,"y":20},{"x":65,"y":18},{"x":78,"y":25},{"x":80,"y":35}],
    ]},
    "s": {"group": "slippery_curves", "strokes": [
        [{"x":70,"y":20},{"x":50,"y":18},{"x":30,"y":25},{"x":22,"y":40},{"x":28,"y":55},{"x":50,"y":60},{"x":70,"y":65},{"x":78,"y":80},{"x":70,"y":92},{"x":50,"y":95},{"x":30,"y":90}],
    ]},
    "t": {"group": "straight_drops", "strokes": [
        [{"x":50,"y":0},{"x":50,"y":85},{"x":48,"y":92}],
        [{"x":30,"y":40},{"x":70,"y":40}],
    ]},
    "u": {"group": "straight_drops", "strokes": [
        [{"x":25,"y":35},{"x":25,"y":75},{"x":30,"y":88},{"x":45,"y":95},{"x":65,"y":92},{"x":75,"y":80},{"x":78,"y":55}],
        [{"x":75,"y":35},{"x":75,"y":55}],
    ]},
    "v": {"group": "slanted_vectors", "strokes": [
        [{"x":20,"y":20},{"x":50,"y":85},{"x":52,"y":88}],
        [{"x":50,"y":85},{"x":80,"y":20}],
    ]},
    "w": {"group": "slanted_vectors", "strokes": [
        [{"x":15,"y":20},{"x":30,"y":85},{"x":35,"y":88}],
        [{"x":30,"y":85},{"x":50,"y":20}],
        [{"x":50,"y":20},{"x":70,"y":85},{"x":72,"y":88}],
        [{"x":70,"y":85},{"x":85,"y":20}],
    ]},
    "x": {"group": "slanted_vectors", "strokes": [
        [{"x":25,"y":15},{"x":75,"y":85}],
        [{"x":75,"y":15},{"x":25,"y":85}],
    ]},
    "y": {"group": "slanted_vectors", "strokes": [
        [{"x":25,"y":20},{"x":50,"y":60}],
        [{"x":50,"y":60},{"x":75,"y":20}],
        [{"x":50,"y":60},{"x":50,"y":95},{"x":45,"y":110},{"x":35,"y":115},{"x":25,"y":112}],
    ]},
    "z": {"group": "slippery_curves", "strokes": [
        [{"x":75,"y":18},{"x":25,"y":18}],
        [{"x":25,"y":18},{"x":75,"y":85}],
        [{"x":75,"y":85},{"x":25,"y":85}],
    ]},
}

# Uppercase versions (capital letters)
HANDWRITING_UPPER = {
    "a": "A","b":"B","c":"C","d":"D","e":"E","f":"F","g":"G",
    "h":"H","i":"I","j":"J","k":"K","l":"L","m":"M","n":"N",
    "o":"O","p":"P","q":"Q","r":"R","s":"S","t":"T","u":"U",
    "v":"V","w":"W","x":"X","y":"Y","z":"Z",
}

# ── UFLI-inspired Learn Curriculum ──
# Each lesson introduces letters, then CVC words using those letters, then heart words.
# Letter → ARPABET mapping for phoneme sound audio
LETTER_PHONEME = {
    "a":"AE","b":"B","c":"K","d":"D","e":"EH","f":"F","g":"G",
    "h":"HH","i":"IH","j":"JH","k":"K","l":"L","m":"M","n":"N",
    "o":"AA","p":"P","q":"KW","r":"R","s":"S","t":"T","u":"AH",
    "v":"V","w":"W","x":"KS","y":"Y","z":"Z",
}

# Speech recognition: what we expect when child says the PHONEME sound (not letter name)
# Key is the letter, value is a list of possible speech-rec text matches
PHONEME_SPEECH_MAP = {
    "a":["a","ah","aa","uh"], "b":["b","buh","buhh"], "c":["k","kuh","c","cuh"],
    "d":["d","duh","dduh"], "e":["e","eh","euh"], "f":["f","ff","fff","fuh"],
    "g":["g","guh","gg"], "h":["h","hh","huh","hhu"], "i":["i","ih","iih"],
    "j":["j","juh","jj"], "k":["k","kuh","c","ck"], "l":["l","ll","luh","el"],
    "m":["m","mm","mmm","um","muh"], "n":["n","nn","nnn","un","nuh"],
    "o":["o","ah","aw","aa","oah"], "p":["p","puh","pp"],
    "q":["kw","qu","k","q"], "r":["r","rr","rrr","er","ruh"],
    "s":["s","ss","sss","ess","suh"], "t":["t","tuh","tt"],
    "u":["u","uh","uu","uuh"], "v":["v","vv","vvv","vuh"],
    "w":["w","ww","www","wuh"], "x":["ks","kss","x","xx","zz"],
    "y":["y","yy","yuh"], "z":["z","zz","zzz","zed"],
}
# Letter name recognition (for detecting wrong answers)
LETTER_NAME_SPEECH = {
    "a":["ay","aye","aei"],"b":["be","bee","bea"],"c":["se","see","sea","cee"],
    "d":["de","dee","dea"],"e":["ee","e"],"f":["ef","effe"],"g":["je","gee","jea"],
    "h":["aitch","eitch","haitch"],"i":["eye","aye"],"j":["jay","jae","jei"],
    "k":["kay","kei","cay"],"l":["el","ell","ele"],"m":["em","emm","eme"],
    "n":["en","enn","ene"],"o":["oh","ow","o"],"p":["pee","pe"],"q":["cue","kyu","q"],
    "r":["ar","are","arr"],"s":["ess","es","ces"],"t":["tee","te"],"u":["you","yew","u"],
    "v":["vee","ve"],"w":["double-u","doubleyou","dabelyu"],"x":["ex","eks","x"],
    "y":["why","wye","wy"],"z":["zed","zee","z"],
}

# UFLI-based Learn Curriculum: lessons, each with letters + CVC words + heart words
LEARN_LESSONS = [
    # ── Unit 1: a m s t ──
    {"id": "l1", "name": "a m s t",
     "letters": ["a","m","s","t"],
     "cvc_words": ["am","at","mat","sat","tam","sam"],
     "heart_words": ["a"]},

    # ── Unit 2: p f i n ──
    {"id": "l2", "name": "p f i n",
     "letters": ["p","f","i","n"],
     "cvc_words": ["sit","fit","fin","pin","pan","tan","tin","map","tap","nap","pit","pat","fat","fan","sip","nip","tip"],
     "heart_words": ["the","is"]},

    # ── Unit 3: c o d u ──
    {"id": "l3", "name": "c o d u",
     "letters": ["c","o","d","u"],
     "cvc_words": ["cod","cot","cat","cap","cup","pup","cop","cut","dad","did","dip","mop","top","mud","sun","sad"],
     "heart_words": ["i","to","has","you"]},

    # ── Unit 4: g b e k ──
    {"id": "l4", "name": "g b e k",
     "letters": ["g","b","e","k"],
     "cvc_words": ["big","bid","kid","kit","bag","pen","pet","net","ten","gum","pig","bed","bus","dog"],
     "heart_words": ["and","said","go"]},

    # ── Unit 5: h r l w ──
    {"id": "l5", "name": "h r l w",
     "letters": ["h","r","l","w"],
     "cvc_words": ["hat","rat","red","led","leg","log","lug","wig","win","hen","hug","hop","run","rug","rot","lap","lip","wet","web"],
     "heart_words": ["he","she","was"]},

    # ── Unit 6: j y v ──
    {"id": "l6", "name": "j y v",
     "letters": ["j","y","v"],
     "cvc_words": ["jam","jet","yet","yak","yam","wet","vet","van","fan","fin"],
     "heart_words": ["they","are","have"]},

    # ── Unit 7: x qu z ──
    {"id": "l7", "name": "x qu z",
     "letters": ["x","q","z"],
     "cvc_words": ["tax","wax","mix","fix","fox","box","quiz","quit","zip","zap","wet"],
     "heart_words": ["of","for","my"]},

    # ── Unit 8: Handwriting — Straight Drops (l t i j u) ──
    {"id": "l8", "name": "Straight Drops l t i j u",
     "letters": ["l","t","i","j","u"],
     "cvc_words": ["lit","fit","lip","lid","led","jet","jug","jut","ill","bill","hill","mill","pill","till","fill"],
     "heart_words": ["see","to"]},

    # ── Unit 9: Handwriting — Bounce-Backs (n m r h b p) ──
    {"id": "l9", "name": "Bounce-Backs n m r h b p",
     "letters": ["n","m","r","h","b","p"],
     "cvc_words": ["pan","pin","pen","hen","hug","rug","run","bun","bin","bit","man","fan","sun","map"],
     "heart_words": ["you","and","said","go","has"]},

    # ── Unit 10: Handwriting — Smooth Loops (c a d o g qu) ──
    {"id": "l10", "name": "Smooth Loops c a d o g qu",
     "letters": ["c","a","d","o","g","q"],
     "cvc_words": ["cat","cot","cod","dog","bog","bag","tag","cab","dad","sad","mad","bad","hag"],
     "heart_words": ["he","she","was","they","are"]},

    # ── Unit 11: Handwriting — Slanted Vectors (v w x y k) ──
    {"id": "l11", "name": "Slanted Vectors v w x y k",
     "letters": ["v","w","x","y","k"],
     "cvc_words": ["van","wet","wig","win","mix","fix","fox","box","yak","kid","kit"],
     "heart_words": ["have","of","for","my"]},

    # ── Unit 12: Handwriting — Slippery Curves (s e f z) ──
    {"id": "l12", "name": "Slippery Curves s e f z",
     "letters": ["s","e","f","z"],
     "cvc_words": ["sun","sat","sit","fit","fed","net","wet","zip","zap","quiz","quit"],
     "heart_words": ["the","is","a","i","to","you","and","said","go","he","she","was","they","are","have","of","for","my"]},
]

LEVELS = {
    "1": {"name": "Beginner", "subtitle": "Alphabet & CVC Basics",
          "words": BEGINNER,
          "subs": [
              {"id": "1a", "name": "Short A", "words_idx": [0,25]},
              {"id": "1b", "name": "Short E", "words_idx": [26,43]},
              {"id": "1c", "name": "Short I", "words_idx": [44,67]},
              {"id": "1d", "name": "Short O", "words_idx": [68,85]},
              {"id": "1e", "name": "Short U", "words_idx": [86,104]},
              {"id": "1f", "name": "Heart Words", "words_idx": [105,132]},
              {"id": "1g", "name": "More CVC", "words_idx": [133,174]},
          ]},
    "2": {"name": "Intermediate", "subtitle": "Blends, Digraphs & Silent E",
          "words": INTERMEDIATE,
          "subs": [
              {"id": "2a", "name": "Blends", "words_idx": [0,27]},
              {"id": "2b", "name": "Digraphs", "words_idx": [28,57]},
              {"id": "2c", "name": "FLSZ & ck", "words_idx": [58,79]},
              {"id": "2d", "name": "Silent e", "words_idx": [80,107]},
              {"id": "2e", "name": "Soft c/g", "words_idx": [108,120]},
              {"id": "2f", "name": "Heart Words", "words_idx": [121,134]},
              {"id": "2g", "name": "More Blends", "words_idx": [135,182]},
          ]},
    "3": {"name": "Advanced", "subtitle": "R-Controlled, Vowels & Morphology",
          "words": ADVANCED,
          "subs": [
              {"id": "3a", "name": "R-Controlled", "words_idx": [0,31]},
              {"id": "3b", "name": "Vowel Teams", "words_idx": [32,94]},
              {"id": "3c", "name": "Diphthongs", "words_idx": [95,112]},
              {"id": "3d", "name": "Silent Letters", "words_idx": [113,121]},
              {"id": "3e", "name": "Suffixes & Affixes", "words_idx": [122,136]},
              {"id": "3f", "name": "Advanced Patterns", "words_idx": [137,149]},
              {"id": "3g", "name": "More Advanced", "words_idx": [150,184]},
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

    # Build grapheme and IPA arrays
    graphemes = split_graphemes(word)
    phoneme_ipa = [ARPABET_TO_IPA.get(name, name) for name in phoneme_names]
    # Pad graphemes to match phoneme count if needed, else truncate
    while len(graphemes) < len(phoneme_names):
        graphemes.append("?")
    phoneme_graphemes = graphemes[:len(phoneme_names)]

    return jsonify({
        "word": word,
        "found": phonemes is not None,
        "phoneme_names": phoneme_names,
        "phoneme_ipa": phoneme_ipa,
        "phoneme_graphemes": phoneme_graphemes,
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


# ── Minimal Pairs ────────────────────────────────────────────────────────────

SHORT_VOWEL_PAIRS = [
    ("cat","cot"),("bat","bot"),("hat","hot"),("mat","mop"),("pat","pot"),
    ("pen","pin"),("bet","bit"),("set","sit"),("met","mitt"),("ten","tin"),
    ("pit","pot"),("bit","but"),("sit","sat"),("hit","hat"),("lip","lap"),
    ("cup","cap"),("cut","cat"),("run","ran"),("sun","sin"),("fun","fan"),
    ("sock","sack"),("lock","lack"),("rock","rack"),("dock","duck"),
    ("bed","bad"),("red","rad"),("fed","fad"),("led","lad"),
    ("big","beg"),("dig","dog"),("pig","peg"),("wig","wag"),
    ("hot","hut"),("pot","put"),("pop","pup"),("mop","map"),
    ("nut","net"),("cut","kit"),("hug","hog"),("bug","bag"),
    ("tap","top"),("nap","nip"),("map","mop"),("gap","gup"),
    ("thin","tin"),("shin","sin"),("chip","ship"),("chop","shop"),
]

CHINESE_ERROR_PAIRS = [
    ("thin","sin"),("thick","sick"),("think","sink"),("thank","sank"),
    ("three","free"),("threw","frew"),("thread","fred"),
    ("bath","bas"),("mouth","mouse"),("teeth","tease"),
    ("three","free"),("thirst","first"),("throw","fro"),
    ("very","wary"),("vine","wine"),("vest","west"),("vet","wet"),
    ("van","wan"),("veil","wail"),
    ("night","light"),("nine","line"),("name","lame"),("need","lead"),
    ("nice","lice"),("knee","lee"),("knock","lock"),
    ("light","right"),("long","wrong"),("late","rate"),("low","row"),
    ("lead","read"),("lace","race"),("lake","rake"),
    ("lice","rice"),("lime","rime"),("load","road"),
    ("ship","sheep"),("chip","cheap"),("full","fool"),("pull","pool"),
    ("bed","bad"),("head","had"),("walk","work"),
]

MINIMAL_PAIR_CATEGORIES = {
    "short-vowels": {"name": "Short Vowels", "desc": "CVC words with different vowels", "pairs": SHORT_VOWEL_PAIRS},
    "th-s": {"name": "th vs s", "desc": "Common TH/S confusion", "pairs": [(a,b) for a,b in CHINESE_ERROR_PAIRS if 'th' in a.lower() or 'th' in b.lower()]},
    "th-f": {"name": "th vs f", "desc": "Common TH/F confusion", "pairs": [(a,b) for a,b in CHINESE_ERROR_PAIRS if a.startswith('th') and b.startswith('f')]},
    "v-w": {"name": "v vs w", "desc": "Common V/W confusion", "pairs": [(a,b) for a,b in CHINESE_ERROR_PAIRS if ('v' in a.lower() and 'w' in b.lower()) or ('w' in a.lower() and 'v' in b.lower())]},
    "n-l": {"name": "n vs l", "desc": "Common N/L confusion", "pairs": [(a,b) for a,b in CHINESE_ERROR_PAIRS if ('n' in a.lower() and 'l' in b.lower()) or ('l' in a.lower() and 'n' in b.lower())]},
    "l-r": {"name": "l vs r", "desc": "Common L/R confusion", "pairs": [(a,b) for a,b in CHINESE_ERROR_PAIRS if ('l' in a.lower() and 'r' in b.lower()) or ('r' in a.lower() and 'l' in b.lower())]},
}


@app.route("/api/minimal_pairs")
def api_minimal_pairs():
    cats = {}
    for k, v in MINIMAL_PAIR_CATEGORIES.items():
        cats[k] = {"name": v["name"], "desc": v["desc"], "count": len(v["pairs"])}
    return jsonify(cats)


@app.route("/api/minimal_pairs/<category>")
def api_minimal_pairs_category(category):
    cat = MINIMAL_PAIR_CATEGORIES.get(category)
    if not cat:
        return jsonify({"error": "Category not found"}), 404
    import random
    pairs = list(cat["pairs"])
    random.shuffle(pairs)
    return jsonify({"name": cat["name"], "pairs": pairs[:20]})


# ── Learn Section API ─────────────────────────────────────────────────────

@app.route("/api/learn/lessons", methods=["GET"])
def api_learn_lessons():
    """Return the full curriculum of learn lessons."""
    lessons = []
    for l in LEARN_LESSONS:
        lessons.append({
            "id": l["id"],
            "name": l["name"],
            "letters": l["letters"],
            "letter_phonemes": [LETTER_PHONEME.get(c, "") for c in l["letters"]],
            "cvc_count": len(l["cvc_words"]),
            "heart_count": len(l["heart_words"]),
        })
    return jsonify(lessons)


@app.route("/api/learn/lesson/<lesson_id>", methods=["GET"])
def api_learn_lesson(lesson_id):
    """Return full lesson data including all practice words with phonemes."""
    lesson = None
    for l in LEARN_LESSONS:
        if l["id"] == lesson_id:
            lesson = l
            break
    if not lesson:
        return jsonify({"error": "Lesson not found"}), 404

    # Build CVC word data with phonemes
    cvc_data = []
    for w in lesson["cvc_words"]:
        phonemes = get_phoneme_list(w)
        names = [p for _, p in phonemes] if phonemes else []
        audios = []
        for _, arp in (phonemes or []):
            audio_path, fmt = get_phoneme_audio(arp)
            if audio_path:
                if audio_path.startswith(tempfile.gettempdir()):
                    cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                    cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                    if not os.path.exists(cache_path):
                        shutil.copy2(audio_path, cache_path)
                    audios.append(f"/tts_cache/{cache_name}")
                else:
                    audios.append(f"/phonemes/{os.path.basename(audio_path)}")
            else:
                audios.append(None)

        tts_path, tts_ok = get_tts_audio(w, 1.0)
        tts_url = f"/tts_cache/{os.path.basename(tts_path)}" if tts_ok else None

        cvc_data.append({
            "word": w,
            "phonemes": names,
            "phoneme_audios": audios,
            "tts_url": tts_url,
        })

    # Letter audio URLs
    letter_data = []
    for ch in lesson["letters"]:
        arp = LETTER_PHONEME.get(ch, "")
        audio_path, fmt = get_phoneme_audio(arp)
        audio_url = None
        if audio_path:
            if audio_path.startswith(tempfile.gettempdir()):
                cache_name = f"espeak_{hashlib.md5(audio_path.encode()).hexdigest()}.wav"
                cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                if not os.path.exists(cache_path):
                    shutil.copy2(audio_path, cache_path)
                audio_url = f"/tts_cache/{cache_name}"
            else:
                audio_url = f"/phonemes/{os.path.basename(audio_path)}"
        # Also get repeat version
        repeat_path, repeat_fmt = get_phoneme_audio(arp, repeat=True)
        repeat_url = None
        if repeat_path:
            if repeat_path.startswith(tempfile.gettempdir()):
                cache_name = f"espeak_{hashlib.md5(repeat_path.encode()).hexdigest()}.wav"
                cache_path = os.path.join(TTS_CACHE_DIR, cache_name)
                if not os.path.exists(cache_path):
                    shutil.copy2(repeat_path, cache_path)
                repeat_url = f"/tts_cache/{cache_name}"
            else:
                repeat_url = f"/phonemes/{os.path.basename(repeat_path)}"

        letter_data.append({
            "letter": ch,
            "phoneme": arp,
            "audio_url": audio_url,
            "repeat_url": repeat_url,
            "expected_speech": PHONEME_SPEECH_MAP.get(ch, []),
            "letter_name_speech": LETTER_NAME_SPEECH.get(ch, []),
        })

    # Heart word data
    heart_data = []
    for w in lesson["heart_words"]:
        tts_path, tts_ok = get_tts_audio(w, 1.0)
        tts_url = f"/tts_cache/{os.path.basename(tts_path)}" if tts_ok else None
        heart_data.append({"word": w, "tts_url": tts_url})

    return jsonify({
        "id": lesson["id"],
        "name": lesson["name"],
        "letters": letter_data,
        "cvc_words": cvc_data,
        "heart_words": heart_data,
    })


# ── Handwriting API ──

@app.route("/api/handwriting/letters", methods=["GET"])
def api_handwriting_letters():
    """Return handwriting stroke data for all lowercase letters."""
    result = {}
    for letter, data in HANDWRITING_STROKES.items():
        result[letter] = {
            "group": data["group"],
            "group_name": HANDWRITING_GROUPS.get(data["group"], {}).get("name", ""),
            "strokes": data["strokes"],
            "uppercase": HANDWRITING_UPPER.get(letter, letter.upper()),
        }
    return jsonify(result)


@app.route("/api/handwriting/groups", methods=["GET"])
def api_handwriting_groups():
    """Return handwriting groups with their letters."""
    result = {}
    for gid, gdata in HANDWRITING_GROUPS.items():
        result[gid] = {
            "name": gdata["name"],
            "letters": gdata["letters"],
        }
    return jsonify(result)


# ── Adventure Mode ──

@app.route("/adventure")
def adventure_mode():
    """Serve the quest-based monster adventure version."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "phonics_web_adventure.html")


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
