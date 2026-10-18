FROM node:22.22.3-alpine

WORKDIR /app
# Manifests first: the dependency layer is rebuilt only when the lock file changes
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .
# the Vite dev server for now; a production image (static build behind a web server) comes later
CMD ["node_modules/.bin/vite", "--host", "0.0.0.0"]
