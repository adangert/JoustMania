# Protocol Buffer Development

## Proto Files Location

All `.proto` files are in the `proto/` directory:

```
proto/
├── settings.proto           # Configuration service
├── controller_manager.proto # Hardware control
├── game_coordinator.proto   # Game lifecycle
├── menu.proto               # Menu/lobby service
├── audio.proto              # Audio playback
└── controller_manager_mock.proto  # Mock controller testing
```

## Making Changes

1. Edit the `.proto` file
2. Regenerate Python bindings:
   ```bash
   make protos
   ```
3. Run integration tests:
   ```bash
   make test
   ```

## Common Patterns

### Message Definition

```protobuf
message PlayerState {
  string serial = 1;
  bool alive = 2;
  int32 score = 3;
  optional string killer_serial = 4;  // Optional field
}
```

### Enum Definition

```protobuf
enum GameState {
  GAME_STATE_UNSPECIFIED = 0;
  GAME_STATE_IDLE = 1;
  GAME_STATE_RUNNING = 2;
  GAME_STATE_ENDED = 3;
}
```

### RPC Patterns

```protobuf
service MyService {
  // Unary (request-response)
  rpc GetState(GetStateRequest) returns (GetStateResponse);

  // Server streaming
  rpc StreamEvents(StreamRequest) returns (stream Event);

  // Bidirectional streaming
  rpc StreamData(stream DataRequest) returns (stream DataResponse);
}
```

## Importing in Python

```python
from proto import service_pb2
from proto import service_pb2_grpc

# Create message
msg = service_pb2.MyMessage(field="value")

# Create stub
stub = service_pb2_grpc.MyServiceStub(channel)
```

## Versioning

- Use `optional` for new fields (backwards compatible)
- Never reuse field numbers
- Add new fields at the end
- Deprecate rather than remove fields

## Testing Proto Changes

After modifying protos:
```bash
make protos                  # Regenerate
make lint                    # Check syntax
cd services/<affected>
uv run pytest               # Unit tests
make test                   # Full integration
```
