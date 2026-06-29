FROM node:22 AS build

WORKDIR /app

# Friendlier npm: skip audit/funding network calls, prefer cache when possible,
# and give Node enough heap for vite/rollup/tailwind-oxide native bundling.
# "Exit handler never called!" on `npm ci` is almost always OOM during the
# native-binary install step on small VPS / slim images.
ENV NPM_CONFIG_AUDIT=false \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_PROGRESS=false \
    NPM_CONFIG_LOGLEVEL=error \
    NODE_OPTIONS=--max-old-space-size=4096

COPY frontend/package.json frontend/package-lock.json ./

# Retry once on transient failures; --prefer-offline reuses any cached tarballs;
# --maxsockets caps parallel downloads so RAM doesn't spike.
RUN npm ci --prefer-offline --maxsockets 6 \
 || (echo "npm ci failed, retrying..." && rm -rf node_modules && \
     npm ci --prefer-offline --maxsockets 4)

COPY frontend/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
