# Codex Handoff

Ultimo aggiornamento: 2026-06-15.

## Obiettivo

PV_GUARDIAN deve diventare un ecosistema gestibile a flotta:

- edge device IOT2050 con app Docker nativa;
- immagini private su GHCR;
- provisioning standard per nuovi device;
- admin centrale per inventario, health, potenza totale, provisioning e rollout;
- aggiornamenti controllati per gruppi, con Watchtower predisposto ma non attivo di default.

## Stato repository

- Repo: `CTApv/CCI_Edge`
- Branch attiva: `docker-pilot`
- Commit validato sul muletto: `09305feceb40`
- Baseline legacy taggata: `v1.0.0-systemd`
- Versione app: `v1.0.0`

Punto di ripristino precedente al quality jump:

```text
Commit: 41b4709a0d786152118222e6645e4263b022d237
Tag: backup/pre-quality-jump-20260612-120846
Backup locale: .codex-backups/pre-quality-jump-20260612-120846
```

GitHub Actions pubblica immagini `linux/arm64` su GHCR:

```text
ghcr.io/ctapv/pv-guardian-edge-backend:docker-pilot
ghcr.io/ctapv/pv-guardian-edge-web:docker-pilot
```

Le immagini sono private. I device devono fare login GHCR con token locale `read:packages`.

## Muletto ufficio

Device: `192.168.2.116`

Stato validato:

- Docker production attivo.
- Frontend: `http://192.168.2.116/`
- API: `http://192.168.2.116:8000/api/health`
- Modbus TCP slave: `192.168.2.116:15020`
- Container backend/web: healthy.
- Legacy `pv-edge-manager-backend.service`: inactive + disabled.
- Legacy `nginx`: inactive + disabled.
- Docker: active + enabled.
- Release attiva: `/opt/pv-edge-manager-docker/current -> releases/09305feceb40`
- Runtime: `v1.0.0-docker-production`
- Edge ID rilevato: `PV4CE70586D7F2`

Backup pre-switch:

```text
/opt/pv-edge-manager/backups/codex-20260605-121318-pre-docker-production-switch.tar.gz
```

Rollback manuale:

```text
/root/pv-guardian-production-rollback-20260605-121318.sh
```

## Device in campo

Device noto in campo: `100.119.142.49`.

Non assumere che sia Docker. Prima di agire:

1. verificare stato;
2. fare backup;
3. non applicare flussi pensati per il muletto senza conferma.

## Admin/control room

URL: `http://100.120.132.11:8000/`

Host noto:

```text
100.120.132.11
Windows host
Path app noto: C:\Users\iot-2050\Desktop\tailscale-control-center
Service noto: TailscaleControlCenter
```

Credenziali non nel repository. Recuperarle dal proprietario o da canale sicuro.

L'admin deve evolvere da dashboard verso control plane di flotta. Vedere:

```text
docs/ADMIN_FLEET_DIRECTIVES.md
docs/ADMIN_ROLLOUT_BACKEND_MILESTONE.md
```

Punto rollout recuperato il 2026-06-15:

- UI, release, gruppi, canali e anteprima sono pronti;
- `Conferma ed esegui` non esegue ancora comandi reali;
- l'OpenAPI admin non espone ancora campagne rollout;
- il primitivo singolo device esistente non sostituisce il deploy Compose con rollback;
- la prossima milestone e il worker/backend campagne descritto in
  `docs/ADMIN_ROLLOUT_BACKEND_MILESTONE.md`.

Verifica tailnet del 2026-06-15:

- muletto ufficio `iot2050-foggia2-4gb` / `100.107.10.127`: raggiungibile via API,
  runtime `v1.0.0` / commit `09305feceb40`; backup/preflight SSH ancora da eseguire;
- device campo `100.119.142.49`: online, da non toccare senza backup e finestra.

## Decisioni tecniche prese

- Nuovi device: provisioning Docker nativo.
- Niente migrazione legacy prevista per nuovi device.
- GHCR privato con token locale `read:packages`.
- Deploy controllato con `deploy-compose-release.sh`.
- Il cambio release immagini deve passare `PV_EDGE_MANAGER_RELEASE_TAG`.
- Il valore mostrato come versione app deve passare `PV_EDGE_MANAGER_RELEASE_VERSION`;
  per tag semantici `v*` viene derivato automaticamente dal release tag.
- Healthcheck API/web obbligatorio.
- Rollback automatico se healthcheck fallisce.
- Watchtower previsto ma disabilitato/non operativo di default.
- Rollout futuro per canali: `canary`, `pilot`, `stable`, `manual`.
- Qualita telemetria centralizzata con raw value preservato.
- SLO di lettura esposti in `/api/system/health`.
- Audit dei comandi diretti e audit aggregato dei comandi flotta.
- Catalogo predisposto per fonte manuale e stato di collaudo.
- Simulatore Modbus TCP multi-slave disponibile per test commissioning.

## Cose da non fare

- Non committare segreti.
- Non mettere token GHCR nell'admin frontend.
- Non abilitare Watchtower globalmente.
- Non aggiornare tutti i device insieme.
- Non cancellare backup o database senza richiesta esplicita.
- Non toccare device in campo senza backup e finestra di intervento.
