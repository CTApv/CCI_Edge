# PV_GUARDIAN Edge

Repository dell'app edge installata sui dispositivi PV_GUARDIAN.

Il sistema gira su gateway industriali Siemens IOT2050 e gestisce il controllo locale di impianti fotovoltaici:

- configurazione inverter;
- comunicazione Modbus seriale, TCP e RTU over TCP;
- dashboard locale;
- storico potenza;
- diagnostica comunicazione;
- invio setpoint di potenza;
- API locali per supervisione e integrazione con control room centrale.

## Stato attuale

La prima versione salvata in questo repository rappresenta la baseline legacy pre Docker, installata tramite servizio systemd su device in campo.

Versione applicativa di riferimento:

```text
v1.0.0
```

Tag consigliato per la baseline produttiva legacy:

```text
v1.0.0-systemd
```

## Struttura

```text
backend/      API FastAPI, servizi Modbus, cataloghi inverter, test
frontend/     Dashboard React/Vite
deployment/   File di installazione legacy systemd/nginx
docs/         Documentazione operativa
```

## Configurazione

I file `.env` reali non devono essere versionati in GitHub. Restano sul dispositivo o verranno generati dal provisioning centrale.

Esempi versionati:

```text
backend/.env.example
frontend/.env.example
```

Percorsi target futuri per installazioni Docker:

```text
/etc/pv-edge-manager/
/var/lib/pv-edge-manager/
/var/log/pv-edge-manager/
/opt/pv-edge-manager/
```

## Avvio locale

Backend:

```powershell
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Dashboard locale:

```text
http://127.0.0.1:5173
```

## Note operative

Non versionare:

- database SQLite;
- file `.env` reali;
- log;
- build `frontend/dist`;
- ambienti virtuali;
- backup locali;
- archivi di release generati.

La dockerizzazione e l'aggiornamento OTA verranno sviluppati su branch pilota, partendo dal device muletto `192.168.2.116`.
