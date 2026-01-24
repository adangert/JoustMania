# Dashboard Dockerfile
# Multi-stage build: Node for build, static-web-server for serving
#
# static-web-server is a lightweight (~6MB) Rust-based HTTP server
# with built-in SPA fallback support via environment variables

# Stage 1: Build the TypeScript application
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY services/dashboard/package.json services/dashboard/package-lock.json* ./

# Install dependencies
RUN npm install

# Copy source code
COPY services/dashboard/ ./

# Build the application
RUN npm run build

# Stage 2: Serve with static-web-server
FROM joseluisq/static-web-server:2-alpine

# Copy built files to the public directory
COPY --from=builder /app/dist /public

# Configure static-web-server via environment variables
ENV SERVER_PORT=8080
ENV SERVER_ROOT=/public
ENV SERVER_FALLBACK_PAGE=/public/index.html
ENV SERVER_COMPRESSION=true

EXPOSE 8080

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD wget -q -O /dev/null http://localhost:8080/ || exit 1
