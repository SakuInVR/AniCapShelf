# AniCapShelf Roadmap

AniCapShelf aims to become a local-first anime scene library for recorded TV
archives and captures. The core promise is simple: every capture should remain
searchable, taggable, shareable, and traceable back to the source recording and
timestamp whenever enough evidence exists.

## Guiding Principles

- Keep source traceability first: captures should link back to a recording,
  episode, and source timestamp whenever possible.
- Treat metadata as evidence with confidence, not magic truth.
- Prefer capture-time annotation for new captures; use best-effort recovery for
  old captures.
- Keep the project self-hosted and local-first by default.
- Make manual correction fast, then reuse those corrections to improve future
  classification.
- Build toward mobile sharing, but keep the indexing engine independent from
  any one UI.

## Phase 0: Prototype Evidence

Status: started.

- [x] Create Python CLI project structure.
- [x] Index TS/m2ts recordings into SQLite.
- [x] Parse Japanese recording filenames into start time, title, episode-like
      token, and flags.
- [x] Index JPG/PNG capture files.
- [x] Match captures to recordings by timestamp window.
- [x] Import ShareX history metadata.
- [x] Probe ARIB caption streams with ffprobe.
- [x] Extract a bounded preview of ARIB subtitles with ffmpeg.
- [ ] Improve ARIB subtitle cleanup, especially ruby text and styling tags.
- [ ] Add basic automated tests for parsers and SRT cleanup.

## Phase 1: Reliable Local Index

Goal: make the CLI useful for repeated scans on a real recording archive.

- [ ] Add idempotent scan reports with created/updated/skipped counts.
- [ ] Add configurable roots through a local config file.
- [ ] Store recording stream metadata from ffprobe.
- [ ] Batch-probe `arib_caption` presence with timeout protection.
- [ ] Improve title normalization for Japanese TV filenames.
- [ ] Separate series title, episode number, subtitle, and broadcast flags.
- [ ] Add confidence scoring for capture-to-recording matches.
- [ ] Store multiple match candidates while marking one as the current best.
- [ ] Add commands to list unmatched captures and ambiguous matches.
- [ ] Add export commands for JSON/CSV debugging.

## Phase 2: Subtitle and Search Index

Goal: make scenes searchable by dialogue and screen text.

- [ ] Build robust ARIB subtitle extraction workers.
- [ ] Normalize subtitle text while preserving raw text for debugging.
- [ ] Store subtitle cues as time-series rows per recording.
- [ ] Link matched captures to nearby subtitle cues.
- [ ] Add SQLite FTS search over titles, subtitles, tags, and notes.
- [ ] Add OCR pipeline for image text.
- [ ] Store OCR results separately from TS subtitles.
- [ ] Add search commands such as `search-text`, `search-title`, and
      `near-capture`.

## Phase 3: Capture-Time Annotation

Goal: stop relying on after-the-fact guessing for new captures.

- [ ] Research KonomiTV integration points for current program and playback
      position.
- [ ] Design an annotation API endpoint:
      `POST /captures` with image, recording id/path, playback timestamp, and
      initial tags.
- [ ] Add a small local capture helper that saves the image and metadata
      together.
- [ ] Support quick tags at capture time.
- [ ] Attach nearby subtitles automatically at capture time.
- [ ] Add "open source scene" metadata that can jump back to the source video
      and timestamp in a local player or KonomiTV route.
- [ ] Preserve fallback import behavior for older screenshots.

## Phase 4: Web API and Local UI

Goal: browse, correct, and search the archive from a browser.

- [ ] Choose the initial API stack.
- [ ] Add endpoints for recordings, captures, matches, subtitles, tags, and
      collections.
- [ ] Build a responsive capture grid.
- [ ] Build capture detail pages with source recording, timestamp, nearby
      subtitles, tags, and ShareX history.
- [ ] Add manual correction UI for series, episode, and source timestamp.
- [ ] Add tag management and saved collections.
- [ ] Add mobile-friendly share actions.
- [ ] Add "unmatched" and "needs review" workflows.

## Phase 5: Anime-Focused Organization

Goal: make the library feel designed for anime archives, not generic photos.

- [ ] Add series pages.
- [ ] Add episode pages with timeline captures.
- [ ] Add collections such as eyecatches, OP/ED cuts, key scenes, and SNS picks.
- [ ] Add duplicate and near-duplicate detection.
- [ ] Add visual similarity search with image embeddings.
- [ ] Add optional character or visual tag suggestions.
- [ ] Support user-defined tag vocabularies.
- [ ] Add bulk tagging and bulk correction flows.

## Phase 6: Mobile and Sharing Experience

Goal: make capture discovery and sharing feel native on a phone.

- [ ] Harden the web UI as a PWA.
- [ ] Add phone-first search and filter interactions.
- [ ] Add share-sheet friendly image export.
- [ ] Add presets for SNS-ready crops or variants.
- [ ] Add saved smart albums.
- [ ] Evaluate whether a native app is worth building after the PWA workflow is
      proven.

## Phase 7: Packaging and Operations

Goal: make AniCapShelf easy to run on the Linux recording PC.

- [ ] Add Docker/Compose packaging.
- [ ] Add systemd service examples.
- [ ] Add scheduled scan workers.
- [ ] Add background job status and retry handling.
- [ ] Add backup/restore guidance for the SQLite or future database.
- [ ] Add safe handling for missing, moved, or renamed source files.
- [ ] Add privacy and local-network deployment notes.

## Open Design Questions

- What is the cleanest KonomiTV integration point for current playback state?
- Should the first web stack be a single Python app, or should API and frontend
  be split early?
- How much should AniCapShelf modify the existing folder layout versus indexing
  paths in place?
- How should subtitle ruby text be represented: stripped, preserved, or stored
  as separate reading metadata?
- What is the best source-jump format for returning from a capture to the
  original recording?
- Which tags should be first-class built-ins, and which should remain fully
  user-defined?

## Near-Term Next Steps

1. Add parser and subtitle-cleanup tests.
2. Improve subtitle text normalization.
3. Add a `review-unmatched` command for old captures.
4. Add config-file support for archive roots.
5. Decide the first KonomiTV capture-time annotation experiment.

