# Milestone 1: Microservices Architecture

**Status:** Complete
**Phases:** 1-5, 7, 8a-c, 9

## Summary

Extracted monolithic JoustMania Python application into 6 containerized gRPC microservices, enabling independent scaling, deployment, and development.

## Background

The original JoustMania was a single Python process using multiprocessing queues for inter-component communication. This made it difficult to:
- Debug individual components
- Deploy updates without full restarts
- Scale specific services
- Add observability

## Implementation

### Services Created

| Service | Port | Responsibility |
|---------|------|----------------|
| **Settings** | 50051 | Game configuration, sensitivity, colors |
| **ControllerManager** | 50052 | PS Move hardware, state streaming |
| **GameCoordinator** | 50053 | Game logic, player lifecycle |
| **Menu** | 50054 | Navigation, lobby, admin mode |
| **Supervisor** | 50055 | Health monitoring, orchestration |
| **WebUI** | 80 | Flask web interface |

### Key Changes

1. **gRPC Communication** - Replaced multiprocessing.Queue with Protocol Buffers
2. **Docker Compose** - All services containerized with health checks
3. **Shared Protos** - `proto/` package with service definitions
4. **Service Discovery** - Docker DNS for inter-service communication

### Architecture Diagram

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   WebUI     │────▶│    Menu     │────▶│    Game     │
│   :80       │     │   :50054    │     │  Coordinator│
└─────────────┘     └─────────────┘     │   :50053    │
                           │            └──────┬──────┘
                           ▼                   │
                    ┌─────────────┐            │
                    │  Supervisor │            ▼
                    │   :50055    │     ┌─────────────┐
                    └─────────────┘     │ Controller  │
                           │            │  Manager    │
                           ▼            │   :50052    │
                    ┌─────────────┐     └─────────────┘
                    │  Settings   │
                    │   :50051    │
                    └─────────────┘
```

## Files Changed

- `services/` - New service implementations
- `proto/` - gRPC service definitions
- `docker-compose.yml` - Service orchestration
- `Dockerfile.*` - Per-service container builds

## Commits

See git history for complete list.

## Related Phases

- Phase 1: Controller Manager extraction
- Phase 2: Game Coordinator extraction
- Phase 3: Settings Service extraction
- Phase 4: Process Supervisor extraction
- Phase 5: Menu Process extraction
- Phase 7: Code restructuring
- Phase 8a: gRPC conversion
- Phase 8b: Dockerization
- Phase 8c: WebUI microservice
- Phase 9: Architecture cleanup
