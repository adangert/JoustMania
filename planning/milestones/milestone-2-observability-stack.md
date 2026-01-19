# Milestone 2: Observability Stack

**Status:** Complete
**Phases:** 35, 36/36b, 38, 43, 56, 76, 78, observability-1

## Summary

Comprehensive observability infrastructure with distributed tracing, metrics collection, and centralized logging across all microservices.

## Background

With 6+ microservices, debugging issues requires visibility into:
- Request flow across services (distributed tracing)
- System and application metrics (Prometheus)
- Centralized logs (Loki)
- Visual dashboards (Grafana)

## Implementation

### Observability Stack

| Component | Purpose | Port |
|-----------|---------|------|
| **Jaeger** | Distributed trace visualization | 16686 |
| **Prometheus** | Metrics collection & alerting | 9090 |
| **Grafana** | Dashboards & visualization | 3000 |
| **Loki** | Log aggregation | 3100 |
| **OTEL Collector** | Telemetry pipeline | 4317 |

### OpenTelemetry Integration

All services instrumented with:
- `lib/telemetry.py` - Shared initialization
- Automatic gRPC server/client instrumentation
- Manual spans for game lifecycle events
- Trace context propagation via W3C headers

### Key Tracing Features

1. **Per-Player Lifecycle Spans** - Track each player from join to death/win
2. **Game Phase Spans** - Initialization, countdown, gameplay, teardown
3. **Event-Driven Spans** - Player warnings, deaths, team changes
4. **Cross-Service Linking** - Menu → Supervisor → GameCoordinator → Audio

### Metrics Exposed

```
# Controller metrics
joustmania_controllers_connected
joustmania_controller_battery_level
joustmania_controller_state_updates_total

# Game metrics
joustmania_games_started_total
joustmania_games_completed_total
joustmania_player_deaths_total

# System metrics
process_cpu_seconds_total
process_resident_memory_bytes
```

### Grafana Dashboards

1. **Game Performance** - Active games, player counts, death rates
2. **Controller Health** - Battery levels, connection strength
3. **Host Metrics** - CPU, memory, temperature (Raspberry Pi)
4. **Service Health** - Request latency, error rates

## Files Changed

- `lib/telemetry.py` - Shared OpenTelemetry setup
- `services/*/server.py` - Per-service instrumentation
- `services/prometheus/` - Prometheus configuration
- `services/grafana/` - Dashboard definitions
- `docker-compose.yml` - Observability services

## Commits

Key commits (see `git log --grep="tracing\|observability\|metrics"` for complete list):

- `99a64e8` feat(tracing): Add manual gRPC client interceptors for async trace propagation
- `458c86f` refactor(audio): Improve OpenTelemetry span names for readability
- `b4ac7c1` feat(tracing): Add admin_mode_session parent span for all admin actions
- `61df453` feat(tracing): Add music tempo changes to gameplay span
- `ed98342` feat(tracing): Propagate trace context through Menu → Supervisor events
- `b3894ca` feat(observability): Rewrite pairing daemon in Python with metrics and tracing
- `5657170` feat(observability): Add Raspberry Pi host metrics dashboard

## Related Phases

- Phase 35: Logging optimization
- Phase 36/36b: Span hierarchy rework
- Phase 38: Production metrics monitoring
- Phase 43: Observability runtime configuration
- Phase 56: Event-driven spans
- Phase 76: Host metrics dashboard
- Phase 78: Pairing daemon observability
- Observability-1: Loki log aggregation
