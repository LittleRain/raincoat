FROM node:20-bullseye

WORKDIR /app

COPY package.json package-lock.json tsconfig.base.json vitest.config.ts ./
COPY apps ./apps
COPY packages ./packages
COPY tools ./tools

RUN npm install
RUN npm run build

ENV NODE_ENV=production
ENV PORT=3200

EXPOSE 3200

CMD ["npx", "tsx", "apps/api/src/index.ts"]
