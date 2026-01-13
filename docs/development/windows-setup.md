# Windows Development Setup for JoustMania

This guide enables development with real PS Move controllers on Windows/WSL without deploying to Raspberry Pi.

## Architecture

```
┌─────────────────────────┐         ┌─────────────────────────┐
│       Windows Host      │         │          WSL            │
│                         │         │                         │
│  PS Move Controllers    │         │                         │
│         ↓ Bluetooth     │         │                         │
│  ┌───────────────────┐  │         │  Docker Compose         │
│  │ Controller Manager│  │         │  ┌──────────────────┐   │
│  │  (Native Python)  │  │  gRPC   │  │ Game Coordinator │   │
│  │                   │◄─┼─────────┼──│                  │   │
│  │  Windows Backend  │  │ :50051  │  │  Menu            │   │
│  │  (psmoveapi)      │  │         │  │  Audio           │   │
│  └───────────────────┘  │         │  │  Settings        │   │
│                         │         │  └──────────────────┘   │
└─────────────────────────┘         └─────────────────────────┘
```

## Benefits

- ✅ Test with 3-4 real controllers without Pi deployment
- ✅ Full IDE debugging with real hardware
- ✅ Faster development iteration
- ✅ Same service architecture as production

## Prerequisites

- **Windows 10/11** with Bluetooth adapter
- **WSL2** with Ubuntu 22.04+
- **Python 3.11+** on both Windows and WSL
- **Docker Desktop** with WSL2 backend
- **3-4 PS Move Controllers**

## Setup Steps

### 1. Install Python on Windows

```powershell
# Windows PowerShell (as Administrator)
# Install Python 3.11 from python.org or via winget
winget install Python.Python.3.11

# Verify installation
python --version
# Should show: Python 3.11.x
```

### 2. Pair PS Move Controllers

**Method 1: Windows Bluetooth Settings (Recommended)**

1. Open **Settings** → **Bluetooth & devices**
2. Click **Add device** → **Bluetooth**
3. On PS Move: Hold **PS + Move** buttons until LED flashes rapidly
4. Select **Motion Controller** when it appears
5. Repeat for each controller

**Method 2: PS Move Pair Tool**

```powershell
# Download PS Move Pair Tool
# https://github.com/nitsch/moveonpc/releases

# Run and follow instructions to pair controllers
```

### 3. Install Controller Manager Dependencies (Windows)

```powershell
# Windows PowerShell
cd C:\path\to\JoustMania

# Create virtual environment (optional but recommended)
python -m venv venv-windows
.\venv-windows\Scripts\activate

# Install Windows dependencies
pip install -r services/controller_manager/requirements-windows.txt

# Install proto package
pip install -e proto/
```

### 4. Test Controller Detection

```powershell
# Windows PowerShell
cd services/controller_manager

# Test psmoveapi
python -c "import psmove; print(f'Found {psmove.count_connected()} controllers')"

# Should show: Found N controllers (where N = your paired controllers)
```

### 5. Configure WSL Services

```bash
# In WSL
cd ~/JoustMania

# Create docker-compose.override.yml for development
cat > docker-compose.override.yml <<'EOF'
services:
  game_coordinator:
    environment:
      - CONTROLLER_MANAGER_HOST=host.docker.internal:50051

  menu:
    environment:
      - CONTROLLER_MANAGER_HOST=host.docker.internal:50051

  supervisor:
    environment:
      - CONTROLLER_MANAGER_HOST=host.docker.internal:50051
EOF

# Verify override is correct
docker-compose config | grep CONTROLLER_MANAGER_HOST
```

### 6. Start Controller Manager on Windows

```powershell
# Windows PowerShell
cd C:\path\to\JoustMania

# Activate venv if using
.\venv-windows\Scripts\activate

# Set environment for backend selection (optional)
$env:CONTROLLER_BACKEND = "windows"

# Start controller manager
python -m services.controller_manager.server --host 0.0.0.0 --port 50051

# You should see:
# INFO: WindowsBackend initialized
# INFO: Found N PS Move controllers on Windows
# INFO: Connected to controller XXXX (battery: 5/5)
# INFO: Controller Manager server started on 0.0.0.0:50051
```

### 7. Start Services in WSL

```bash
# In WSL (separate terminal)
cd ~/JoustMania

# Start all services
docker-compose up

# Services will connect to Windows controller manager via gRPC
```

### 8. Verify Everything Works

1. **Check logs** in Windows terminal for controller connections
2. **Open WebUI** at `http://localhost:5000`
3. **Press Move button** on a controller - should see it in lobby
4. **LED should change color** when controller ready

## Development Workflow

### Daily Development

```powershell
# Terminal 1 (Windows) - Controller Manager
cd C:\path\to\JoustMania
.\venv-windows\Scripts\activate
python -m services.controller_manager.server --host 0.0.0.0 --port 50051
```

```bash
# Terminal 2 (WSL) - Services
cd ~/JoustMania
docker-compose up
```

### Debug a Specific Service

```bash
# WSL - Stop one service and run it outside Docker for debugging
docker-compose up audio menu settings supervisor  # Exclude game_coordinator

# In another WSL terminal
cd ~/JoustMania
export CONTROLLER_MANAGER_HOST=host.docker.internal:50051
python services/game_coordinator/server.py
```

### Test with Mock Controllers

If controllers are low battery or unavailable:

```powershell
# Windows - Use mock backend
$env:CONTROLLER_BACKEND = "mock"
$env:MOCK_CONTROLLER_COUNT = "4"
python -m services.controller_manager.server --host 0.0.0.0 --port 50051
```

## Troubleshooting

### Controllers Not Detected

```powershell
# Verify controllers are paired in Windows Bluetooth settings
# Should see "Motion Controller" listed as Connected

# Test psmoveapi directly
python -c "import psmove; print(f'Found {psmove.count_connected()} controllers'); [print(f'  - {psmove.PSMove(i).get_serial()}') for i in range(psmove.count_connected())]"
```

### WSL Can't Connect to Windows Service

```bash
# Test connectivity from WSL
ping host.docker.internal

# Test gRPC endpoint
curl -v http://host.docker.internal:50051
# Should get HTTP/2 response (even if gibberish)
```

**Fix**: Check Windows Firewall

```powershell
# Windows PowerShell (as Administrator)
# Allow Python through firewall
New-NetFirewallRule -DisplayName "Python gRPC Server" -Direction Inbound -Program "C:\path\to\python.exe" -Action Allow
```

### Import Errors

```powershell
# Ensure proto package is installed
pip install -e proto/

# Verify imports work
python -c "from proto import controller_manager_pb2; print('OK')"
```

### Controllers Work But No LED/Rumble

- Bluetooth controllers: Check battery level (needs >20%)
- USB controllers: Disconnect USB, use only Bluetooth
- Try reconnecting controller (unpair and re-pair)

## Environment Variables

### Controller Manager (Windows)

- `CONTROLLER_BACKEND`: Force backend (`windows`, `bluetooth`, `mock`)
- `MOCK_CONTROLLERS`: Set to `true` for mock mode
- `MOCK_CONTROLLER_COUNT`: Number of mock controllers (default: 4)
- `OTEL_EXPORTER_OTLP_ENDPOINT`: OpenTelemetry endpoint
- `PROMETHEUS_PORT`: Metrics port (default: 8001)

### Services (WSL)

- `CONTROLLER_MANAGER_HOST`: Controller manager address (set in docker-compose.override.yml)

## Performance Notes

- **Latency**: gRPC over host network adds ~1-2ms vs local
- **USB vs Bluetooth**: Bluetooth has same latency on Windows as Linux
- **Multiple Controllers**: Tested with 4 controllers, ~60 FPS state updates

## Production Deployment

This Windows setup is **for development only**. Production deployment uses:

```bash
# Raspberry Pi - Uses BluetoothBackend automatically
docker-compose up

# CONTROLLER_BACKEND auto-detects Linux and uses BlueZ
```

## Advanced: Running Controller Manager in Docker (WSL)

If you prefer to run everything in Docker:

```yaml
# docker-compose.override.yml
services:
  controller_manager:
    environment:
      - CONTROLLER_BACKEND=mock  # No access to Windows Bluetooth from Docker
      - MOCK_CONTROLLER_COUNT=4
```

This runs mock controllers in WSL Docker, not real hardware.

## See Also

- [Controller Backend Architecture](../architecture/controller-backends.md)
- [Phase 57: Windows Controller Backend](../../planning/phases/in-progress/phase-57-windows-controller-backend.md)
- [psmoveapi Documentation](https://github.com/thp/psmoveapi)
