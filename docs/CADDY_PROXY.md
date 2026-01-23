# Dashboard Reverse Proxy - Caddy Configuration

## Overview

The JoustMania dashboard serves as a unified entry point for all services, including:
- The main dashboard UI (TypeScript/React SPA)
- gRPC-Web API (`/joustmania`)
- Observability tools: Grafana (`/grafana`), Prometheus (`/prometheus`), Jaeger (`/jaeger`), Loki (`/loki`)
- Legacy WebUI (`/legacy`)

As of Phase 65, the reverse proxy implementation has been migrated from **nginx** to **Caddy** to address redirect issues and improve configuration maintainability.

## Why Caddy?

### Problems with nginx
The previous nginx setup had several issues:
1. **Redirect Issues**: Users were sometimes redirected to `localhost` instead of staying on their original IP/domain
2. **Fragile Configuration**: Upstream services (like Grafana, Prometheus) would generate absolute URLs based on their internal config, and nginx couldn't reliably rewrite these without complex hacks
3. **Header Management**: Required manual configuration for proper header forwarding
4. **WebSocket Support**: Needed explicit configuration for WebSocket upgrades

### Benefits of Caddy
1. **Automatic Header Rewriting**: Caddy automatically rewrites `Location` headers in HTTP redirects, preventing localhost redirect issues
2. **Simpler Configuration**: More intuitive syntax compared to nginx
3. **Better Defaults**: Automatically handles common scenarios like WebSocket upgrades and proper header forwarding
4. **Automatic HTTPS**: Built-in support for automatic HTTPS (though not used in the current Docker setup)

## Configuration

The Caddyfile is located at `services/dashboard/Caddyfile` and serves on port 80 within the Docker network.

### Key Configuration Sections

#### 1. Static File Serving
```caddyfile
# Root directory for static files
root * /usr/share/caddy

# Serve static files with caching for assets
@assets {
    path /assets/*
}
handle @assets {
    header Cache-Control "public, max-age=31536000, immutable"
    file_server
}

# SPA fallback - serve index.html for all other routes
handle {
    try_files {path} /index.html
    file_server
}
```

#### 2. gRPC-Web Proxy
```caddyfile
handle /joustmania* {
    reverse_proxy connect-proxy:8080 {
        # Disable buffering for streaming support
        flush_interval -1
        # Extended timeout for long-running requests
        transport http {
            read_timeout 3600s
        }
    }
}
```

#### 3. Observability Tools
```caddyfile
# handle_path strips the path prefix before proxying
handle_path /grafana/* {
    reverse_proxy grafana:3000
}

handle_path /prometheus/* {
    reverse_proxy prometheus:9090
}

handle_path /jaeger/* {
    reverse_proxy jaeger:16686
}

handle_path /loki/* {
    reverse_proxy loki:3100
}
```

**Important**: The `handle_path` directive automatically strips the path prefix (e.g., `/grafana`) before forwarding the request to the upstream service. This is why Grafana is configured with:
```yaml
GF_SERVER_ROOT_URL=%(protocol)s://%(domain)s/grafana/
GF_SERVER_SERVE_FROM_SUB_PATH=true
```

And Prometheus with:
```yaml
--web.external-url=/prometheus/
--web.route-prefix=/
```

## Upstream Service Configuration

### Grafana
Grafana is configured in `docker-compose.yml` to serve from the `/grafana/` subpath:
```yaml
environment:
  - GF_SERVER_ROOT_URL=%(protocol)s://%(domain)s/grafana/
  - GF_SERVER_SERVE_FROM_SUB_PATH=true
```

This ensures that all Grafana-generated URLs include the `/grafana/` prefix.

### Prometheus
Prometheus is configured with command-line flags:
```yaml
command:
  - '--web.external-url=/prometheus/'
  - '--web.route-prefix=/'
```

These flags tell Prometheus:
- External users access it at `/prometheus/`
- Routes are handled without the prefix internally

### Jaeger, Loki, Legacy WebUI
These services work out-of-the-box with subpath proxying and don't require special configuration.

## Testing the Proxy

To verify the reverse proxy is working correctly:

1. **Build the dashboard image**:
   ```bash
   make image-dashboard
   ```

2. **Start the stack**:
   ```bash
   make up-mock  # For testing without hardware
   ```

3. **Access services**:
   - Dashboard: http://localhost:8080/
   - Grafana: http://localhost:8080/grafana/
   - Prometheus: http://localhost:8080/prometheus/
   - Jaeger: http://localhost:8080/jaeger/
   - Loki API: http://localhost:8080/loki/
   - Legacy WebUI: http://localhost:8080/legacy/

4. **Verify redirects**:
   - Navigate to Grafana dashboards - ensure URLs stay on `localhost:8080/grafana/` and don't redirect to `localhost:3000`
   - Check Prometheus targets - URLs should include `/prometheus/` prefix
   - Test login/logout flows in Grafana

## Troubleshooting

### Service returns 502 Bad Gateway
- Check that the upstream service is healthy: `docker ps` and look for health status
- Check logs: `docker logs joustmania-dashboard`
- Verify service names in Caddyfile match docker-compose.yml

### Redirects to wrong URL
- Ensure upstream service is configured for subpath serving (see above)
- Check Caddy logs for rewrite behavior
- Verify the `handle_path` directive is used (it strips the prefix automatically)

### Assets not loading
- Verify the dashboard build copied files to `/usr/share/caddy`
- Check browser console for 404 errors
- Ensure Cache-Control headers are set correctly for `/assets/*`

## Migration Checklist

When migrating a new service to the Caddy proxy:

1. [ ] Add a `handle_path` or `handle` block in the Caddyfile
2. [ ] Configure the upstream service for subpath serving (if needed)
3. [ ] Test the service through the proxy
4. [ ] Verify redirects stay on the correct domain/IP
5. [ ] Check that all assets load correctly
6. [ ] Update docker-compose.yml health checks if needed

## References

- [Caddy Reverse Proxy Documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
- [Caddy handle_path Directive](https://caddyserver.com/docs/caddyfile/directives/handle_path)
- [Grafana Behind a Reverse Proxy](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/#server)
- [Prometheus Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
