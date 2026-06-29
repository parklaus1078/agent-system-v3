# Control Tower web — build the Vite SPA, serve it (and reverse-proxy /api) via nginx.
FROM node:20-alpine AS build
WORKDIR /web

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
# Baked at build time: the SPA calls "/api/...", which nginx proxies to the backend.
# Setting it (vs empty) is what selects HttpApiClient over the in-browser mock.
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
