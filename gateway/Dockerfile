# Build from the repository root: docker build -f gateway/Dockerfile .
# Nginx gateway: serves the static frontend and proxies /api/* to the services.
FROM nginxinc/nginx-unprivileged:1.27-alpine@sha256:65e3e85dbaed8ba248841d9d58a899b6197106c23cb0ff1a132b7bfe0547e4c0

COPY gateway/nginx.conf /etc/nginx/nginx.conf
COPY gateway/proxy_common.conf /etc/nginx/proxy_common.conf
COPY frontend/ /usr/share/nginx/html/
EXPOSE 8080
