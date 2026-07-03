# PV_GUARDIAN Deploy Runbook

Questo runbook descrive il flusso Docker edge validato sul muletto `192.168.2.116`.

## Percorsi target Docker

```text
/opt/pv-edge-manager-docker/
/etc/pv-edge-manager/
/var/lib/pv-edge-manager/
/var/log/pv-edge-manager/
```

File principali:

```text
/etc/pv-edge-manager/compose.env
/etc/pv-edge-manager/app.env
/etc/pv-edge-manager/registry.env
/opt/pv-edge-manager-docker/current
```

## Stato production atteso

```sh
systemctl is-active docker.service
systemctl is-enabled docker.service
systemctl is-active pv-edge-manager-backend.service nginx || true
systemctl is-enabled pv-edge-manager-backend.service nginx || true
cd /opt/pv-edge-manager-docker/current
docker compose --env-file /etc/pv-edge-manager/compose.env ps
```

Atteso:

- Docker `active` + `enabled`.
- Legacy backend/nginx `inactive` + `disabled`.
- `pv-guardian-backend` healthy.
- `pv-guardian-web` healthy.
- porte `80`, `8000`, `15020` esposte da Docker.

## Verifiche rapide

```sh
curl -fsS http://127.0.0.1:8000/api/health
curl -fsSI http://127.0.0.1/ | grep -i 'X-PV-Guardian-Frontend: docker'
curl -fsS http://127.0.0.1:8000/api/system/health | python3 -m json.tool | sed -n '1,30p'
ss -ltnp | grep -E ':80|:8000|:15020'
```

Da PC:

```powershell
Invoke-WebRequest -UseBasicParsing http://192.168.2.116/
Invoke-WebRequest -UseBasicParsing http://192.168.2.116:8000/api/health
Test-NetConnection 192.168.2.116 -Port 15020
```

## Aggiornamento controllato

Creare un tar del commit corrente:

```powershell
$commit = (git rev-parse --short=12 HEAD).Trim()
git archive --format=tar -o "tmp-pv-guardian-release-$commit.tar" HEAD
```

Caricare sul device e lanciare:

```sh
PV_EDGE_MANAGER_BASE_DIR=/opt/pv-edge-manager-docker \
PV_EDGE_MANAGER_ENV_DIR=/etc/pv-edge-manager \
PV_EDGE_MANAGER_RELEASE_ID=<commit> \
PV_EDGE_MANAGER_RELEASE_TAG=v1.1.0-rc4 \
PV_EDGE_MANAGER_RELEASE_VERSION=v1.1.0-rc4 \
PV_EDGE_MANAGER_RELEASE_COMMIT=<commit> \
PV_EDGE_MANAGER_RELEASE_LABEL=v1.1.0-rc4-docker-production \
sh /path/to/release/deployment/docker/deploy-compose-release.sh /tmp/pv-guardian-release.tar
```

Lo script:

1. estrae la release;
2. se indicato, applica `PV_EDGE_MANAGER_RELEASE_TAG` alle immagini backend/web;
3. aggiorna `PV_EDGE_MANAGER_VERSION` usando `PV_EDGE_MANAGER_RELEASE_VERSION`;
4. valida compose;
5. fa login GHCR da `registry.env`;
6. esegue pull immagini;
7. avvia/recrea container;
8. verifica API e web;
9. ripristina `compose.env` e release precedente se il deploy fallisce.

Non omettere `PV_EDGE_MANAGER_RELEASE_TAG` quando la release deve cambiare le immagini
attive. L'archivio aggiorna gli script e il file Compose, ma senza tag esplicito il device
continua a usare le immagini gia configurate in `/etc/pv-edge-manager/compose.env`.

Per tag semantici che iniziano con `v`, lo script usa automaticamente
`PV_EDGE_MANAGER_RELEASE_TAG` anche come versione applicativa. Per tag mobili come
`docker-pilot` o `sha-*`, passare esplicitamente `PV_EDGE_MANAGER_RELEASE_VERSION`.

`/api/system/health` espone anche `identity.release_tag`. Nelle immagini recenti,
`build_label`, `build_commit` e `build_time` provengono dai metadati immutabili inclusi
nell'immagine, quindi non vengono falsati da vecchie variabili preservate durante una
ricreazione container via SSH.

## Rollback manuale muletto

Sul muletto validato:

```sh
sh /root/pv-guardian-production-rollback-20260605-121318.sh
```

Questo spegne lo stack Docker production e riavvia legacy backend/nginx.
Usarlo solo se serve tornare alla situazione pre-Docker del muletto.

## Provisioning nuovi device

I nuovi device non devono partire da legacy. Flusso previsto:

1. installare Docker statico;
2. verificare NetworkManager attivo sull'host per abilitare LAN Config da dashboard;
3. creare `/etc/pv-edge-manager`, `/var/lib/pv-edge-manager`, `/var/log/pv-edge-manager`;
4. creare `registry.env` locale con token `read:packages`;
5. creare `compose.env` production;
6. creare `app.env`;
7. deploy da GHCR;
8. verificare health/API/web/porta `15020` e `/api/system/network-config`;
9. assegnare dalla dashboard i ruoli LAN `cci` e `internet_inverter`;
10. registrare Edge ID, MAC LAN e IP Tailscale nell'admin.

I ruoli LAN sono persistiti nel data dir, di default:

```text
/var/lib/pv-edge-manager/network_interface_roles.json
```

Regola commissioning:

- ruolo `cci`: IP statico `10.56.69.100/24`, nessun gateway/default route;
- ruolo `internet_inverter`: gateway dell'impianto, DNS e fino a due IP sulla LAN internet/inverter.

Script da creare come prossimo lavoro:

```text
deployment/docker/provision-new-device.sh
```

## Watchtower

Watchtower e previsto ma non attivo di default.

Regole:

- installabile durante provisioning;
- nessun aggiornamento automatico globale;
- non considerarlo affidabile sui device con Docker API 1.25;
- usare in futuro solo con label o canali controllati;
- rollout iniziale manuale via admin/script;
- canali previsti: `canary`, `pilot`, `stable`, `manual`.

Per il contratto della prossima milestone backend admin vedere:

```text
docs/ADMIN_ROLLOUT_BACKEND_MILESTONE.md
```
