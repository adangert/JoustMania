# Phase 66: Extend psmoveapi moved2 Protocol (Rumble + RSSI)

> **Status**: Future
>
> **Prerequisites**: Phase 65 (Host Pairing Daemon) complete
>
> **Blocks**: Phase 67 (moved2 Backend)

## Overview

Contribute rumble/vibration and RSSI (signal strength) support to the psmoveapi `moved2` daemon protocol. This enables the clean cloud-native architecture where hardware access is handled by an edge daemon and game logic runs in Kubernetes.

## Motivation

The moved2 daemon exposes PS Move controllers over UDP, but currently lacks rumble and RSSI support:

| Command/Feature | Supported | Needed for JoustMania |
|-----------------|-----------|----------------------|
| SET_LEDS | Yes | Yes - player colors |
| READ_INPUT | Yes | Yes - motion/buttons |
| GET_SERIAL | Yes | Yes - identification |
| **SET_RUMBLE** | **No** | **Yes - hit feedback, death** |
| **RSSI in response** | **No** | **Yes - signal strength monitoring** |

Rumble is essential for JoustMania gameplay - it provides feedback when players are hit or eliminated.

RSSI enables monitoring Bluetooth signal strength for:
- Dashboard visualization of connection quality
- Weak signal warnings to players
- Debugging connectivity issues

### Why RSSI in moved2?

RSSI requires host-level Bluetooth HCI access (`hcitool rssi`). Containers cannot access HCI due to network namespace isolation. By having the moved2 daemon (which runs on the host) collect RSSI and include it in responses, containers get signal strength data without special privileges.

## Technical Approach

### 1. Rumble Protocol Addition

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

### Rumble Request Packet Structure

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

### Rumble Daemon Handler

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

### 2. RSSI in READ_INPUT Response

The current 64-byte response has 3 unused padding bytes. Use one for RSSI:

**Current response structure:**
```c
union PACKED PSMoveMovedResponse {
    struct {
        struct PSMoveMovedProtocolHeader header;  // 8 bytes
        union {
            struct {
                int32_t poll_return_value;        // 4 bytes
                uint8_t data[49];                 // 49 bytes (HID input report)
            } read_input;
            // ... other response types
        };
        uint8_t _padding[3];                      // 3 bytes unused
    };
    uint8_t bytes[64];
};
```

**Updated response structure:**
```c
union PACKED PSMoveMovedResponse {
    struct {
        struct PSMoveMovedProtocolHeader header;  // 8 bytes
        union {
            struct {
                int32_t poll_return_value;        // 4 bytes
                uint8_t data[49];                 // 49 bytes (HID input report)
            } read_input;
            // ... other response types
        };
        int8_t rssi;                              // 1 byte: RSSI in dBm (-128 to 0)
        uint8_t _padding[2];                      // 2 bytes remaining
    };
    uint8_t bytes[64];
};
```

### RSSI Collection in Daemon

Add RSSI query helper to `src/daemon/moved.cpp`:

```cpp
#include <cstdlib>
#include <cstring>

// Cache RSSI per controller (update every 10 seconds)
static std::map<std::string, int8_t> controller_rssi;
static std::map<std::string, time_t> rssi_last_update;

int8_t get_controller_rssi(const char* bt_address) {
    time_t now = time(nullptr);
    std::string addr(bt_address);

    // Check cache (10 second TTL)
    if (rssi_last_update.count(addr) && now - rssi_last_update[addr] < 10) {
        return controller_rssi[addr];
    }

    // Query via hcitool
    char cmd[64];
    snprintf(cmd, sizeof(cmd), "hcitool rssi %s 2>/dev/null", bt_address);

    FILE* pipe = popen(cmd, "r");
    if (!pipe) return 0;

    char buffer[128];
    int8_t rssi = 0;
    if (fgets(buffer, sizeof(buffer), pipe)) {
        // Parse "RSSI return value: -45"
        char* colon = strchr(buffer, ':');
        if (colon) {
            rssi = (int8_t)atoi(colon + 1);
        }
    }
    pclose(pipe);

    // Update cache
    controller_rssi[addr] = rssi;
    rssi_last_update[addr] = now;

    return rssi;
}
```

Update READ_INPUT handler:

```cpp
case CYCLEA_Moved_Request_Read_Input: {
    if (controller_id < controllers.size()) {
        PSMove *move = controllers[controller_id];
        response->read_input.poll_return_value = psmove_poll(move);

        // Copy input data
        unsigned char *data = psmove_get_input_buffer(move);
        memcpy(response->read_input.data, data, 49);

        // Add RSSI (new)
        const char* serial = psmove_get_serial(move);
        response->rssi = get_controller_rssi(serial);
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
3. **Implement rumble daemon handler** in moved.cpp
4. **Update client library** to send rumble over network
5. **Add RSSI field** to response structure
6. **Implement RSSI collection** in daemon (hcitool query with caching)
7. **Add tests** for remote rumble and RSSI
8. **Test with JoustMania** locally
9. **Submit PR** to upstream thp/psmoveapi

## Tasks

### Rumble Support
- [ ] Fork github.com/thp/psmoveapi
- [ ] Add SET_RUMBLE to protocol header
- [ ] Implement SET_RUMBLE handler in moved.cpp
- [ ] Update psmove_set_rumble() for remote controllers

### RSSI Support
- [ ] Add `int8_t rssi` field to PSMoveMovedResponse (use padding byte)
- [ ] Implement `get_controller_rssi()` helper with hcitool query
- [ ] Add RSSI caching (10 second TTL to avoid subprocess overhead)
- [ ] Update READ_INPUT handler to populate rssi field
- [ ] Handle USB-connected controllers (rssi = 0)

### Testing & Submission
- [ ] Write test cases for rumble and RSSI
- [ ] Test locally with moved2 + JoustMania
- [ ] Document protocol additions
- [ ] Submit upstream pull request
- [ ] (If rejected) Maintain fork with extensions

## Estimation

- Rumble protocol addition: 1 day
- Rumble daemon handler: 1 day
- RSSI response field + collection: 0.5 day
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
