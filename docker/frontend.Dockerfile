# syntax=docker/dockerfile:1
FROM node:22-alpine AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM dependencies AS build
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/ ./
RUN mkdir -p public && npm run typecheck && npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
