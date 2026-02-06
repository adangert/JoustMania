# Grafana Live Publisher Dockerfile
# Receives OTLP metrics and pushes to Grafana Live WebSocket

# Stage 1: Build the Go binary
FROM --platform=$BUILDPLATFORM golang:1.22-alpine AS builder

# Build arguments for cross-compilation
ARG TARGETARCH

WORKDIR /app

# Copy go.mod (no external dependencies)
COPY services/grafana-live-publisher/go.mod ./

# Copy source code
COPY services/grafana-live-publisher/*.go ./

# Build the binary (cross-compile for target architecture)
RUN CGO_ENABLED=0 GOOS=linux GOARCH=${TARGETARCH} go build -ldflags="-s -w" -o /grafana-live-publisher .

# Stage 2: Runtime image
FROM alpine:3.19

# Install wget for health checks
RUN apk add --no-cache wget ca-certificates

COPY --from=builder /grafana-live-publisher /grafana-live-publisher

EXPOSE 4318

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD wget --spider -q http://localhost:4318/health || exit 1

ENTRYPOINT ["/grafana-live-publisher"]
