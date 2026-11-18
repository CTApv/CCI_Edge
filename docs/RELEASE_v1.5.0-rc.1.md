# v1.5.0-rc.1 — Catalogo Aurora e diagnostica offline

Prerelease per il collaudo della copertura Power-One Aurora. Aggiunge 40 identità
documentate, portando il catalogo Aurora a 49 profili complessivi, e strumenti
offline per analizzare catture seriali e compatibilità firmware dei Central.

## Catalogo

- Famiglie distinte PVI storici, OUTD, versioni isolate, UNO, TRIO e Central.
- Fonte, stato di verifica e codici identificativi documentati nei metadati.
- Nuovi profili indicati come «Identificato: letture da collaudare»; le letture
  usano il template Aurora generico e richiedono conferma sul dispositivo.
- Nessun nuovo comando abilitato sui profili aggiunti. I comandi dei profili
  precedenti restano disponibili con il comportamento già esistente.
- Codici di modulo separati dall'identità del rack; nessuna nuova associazione
  automatica o equivalenza commerciale dedotta dal solo nome.

## Protocollo e strumenti

**Il driver Aurora operativo e il protocollo di scrittura 151 collaudato sono
invariati rispetto alla v1.4.2**, inclusi conversione, timeout, rampa e CRC.

- Test di regressione dei frame completi a 0, 1, 25, 50, 75, 99 e 100% tramite
  seriale emulata, inclusi errori, frammentazione e timeout.
- `scripts/aurora_analyze_capture.py`: interpreta quattro scambi di lettura
  già catturati (83/132–135), mantenendo distinti limite memorizzato e abilitazione.
- `scripts/aurora_inspect_firmware.py`: confronta identificativi e revisioni DSP
  e MCU con la tabella locale AN101 del software Central CVI.
- Gli strumenti non aprono connessioni e non modificano il polling operativo.

## Verifiche

- 393 test backend superati, di cui 27 dedicati ad Aurora.
- Build frontend e compilazione Python completate.
- Configurazioni Docker production e pilot-ghcr validate.
- Verificate 38 combinazioni ai confini delle 19 regole della tabella firmware
  locale del costruttore.

## Limiti della prerelease

La presenza di un modello nel catalogo non certifica la compatibilità di tutte
le misure o del controllo per ogni firmware. Sono ancora necessari collaudi reali
di letture, riscontro del limite, comportamento del timeout, master/slave e
potenza erogata. La compatibilità AN101 ricavata dal software non abilita scritture.
Gli eseguibili proprietari, le catture dei clienti e i dati locali non sono inclusi.

Questa pubblicazione riguarda GitHub e gli artefatti della prerelease.
Non è previsto alcun aggiornamento dell'IOT locale; la release stabile resta
v1.4.2. SINVERT e gli altri driver preesistenti sono inclusi nella base del progetto.

Dettagli: [copertura del catalogo](AURORA_CATALOG_COVERAGE.md) e
[verifiche offline](AURORA_OFFLINE_VALIDATION.md).
