# PV_GUARDIAN Codex Handoff

Questo repository contiene l'app edge PV_GUARDIAN per gateway Siemens IOT2050.
Leggere questo file prima di modificare codice, deploy o documentazione.

## Stato di riferimento

- Repository GitHub: `https://github.com/CTApv/CCI_Edge.git`
- Branch operativo Docker: `docker-pilot`
- Commit validato sul muletto ufficio: `09305feceb40`
- Versione app: `v1.0.0`
- Muletto ufficio: `192.168.2.116`
- Stato muletto: Docker production attivo su porte reali.
- Admin/control room: `http://100.120.132.11:8000/`

I segreti non devono essere committati:

- password SSH;
- token GHCR;
- file `.env` reali;
- file `registry.env`;
- database e backup.

## Regole operative

1. Prima di modificare un device remoto, verificare stato servizi e fare backup.
2. Non usare comandi distruttivi senza rollback pronto.
3. Non committare file generati, database, log o archivi.
4. Per deploy Docker usare GHCR privato e token locale `read:packages`.
5. I nuovi device vanno provisionati Docker nativi, non migrati da legacy.
6. Watchtower e previsto ma disabilitato/non operativo di default.
7. Se si lavora sull'admin, non spostare token o credenziali nel frontend.

## Documenti da leggere

- `docs/CODEX_HANDOFF.md`: stato attuale dell'ecosistema.
- `docs/DEPLOY_RUNBOOK.md`: comandi e rollback edge Docker.
- `docs/ADMIN_FLEET_DIRECTIVES.md`: direttive per adattare l'admin alla gestione flotta.
- `deployment/docker/FLEET_AUTH.md`: accesso privato GHCR.
- `deployment/docker/README.md`: dettagli Docker edge.

## Verifiche minime edge

Backend:

```powershell
cd c:\progetti\pv-edge-manager\backend
python -m unittest discover -s tests
python -m compileall app tests
```

Frontend:

```powershell
cd c:\progetti\pv-edge-manager\frontend
npm run build
```

Docker:

```powershell
$env:PV_EDGE_MANAGER_ENV_FILE='deployment/docker/app.env.example'
docker compose --env-file deployment/docker/production.compose.env.example config --quiet
docker compose --env-file deployment/docker/pilot-ghcr.compose.env.example config --quiet
Remove-Item Env:\PV_EDGE_MANAGER_ENV_FILE
```

