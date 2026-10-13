FROM node:22-bookworm-slim AS web-build
WORKDIR /app
COPY package*.json ./
COPY client/package.json client/package.json
COPY server/package.json server/package.json
RUN npm install
COPY client ./client
RUN npm run build -w client

FROM node:22-bookworm-slim
ENV NODE_ENV=production HEADLESS=true PYTHONUNBUFFERED=1 DATA_DIR=/var/data REPORT_DIR=/var/data/reports
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver python3 python3-dev python3-pip \
    build-essential fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package*.json ./
COPY server/package.json server/package.json
COPY client/package.json client/package.json
# sqlite3's upstream prebuilt binary currently targets a newer GLIBC than
# Debian Bookworm. Building native modules here links them to this image.
RUN npm_config_build_from_source=true npm install --omit=dev
COPY --from=web-build /app/client/dist ./client/dist
COPY server ./server
COPY *.py requirements.txt ./
RUN pip3 install --break-system-packages --no-cache-dir -r requirements.txt
RUN mkdir -p /var/data/reports && chown -R node:node /var/data
USER node
EXPOSE 3000
CMD ["npm", "start"]
