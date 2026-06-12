# Qualita dati e affidabilita

## Punto di ripristino locale

Prima dell'introduzione delle funzioni di qualita e affidabilita e stato creato:

```text
Commit: 41b4709a0d786152118222e6645e4263b022d237
Tag: backup/pre-quality-jump-20260612-120846
Backup: .codex-backups/pre-quality-jump-20260612-120846
```

Il backup contiene bundle Git completo, archivio sorgenti e copie SQLite verificate.

Ripristino sorgenti in una nuova cartella:

```powershell
git clone .codex-backups/pre-quality-jump-20260612-120846/pv-guardian-source.bundle pv-guardian-restore
cd pv-guardian-restore
git checkout backup/pre-quality-jump-20260612-120846
```

I database vanno sostituiti solo a backend arrestato.

## Qualita telemetria

Ogni punto letto viene classificato:

- `valid`: valore plausibile;
- `warning`: valore possibile ma fuori intervallo nominale;
- `invalid`: valore non plausibile o sentinella di protocollo;
- `unavailable`: valore assente.

Il valore grezzo resta visibile nella telemetria tecnica. I riepiloghi di energia e temperatura
non usano valori classificati `invalid` o `unavailable`.

I profili catalogo possono dichiarare limiti specifici in `protocol_meta`:

```python
{
    "valid_min": 0,
    "valid_max": 100,
    "warning_min": 10,
    "warning_max": 90,
    "invalid_values": [65535],
}
```

## Obiettivi temporali

La pagina Controllo mostra gli SLO iniziali:

- giro potenza attiva: 30 secondi;
- telemetria completa: 300 secondi;
- comando diretto: 2 secondi.

Gli SLO sono obiettivi operativi, non garanzie del protocollo. La stima usa tempi runtime e
numero di slave per endpoint.

## Audit comandi

I comandi diretti registrano esito, device, comando, stage ed eventuale errore nella timeline.
I comandi flotta e broadcast mantengono l'evento aggregato per evitare centinaia di eventi
duplicati durante un singolo dispatch.

## Catalogo verificabile

I profili possono dichiarare:

- stato verifica;
- manuale e versione sorgente;
- data ultima revisione;
- collaudo in campo;
- note operative.

Il wizard commissioning mostra questi dati e segnala eventuali punti telemetrici non plausibili.

## Test

Usare il simulatore descritto in `docs/MODBUS_TEST_SIMULATOR.md` per provare:

- molti slave sullo stesso gateway;
- latenza elevata;
- unit id offline;
- perdita casuale di risposte;
- qualità e scalatura dei dati.
