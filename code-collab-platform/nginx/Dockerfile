FROM nginx:1.27-alpine

RUN apk add --no-cache openssl \
    && mkdir -p /etc/nginx/certs \
    && openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/certs/key.pem \
        -out /etc/nginx/certs/cert.pem \
        -subj "/CN=localhost"

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/conf.d/api.conf /etc/nginx/conf.d/api.conf
COPY nginx/conf.d/websocket.conf /etc/nginx/conf.d/websocket.conf
COPY nginx/conf.d/static.conf /etc/nginx/conf.d/static.conf

# Remove default site bundled with the base image
RUN rm -f /etc/nginx/conf.d/default.conf

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
