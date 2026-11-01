# La pagina statica, servita da nginx dietro Traefik. I dati arrivano dall'API in api/
# (Traefik manda /api/ a quel container, vedi deploy/stack.yml).
FROM nginx:alpine
COPY index.html /usr/share/nginx/html/index.html
