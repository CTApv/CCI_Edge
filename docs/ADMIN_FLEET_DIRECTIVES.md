# Admin Fleet Directives For Codex

Questo documento e il brief per l'agente Codex che lavorera sull'admin/control room.

## Contesto

L'admin gira su:

```text
http://100.120.132.11:8000/
```

Host noto:

```text
100.120.132.11
Path app noto: C:\Users\iot-2050\Desktop\tailscale-control-center
Service noto: TailscaleControlCenter
```

Le credenziali non sono nel repository e vanno richieste al proprietario.

L'admin deve gestire molti edge PV_GUARDIAN installati in Italia via Tailscale.
Ogni edge espone API su porta `8000`.

Endpoint edge utili:

```text
/api/health
/api/system/health
/api/dashboard/active-power
```

`/api/system/health` espone anche:

- `data_quality`: conteggio punti validi, warning, invalidi e device interessati;
- `service_levels`: rispetto degli obiettivi temporali per potenza e telemetria completa;
- SLO e stime per ogni `endpoint_runtime`;
- metadati build, topologia broadcast e diagnostica comunicazione.

## Obiettivo

Trasformare l'admin in control plane di flotta:

- inventario device;
- stato online/offline;
- versioni e build;
- potenza attiva totale;
- provisioning nuovi device;
- rollout controllato aggiornamenti;
- audit operativo.

## Prima milestone: sola lettura

Implementare prima solo inventory e monitoraggio, senza comandi distruttivi.

### Modello device

Persistire almeno:

- `edge_id`
- `hostname`
- `plant_name`
- `customer`
- `site_name`
- `region`
- `tailscale_ip`
- `lan_ip`
- `status`
- `last_seen`
- `app_version`
- `build_label`
- `build_commit`
- `docker_mode`
- `update_channel`
- `active_power_kw`
- `configured_device_count`
- `online_device_count`
- `pending_device_count`
- `offline_device_count`
- `last_error`
- `notes`
- `created_at`
- `updated_at`

### Collector backend

Il frontend non deve interrogare direttamente tutti gli edge.
Creare un collector lato backend admin che:

- chiama `/api/system/health`;
- chiama `/api/dashboard/active-power`;
- usa timeout brevi;
- gestisce device offline senza bloccare tutto;
- salva ultimo stato noto e timestamp;
- scagliona richieste per scalare a 500 device;
- registra errori e durata richieste.

Frequenze iniziali consigliate:

- health: 30-60 secondi;
- active power: 5-15 secondi per device online;
- dati pesanti o storico: on-demand.

## Dashboard flotta

Mostrare:

- totale device;
- online/offline/warning/error;
- potenza attiva totale;
- distribuzione versioni;
- device non allineati;
- ultimo aggiornamento collector;
- filtri per cliente, regione, stato, versione, canale.

La UI deve mostrare ultimo dato noto e timestamp, non svuotarsi se un device non risponde.

## Scheda device

Mostrare:

- Edge ID;
- IP Tailscale;
- link all'interfaccia edge;
- versione/build/commit;
- uptime o `backend_started_at`;
- stato polling Modbus;
- numero inverter configurati;
- online/pending/offline inverter;
- potenza attiva;
- ultimo errore;
- qualita dati e punti invalidi;
- rispetto SLO di lettura;
- eventi recenti.

## Provisioning nuovi device

I nuovi edge saranno Docker nativi.
L'admin dovra preparare/gestire:

- associazione cliente/impianto;
- registrazione Edge ID;
- IP Tailscale;
- canale update iniziale;
- stato primo healthcheck;
- istruzioni/script provisioning.

Il provisioning edge deve prevedere:

- Docker statico;
- compose production;
- GHCR `registry.env` locale con token `read:packages`;
- `app.env`;
- deploy da GHCR;
- Watchtower previsto ma disabilitato/non operativo.

Mai salvare token GHCR nel frontend o in log.

## Rollout update

Canali previsti:

```text
manual
canary
pilot
stable
```

Per ora niente auto-update globale.
L'admin deve arrivare a:

- mostrare versione corrente per device;
- preparare campagna update;
- selezionare gruppo/canale;
- tracciare `pending`, `running`, `success`, `failed`, `rolled_back`;
- registrare audit evento;
- bloccare rollout se canary fallisce.

Watchtower:

- predisporre campi/config;
- non abilitare automaticamente;
- futuro uso con label e gruppi controllati.

## Affidabilita

Implementare:

- timeout per device;
- retry limitati;
- circuit breaker per offline persistenti;
- log eventi;
- nessun blocco UI;
- nessun comando distruttivo nella prima milestone.

## Sicurezza

- Nessun token nel frontend.
- Nessuna password nel repository.
- Audit per provisioning, update, reboot e modifiche device.
- Separare credenziali device da metadati inventory.

## Ordine di lavoro consigliato

1. Fare backup dell'admin prima di modificare.
2. Analizzare backend/frontend/DB esistenti.
3. Aggiungere modello inventory o estendere quello esistente.
4. Implementare collector backend.
5. Aggiungere dashboard flotta.
6. Aggiungere scheda device.
7. Solo dopo, progettare provisioning e update.
