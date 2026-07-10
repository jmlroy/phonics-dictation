# Phonics Dictation Trainer

A children's phonics dictation practice app with hybrid TTS engine:
- **Volcengine Doubao** for natural whole-word playback (Dacey / Myra voice)
- **espeak-ng** for accurate isolated phoneme sounds
- **Freesound phoneme WAV library** for real human-voice phoneme clips

## Features
- 3 levels: Beginner, Intermediate, Advanced
- Normal / Slow / Phoneme-by-phoneme modes
- Adaptive error tracking (focuses on weak letters)
- Hint, reveal, and retry options
- Web interface for mobile use

## Deploy
```bash
pip install -r requirements.txt
gunicorn phonics_web:app --bind 0.0.0.0:8080
```
