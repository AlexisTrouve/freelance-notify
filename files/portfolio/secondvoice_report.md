# SecondVoice - Real-Time Translation

## Tech Stack
- **Language**: C++17 (3 threads)
- **Audio**: PortAudio, RNNoise, Opus
- **UI**: ImGui v1.90.1
- **AI**: Whisper + Claude

## Metrics
**Size**: 3.8k LOC | **Files**: 28 | **Status**: Production-ready

## Purpose
Real-time Chinese-to-French translation for live meetings. Audio capture → Whisper → Claude → ImGui.

## Key Features
- Voice Activity Detection (VAD)
- RNNoise neural denoising
- Opus compression (46x)
- Whisper hallucination filtering
- GPU support (NvOptimus/AMD)
- Session logging
- Multi-platform (Windows/Linux)

---

## Repository Info
- **Last Commit**: 1db83b7 - Gitignore update (2025-12-02)
- **Report Generated**: 02/02/2026
