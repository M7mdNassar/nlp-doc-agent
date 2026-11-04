FROM node:20-alpine AS base

WORKDIR /app

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
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]