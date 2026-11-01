#!/usr/bin/env python3
"""API di globe-stick, dietro Traefik su https://globe-stick.mrgabri.it/api/

  GET /api/gp/<gruppo>            elementi orbitali (OMM) del gruppo, da CelesTrak
  GET /api/satcat/<gruppo>        catalogo SATCAT del gruppo, ridotto ai campi della schedina
  GET /api/above?lat=..&lon=..    tutti i satelliti sopra un punto, da N2YO ("What's up?")

CelesTrak: i dati si scaricano qui, al massimo ogni 2 ore (il catalogo una volta al giorno), e
restano nel volume /data. CelesTrak vede così un solo client invece di un download per ogni
visitatore: chi sta dietro lo stesso IP (stessa rete di casa, operatore mobile) altrimenti riceve
403 per i gruppi che un altro ha già scaricato. Le età si misurano dalla data dei file, quindi un
nuovo deploy non riscarica niente.

N2YO: la chiave resta qui (Docker secret) e non arriva mai al browser. N2YO concede 100 chiamate
all'ora per chiave, quindi: risposte in memoria per qualche minuto per punto arrotondato, un tetto
orario sotto il limite, un limite per IP del visitatore e solo richieste dalla pagina del sito.

Solo libreria standard: niente dipendenze da installare.
"""
import gzip
import ipaddress
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GROUPS = ('visual', 'stations', 'weather', 'gps-ops', 'galileo', 'geo', 'starlink')
DATA = os.environ.get('DATA_DIR', '/data')
REFRESH = os.environ.get('CELESTRAK_REFRESH', '1') == '1'   # 0 per le prove in locale
SITE = 'https://globe-stick.mrgabri.it'
UA = 'globe-stick.mrgabri.it (api)'

GP_MAX_AGE = 125 * 60          # CelesTrak aggiorna gli elementi ogni 2 ore
SATCAT_MAX_AGE = 24 * 3600
RETRY_AFTER = 3600             # dopo un errore, per un'ora niente nuovi tentativi su quel file
SATCAT_FIELDS = ('NORAD_CAT_ID', 'OBJECT_TYPE', 'OPS_STATUS_CODE', 'OWNER', 'LAUNCH_DATE', 'LAUNCH_SITE', 'DECAY_DATE')
SOURCES = {   # tipo -> (URL del gruppo, età massima, riduzione dei record)
    'gp': ('https://celestrak.org/NORAD/elements/gp.php?GROUP={}&FORMAT=json', GP_MAX_AGE, None),
    'satcat': ('https://celestrak.org/satcat/records.php?GROUP={}&FORMAT=json', SATCAT_MAX_AGE,
               lambda rows: [{k: r.get(k) for k in SATCAT_FIELDS} for r in rows]),
}

N2YO_KEY_FILE = '/run/secrets/n2yo_api_key'
N2YO_RADIUS = 80       # gradi dallo zenit: sopra i 10° di elevazione, come la pagina
N2YO_HOURLY = 90       # tetto nostro, sotto le 100 chiamate all'ora concesse da N2YO
ABOVE_TTL = 120        # secondi di vita di una risposta in memoria
ABOVE_GRID = 0.5       # gradi: il punto si arrotonda (cache comune, e N2YO non riceve la posizione esatta)
PER_IP_PER_MIN = 6

# Reti di Cloudflare (https://www.cloudflare.com/ips/). Solo se la connessione arriva da qui
# CF-Connecting-IP è affidabile: la VPS risponde anche chiamata direttamente, e chi lo fa può
# scrivere in quell'intestazione l'IP che vuole per aggirare il limite per visitatore.
CLOUDFLARE_NETS = [ipaddress.ip_network(n) for n in (
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '141.101.64.0/18',
    '108.162.192.0/18', '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22', '198.41.128.0/17',
    '162.158.0.0/15', '104.16.0.0/13', '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
    '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32', '2405:8100::/32',
    '2a06:98c0::/29', '2c0f:f248::/32',
)]


def log(msg):
    print(time.strftime('%Y-%m-%d %H:%M:%S'), msg, flush=True)


# ---------------------------------------------------------------- CelesTrak
def path_for(kind, group):
    return os.path.join(DATA, kind, group + '.json')


def age(path):
    try:
        return time.time() - os.path.getmtime(path)
    except OSError:
        return float('inf')


failures = {}   # file -> ora dell'ultimo errore


def download(kind, group):
    url, _, reduce = SOURCES[kind]
    url, path = url.format(group), path_for(kind, group)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=180) as res:
            rows = json.loads(res.read())
        if not isinstance(rows, list) or not rows:
            raise ValueError('risposta vuota')
        if reduce:
            rows = reduce(rows)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(rows, f, separators=(',', ':'))
        os.replace(tmp, path)
        failures.pop(path, None)
        log(f'ok {kind}/{group}: {len(rows)} oggetti')
    except urllib.error.HTTPError as err:
        failures[path] = time.time()
        log(f'ERRORE {kind}/{group}: HTTP {err.code} {err.read(200).decode("utf-8", "replace").strip()}')
    except Exception as err:  # rete, JSON non valido…: si riprova fra un'ora
        failures[path] = time.time()
        log(f'ERRORE {kind}/{group}: {err}')


def refresher():
    while True:
        for group in GROUPS:
            for kind, (_, max_age, _) in SOURCES.items():
                path = path_for(kind, group)
                if age(path) > max_age and time.time() - failures.get(path, 0) > RETRY_AFTER:
                    download(kind, group)
                    time.sleep(3)
        time.sleep(600)


files = {}   # file -> (mtime, json, json in gzip): si comprime una volta per versione
files_lock = threading.Lock()


def load(path):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    with files_lock:
        cached = files.get(path)
        if cached and cached[0] == mtime:
            return cached
        with open(path, 'rb') as f:
            raw = f.read()
        files[path] = cached = (mtime, raw, gzip.compress(raw, 6))
        return cached


# ---------------------------------------------------------------- N2YO
try:
    with open(N2YO_KEY_FILE, encoding='utf-8') as f:
        N2YO_KEY = f.read().strip()
except OSError:
    N2YO_KEY = ''

n2yo_lock = threading.Lock()
n2yo_calls = deque()   # orari delle chiamate a N2YO nell'ultima ora
above_cache = {}       # (lat, lon) arrotondati -> (ora, risposta)
above_inflight = {}    # (lat, lon) arrotondati -> Event di una chiamata a N2YO in corso
ip_hits = defaultdict(deque)
ip_pruned_at = 0.0
NO_ANSWER = b'{"error":"N2YO non risponde"}'


def snap(v):
    return round(round(v / ABOVE_GRID) * ABOVE_GRID, 2)


def above(lat, lon):
    key, now = (snap(lat), snap(lon)), time.time()
    with n2yo_lock:
        hit = above_cache.get(key)
        if hit and now - hit[0] < ABOVE_TTL:
            return 200, hit[1]
        # Se la stessa chiamata è già partita per un altro visitatore, si aspetta quella invece di
        # farne una seconda: con molte richieste insieme il tetto orario si consumerebbe in fretta.
        pending = above_inflight.get(key)
        if not pending:
            while n2yo_calls and now - n2yo_calls[0] > 3600:
                n2yo_calls.popleft()
            if len(n2yo_calls) >= N2YO_HOURLY:
                return 429, b'{"error":"troppe richieste a N2YO in questa ora"}'
            n2yo_calls.append(now)
            above_inflight[key] = threading.Event()
    if pending:
        pending.wait(timeout=35)
        with n2yo_lock:
            hit = above_cache.get(key)
        return (200, hit[1]) if hit else (502, NO_ANSWER)
    try:
        return fetch_above(key, now)
    finally:
        with n2yo_lock:
            above_inflight.pop(key).set()


def fetch_above(key, now):
    url = (f'https://api.n2yo.com/rest/v1/satellite/above/{key[0]}/{key[1]}/0/{N2YO_RADIUS}/0/'
           f'&apiKey={urllib.parse.quote(N2YO_KEY)}')
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30) as res:
            j = json.loads(res.read())
    except Exception as err:   # nel log mai l'URL: contiene la chiave
        log(f'ERRORE N2YO above: {type(err).__name__} {getattr(err, "code", "")}')
        return 502, NO_ANSWER
    # Risposta di forma inattesa (null, lista, "above" che non è una lista…): errore pulito, non un'eccezione
    if not isinstance(j, dict) or not isinstance(j.get('above') or [], list):   # null = niente sopra
        log(f'ERRORE N2YO above: risposta inattesa ({type(j).__name__})')
        return 502, b'{"error":"risposta di N2YO non valida"}'
    if 'error' in j:
        log(f'ERRORE N2YO above: {str(j["error"])[:200]}')
        return 502, b'{"error":"N2YO ha rifiutato la richiesta"}'
    objects = [o for o in j.get('above') or [] if isinstance(o, dict)]
    info = j.get('info') if isinstance(j.get('info'), dict) else {}
    log(f'N2YO above: {len(objects)} oggetti, {info.get("transactionscount", "?")} chiamate nell\'ultima ora')
    payload = json.dumps({'at': int(now), 'lat': key[0], 'lon': key[1], 'above': objects},
                         separators=(',', ':')).encode()
    with n2yo_lock:
        for k in [k for k, (t, _) in above_cache.items() if now - t >= ABOVE_TTL]:
            del above_cache[k]
        above_cache[key] = (now, payload)
    return 200, payload


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = 'globe-api'
    sys_version = ''

    def client_ip(self):
        # Traefik scrive in X-Forwarded-For l'indirizzo di chi gli si è collegato davvero (quello
        # mandato dal client lo scarta). Se è Cloudflare, il visitatore è in CF-Connecting-IP;
        # altrimenti è quell'indirizzo stesso, e un CF-Connecting-IP inventato non conta.
        remote = (self.headers.get('X-Forwarded-For') or '').split(',')[-1].strip() or self.client_address[0]
        try:
            via_cloudflare = any(ipaddress.ip_address(remote) in net for net in CLOUDFLARE_NETS)
        except ValueError:
            via_cloudflare = False
        return (via_cloudflare and self.headers.get('CF-Connecting-IP', '').strip()) or remote

    def reply(self, code, body, gz=None, cache='no-store'):
        use_gz = gz is not None and 'gzip' in (self.headers.get('Accept-Encoding') or '')
        data = gz if use_gz else body
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', cache)
        self.send_header('Vary', 'Accept-Encoding')
        if use_gz:
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def fail(self, code, msg):
        self.reply(code, json.dumps({'error': msg}).encode())

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        m = re.fullmatch(r'/api/(gp|satcat)/([a-z0-9-]+)', url.path)
        if m:
            kind, group = m.groups()
            if group not in GROUPS:
                return self.fail(404, 'gruppo sconosciuto')
            f = load(path_for(kind, group))
            if not f:
                return self.fail(503, 'dati non ancora scaricati')
            return self.reply(200, f[1], f[2], 'public, max-age=300')
        if url.path == '/api/above':
            return self.handle_above(urllib.parse.parse_qs(url.query))
        self.fail(404, 'non trovato')

    def do_HEAD(self):
        # Su /api/above una HEAD farebbe partire una chiamata vera a N2YO senza restituire niente.
        if urllib.parse.urlsplit(self.path).path == '/api/above':
            return self.fail(405, 'usa GET')
        return self.do_GET()

    def handle_above(self, query):
        # Solo dalla pagina del sito: i browser lo dichiarano con Origin e Sec-Fetch-Site. Chi chiama a
        # mano (curl) può fingere: per questo ci sono anche il limite per IP e il tetto orario.
        origin, fetch_site = self.headers.get('Origin'), self.headers.get('Sec-Fetch-Site')
        if (origin and origin != SITE) or (fetch_site and fetch_site != 'same-origin'):
            return self.fail(403, 'solo dalla pagina del sito')
        if not N2YO_KEY:
            return self.fail(503, 'N2YO non configurato')
        global ip_pruned_at
        now, hits = time.time(), ip_hits[self.client_ip()]
        with n2yo_lock:
            # Una volta al minuto via i visitatori senza richieste nell'ultimo minuto: la tabella
            # non cresce all'infinito e non tiene gli IP più del necessario.
            if now - ip_pruned_at > 60:
                for ip in [ip for ip, d in ip_hits.items() if not d or now - d[-1] > 60]:
                    if ip_hits[ip] is not hits:
                        del ip_hits[ip]
                ip_pruned_at = now
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= PER_IP_PER_MIN:
                return self.fail(429, 'troppe richieste, riprova fra un minuto')
            hits.append(now)
        try:
            lat, lon = float(query['lat'][0]), float(query['lon'][0])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except (KeyError, ValueError):
            return self.fail(400, 'lat e lon non validi')
        self.reply(*above(lat, lon))

    def log_request(self, code='-', size='-'):
        # Senza query string: lì ci sono le coordinate dei visitatori.
        log(f'{self.client_ip()} {self.command} {urllib.parse.urlsplit(self.path).path} {code}')


def main():
    for kind in SOURCES:
        os.makedirs(os.path.join(DATA, kind), exist_ok=True)
    log(f'avvio: dati in {DATA}, N2YO {"configurato" if N2YO_KEY else "NON configurato"}')
    if REFRESH:
        threading.Thread(target=refresher, daemon=True).start()
    ThreadingHTTPServer(('', int(os.environ.get('PORT', '8000'))), Handler).serve_forever()


if __name__ == '__main__':
    main()
