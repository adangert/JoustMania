# Supervisor Service

**Part of JoustMania Microservices Architecture**

## Overview

The Supervisor Service monitors the health of all JoustMania microservices and provides system-wide health status. It tracks process states, handles restarts, and exposes health metrics for observability.

## Quick Reference

| Property | Value |
|----------|-------|
| **Port** | 50055 |
| **Proto** | `proto/supervisor.proto` |
| **Container** | `joustmania-supervisor` |

## gRPC API

### GetProcessStatus
Gets the status of a specific service.

```bash
grpcurl -plaintext -d '{"name": "ControllerManager"}' \
  localhost:50055 joustmania.supervisor.SupervisorService/GetProcessStatus
```

### GetAllProcessStatus
Gets the status of all monitored services.

```bash
grpcurl -plaintext localhost:50055 \
  joustmania.supervisor.SupervisorService/GetAllProcessStatus
```

### RestartProcess
Restarts a failed or unhealthy service.

```bash
grpcurl -plaintext -d '{"name": "Audio"}' \
  localhost:50055 joustmania.supervisor.SupervisorService/RestartProcess
```

### GetHealthSummary
Gets a summary of system health.

```bash
grpcurl -plaintext localhost:50055 \
  joustmania.supervisor.SupervisorService/GetHealthSummary
```

### StreamProcessUpdates
Streams real-time process status updates.

```bash
grpcurl -plaintext localhost:50055 \
  joustmania.supervisor.SupervisorService/StreamProcessUpdates
```

## Process States

| State | Description |
|-------|-------------|
| `UNKNOWN` | Process state not determined |
| `STARTING` | Process is starting up |
| `RUNNING` | Process is healthy and running |
| `STOPPING` | Process is shutting down |
| `STOPPED` | Process has stopped |
| `FAILED` | Process has failed |

## Monitored Services

| Service | Critical | Port |
|---------|----------|------|
| Settings | Yes | 50051 |
| Controller Manager | Yes | 50052 |
| Game Coordinator | Yes | 50053 |
| Menu | Yes | 50054 |
| Audio | No | 50056 |

## Health Checks

The Supervisor performs periodic health checks via gRPC Health protocol:
- Check interval: 5 seconds
- Timeout: 2 seconds
- Failure threshold: 3 consecutive failures

## Development

```bash
# Run locally
cd services/supervisor
python server.py

# Run tests
pytest tests/
```

## See Also

- [Architecture](../../docs/ARCHITECTURE.md) - System architecture
- [Proto Definition](../../proto/supervisor.proto) - Full API specification
- [Development Guide](../../docs/DEVELOPMENT.md) - Development workflow
