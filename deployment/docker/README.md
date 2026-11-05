# Docker Pilot

Questa cartella contiene la configurazione Docker/Compose per PV_GUARDIAN Edge.

## Modalita pilot

Sul muletto `192.168.2.116` il pilot deve partire su porte alternative, lasciando attivi servizio legacy e nginx:

```text
legacy web:     80
legacy api:     8000
legacy slave:   15020

docker web:     18080
docker api:     18000
docker slave:   15021
```

File locali pilot:

```text
/etc/pv-edge-manager-pilot/compose.env
/etc/pv-edge-manager-pilot/app.env
/var/lib/pv-edge-manager-pilot/
/var/log/pv-edge-manager-pilot/
/opt/pv-edge-manager-docker-pilot/
```

## Avvio pilot

Da `/opt/pv-edge-manager-docker-pilot`:

```sh
docker compose --env-file /etc/pv-edge-manager-pilot/compose.env up -d --build
docker compose --env-file /etc/pv-edge-manager-pilot/compose.env ps
```

Per usare le immagini pubblicate da GitHub Container Registry invece della build locale:

```sh
cp deployment/docker/pilot-ghcr.compose.env.example /etc/pv-edge-manager-pilot/compose.env
docker compose --env-file /etc/pv-edge-manager-pilot/compose.env pull
docker compose --env-file /etc/pv-edge-manager-pilot/compose.env up -d --no-build
```

Se i package GHCR sono privati, il device deve fare login prima del pull:

```sh
install -m 0600 deployment/docker/ghcr-login.env.example /etc/pv-edge-manager-pilot/registry.env
# compilare /etc/pv-edge-manager-pilot/registry.env con utente GitHub e token read:packages
sh deployment/docker/login-ghcr.sh /etc/pv-edge-manager-pilot/registry.env
```

## Deploy controllato

Lo script `deploy-compose-release.sh` estrae una release, aggiorna il symlink `current`,
scarica le immagini configurate in `compose.env`, avvia lo stack e fa rollback se API o web
non superano l'healthcheck.

Per la gestione dei package privati GHCR sui device vedere `FLEET_AUTH.md`.

```sh
PV_EDGE_MANAGER_BASE_DIR=/opt/pv-edge-manager-docker \
PV_EDGE_MANAGER_ENV_DIR=/etc/pv-edge-manager \
PV_EDGE_MANAGER_RELEASE_TAG=v1.1.0-rc4 \
PV_EDGE_MANAGER_RELEASE_VERSION=v1.1.0-rc4 \
PV_EDGE_MANAGER_RELEASE_COMMIT=8b399a764f71 \
sh deployment/docker/deploy-compose-release.sh /tmp/pv-guardian-release.tar
```

Per default lo script cerca le credenziali GHCR in `$PV_EDGE_MANAGER_ENV_DIR/registry.env`
ed esegue il login prima del pull. Il file non deve essere committato nel repository.

`PV_EDGE_MANAGER_RELEASE_TAG` aggiorna entrambe le immagini backend/web configurate nel
`compose.env`. Se config, login, pull o healthcheck falliscono, il file viene ripristinato.

`PV_EDGE_MANAGER_RELEASE_VERSION` aggiorna il valore mostrato nel footer e in
`/api/system/health`. Se non viene impostato e il tag immagine inizia con `v`, lo script usa
automaticamente il tag come versione.

Le immagini recenti includono inoltre metadati build immutabili. `/api/system/health`
preferisce questi valori per `build_label`, `build_commit` e `build_time`, evitando che una
ricreazione SSH che conserva vecchie env mostri una build precedente.

Il valore `PV_EDGE_MANAGER_RELEASE_COMMIT` viene riportato in `/api/system/health`,
insieme al timestamp del deploy. Se non viene passato, lo script usa il nome archivio
come identificativo release.

## Installazione Docker statica

Per dispositivi con APT non affidabile si puo installare Docker dai binari statici ufficiali.
Scaricare `docker-29.5.2.tgz` e `docker-compose-linux-aarch64`, copiarli sul device e lanciare:

```sh
sh deployment/docker/install-static-docker.sh /percorso/pacchetti
```

Verifiche:

```text
http://DEVICE:18080/
http://DEVICE:18000/api/health
http://DEVICE:18000/api/system/health
```

## LAN Config in Docker

La dashboard puo modificare le interfacce LAN anche con app in Docker se l'host espone
NetworkManager al backend container:

- l'host deve avere NetworkManager attivo e le LAN reali gestite da `nmcli`;
- l'immagine backend include `nmcli`;
- il Compose monta `/run/dbus` dell'host nel backend, cosi `nmcli` parla con
  NetworkManager host via D-Bus;
- se NetworkManager non e raggiungibile, `/api/system/network-config` degrada in sola
  lettura e mostra un messaggio operativo invece di fallire.

Verifica sul device:

```sh
systemctl is-active NetworkManager || systemctl is-active network-manager
docker exec pv-guardian-backend nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status
curl -fsS http://127.0.0.1:8000/api/system/network-config
```

La modifica resta protetta dal rollback automatico: dopo `Applica configurazione`,
l'operatore deve confermare entro 30 secondi dalla dashboard.

La dashboard salva inoltre il ruolo stabile di ogni interfaccia, preferendo il MAC address
come chiave:

```text
/var/lib/pv-edge-manager/network_interface_roles.json
```

Ruoli previsti:

- `cci`: LAN dedicata al CCI, vincolata a `10.56.69.100/24` senza gateway;
- `internet_inverter`: LAN con gateway dell'impianto e, se serve, secondo IP per rete inverter.

Il ruolo evita che la UI scambi LAN 1/LAN 2 se l'ordine delle interfacce cambia.

## Switch produzione

Il muletto ufficio `192.168.2.116` e stato validato in Docker production su porte reali.
Per altri device, usare comunque finestra di intervento, backup e rollback:

1. stop servizio legacy `pv-edge-manager-backend`;
2. stop nginx legacy;
3. compose production su porte `80`, `8000`, `15020`;
4. healthcheck;
5. rollback immediato se fallisce.
