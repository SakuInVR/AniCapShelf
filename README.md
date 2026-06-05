# AniCapShelf

AniCapShelf is a local-first media index for anime captures and recorded TV
archives. It links screenshots back to their source recording, episode,
timestamp, captions, and user tags so a capture can become a searchable scene
card instead of an orphaned image file.

This repository starts with a small Python prototype:

- index TS/m2ts recordings from a folder such as `Z:\TV-Record`
- parse Japanese recording filenames into date, title, episode-like tokens, and flags
- index capture images from a folder such as `Z:\TV-Capture`
- match captures to recordings by timestamp where possible
- probe TS subtitle streams such as `arib_caption`
- optionally extract subtitle text for a single recording with ffmpeg

## Quick Start

```powershell
python -m anicapshelf scan-records --db .\anicapshelf.db --records-root Z:\TV-Record
python -m anicapshelf scan-captures --db .\anicapshelf.db --captures-root Z:\TV-Capture
python -m anicapshelf match --db .\anicapshelf.db
python -m anicapshelf report --db .\anicapshelf.db
```

Probe subtitle streams on a sample:

```powershell
python -m anicapshelf probe-subtitles --records-root Z:\TV-Record --limit 40
```

Extract subtitles from one recording:

```powershell
python -m anicapshelf extract-subtitles --db .\anicapshelf.db --recording-id 1 --seconds 120 --max-cues 50
```

## Current Design

AniCapShelf treats source metadata as layered evidence:

1. Recording filename metadata: start time, title, episode-like token, flags.
2. Capture filename or filesystem time.
3. Time-window matching between captures and recordings.
4. TS caption streams, usually ARIB captions in Japanese TV recordings.
5. OCR, image embeddings, and manual tags in later stages.

Older captures can only be reconstructed when enough evidence remains. New
captures should eventually be saved through an annotation path that records the
KonomiTV source recording and playback position at capture time.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the staged plan from the current indexing
prototype to capture-time annotation, searchable scene cards, and mobile sharing.
