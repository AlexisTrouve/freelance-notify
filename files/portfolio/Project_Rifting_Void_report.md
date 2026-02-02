# Project Rifting Void - Space Combat Game

## Tech Stack
- **Language**: C++17
- **Engine**: GroveEngine (0.4ms hot-reload)
- **Renderer**: BgfxRenderer (hex grid, 2D)
- **Build**: CMake 3.20+

## Metrics
**Size**: 150 LOC | **Modules**: 62 planned | **Status**: Phase 1 (design done)

## Purpose
Tactical turn-based carrier combat (Crying Suns-inspired). Manage squadrons, hex-grid combat, resource management, 100+ events.

## Architecture
- 62 modules (System, Data, Query, Command, Resolver, Manager)
- Pub/sub communication
- JSON-configurable
- Hot-reloadable

---

## Repository Info
- **Last Commit**: 6a419bb - Initial structure (2026-01-16)
- **Report Generated**: 02/02/2026
