# Control Tower web — dev (vite HMR) OR prod (build the SPA, serve via nginx + /api proxy).
#   prod (default):  docker compose build web           -> nginx static on :80
#   dev:             target `dev` (docker-compose.dev.yml) -> vite dev server on :5173

# ---- deps: node + installed packages (shared by the dev and build stages) ----
FROM node:20-alpine AS deps
WORKDIR /web
COPY package.json package-lock.json* ./
RUN npm ci

# ---- dev: vite dev server with HMR (source is synced in at runtime via Compose Watch) ----
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ---- build: produce the static bundle ----
FROM deps AS build
COPY . .
# Baked at build time: the SPA calls "/api/...", which nginx proxies to the backend.
# Setting it (vs empty) is what selects HttpApiClient over the in-browser mock.
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

# ---- prod (default final stage): nginx serves the bundle and reverse-proxies /api ----
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
