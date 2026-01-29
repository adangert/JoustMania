# JoustMania

[![CI](https://github.com/WatchMeJoustMyFlags/JoustMania/actions/workflows/ci.yml/badge.svg)](https://github.com/WatchMeJoustMyFlags/JoustMania/actions/workflows/ci.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=WatchMeJoustMyFlags_JoustMania&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=WatchMeJoustMyFlags_JoustMania)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=WatchMeJoustMyFlags_JoustMania&metric=coverage)](https://sonarcloud.io/summary/new_code?id=WatchMeJoustMyFlags_JoustMania)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)

**Microservices-based motion gaming platform for PlayStation Move controllers.**

A cloud-native refactor of the [original JoustMania](https://github.com/adangert/JoustMania) party game system, rebuilt with modern observability practices. Ideal for learning distributed systems, gRPC, and OpenTelemetry.

![JoustMania at Magfest](logo/magfest.jpg)

## Quick Start

```bash
git clone https://github.com/WatchMeJoustMyFlags/JoustMania.git
cd JoustMania
docker compose up -d
```

**Open the dashboard:** http://localhost:8080

| Interface | URL | Purpose |
|-----------|-----|---------|
| Dashboard | http://localhost:8080 | Main UI, controller visualization |
| Jaeger | http://localhost:8080/jaeger/ | Distributed tracing |
| Prometheus | http://localhost:8080/prometheus/ | Metrics |
| Grafana | http://localhost:8080/grafana/ | Dashboards (admin/joustmania) |

## Game Modes

- **Joust FFA** - Free-for-all elimination
- **Joust Teams** - Team-based combat
- **Joust Random Teams** - Randomized team assignment
- **Tournament** - Elimination brackets
- **Werewolf** - Social deduction
- **Zombies** - Infection survival
- **Non-Stop Joust** - Respawn-enabled combat
- **Fight Club** - 1v1 bracket tournament
- And more...

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dashboard (:8080)                        │
│         Unified entry point with reverse proxy routing          │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│     Menu      │    │     Game      │    │   Settings    │
│    :50054     │    │  Coordinator  │    │    :50051     │
└───────────────┘    │    :50053     │    └───────────────┘
                     └───────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  Controller   │    │     Audio     │    │ Observability │
│   Manager     │    │    :50056     │    │ Jaeger/Prom   │
│    :50052     │    └───────────────┘    │ Grafana/Loki  │
└───────────────┘                         └───────────────┘
```

7 microservices communicating via gRPC with full distributed tracing.

## Development

```bash
make lint          # Lint code
make format        # Format code
make test          # Run integration tests
```

**Dev Container:** Open in VS Code and click "Reopen in Container" for a pre-configured environment.

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for the full development guide.

## Mock Environment

Test without hardware:

```bash
CONTROLLER_BACKEND=mock docker compose up -d
```

See [Mock Environment Guide](services/controller_manager/MOCK_ENVIRONMENT.md) for details.

## Hardware Setup

For physical PS Move controllers, see [Hardware Setup Guide](docs/hardware-setup-guide.md).

**Requirements:** PS Move controllers, USB Bluetooth adapter, Raspberry Pi or Linux

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design and service interactions |
| [Development](docs/DEVELOPMENT.md) | Building, running, debugging |
| [Contributing](docs/CONTRIBUTING.md) | Code style, PR workflow |
| [Controller Guide](docs/controller-guide.md) | Button layout, admin mode |
| [LED Feedback](docs/controller-feedback.md) | Controller LED color reference |
| [Observability](docs/observability-quickstart.md) | Tracing, metrics, dashboards |

## Services

| Service | Port | Purpose |
|---------|------|---------|
| Settings | 50051 | Centralized configuration |
| Controller Manager | 50052 | PS Move I/O and pairing |
| Game Coordinator | 50053 | Game lifecycle management |
| Menu | 50054 | Menu navigation |
| Audio | 50056 | Audio playback and mixing |
| Dashboard | 8080 | Web UI and reverse proxy |
| Connect Proxy | - | gRPC-web bridge |

## Technology Stack

- **Language:** Python 3.11
- **Communication:** gRPC with Protocol Buffers
- **Observability:** OpenTelemetry, Jaeger, Prometheus, Grafana
- **Infrastructure:** Docker, Docker Compose

## Credits

- **[Adam Engert](https://github.com/adangert)** - Original JoustMania creator
- **[Original JoustMania](https://github.com/adangert/JoustMania)** - The game this fork is based on
- **[Steam Release](https://store.steampowered.com/app/1093850/JoustMania/)** - Original game on Steam

## License

See [LICENSE](LICENSE) file for details.

## Links

- [Issues](https://github.com/WatchMeJoustMyFlags/JoustMania/issues)
- [Discussions](https://github.com/WatchMeJoustMyFlags/JoustMania/discussions)
