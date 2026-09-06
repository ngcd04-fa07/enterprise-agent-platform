FROM node:22-slim AS base
WORKDIR /app

FROM base AS deps
COPY package.json package-lock.json* ./
RUN npm install

FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# next.config.ts resolves API_ORIGIN when rewrites() is evaluated, and Next.js
# bakes that resolved destination into .next/routes-manifest.json at build
# time — next start does not re-evaluate it. So the compose service-to-service
# origin must be available here as a build arg, not just as the container's
# runtime environment variable.
ARG API_ORIGIN
ENV API_ORIGIN=$API_ORIGIN
# Same gotcha, same fix (Stage 20): headers() is baked into the routes
# manifest at build time exactly like rewrites() — without this, the
# HSTS gate in next.config.ts would read `process.env.ENVIRONMENT` as
# unset during `docker build` (not "development"), bake in as
# "production" unconditionally, and emit HSTS even for this dev/demo
# compose deployment.
ARG ENVIRONMENT
ENV ENVIRONMENT=$ENVIRONMENT
RUN npm run build

FROM base AS run
ENV NODE_ENV=production
COPY --from=build /app/public ./public
COPY --from=build /app/.next ./.next
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/next.config.ts ./next.config.ts

EXPOSE 3000
CMD ["npm", "run", "start"]
