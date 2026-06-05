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
PV_EDGE_MANAGER_RELEASE_COMMIT=8b399a764f71 \
sh deployment/docker/deploy-compose-release.sh /tmp/pv-guardian-release.tar
```

Per default lo script cerca le credenziali GHCR in `$PV_EDGE_MANAGER_ENV_DIR/registry.env`
ed esegue il login prima del pull. Il file non deve essere committato nel repository.

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

## Switch produzione

Il muletto ufficio `192.168.2.116` e stato validato in Docker production su porte reali.
Per altri device, usare comunque finestra di intervento, backup e rollback:

1. stop servizio legacy `pv-edge-manager-backend`;
2. stop nginx legacy;
3. compose production su porte `80`, `8000`, `15020`;
4. healthcheck;
5. rollback immediato se fallisce.
