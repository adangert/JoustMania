# Service Development

## Adding/Modifying Services

### Directory Structure

```
services/<service-name>/
├── __init__.py
├── server.py              # Entry point, gRPC server setup
├── servicer.py            # gRPC servicer implementation
├── metrics.py             # OTEL metrics definitions
├── pyproject.toml         # Dependencies (uv managed)
├── Dockerfile
├── README.md
└── tests/
```

### gRPC Servicer Pattern

```python
class MyServiceServicer(my_pb2_grpc.MyServiceServicer):
    def __init__(self, settings_client, ...):
        self.settings = settings_client
        # Initialize state

    async def MyMethod(self, request, context):
        # Implement RPC
        return my_pb2.MyResponse(...)
```

### Metrics

Use OTEL push metrics (not prometheus pull):

```python
from lib.otel_metrics import Counter, Gauge, Histogram

requests_total = Counter("my_requests_total", "Total requests", ["method"])
active_connections = Gauge("my_active_connections", "Active connections")
```

### Proto Definitions

1. Add/modify in `proto/<service>.proto`
2. Run `make protos` to regenerate
3. Import from `proto import <service>_pb2, <service>_pb2_grpc`

## Common Patterns

### Settings Integration

```python
# Get setting
response = await settings_stub.GetSetting(
    settings_pb2.GetSettingRequest(key="sensitivity")
)
value = response.value

# Subscribe to changes
async for event in settings_stub.SubscribeToChanges(...):
    if event.key == "sensitivity":
        self.update_sensitivity(event.new_value)
```

### Controller Manager Integration

```python
# Button events (menu uses this)
stream = stub.StreamButtonEvents(request_generator())
async for event in stream:
    if event.event_type == EVENT_CONNECT:
        handle_connect(event.serial)
    elif event.button == BUTTON_TRIGGER:
        handle_trigger(event.serial, event.action)

# Gameplay data (game coordinator uses this)
stream = stub.StreamGameplayData(request_generator())
async for update in stream:
    for controller in update.controllers:
        process_motion(controller.serial, controller.accel)
```

### LED Feedback

Send via the stream's write channel:

```python
# Set color
await stream.write(ButtonEventStreamControl(
    color_config=ControllerColorConfig(serial=serial, color=RGB(r=255, g=0, b=0))
))

# Game effect
await stream.write(GameplayStreamControl(
    effect=GameEffectCommand(serial=serial, effect=GAME_EFFECT_PLAYER_DEATH)
))
```
