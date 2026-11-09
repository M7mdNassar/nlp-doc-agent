FROM node:22-alpine AS base

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# -----------------
# Development Stage
# -----------------
FROM base AS development
COPY frontend/package.json frontend/package-lock.json* /app/
RUN npm ci
COPY frontend/ /app/

# -----------------
# Build Stage (Production)
# -----------------
FROM base AS builder
COPY frontend/package.json frontend/package-lock.json* /app/
RUN npm ci
COPY frontend/ /app/
RUN npm run build

# -----------------
# Production Stage
# -----------------
FROM base AS production
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
USER node

EXPOSE 3000
CMD ["node", "server.js"]
