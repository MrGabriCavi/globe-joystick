# Globe Joystick

Un joystick da cabinato anni '80 che fa ruotare un globo 3D con i satelliti veri sopra:
orbite a puntini, schedina con le informazioni e l'elenco di quelli sopra la tua testa.
Solo frontend, un unico file `index.html`, nessun build. Librerie, texture e dati arrivano
da internet, quindi serve la connessione; offline il globo mostra una griglia.

## Aprirla

- **Dal PC:** doppio clic su `index.html`.
- **Dal telefono:** avvia il server locale e apri dal telefono l'indirizzo che stampa
  (stessa rete Wi-Fi). Il server mostra in rete solo `index.html`:

  ```powershell
  powershell -ExecutionPolicy Bypass -File .\avvia-server.ps1
  ```

## Comandi

| Comando | Effetto |
|---|---|
| Leva (mouse o dito) | sinistra/destra fa girare il globo sull'asse, alto/basso lo inclina; più spingi, più va veloce. Lasciata, torna al centro |
| Frecce / WASD | come la leva |
| Rotella / pinch | zoom |
| Pulsante rosso, `R` | torna su Roma |
| Pulsante giallo, `M` | modalità **VOLA** (su = nord, destra = est) o **RUOTA** (muovi il globo come con la mano) |
| Menu in alto a sinistra | gruppo di satelliti: più luminosi, stazioni, meteo, GPS, Galileo, geostazionari, Starlink |
| ◎ SOPRA DI ME | chiede la posizione e mostra i satelliti del gruppo più alti di 10° sul tuo orizzonte (anelli azzurri ed elenco). La posizione precisa il browser la dà solo al file aperto dal PC o a pagine https: dal telefono via `avvia-server.ps1` (http) si può usare quella approssimativa dalla rete |
| Clic / tocco su un satellite | apre la schedina (con `Esc` o ✕ si chiude); CENTRA porta il globo sopra il satellite |

## Satelliti

- **Orbite:** elementi orbitali in formato OMM (JSON) da [CelesTrak](https://celestrak.org). Non TLE: le
  righe TLE non hanno posto per i numeri NORAD oltre 99999, già usati dai lanci recenti, e CelesTrak quei
  satelliti in TLE non li pubblica. Le posizioni sono calcolate nel browser con SGP4
  ([satellite.js](https://github.com/shashwatak/satellite-js)).
- **Aggiornamento:** per i gruppi fino a 2000 satelliti (`LIVE_MAX`) le posizioni si ricalcolano **ogni
  secondo** (accanto al menu: IN DIRETTA); per quelli più grandi, come Starlink, ogni **10 minuti**
  (`POSITION_REFRESH_MS`), con il conto alla rovescia. Le orbite a puntini si ricalcolano ogni 10 minuti e
  intanto girano con la Terra. Gli elementi orbitali si riscaricano al massimo ogni **2 ore**
  (`GP_MAX_AGE_MS`) e restano in cache nel browser: CelesTrak li aggiorna con quel ritmo e blocca chi scarica
  lo stesso gruppo più spesso.
- **Orbite a puntini:** per tutti i satelliti del gruppo se sono al massimo 300, altrimenti (es. Starlink,
  geostazionari) solo per quello selezionato, in verde.
- **Schedina:** quota, velocità, posizione, inclinazione, periodo, apogeo/perigeo ed età dei dati (calcolati);
  tipo, stato, proprietario, lancio e base dal catalogo SATCAT di CelesTrak; descrizione, foto e link da
  Wikidata, quando la voce esiste.

Tutto quello che deve girare con la Terra sta in `earthPivot`, i satelliti in `satellitesLayer`.
Dalla console del browser: `globeApp.addMarker(0, -30, { altKm: 420 })`, `globeApp.sats`.

## Crediti

Nessuna di queste risorse è inclusa nel repository: la pagina le carica mentre gira.

| Risorsa | Fonte | Licenza / condizioni |
|---|---|---|
| Motore 3D | [three.js](https://threejs.org) | MIT |
| Calcolo delle orbite (SGP4) | [satellite.js](https://github.com/shashwatak/satellite-js) | MIT |
| Immagine della Terra, rilievo, mari | [NASA Blue Marble](https://visibleearth.nasa.gov/collection/1484/blue-marble), via [three-globe](https://github.com/vasturiano/three-globe) | Pubblico dominio (NASA); pacchetto MIT |
| Elementi orbitali e catalogo SATCAT | [CelesTrak](https://celestrak.org) | Uso gratuito; non scaricare lo stesso gruppo più di una volta ogni 2 ore |
| Descrizioni e collegamenti | [Wikidata](https://www.wikidata.org) | CC0 |
| Foto dei satelliti | [Wikimedia Commons](https://commons.wikimedia.org) | Licenza propria per ogni file: autore e licenza dal link sotto la foto |
| Posizione approssimativa (facoltativa) | [GeoJS](https://www.geojs.io) | Usata solo se la scegli tu nella schedina |
| Carattere | [Press Start 2P](https://fonts.google.com/specimen/Press+Start+2P), via Google Fonts | SIL Open Font License |

## Licenza

[MIT](LICENSE) © 2026 MrGabri
