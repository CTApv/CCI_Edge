# GHCR private fleet access

PV_GUARDIAN usa GitHub Container Registry con package privati. Ogni device deve avere
credenziali locali con permesso minimo di sola lettura.

## Token GitHub

Creare un Personal Access Token classic dedicato al deploy dei device con scope:

```text
read:packages
```

Il token non deve avere `write:packages` o accesso al repository se non serve ad altri flussi.
Riferimenti GitHub: working with Container registry e package access control.

```text
https://docs.github.com/packages/working-with-a-github-packages-registry/working-with-the-container-registry
https://docs.github.com/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility
```

## File sul device

Sul device creare il file:

```sh
install -d -m 0750 /etc/pv-edge-manager
install -m 0600 deployment/docker/ghcr-login.env.example /etc/pv-edge-manager/registry.env
```

Compilarlo cosi:

```text
PV_EDGE_MANAGER_GHCR_USERNAME=utente-github
PV_EDGE_MANAGER_GHCR_TOKEN=token-read-packages
```

Per il muletto/pilot usare invece:

```sh
install -d -m 0750 /etc/pv-edge-manager-pilot
install -m 0600 deployment/docker/ghcr-login.env.example /etc/pv-edge-manager-pilot/registry.env
```

## Verifica manuale

```sh
sh deployment/docker/login-ghcr.sh /etc/pv-edge-manager/registry.env
docker pull ghcr.io/ctapv/pv-guardian-edge-backend:v1.0.0
docker pull ghcr.io/ctapv/pv-guardian-edge-web:v1.0.0
```

## Deploy

`deploy-compose-release.sh` cerca automaticamente il file `registry.env` dentro
`$PV_EDGE_MANAGER_ENV_DIR` ed esegue `docker login ghcr.io` prima del pull.

Il token non deve mai essere salvato nel repository, negli artifact o nei log di deploy.
