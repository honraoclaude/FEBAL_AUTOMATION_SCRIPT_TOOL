# Production web image (D-06, plan 11-02). This is the image GHCR publishes and K8s runs.
#
# Multi-stage build following the repo's canonical two-stage shape
# (infra/targets/saucedemo/Dockerfile:22-31) adapted to Next 16:
#   build stage  -> npm ci (full deps) + `next build`
#   runtime stage -> slim node:22-alpine that runs `next start` (NOT `npm run dev`,
#                    NOT Turbopack — the dev server has no place in a published image,
#                    T-11-08 / RESEARCH Pitfall 3).
#
# Next 16 serving mode (verified against node_modules/next/dist/docs, NOT training data —
# apps/web/AGENTS.md): we use `next start`, which works zero-config here. The next.config.ts
# `rewrites()` proxy to the FastAPI backend reads API_URL at RUNTIME (the rewrite function is
# evaluated per request), so the compose/K8s env switch (API_URL=http://api:8000) still works
# against this image. `output: 'standalone'` is the alternative but would require manual
# public/.next/static copy steps + a config change; `next start` is simpler and adds no deps.
#
# No new npm dependency is introduced. The runtime stage copies only the build artifacts +
# the already-installed node_modules from the build stage (no second `npm ci` at runtime).

FROM node:22-alpine AS build
WORKDIR /app

# Manifests first for layer caching — deps only re-resolve when the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- Runtime stage: slim image that serves the production build via `next start` ----
FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

# Copy only what `next start` needs: the build output, public assets, the manifest, and the
# (already-installed) node_modules from the build stage — no dev tooling rebuild at runtime.
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.ts ./next.config.ts

EXPOSE 3000
# Production server — `next start` (no dev/Turbopack watcher). Bind 0.0.0.0 for the container.
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
