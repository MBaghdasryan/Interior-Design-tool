FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.28-alpine
# pick up OS security fixes released after the base image was built (scanned by trivy in CI)
RUN apk upgrade --no-cache
# the image renders /etc/nginx/templates/*.template with envsubst at start (only defined variables)
ENV CSP_CONNECT_EXTRA=""
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
