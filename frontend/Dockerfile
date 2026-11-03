# The BatchGate web app: built with Vite, served by Caddy, which also forwards /api to the api
# service. With DOMAIN set (a DNS A record pointing at the server) Caddy gets an HTTPS
# certificate on its own; without it, plain HTTP on port 80.

FROM node:22-slim AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv
