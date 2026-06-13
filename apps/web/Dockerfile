# Dev-oriented web image (plan 01-04). Containerized hot-reload is NOT
# promised on Windows (Turbopack + bind mounts — RESEARCH Pitfall 1); hybrid
# host mode (`npm run dev` on the host) is the primary DX. This container's
# job is the one-command D-08 promise: the stack is up and serving.
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]
