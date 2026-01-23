# Dashboard Dockerfile
# Multi-stage build: Node for build, nginx for serving

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

# Stage 2: Serve with Caddy
FROM caddy:2.8-alpine

# Copy built files to Caddy html directory
COPY --from=builder /app/dist /usr/share/caddy

# Copy Caddyfile
COPY services/dashboard/Caddyfile /etc/caddy/Caddyfile

EXPOSE 80

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
