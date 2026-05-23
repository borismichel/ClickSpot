# ClickSpot frontend image — builds the Vite/React app to static files and
# serves them through nginx, which also reverse-proxies /api and /health to the
# backend so the browser only ever talks to a single origin (no CORS, no knobs).

# ---- build: compile the SPA to static assets --------------------------------
FROM node:20-alpine AS build

WORKDIR /app
# Copy manifests first so `npm ci` is cached until dependencies actually change.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# `build` runs `tsc -b && vite build` (see package.json) -> ./dist
RUN npm run build

# ---- serve: nginx with SPA fallback + API reverse proxy ---------------------
FROM nginx:1.27-alpine

# BACKEND_ORIGIN is substituted into the nginx template at container start
# (handled by the stock nginx image's envsubst entrypoint). Defaults to the
# compose service name so `docker compose up` needs zero configuration.
ENV BACKEND_ORIGIN=http://backend:8192

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=5 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1
