# API di globe-stick (server.py): copia dei dati di CelesTrak e proxy di N2YO con la chiave.
FROM python:3.12-alpine
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
# /data di nobody: un volume nuovo e vuoto prende proprietario e permessi da qui
RUN mkdir /data && chown nobody /data
COPY server.py /app/server.py
USER nobody
EXPOSE 8000
CMD ["python", "/app/server.py"]
