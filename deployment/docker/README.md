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

Verifiche:

```text
http://DEVICE:18080/
http://DEVICE:18000/api/health
http://DEVICE:18000/api/system/health
```

## Switch produzione

Lo switch produzione non viene fatto in questa fase. Quando il pilot sara validato:

1. stop servizio legacy `pv-edge-manager-backend`;
2. stop nginx legacy;
3. compose production su porte `80`, `8000`, `15020`;
4. healthcheck;
5. rollback immediato se fallisce.
