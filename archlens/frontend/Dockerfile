# ── Stage 1: build ─────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ── Stage 2: nginx ─────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Custom nginx conf (proxies /api and /samples to backend service)
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Default backend host/port — override at runtime with -e BACKEND_HOST=...
ENV BACKEND_HOST=archlens-backend \
    BACKEND_PORT=8000

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# nginx:alpine image already runs envsubst on /etc/nginx/templates/*.template
CMD ["nginx", "-g", "daemon off;"]
