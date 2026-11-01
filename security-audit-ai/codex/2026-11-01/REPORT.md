# Codex review — 2026-11-01 (Europe/Rome)

## Scope and method

Reviewed all 12 initially present project files outside `.git` and `security-audit-ai`, including all three HTML pages, API source, container definitions, deployment configuration, documentation, license and dotfiles. Seven additional JPEG screenshots appeared in `docs/img` during the review and were each visually inspected; they were not created or modified by this audit. Git internals are repository metadata, not application source. The working tree was clean at initial inspection. `security-audit-ai` did not exist at initial inspection: there were no existing audit findings or directory conventions to verify. No pre-existing audit content was read. This report uses `security-audit-ai/codex/2026-11-01/` as requested.

No tests, test dependencies, package manifests or test framework configuration existed. Added Python standard-library `unittest`, matching the API's dependency-free implementation, without installing dependencies or changing production behavior.

Python 3.12.10: 12 contract tests passed. All network operations in tests are mocked; no public services, production endpoints, deployment or real secrets were used. Handler tests invoke production handler methods with in-memory response streams; they do not exercise socket parsing, proxies or TLS. The separate reproduction script verifies defects against the actual API module and is deliberately not part of the passing contract suite.

Frontend findings below are verified by source control flow, not browser execution. Node has no active version configured, so JavaScript execution/syntax checks were unavailable. Docker images, upstream dependency vulnerabilities and the external Traefik/Cloudflare configuration were not assessed at runtime. No claim of a complete security certification is made.

## Important missing coverage added

`tests/test_api.py` covers the important case where an already cached N2YO response must remain available even after the hourly upstream quota is exhausted. The same test checks that an uncached location is denied without an upstream call. Additional focused tests cover nearby-point cache reuse and rounded upstream coordinates, exact TTL expiry, hourly expiry, failed upstream calls, invalid/nonfinite coordinates, valid geographic extremes, cross-origin rejection, per-IP limit and recovery, HEAD body suppression, group allowlisting and file-cache gzip round trips.

Run from repository root:

```powershell
python -B -m unittest discover -s tests -v
python -B security-audit-ai/codex/2026-11-01/reproduce.py
```

`test-results.txt` stores the actual test output; `reproduction-results.json` stores the offline defect evidence. `inventory.json` records source file hashes and sizes for reproducibility.

## Findings

### F1 — Medium: location sent to site at higher precision than disclosed

`index.html`, `loadAllAbove()` (around line 1745), sends `o.lat.toFixed(3)` and `o.lon.toFixed(3)` in the request URL. `about.html` states in both languages that coordinates are rounded to half a degree before being sent to the site's server. Actual transmission is approximately 0.001 degrees (about 111 m latitude), not 0.5 degrees. The API subsequently rounds before sending to N2YO, so the disclosure concerning N2YO precision is consistent, but the first hop is not. Upstream proxies may log query strings; their actual logging configuration is outside this repository and is unverified. The Python request logger does strip query strings.

Recommendation: round to the shared half-degree grid before constructing the browser request, and ensure infrastructure logging agrees with the privacy description. Evidence is direct source comparison; no visitor coordinates were collected.

### F2 — Medium: concurrent cache misses duplicate upstream calls

`api/server.py`, `above()`: the lock protects lookup and quota reservation, but is released before fetching. Two requests for the same rounded point before either finishes each reserve quota and call N2YO. Ordinary concurrent visitors can exhaust the shared quota faster than intended. The hourly cap itself remains protected by the lock; this is not a bypass of that cap.

Offline deterministic reproduction uses a two-party barrier in the mocked upstream call. Both requests return 200 and two upstream calls occur for one point. Recommendation: coalesce in-flight requests per cache key, without holding the global lock across network I/O. Preserve quota accounting for distinct keys and failures.

### F3 — Medium: expired per-IP entries never leave memory

`api/server.py`, `ip_hits` and `Handler.handle_above()`: a deque is allocated for each new client identifier. Old timestamps are trimmed only when that same identifier requests again; dictionary keys are never removed. Long-running instances accumulate unique visitors indefinitely. This also retains identifiers beyond the rate-limit window. If forwarding headers are untrusted, spoofed identifiers could accelerate growth, but actual proxy sanitization is not established here.

Recommendation: periodically remove expired keys under synchronization and bound the table. Verify trusted-proxy behavior separately. Source-confirmed; no memory exhaustion test was performed.

### F4 — Low: malformed upstream JSON can terminate a request without JSON error response

`api/server.py`, `above()`: JSON parsing is caught, but schema access after the try block is not. A valid JSON `null` causes `TypeError` at `'error' in j`; other unexpected structures can cause attribute errors. The handler thread fails instead of returning the intended 502 JSON response. This requires an unexpected upstream payload; an unauthenticated client cannot directly supply this payload through the API.

Offline reproduction confirms the uncaught TypeError. Recommendation: validate a mapping response, `info` structure and `above` list before use, and return sanitized 502 on invalid schema.

### F5 — Low: HEAD requests consume upstream quota on cache misses

`api/server.py`, `Handler.do_HEAD = do_GET`: a HEAD request to `/api/above` executes the full upstream lookup and consumes both visitor and shared quotas, although the body is suppressed. A monitor or crawler could spend quota without retrieving data. Existing quotas still apply, so this is not a quota bypass or a stronger attack primitive than GET.

Offline reproduction confirms one upstream call and zero response body bytes. Recommendation: explicitly define HEAD behavior for this endpoint, preferably without initiating new upstream requests.

### F6 — Medium functional: obsolete group request errors affect the current group

`index.html`, `loadGroup()` (around line 1222): success checks `sats.group`, but catch sets `sats.error` unconditionally. Scenario: start group A, switch to B, B succeeds, then A fails. B is displayed with an unavailable-data error. A-to-B-to-A also permits an older successful A response because group equality is not a unique request token.

Recommendation: use a monotonically increasing request generation for both success and error paths. This confirms the earlier chat finding against the current source; not dynamically reproduced.

### F7 — Low functional: delayed geolocation overrides subsequent navigation

`index.html`, the `btnOverhead` listener and approximate-location listener: resolving geolocation calls `setObserver()` unconditionally. That moves the camera and reopens the overhead card after the user has closed it or selected a satellite. Rejecting geolocation also reopens an error card.

Recommendation: invalidate pending UI requests when navigation or card state changes; optionally save the observer without forcing navigation. Earlier chat finding remains present by source inspection.

### F8 — Low functional: orbital refresh can strand details in loading state

`index.html`, `tick()` replaces the selected satellite object after a GP download, while `loadDetails()` rejects results when `sats.selected !== s`. If the details request was pending, its result is discarded and no request is restarted for the replacement object. The catalog can remain loading until reopened. Already-loaded details are unaffected by this specific sequence.

Recommendation: reload details for the replacement selection or use a request generation and stable NORAD identity. Earlier chat finding remains present by source inspection.

## File-by-file disposition

| File | Review outcome |
| --- | --- |
| `index.html` | Reviewed markup, CSS, translations, graphics, controls, propagation, selection, requests, cache and observers. Findings F1, F6–F8. Other observations: repeated overhead requests have no response-generation guard; fallback to CelesTrak also happens on public-site API failure, not only local-file use. These were not dynamically tested. External text generally reaches `textContent`; `innerHTML` uses authored translations/flags. No demonstrated external-text XSS found. |
| `dock.html` | Reviewed all markup, styles, translations, controls, physics, drawing and results. No demonstrated injection path: query telemetry is formatted numerically into `textContent`, and result HTML uses internal labels/numbers. Persisted settings lack type/range validation, which can break a locally corrupted profile; not identified as a remote security issue. No browser/gameplay verification. |
| `about.html` | Reviewed both language variants, links and language script. F1 privacy discrepancy. Dynamic translations are assigned through `textContent`. |
| `api/server.py` | Reviewed every function, shared state, request routing, logging, download and caching. Findings F2–F5; contract tests exercise cache/quota/input behavior. Allowlists constrain served file paths and upstream group URLs; no demonstrated path traversal or client-directed SSRF found. Origin metadata is explicitly documented as spoofable and is not authentication. |
| `api/Dockerfile` | Runs as nobody, secret is outside image, data volume owned by nobody. Base tag is mutable; no image vulnerability scan performed. |
| `Dockerfile` | Copies only the three public pages; does not publish repository or API source. Base tag is mutable. No runtime nginx validation. |
| `deploy/stack.yml` | Reviewed routing, replica count, stop-first API updates, secret and volume wiring. API shares an external Traefik network; no host ports are published. Trust in forwarding headers depends on external proxy/network configuration. No resource limits or health checks defined. No deployment performed. |
| `.dockerignore` | Allowlist includes only public HTML pages for the root build context. Separate API context is unaffected. |
| `.gitignore` | Reviewed full contents; no test framework exclusions. Does not ignore Python bytecode; checks use `-B` to avoid generating it. |
| `.gitattributes` | Reviewed LF normalization for deployment files. No executable behavior. |
| `README.md` | Reviewed all instructions and behavior claims. Cache/rate limits match constants except ordinary rounded-grid cache reuse is not guaranteed under concurrent misses (F2). Offline fallback grid requires CDN libraries to have loaded; fully cold offline operation is not guaranteed. |
| `LICENSE` | Reviewed complete MIT notice; no executable content. Third-party licensing statements were not legally audited. |
| `docs/img/globo.jpg` | Visually inspected desktop globe screenshot; no executable source. |
| `docs/img/iss.jpg` | Visually inspected ISS card screenshot; no executable source. |
| `docs/img/sopra-di-me.jpg` | Visually inspected overhead/cluster screenshot; displays location information, so review intended publication of the screenshot. No coordinates are copied into audit evidence. |
| `docs/img/telefono.jpg` | Visually inspected mobile globe screenshot; no executable source. |
| `docs/img/attracco.jpg` | Visually inspected desktop docking screenshot; no executable source. |
| `docs/img/attracco-inizio.jpg` | Visually inspected docking start screen; no executable source. |
| `docs/img/attracco-telefono.jpg` | Visually inspected mobile docking screenshot; no executable source. Image metadata and embedded payload forensics were not performed on these JPEGs. |

## Changes and remaining work

Added only tests and this dated audit directory. Production code is unchanged. Findings are not fixed by passing tests: the test suite checks existing working contracts; the reproduction script separately documents three current defects. Frontend regression tests and fixes remain future work. No installed test framework was available to reuse, and none was represented as pre-existing.
