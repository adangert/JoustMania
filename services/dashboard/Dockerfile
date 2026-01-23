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

# Stage 2: Serve with nginx
FROM nginx:alpine

# Copy built files to nginx html directory
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY services/dashboard/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
