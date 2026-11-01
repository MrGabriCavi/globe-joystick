# Globe Joystick

Una cloche da caccia che fa ruotare un globo 3D con i satelliti veri sopra: orbite a
puntini, schedina con le informazioni e l'elenco di quelli sopra la tua testa. Online su
<https://globe-stick.mrgabri.it>.

La pagina è un unico file `index.html`, nessun build. Sul sito pubblico i dati passano da una
piccola API Python ([api/server.py](api/server.py)); aperta in locale, la pagina li chiede
direttamente a CelesTrak. Librerie e texture arrivano da internet, quindi serve la connessione;
offline il globo mostra una griglia.

## Aprirla

- **Online, anche dal telefono:** <https://globe-stick.mrgabri.it>.
- **In locale, per le prove:** doppio clic su `index.html`. Senza l'API la pagina chiede i dati
  direttamente a CelesTrak: va bene ogni tanto, non a raffica (CelesTrak blocca l'IP).

## Comandi

| Comando | Effetto |
|---|---|
| Leva (mouse o dito) | sinistra/destra fa girare il globo sull'asse, alto/basso lo inclina; più spingi, più va veloce. Lasciata, torna al centro |
| Frecce / WASD | come la leva |
| Rotella / pinch | zoom |
| Pulsante rosso, `R` | torna su Roma |
| Pulsante giallo, `M` | modalità **VOLA** (su = nord, destra = est) o **RUOTA** (muovi il globo come con la mano) |
| Menu in alto a sinistra | gruppo di satelliti: più luminosi, stazioni, meteo, GPS, Galileo, geostazionari, Starlink |
| ◎ SOPRA DI ME | chiede la posizione e mostra i satelliti del gruppo più alti di 10° sul tuo orizzonte (anelli azzurri ed elenco). Sul sito pubblico aggiunge, da N2YO, *tutti* gli oggetti sopra di te, di qualunque gruppo (icone piccole ed elenco; stadi di razzo e detriti raggruppati in cluster che si aprono con lo zoom, tocca un cluster per avvicinarti). Se il browser non dà la posizione precisa si può usare quella approssimativa dalla rete |
| Interruttore MASTER ARM nel pannello | in sicurezza (sportellino chiuso) si vedono solo satelliti e stazioni spaziali; armato compaiono anche stadi di razzo e detriti, nei gruppi e in SOPRA DI ME. La scelta resta nel browser |
| ✦ VAI A ISS, `I` | porta il globo sopra la Stazione spaziale internazionale e apre la sua schedina; se il gruppo scelto non la contiene passa a «Stazioni spaziali» |
| IL PIÙ VELOCE / LENTO / LONTANO / VICINO | porta il globo sul satellite del gruppo scelto più veloce, più lento, più lontano o più vicino alla Terra e apre la sua schedina |
| Bandierina nel pannello comandi | passa dall'italiano all'inglese e viceversa; la prima volta la pagina segue la lingua del browser |
| Clic / tocco su un satellite | apre la schedina (con `Esc` o ✕ si chiude); CENTRA porta il globo sopra il satellite |

## Attracco alla ISS

Nella schedina della ISS (✦ VAI A ISS) il pulsante **PROVA L'ATTRACCO** apre [dock.html](dock.html): un
minigioco in cui la stazione gira attorno all'asse del portello e bisogna agganciarsi.

- **ROLL** (↺ ↻, `Q` `E`): fai ruotare la navetta alla stessa velocità della stazione. Quando sei
  sincronizzato la ISS sembra ferma e sono Terra e stelle a girare.
- **Cloche** (frecce): spostamenti laterali, nel riferimento della navetta: se la navetta gira, girano
  anche le direzioni.
- **Leva di spinta**, a sinistra nel pannello (`G` gas / `F` freno, oppure `W` `S`): avanti e indietro.
  Torna al centro quando la lasci.
- **Cruscotto** sopra i comandi: strumenti a lancetta per distanza, velocità di avvicinamento,
  differenza di rotazione e di rollio e carburante (in verde i valori buoni per l'aggancio), uno schermo
  a fosfori con lo scostamento dal centro e le spie SYNC, CENTRO, VELOCITÀ e RCS.
- **Regolazioni sul pannello:** sensibilità (0,25–2×), movimento **ASSIST** (gli smorzatori fermano da
  soli gli spostamenti laterali e tengono l'avanzamento sotto 2 m/s; il rollio no) o **MANUAL** (inerzia pura), asse Y normale o
  invertito. Restano nel browser.
- **Livelli:** stazione ferma, 8°/s, 25°/s e «in avaria» a 60°/s.
- **Aggancio riuscito** se al contatto sei entro 25 cm dal centro, sotto 0,35 m/s, con rollio entro 5° e
  rotazione entro 3°/s. Il carburante dei propulsori (RCS) è limitato.

## Satelliti

- **Orbite:** elementi orbitali in formato OMM (JSON) da [CelesTrak](https://celestrak.org). Non TLE: le
  righe TLE non hanno posto per i numeri NORAD oltre 99999, già usati dai lanci recenti, e CelesTrak quei
  satelliti in TLE non li pubblica. Le posizioni sono calcolate nel browser con SGP4
  ([satellite.js](https://github.com/shashwatak/satellite-js)).
- **Aggiornamento:** per i gruppi fino a 2000 satelliti (`LIVE_MAX`) le posizioni si ricalcolano **ogni
  secondo** (accanto al menu: IN DIRETTA); per quelli più grandi, come Starlink, ogni **10 minuti**
  (`POSITION_REFRESH_MS`), con il conto alla rovescia. Le orbite a puntini si ricalcolano ogni 10 minuti e
  intanto girano con la Terra. Gli elementi orbitali la pagina li riscarica al massimo ogni **2 ore**
  (`GP_MAX_AGE_MS`) e li tiene in cache nel browser.
- **Copia sul sito:** CelesTrak aggiorna gli elementi ogni 2 ore e risponde 403 a un IP che riscarica un
  gruppo prima dell'aggiornamento; un'altra persona dietro lo stesso IP (stessa rete di casa, operatore
  mobile) resterebbe senza dati. Per questo sul sito pubblico scarica solo l'API, una volta per gruppo
  ogni 2 ore (il catalogo SATCAT una volta al giorno), e i visitatori leggono da `/api/gp/<gruppo>` e
  `/api/satcat/<gruppo>`. I file restano in un volume, quindi un nuovo deploy non riscarica niente.
- **Tutti gli oggetti sopra di te:** `/api/above` chiede a [N2YO](https://www.n2yo.com/api/) ("What's up?")
  con la chiave dell'API, che resta sul server. N2YO concede 100 chiamate all'ora: l'API tiene le risposte
  in memoria per 2 minuti per punto (arrotondato a mezzo grado), si ferma a 90 chiamate all'ora, accetta
  6 richieste al minuto per visitatore e solo dalla pagina del sito.
- **Orbite a puntini:** per tutti i satelliti del gruppo se sono al massimo 300, altrimenti (es. Starlink,
  geostazionari) solo per quello selezionato, in verde.
- **Schedina:** quota, velocità, posizione, inclinazione, periodo, apogeo/perigeo ed età dei dati (calcolati);
  tipo, stato, proprietario, lancio e base dal catalogo SATCAT di CelesTrak; descrizione, foto e link da
  Wikidata, quando la voce esiste.

Tutto quello che deve girare con la Terra sta in `earthPivot`, i satelliti in `satellitesLayer`.
Dalla console del browser: `globeApp.addMarker(0, -30, { altKm: 420 })`, `globeApp.sats`.

## Pubblicazione

Sulla VPS, con Docker Swarm dietro Traefik: si pubblica creando un tag di versione `vX.Y.Z` su GitHub.
Il webhook mette il repo in coda e `~/stacks/deploy/deploy.sh` costruisce le immagini
(`Dockerfile` → `globe-joystick`, `api/Dockerfile` → `globe-joystick-api`) e aggiorna lo stack
[deploy/stack.yml](deploy/stack.yml): nginx con la pagina e l'API su `/api/`.

Prima del primo deploy serve il segreto Docker con la chiave di N2YO. Sulla VPS (la chiave si digita
senza che compaia e non resta nella cronologia):

```bash
read -rs N2YO && printf %s "$N2YO" | docker secret create globe_n2yo_api_key - && unset N2YO
```

Se N2YO non risponde, o la chiave non è valida, il resto funziona: manca solo l'elenco di tutti gli oggetti.

## Crediti

Nessuna di queste risorse è inclusa nel repository: la pagina le carica mentre gira.

| Risorsa | Fonte | Licenza / condizioni |
|---|---|---|
| Motore 3D | [three.js](https://threejs.org) | MIT |
| Calcolo delle orbite (SGP4) | [satellite.js](https://github.com/shashwatak/satellite-js) | MIT |
| Immagine della Terra, rilievo, mari | [NASA Blue Marble](https://visibleearth.nasa.gov/collection/1484/blue-marble), via [three-globe](https://github.com/vasturiano/three-globe) | Pubblico dominio (NASA); pacchetto MIT |
| Elementi orbitali e catalogo SATCAT | [CelesTrak](https://celestrak.org) | Uso gratuito; non scaricare lo stesso gruppo più di una volta ogni 2 ore |
| Oggetti sopra un punto | [N2YO](https://www.n2yo.com) | API con chiave personale, 100 chiamate all'ora |
| Descrizioni e collegamenti | [Wikidata](https://www.wikidata.org) | CC0 |
| Foto dei satelliti | [Wikimedia Commons](https://commons.wikimedia.org) | Licenza propria per ogni file: autore e licenza dal link sotto la foto |
| Posizione approssimativa (facoltativa) | [GeoJS](https://www.geojs.io) | Usata solo se la scegli tu nella schedina |
| Carattere | [Press Start 2P](https://fonts.google.com/specimen/Press+Start+2P), via Google Fonts | SIL Open Font License |

## Licenza

[MIT](LICENSE) © 2026 MrGabri
