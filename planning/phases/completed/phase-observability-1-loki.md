# Phase: Loki Log Aggregation

**Status**: Complete

## Summary

Integrated a Loki-based log aggregation system into the JoustMania microservice architecture for improved observability, deployed via Docker Compose. All logs from each service are sent via OTLP to the Loki stack, which retains logs for just 1 hour to optimize resource usage on the Raspberry Pi, allowing near real-time querying and troubleshooting.

Also reorganized all infrastructure service configurations into the `services/` directory for consistency.

**Observability Stack Overview:**
- **Loki** (http://localhost:3100): Log aggregation with 1-hour retention
- **Prometheus** (http://localhost:9090): Metrics collection with 30-day retention
- **Jaeger** (http://localhost:16686): Distributed tracing
- **Grafana** (http://localhost:3000): Unified visualization (admin/joustmania)
- **OpenTelemetry Collector**:  Central telemetry pipeline (OTLP → Loki/Prometheus/Jaeger)

**Loki Configuration Details:**
- **Endpoint**: `http://localhost:3100`
- **API Path**: `/loki/api/v1/query_range` (for queries), `/loki/api/v1/push` (for ingestion)
- **Retention Period**: 1 hour (enforced via `limits_config.retention_period` and `table_manager`)
- **Storage**: Local filesystem (`/tmp/loki` in container, mounted as `loki-data` volume)
- **Schema**: BoltDB-shipper with filesystem object store
- **Compaction**: Runs every 10 minutes to clean up old data
- **Query Limits**: Max 1000 lines default (configurable in Grafana datasource)

**How to Query Loki:**

All services are tagged with:
- `service.namespace="joustmania"`
- `service.name="<service-name>"` (e.g., "settings-service", "controller-manager-service")

Example LogQL queries:
```logql
# All logs from all JoustMania services
{service_namespace="joustmania"}

# Logs from a specific service
{service_namespace="joustmania", service_name="settings-service"}

# Search for errors across all services
{service_namespace="joustmania"} |= "error"

# Filter by log level (if structured logging is used)
{service_namespace="joustmania"} | json | level="ERROR"
```

**HTTP API Query Example:**
```bash
# Get last 100 log lines from the past hour
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={service_namespace="joustmania"}' \
  --data-urlencode "start=$(date -d '1 hour ago' +%s)000000000" \
  --data-urlencode "end=$(date +%s)000000000" \
  --data-urlencode 'limit=100'
```

**Python Query Example:**
```python
import requests
from datetime import datetime, timedelta

def query_logs(service_name=None, search_text=None, limit=100):
    loki_url = "http://localhost:3100"
    
    query = '{service_namespace="joustmania"}'
    if service_name:
        query = f'{{service_namespace="joustmania", service_name="{service_name}"}}'
    if search_text:
        query += f' |= "{search_text}"'
    
    end = datetime.now()
    start = end - timedelta(hours=1)
    
    params = {
        'query': query,
        'limit': limit,
        'start':  int(start.timestamp() * 1e9),
        'end': int(end.timestamp() * 1e9),
        'direction': 'backward'
    }
    
    response = requests.get(f"{loki_url}/loki/api/v1/query_range", params=params)
    return response.json()
```

**Service Names (for filtering):**
- `settings-service`
- `controller-manager-service`
- `game-coordinator-service`
- `menu-service`
- `supervisor-service`
- `webui-service`
- `audio-service`

**Benefits for CLI Agents:**
- Query recent logs programmatically without SSH/file access
- Filter by service, time range, log level, or content
- Combine with Prometheus metrics and Jaeger traces for complete observability
- 1-hour retention keeps resource usage minimal on Raspberry Pi

---

**Note on Service Configuration Structure:**  
Currently, configuration files for observability tools (`otel-collector-config.yaml`, `loki-config.yaml`, Prometheus, Grafana, etc.) are in the project root or separate directories.

**Recommended Best Practice:**  
Group **all service configuration files (including infrastructure, monitoring, and logging tools)** within a unified directory structure under `services/`:

```
services/
  otel-collector/
    otel-collector-config.yaml
  loki/
    loki-config.yaml
  prometheus/
    prometheus.yml
    prometheus-alerts.yml
  grafana/
    provisioning/
      datasources/
        prometheus.yml
        loki.yml
      dashboards/
    dashboards/
  settings/
    ... 
  controller-manager/
    ...
  game-coordinator/
    ...
  menu/
    ...
  supervisor/
    ... 
  webui/
    ... 
  audio/
    ... 
```

**Benefits of this structure:**
- Cleaner project root
- Logical grouping of all service-related files (code + config)
- Easier Docker volume mounting paths
- Better scalability for adding new services or tools
- Clear separation between infrastructure config and application code

**Volume Mount Updates (example):**
```yaml
# Before: 
- ./loki-config.yaml:/etc/loki/loki-config.yaml:ro

# After:
- ./services/loki/loki-config.yaml:/etc/loki/loki-config.yaml:ro
```

---

**Summary:**  
You can now query logs for the past hour from any JoustMania service using simple Loki LogQL expressions (filter by service name, log content, severity, etc.), either via Grafana UI or programmatically using the Loki HTTP API—no more manual log copying or SSH access required!

---