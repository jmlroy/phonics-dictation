#!/usr/bin/env python3
"""
Phonics Dictation Trainer V3 — Hybrid TTS Engine
=================================================
- Word playback: Volcengine Doubao Dacey (natural American English)
- Phoneme sounds: espeak-ng (accurate isolated phoneme pronunciation)
- CMU Pronouncing Dictionary for word→phoneme mapping
"""

import requests, base64, json, os, sys, time, random, shutil, tempfile, subprocess
from dataclasses import dataclass, field
from collections import defaultdict
import pronouncing

# ── API Config ──────────────────────────────────────────────────────────────

VOLC_API_KEY = "7ac606a7-4e1f-4a0a-b0d4-6c7d45bd7ff4"
TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
SPEAKER = "en_female_dacey_uranus_bigtts"

def _speed_to_rate(ratio):
    return int((ratio - 1.0) * 100)

# ── Terminal helpers ────────────────────────────────────────────────────────

def _has_color():
    return bool(os.environ.get("TERM")) and shutil.get_terminal_size().columns >= 30

def _c(code, text):
    if not _has_color():
        return text
    return code + text + "\033[0m"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"


# ── Phoneme audio library ──────────────────────────────────────────────────

PHONEME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phonemes")

# ARPAbet → WAV file mapping
# Uses _single.wav (user recordings) when available, falls back to originals
ARPABET_TO_WAV = {
    "AA": "AA_single.wav",  # /ɒ/ as in "octopus" (your voice)
    "AE": "AE_single.wav",  # /æ/ as in "apple" (your voice)
    "AH": "AH_single.wav",  # /ə/ schwa (your voice)
    "AO": "AO.wav",         # /ɔ/ as in "saw"
    "AR": "AR.wav",         # /ɑr/ as in "car"
    "AW": "AW_single.wav",  # /aʊ/ as in "now" (your voice)
    "AY": "AY_single.wav",  # /aɪ/ as in "ice" (your voice)
    "B": "B_single.wav",    # /b/ (your voice)
    "CH": "CH.wav",         # /tʃ/ as in "chip"
    "D": "D_single.wav",    # /d/ (your voice)
    "DH": "DH_single.wav",  # /ð/ as in "the"
    "EH": "EH_single.wav",  # /ɛ/ as in "bed" (your voice)
    "ER": "ER_single.wav",  # /ɝ/ as in "bird" (your voice)
    "EY": "EY_single.wav",  # /eɪ/ as in "face" (your voice)
    "F": "F_single.wav",    # /f/ (your voice)
    "G": "G_single.wav",    # /g/ (your voice)
    "HH": "HH.wav",         # /h/
    "IH": "IH_single.wav",  # /ɪ/ as in "ship" (your voice)
    "IY": "IY_single.wav",  # /i/ as in "see" (your voice)
    "JH": "JH.wav",         # /dʒ/ as in "jump"
    "K": "K_single.wav",    # /k/ (your voice)
    "KS": "KS.wav",         # /ks/ as in "box"
    "KW": "KW.wav",         # /kw/ as in "queen"
    "L": "L.wav",           # /l/
    "M": "M.wav",           # /m/
    "N": "N.wav",           # /n/
    "NG": "NG.wav",         # /ŋ/ as in "king"
    "OW": "OW_single.wav",  # /oʊ/ as in "go" (your voice)
    "OY": "OY_single.wav",  # /ɔɪ/ as in "boy" (your voice)
    "P": "P_single.wav",    # /p/ (your voice)
    "R": "R.wav",           # /r/
    "S": "S.wav",           # /s/
    "SH": "SH.wav",         # /ʃ/ as in "ship"
    "T": "T_single.wav",    # /t/ (your voice)
    "TH": "TH.wav",         # /θ/ as in "thin"
    "UH": "UH_single.wav",  # /ʊ/ as in "book" (your voice)
    "UW": "UW_single.wav",  # /u/ as in "moon" (your voice)
    "V": "V.wav",           # /v/
    "W": "W.wav",           # /w/
    "WH": "WH.wav",         # hw as in whip
    "Y": "Y.wav",           # /j/ as in "yes"
    "Z": "Z.wav",           # /z/
    "ZH": "ZH.wav",         # /ʒ/ as in "measure"
}

# Repeat versions — played when a child makes an error on this phoneme
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

# /æ/ (short a, as in "cat") — not in the collection; use espeak-ng
# DH /ð/ (voiced th, as in "the") — not in the collection; use espeak-ng

# Fallback mapping: ARPAbet → espeak-ng phoneme name
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
# Format: "word": pronunciation_index (0-based) to use
PRONUNCIATION_OVERRIDES = {
    "wind": 1,  # /wɪnd/ (the wind blows), not /waɪnd/ (wind up)
    "live": 1,  # /lɪv/ (to live), not /laɪv/ (live music)
}


def get_phoneme_list(word):
    """Get ARPAbet phoneme sequence for a word from CMUdict.
    Returns list of (espeak_phoneme_name, arpabet_phoneme) pairs,
    or None if word not found."""
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


def _find_player():
    """Find best audio player."""
    return (shutil.which("ffplay") or shutil.which("aplay")
            or shutil.which("paplay") or shutil.which("mpg123"))


def play_phoneme_wav(wav_path):
    """Play a phoneme WAV file."""
    player = _find_player()
    if not player:
        return False
    try:
        if "ffplay" in player:
            subprocess.run(
                [player, "-nodisp", "-autoexit", "-loglevel", "quiet", wav_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
            )
        else:
            subprocess.run(
                [player, wav_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
            )
        return True
    except (subprocess.TimeoutExpired, OSError):
        return False


def speak_phoneme(arpabet_phoneme, repeat=False):
    """Speak a single phoneme sound. Uses WAV file if available,
    falls back to espeak-ng phoneme synthesis.
    If repeat=True, uses the repeated version (for error correction)."""
    if repeat:
        wav = ARPABET_TO_WAV_REPEAT.get(arpabet_phoneme)
        if wav:
            wav_path = os.path.join(PHONEME_DIR, wav)
            if os.path.exists(wav_path):
                return play_phoneme_wav(wav_path)
    wav = ARPABET_TO_WAV.get(arpabet_phoneme)
    if wav:
        wav_path = os.path.join(PHONEME_DIR, wav)
        if os.path.exists(wav_path):
            return play_phoneme_wav(wav_path)

    # Fallback: espeak-ng phoneme synthesis
    espeak_name = ARPABET_TO_ESPEAK.get(arpabet_phoneme)
    if espeak_name and ESPEAK_EXE:
        try:
            subprocess.run(
                [ESPEAK_EXE, "-v", "en-us", "-s", "140", "-p", "50",
                 "[[" + espeak_name + "]]"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
            )
            return True
        except OSError:
            pass
    return False


def speak_phoneme_sequence(word):
    """Speak a word's phonemes using WAV library + espeak-ng.
    Plays: full word → phonemes one by one → full word again.
    Returns ARPAbet display list."""
    phonemes = get_phoneme_list(word)
    if not phonemes:
        # Fallback: use volcengine TTS for the whole word
        volc_speak(word)
        return None

    # Step 1: Say the whole word first (natural voice)
    time.sleep(0.1)
    volc_speak(word)
    time.sleep(0.3)

    # Step 2: Phoneme by phoneme
    arpabet_display = []
    for espeak_name, arpabet_name in phonemes:
        speak_phoneme(arpabet_name)
        time.sleep(0.12)
        arpabet_display.append(arpabet_name)

    # Step 3: Say the whole word again
    time.sleep(0.3)
    volc_speak(word)

    return arpabet_display


# ── Volcengine TTS (for whole-word natural playback) ───────────────────────

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


def _play_file(path):
    player = (shutil.which("ffplay") or shutil.which("mpg123")
              or shutil.which("aplay") or shutil.which("paplay"))
    if player:
        try:
            if "ffplay" in player:
                subprocess.run([player, "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            else:
                subprocess.run([player, path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            pass


def volc_speak(word, speed=1.0):
    """Speak a whole word using Volcengine TTS (natural voice)."""
    audio = _call_volc_tts(word, _speed_to_rate(speed))
    if not audio:
        return False
    fd, tmp = tempfile.mkstemp(suffix=".mp3")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio)
        _play_file(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return True


# ── Error highlighting ─────────────────────────────────────────────────────

def highlight_errors(correct, attempt):
    correct = correct.lower().strip()
    attempt = attempt.lower().strip()
    result = []
    errors = 0
    tips = []
    ml = min(len(correct), len(attempt))
    for i in range(ml):
        if attempt[i] == correct[i]:
            result.append(_c(GREEN, attempt[i]))
        else:
            result.append(_c(RED, attempt[i]))
            errors += 1
            tips.append("pos " + str(i+1) + ": got '" + attempt[i] + "' should be '" + correct[i] + "'")
    if len(attempt) > len(correct):
        extra = attempt[len(correct):]
        result.append(_c(RED, "[+'" + extra + "']"))
        errors += 1
        tips.append("extra: '" + extra + "'")
    if len(correct) > len(attempt):
        missing = correct[len(attempt):]
        for j, m in enumerate(missing):
            result.append(_c(RED, "\u00ab" + m + "\u00bb"))
            errors += 1
            tips.append("pos " + str(len(attempt)+j+1) + ": missing '" + m + "'")
    return "".join(result), errors, tips


# ── Word data ───────────────────────────────────────────────────────────────

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
    "1": {"name":"Beginner","subtitle":"Alphabet & CVC Basics","color":GREEN,
          "emoji":"\U0001f7e2","words":BEGINNER},
    "2": {"name":"Intermediate","subtitle":"Blends, Digraphs & Silent E","color":YELLOW,
          "emoji":"\U0001f7e1","words":INTERMEDIATE},
    "3": {"name":"Advanced","subtitle":"R-Controlled, Vowels & Morphology","color":BLUE,
          "emoji":"\U0001f535","words":ADVANCED},
}


# ── Session ─────────────────────────────────────────────────────────────────

@dataclass
class Session:
    level_key: str
    words: list
    all_words: list = field(init=False)
    error_bank: list = field(default_factory=list)
    speed_mode: str = "normal"
    letter_errors: dict = field(default_factory=lambda: defaultdict(lambda: {"wrong": 0, "correct": 0}))
    word_error_detail: dict = field(default_factory=dict)
    round_num: int = 0
    total_attempts: int = 0
    total_correct: int = 0
    total_errors: int = 0
    words_this_round: int = 0
    correct_this_round: int = 0
    incorrect_this_round: int = 0

    def __post_init__(self):
        seen = set()
        combined = []
        for w in self.words:
            wl = w.lower()
            if wl not in seen:
                seen.add(wl)
                combined.append(wl)
        self.all_words = combined

    def _pick_word(self):
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

    def _log_error(self, word, attempt):
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

    def _speak_word(self, word):
        label = ""
        if self.speed_mode == "slow":
            label = " (slow)"
        elif self.speed_mode == "phoneme":
            label = " (phoneme by phoneme)"
        print()
        print("  " + _c(BOLD, "\U0001f50a Dictation" + label))
        print("  " + _c(DIM, "-" * 40))

        if self.speed_mode == "phoneme":
            # Use phoneme WAV library (with espeak-ng fallback)
            phonemes = speak_phoneme_sequence(word)
            if phonemes:
                # Show ARPAbet display
                display = "  " + _c(MAGENTA, "  /  ".join(phonemes))
                print(display)
        elif self.speed_mode == "slow":
            volc_speak(word, speed=0.5)
        else:
            volc_speak(word, speed=1.0)

    def _speak_hint(self, word):
        """Hint: phoneme breakdown using espeak-ng."""
        print("  " + _c(CYAN, "(phoneme breakdown...)"))
        phonemes = get_phoneme_list(word)
        if phonemes:
            for espeak_name, arpabet_name in phonemes:
                speak_phoneme(arpabet_name)
                time.sleep(0.12)
            display = "  " + _c(MAGENTA, "  /  ".join(p for _, p in phonemes))
            print(display)
        time.sleep(0.2)
        volc_speak(word, speed=0.5)

    def _test_tts(self):
        print()
        print("  " + _c(CYAN, "Testing audio..."))
        ok = volc_speak("hello")
        if ok:
            print("  " + _c(GREEN, "Volcengine TTS OK") + _c(DIM, " (Dacey voice)"))
            # Count phoneme WAV files
            wav_count = sum(1 for f in os.listdir(PHONEME_DIR) if f.endswith(".wav")) if os.path.isdir(PHONEME_DIR) else 0
            if wav_count > 0:
                print("  " + _c(GREEN, f"Phoneme library: {wav_count} sounds") + _c(DIM, " (Freesound collection)"))
            if ESPEAK_EXE:
                print("  " + _c(GREEN, "espeak-ng OK") + _c(DIM, " (fallback for missing phonemes)"))
            return True
        c = input("  " + _c(CYAN, "Audio failed. Continue? (y/n): ")).strip().lower()
        return c == "y"

    def _summary(self):
        t = self.correct_this_round + self.incorrect_this_round
        if t == 0:
            return
        pct = round(self.correct_this_round / t * 100, 1)
        print()
        print("  " + _c(BOLD, "-" * 44))
        print("  " + _c(BOLD, "Round " + str(self.round_num) + " Summary"))
        print("  " + _c(DIM, "-" * 44))
        print("    Words:     " + str(t))
        print("    Correct:   " + _c(GREEN, str(self.correct_this_round)))
        ic = _c(RED if self.incorrect_this_round > 0 else GREEN, str(self.incorrect_this_round))
        print("    Incorrect: " + ic)
        ac = GREEN if pct >= 80 else (YELLOW if pct >= 50 else RED)
        print("    Accuracy:  " + _c(ac, str(pct) + "%"))
        if self.error_bank:
            print("  " + _c(YELLOW, "    Review: " + str(len(self.error_bank)) + " words"))
            print("    " + _c(DIM, ", ".join(self.error_bank[:8])))
            if len(self.error_bank) > 8:
                print("    " + _c(DIM, "  ... +" + str(len(self.error_bank) - 8) + " more"))
        weak = [(l, s) for l, s in self.letter_errors.items()
                if s["wrong"] > s["correct"] and s["wrong"] >= 2]
        if weak:
            weak.sort(key=lambda x: -x[1]["wrong"])
            print("  " + _c(YELLOW, "    Focus letters:") + " " + _c(RED, ", ".join(l for l, _ in weak[:5])))
        cp = round(self.total_correct / max(self.total_attempts, 1) * 100, 1)
        cc = GREEN if cp >= 80 else YELLOW
        print("  " + _c(DIM, "-" * 44))
        print("  All time: " + str(self.total_attempts) + " tries, "
              + _c(GREEN, str(self.total_correct) + " ok") + ", "
              + _c(RED, str(self.total_errors) + " wrong") + ", "
              + _c(cc, str(cp) + "%"))
        print("  " + _c(BOLD, "-" * 44))

    def run(self):
        info = LEVELS[self.level_key]
        self._header(info)
        if not self._test_tts():
            return
        while True:
            self.round_num += 1
            self.words_this_round = 10 + 2 * int(self.level_key)
            self.correct_this_round = 0
            self.incorrect_this_round = 0
            print()
            print("  " + _c(BOLD, "Round " + str(self.round_num)))
            print("  " + _c(DIM, str(self.words_this_round) + " words"))
            if self.error_bank:
                print("  " + _c(YELLOW, str(len(self.error_bank)) + " to review"))
            weak = [(l, s) for l, s in self.letter_errors.items()
                    if s["wrong"] > s["correct"] and s["wrong"] >= 2]
            if weak:
                weak.sort(key=lambda x: -x[1]["wrong"])
                print("  " + _c(YELLOW, "Watch:") + " " + _c(RED, ", ".join(l for l, _ in weak[:5])))
            print()
            for i in range(self.words_this_round):
                word = self._pick_word()
                result = self._handle_word(word, i + 1)
                self.total_attempts += 1
                if result == "correct":
                    self.correct_this_round += 1
                    self.total_correct += 1
                    if word in self.error_bank:
                        self.error_bank.remove(word)
                else:
                    self.incorrect_this_round += 1
                    self.total_errors += 1
                    if word not in self.error_bank:
                        self.error_bank.append(word)
                print()
            self._summary()
            print()
            r = input("  " + _c(CYAN, "Next round? (Enter=yes, q=quit): ")).strip().lower()
            if r == "q":
                break
        self._goodbye()

    def _handle_word(self, word, seq):
        print("  " + _c(DIM, "[" + str(seq) + "/" + str(self.words_this_round) + "] "), end="")
        self._speak_word(word)
        attempt = input("\n  Your spelling: ").strip().lower()
        if attempt in ("q", "quit", "exit"):
            raise EOFError()
        if attempt == "speed":
            modes = ["normal", "slow", "phoneme"]
            idx = modes.index(self.speed_mode)
            self.speed_mode = modes[(idx + 1) % 3]
            print("  " + _c(CYAN, "Speed: " + self.speed_mode.upper()))
            return self._handle_word(word, seq)
        if not attempt:
            print("  " + _c(YELLOW, "(skipped)"))
            return "incorrect"
        display, err_count, tips = highlight_errors(word, attempt)
        if err_count == 0:
            print("  " + _c(GREEN, "Perfect!"))
            print("     " + display)
            for ch in word.lower():
                self.letter_errors[ch]["correct"] += 1
            return "correct"
        self._log_error(word, attempt)
        print("  " + _c(RED, "Not quite. Try again!"))
        print("     " + display)
        while True:
            print()
            cmd = input("  " + _c(CYAN, "[Enter] retry  [h]int  [r]eveal  [s]kip  [speed]: ")).strip().lower()
            if cmd in ("", "retry"):
                self._speak_word(word)
                attempt = input("\n  Your spelling: ").strip().lower()
                if attempt in ("q", "quit", "exit"):
                    raise EOFError()
                if not attempt:
                    print("  " + _c(YELLOW, "(skipped)"))
                    return "incorrect"
                d2, e2, t2 = highlight_errors(word, attempt)
                if e2 == 0:
                    print("  " + _c(GREEN, "Correct this time!"))
                    print("     " + d2)
                    for ch in word.lower():
                        self.letter_errors[ch]["correct"] += 1
                    return "correct"
                self._log_error(word, attempt)
                print("  " + _c(RED, "Still not quite:"))
                print("     " + d2)
            elif cmd in ("h", "hint"):
                self._speak_hint(word)
            elif cmd in ("r", "reveal"):
                print("  " + _c(GREEN, "The word: ") + _c(BOLD, word))
                ph = get_phoneme_list(word)
                if ph:
                    pstr = "  /  ".join(p for _, p in ph)
                    print("  " + _c(MAGENTA, pstr))
                return "incorrect"
            elif cmd in ("s", "skip"):
                print("  " + _c(YELLOW, "(skipped)"))
                return "incorrect"
            elif cmd == "speed":
                modes = ["normal", "slow", "phoneme"]
                idx = modes.index(self.speed_mode)
                self.speed_mode = modes[(idx + 1) % 3]
                print("  " + _c(CYAN, "Speed: " + self.speed_mode.upper()))

    def _header(self, info):
        print()
        print("  " + _c(BOLD, "=" * 56))
        print("  " + _c(BOLD, "  Phonics Dictation Trainer V3"))
        print("  " + _c(DIM, "=" * 56))
        print("  " + info["emoji"] + " Level " + self.level_key + ": " + info["name"])
        print("  " + _c(DIM, info["subtitle"]))
        print("  Words: " + str(len(self.all_words)))
        print("  Voice: Dacey (natural) + espeak-ng (phonemes)")
        sp = {"normal": "NORMAL (Dacey)", "slow": "SLOW (Dacey, 0.5x)", "phoneme": "PHONEME (espeak-ng)"}
        print("  Speed: " + sp.get(self.speed_mode, self.speed_mode))
        print("  " + _c(DIM, "=" * 56))
        print()
        print("  " + _c(DIM, "Commands: q=quit, speed=cycle modes"))

    def _goodbye(self):
        print()
        pct = round(self.total_correct / max(self.total_attempts, 1) * 100, 1)
        c = GREEN if pct >= 80 else YELLOW
        print("  " + _c(BOLD, "=" * 44))
        print("  " + _c(BOLD, "Goodbye!"))
        print("  Total: " + str(self.total_attempts) + " words, Accuracy: " + _c(c, str(pct) + "%"))
        weak = [(l, s) for l, s in self.letter_errors.items()
                if s["wrong"] > s["correct"] and s["wrong"] >= 2]
        if weak:
            weak.sort(key=lambda x: -x[1]["wrong"])
            print("  " + _c(YELLOW, "Keep practising:"))
            for l, s in weak[:8]:
                print("    " + _c(RED, l) + ": " + str(s["wrong"]) + " wrong, " + str(s["correct"]) + " correct")
        print("  " + _c(BOLD, "=" * 44))
        print()


# ── Entry ───────────────────────────────────────────────────────────────────

def select_level_mode():
    print()
    print("  " + _c(BOLD, "Phonics Dictation Trainer V3"))
    print("  " + _c(DIM, "=" * 48))
    print("  " + _c(CYAN, "Volcengine Doubao + espeak-ng hybrid"))
    print()
    for k, v in LEVELS.items():
        n = len(v["words"])
        line = ("  " + v["emoji"] + "  "
                + _c(v["color"], "[" + k + "] " + v["name"]) + "  -  " + str(n) + " words")
        print(line)
        print("     " + _c(DIM, v["subtitle"]))
        print()
    while True:
        choice = input("  " + _c(CYAN, "Level (1-3): ")).strip()
        if choice in LEVELS:
            break
        print("  " + _c(RED, "Invalid."))
    print()
    print("  " + _c(BOLD, "Speed:"))
    print("  " + _c(CYAN, "  [n] Normal (Dacey voice, 1.0x)"))
    print("  " + _c(CYAN, "  [s] Slow (Dacey voice, 0.5x)"))
    print("  " + _c(CYAN, "  [p] Phoneme (espeak-ng, sound by sound)"))
    print("  " + _c(DIM, '  (Type "speed" during practice to cycle)'))
    sc = input("  " + _c(CYAN, "Choose (n/s/p) [n]: ")).strip().lower()
    sm = {"s": "slow", "p": "phoneme"}.get(sc, "normal")
    return choice, sm


def main():
    print()
    print("  " + _c(BOLD, "=" * 56))
    print("  " + _c(BOLD, "  Phonics Dictation Trainer V3"))
    print("  " + _c(BOLD, "  Hybrid TTS Engine"))
    print("  " + _c(DIM, "=" * 56))

    if not ESPEAK_EXE:
        print("  " + _c(YELLOW, "Note: espeak-ng not found. Install: sudo apt install espeak-ng"))
        print("  " + _c(YELLOW, "Phoneme mode will fall back to word-level playback."))

    try:
        lk, sm = select_level_mode()
        seen = set()
        words = []
        for w in LEVELS[lk]["words"]:
            wl = w.lower()
            if wl not in seen:
                seen.add(wl)
                words.append(wl)
        sess = Session(level_key=lk, words=words, speed_mode=sm)
        sess.run()
        return 0
    except (KeyboardInterrupt, EOFError):
        print("\n\n  " + _c(YELLOW, "Goodbye!"))
        return 0


if __name__ == "__main__":
    sys.exit(main())
