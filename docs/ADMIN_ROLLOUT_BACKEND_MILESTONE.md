# Admin Rollout Backend Milestone

Ultimo aggiornamento: 2026-06-15.

## Punto recuperato

L'admin remoto `http://100.120.132.11:8000/` espone gia:

- inventory e collector flotta;
- canali `manual`, `canary`, `pilot`, `stable`;
- gruppi aggiornamento Docker;
- selezione release e target;
- anteprima rollout;
- installazione SSH sincrona di una singola immagine Docker.

Il pulsante frontend `Conferma ed esegui` non avvia ancora un aggiornamento. Mostra:

```text
Piano rollout pronto. Esecuzione reale da collegare nella prossima milestone backend
```

L'OpenAPI remoto non espone ancora endpoint campagna/rollout. Il primitivo esistente:

```text
POST /api/docker/devices/{device_id}/install
```

gestisce una singola immagine e non rappresenta da solo il deploy Compose PV_GUARDIAN con
backup, healthcheck e rollback. Non deve essere semplicemente eseguito in parallelo su tutta
la flotta.

## Contratto edge pronto

Il deploy edge deve usare:

```text
deployment/docker/deploy-compose-release.sh
```

Parametri minimi per una release:

```sh
PV_EDGE_MANAGER_RELEASE_ID=<id-univoco> \
PV_EDGE_MANAGER_RELEASE_TAG=<tag-ghcr> \
PV_EDGE_MANAGER_RELEASE_VERSION=<versione-app> \
PV_EDGE_MANAGER_RELEASE_COMMIT=<commit> \
PV_EDGE_MANAGER_RELEASE_LABEL=<label> \
sh deployment/docker/deploy-compose-release.sh /tmp/pv-guardian-release.tar
```

`PV_EDGE_MANAGER_RELEASE_TAG` aggiorna in modo persistente entrambe le immagini Compose
backend/web. Se config, login, pull, avvio o healthcheck falliscono, `compose.env` viene
ripristinato; dopo l'avvio fallito viene ripristinata anche la release precedente.

`PV_EDGE_MANAGER_RELEASE_VERSION` aggiorna `identity.app_version`, mostrato anche nel footer.
Per tag semantici che iniziano con `v`, lo script usa automaticamente il tag come versione.

Il backend admin deve verificare dopo il deploy:

- `GET /api/health`;
- `GET /api/system/health`;
- frontend HTTP;
- `identity.build_commit` uguale al commit target;
- `identity.build_label` uguale alla label target;
- `identity.release_tag` uguale al tag target;
- container backend/web healthy;
- porta Modbus TCP slave prevista raggiungibile.

## API backend minima

Endpoint consigliati:

```text
POST /api/rollouts
GET  /api/rollouts
GET  /api/rollouts/{rollout_id}
POST /api/rollouts/{rollout_id}/execute
POST /api/rollouts/{rollout_id}/cancel
POST /api/rollouts/{rollout_id}/retry-failed
```

Creare prima una campagna immutabile con:

- release tag, commit e label;
- gruppo/canale e target risolti;
- ordine dei target;
- concorrenza massima;
- operatore e nota;
- timestamp e audit.

Stati campagna:

```text
draft
pending
running
success
failed
blocked
cancelled
```

Stati target:

```text
pending
preflight
backing_up
running
verifying
success
failed
rolled_back
blocked
cancelled
```

## Flusso per target

1. Verificare che il device sia online e Docker nativo.
2. Verificare SSH, release corrente, servizi, spazio disco e health corrente.
3. Creare backup locale sul device e registrare percorso/permessi nell'audit.
4. Caricare l'archivio release in `/tmp`.
5. Invocare `deploy-compose-release.sh` con tag, commit e label target.
6. Verificare health, build identity, container e porta Modbus.
7. Registrare output sanitizzato, durata ed esito.
8. In caso di errore registrare `failed` o `rolled_back` in base all'esito reale.

Credenziali SSH e GHCR non devono essere salvate nella campagna, restituite al frontend o
registrate nei log. Il worker backend deve usare riferimenti a credenziali server-side.

## Regole rollout

- `canary`: un solo target alla volta; un fallimento blocca la campagna.
- `pilot`: piccoli batch e stop automatico oltre la soglia errori.
- `stable`: disponibile solo dopo canary/pilot riusciti per la stessa release.
- `manual`: richiede selezione esplicita e conferma operatore.
- Nessun auto-update globale e nessuna attivazione automatica Watchtower.
- Retry limitati e idempotenti; mai due rollout contemporanei sullo stesso device.

## Stato operativo rilevato

Verifica del 2026-06-15:

- release candidata edge: `v1.1.0-rc4`, con metadati immutabili, `identity.release_tag` e
  compatibilita con gli alias runtime usati dal Control Center;
- `v1.1.0-rc3` corregge il deploy Compose ma non garantisce build metadata corretti quando
  il rollout SSH conserva vecchie env del container;
- test locali edge: 207 backend passati, compileall passato, frontend build passato,
  compose production/pilot validi;
- tag Git remoti precedenti `v1.1.0-rc2` e `v1.1.0-rc3` presenti;
- manifest GHCR non verificabile dalla workstation senza login privato;
- muletto ufficio/Tailscale `iot2050-foggia2-4gb` (`100.107.10.127`) raggiungibile via API,
  runtime ancora `v1.0.0` / commit `09305feceb40`;
- accesso SSH al muletto non disponibile dalla workstation, quindi backup e preflight
  remoto non ancora eseguiti;
- device campo `100.119.142.49` online ma escluso dal rollout senza backup e finestra.

Watchtower non deve essere usato sul muletto finche il Docker Engine espone API 1.25.
Preferire rollout SSH/Compose con rollback.

Il primo rollout reale resta bloccato finche non vengono eseguiti preflight e backup sul
muletto.
