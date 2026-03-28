FROM node:20-bullseye

WORKDIR /app

RUN apt-get update \
  && apt-get install -y python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json tsconfig.base.json vitest.config.ts ./
COPY apps ./apps
COPY packages ./packages
COPY tools ./tools

RUN npm install
RUN npm run build

ENV NODE_ENV=production

CMD ["npx", "tsx", "apps/worker/src/index.ts"]
