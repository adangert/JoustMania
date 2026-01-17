# Phase 66: Add Rumble Support to psmoveapi moved2 Protocol

> **Status**: Future
>
> **Prerequisites**: Phase 65 (Host Pairing Daemon) complete
>
> **Blocks**: Phase 67 (moved2 Backend)

## Overview

Contribute rumble/vibration support to the psmoveapi `moved2` daemon protocol. This enables the clean cloud-native architecture where hardware access is handled by an edge daemon and game logic runs in Kubernetes.

## Motivation

The moved2 daemon exposes PS Move controllers over UDP, but currently lacks rumble support:

| Command | Supported | Needed for JoustMania |
|---------|-----------|----------------------|
| SET_LEDS | Yes | Yes - player colors |
| READ_INPUT | Yes | Yes - motion/buttons |
| GET_SERIAL | Yes | Yes - identification |
| **SET_RUMBLE** | **No** | **Yes - hit feedback, death** |

Rumble is essential for JoustMania gameplay - it provides feedback when players are hit or eliminated.

## Technical Approach

### Protocol Addition

Add new command to `src/daemon/psmove_moved_protocol.h`:

```c
enum PSMove_Moved_Command {
    CYCLEA_Moved_Request_Discover = 1,
    CYCLEA_Moved_Request_Count_Connected = 2,
    CYCLEA_Moved_Request_Set_LEDs = 3,
    CYCLEA_Moved_Request_Read_Input = 4,
    CYCLEA_Moved_Request_Get_Serial = 5,
    CYCLEA_Moved_Request_Get_Host_Btaddr = 6,
    CYCLEA_Moved_Request_Register_Controller = 7,
    CYCLEA_Moved_Request_Set_Rumble = 8,  // NEW
};
```

### Request Packet Structure

```c
// SET_RUMBLE request (fits in existing 16-byte request packet)
struct PSMove_Moved_Request_Set_Rumble {
    uint32_t request_sequence;
    uint16_t command_id;      // = 8
    uint16_t controller_id;
    uint8_t  rumble_intensity; // 0-255
    uint8_t  reserved[7];
};
```

### Daemon Handler

Add to `src/daemon/moved.cpp`:

```cpp
case CYCLEA_Moved_Request_Set_Rumble: {
    if (controller_id < controllers.size()) {
        PSMove *move = controllers[controller_id];
        uint8_t intensity = request->data[0];
        psmove_set_rumble(move, intensity);
        psmove_update_leds(move);  // Rumble sent with LED update
        response->result = 1;  // Success
    } else {
        response->result = 0;  // Invalid controller
    }
    break;
}
```

### Client API

Add to psmove library for remote controllers:

```c
// In psmove.c - handle remote rumble
void psmove_set_rumble(PSMove *move, unsigned char rumble) {
    if (move->remote) {
        // Send SET_RUMBLE to moved2 daemon
        moved_set_rumble(move->remote_id, rumble);
    } else {
        // Local controller - existing implementation
        move->rumble = rumble;
    }
}
```

## Implementation Steps

1. **Fork psmoveapi** on GitHub
2. **Add protocol constant** for SET_RUMBLE command
3. **Implement daemon handler** in moved.cpp
4. **Update client library** to send rumble over network
5. **Add tests** for remote rumble
6. **Test with JoustMania** locally
7. **Submit PR** to upstream thp/psmoveapi

## Tasks

- [ ] Fork github.com/thp/psmoveapi
- [ ] Add SET_RUMBLE to protocol header
- [ ] Implement SET_RUMBLE handler in moved.cpp
- [ ] Update psmove_set_rumble() for remote controllers
- [ ] Write test cases
- [ ] Test locally with moved2 + JoustMania
- [ ] Document protocol addition
- [ ] Submit upstream pull request
- [ ] (If rejected) Maintain fork with rumble support

## Estimation

- Protocol addition: 1 day
- Daemon handler: 1 day
- Client library changes: 1 day
- Testing: 1-2 days
- PR process: Variable

**Total**: ~1 week of focused work

## Cloud-Native Demo Value

- Demonstrates open source contribution as part of development
- Shows how to extend protocols for specific needs
- Good conference talk material: "Contributing to open source for cloud-native gaming"

## Risks

| Risk | Mitigation |
|------|------------|
| PR rejected | Maintain fork, document rationale |
| Protocol changes upstream | Base on stable release tag |
| Latency concerns | Benchmark UDP round-trip |

## References

- [psmoveapi GitHub](https://github.com/thp/psmoveapi)
- [moved documentation](https://psmoveapi.readthedocs.io/en/latest/moved.html)
- [Protocol header](https://github.com/thp/psmoveapi/blob/master/src/daemon/psmove_moved_protocol.h)

## Next Phase

Phase 67: moved2 Backend for Controller Manager
