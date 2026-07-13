# =============================================================================
# Frontend Dockerfile — multi-stage
# Stage 1: development (Vite dev server)
# Stage 2: builder (npm build)
# Stage 3: production (nginx static serving)
# =============================================================================

# ── Stage 1: Development ─────────────────────────────────────────────────────
FROM node:20-alpine AS development

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ── Stage 2: Builder ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ── Stage 3: Production (nginx) ───────────────────────────────────────────────
FROM nginx:1.27-alpine AS production

# SPA routing: all paths → index.html
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
