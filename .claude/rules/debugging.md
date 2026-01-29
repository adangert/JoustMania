# Debugging Guide

## Logs

### Docker Compose Logs

```bash
docker compose logs -f <service>           # Follow specific service
docker compose logs -f menu game-coordinator  # Multiple services
docker compose logs --tail=100 <service>   # Last 100 lines
```

### Log Levels

Set via environment variable:
```bash
LOG_LEVEL=DEBUG docker compose up <service>
```

## Observability Stack

Access at `http://localhost:8080/`:
- `/jaeger/` - Distributed traces
- `/grafana/` - Dashboards and metrics
- `/prometheus/` - Raw metrics

### Useful Traces

Search in Jaeger by:
- Service: `menu`, `game-coordinator`, `controller-manager`
- Operation: `StartGame`, `StreamGameEvents`, `process_controller_state`
- Tags: `game.mode=JoustFFA`, `player.serial=...`

### Key Dashboards

- **Service Health Overview** - All services up/down status
- **Game Quality** - Frame timing, jitter, dropped frames
- **Player Insights** - Per-player movement, deaths
- **Controller Overview** - Battery, connection status

## Common Issues

### "No module named X"

```bash
cd services/<service>
uv sync --dev    # Reinstall dependencies
```

### gRPC Connection Refused

Check service is running:
```bash
docker compose ps
docker compose logs <service> | tail -20
```

### Proto Mismatch

Regenerate after any `.proto` changes:
```bash
make protos
```

### Controller Not Detected

1. Check backend: `CONTROLLER_BACKEND=mock` for testing
2. Check Bluetooth: `bluetoothctl devices`
3. Check permissions: user must be in `bluetooth` group

## Interactive Debugging

### Python REPL with Service Context

```bash
cd services/<service>
uv run python
>>> from proto import service_pb2
>>> # Explore proto messages
```

### Mock Controller Testing

```bash
CONTROLLER_BACKEND=mock docker compose up controller-manager
# Use MockControllerService on port 50062 to simulate controllers
```

## Performance Profiling

Enable in docker-compose:
```yaml
environment:
  - OTEL_TRACES_SAMPLER=always_on  # Sample all traces
```

Check Jaeger for slow spans, look at:
- `game_loop` iteration times
- `process_controller_state` latency
- gRPC call durations
