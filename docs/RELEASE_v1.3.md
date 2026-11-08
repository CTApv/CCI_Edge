# PV Guardian v1.3

Fronius Verto e Verto Plus entrano nel catalogo standard con telemetria inverter SunSpec e limitazione della potenza tramite il normale riferimento esterno di PV Guardian. Profili distinti per modello, serie, numero di MPPT e protocollo Modbus TCP/RTU. Rilevamento automatico float/int+SF, fattori di scala dinamici, scrittura del riferimento insieme all'abilitazione e verifica tramite rilettura.

Sono comprese le modifiche SINVERT sviluppate fino alla build locale `.8`: dashboard dedicata, monitoraggio della catena dei riferimenti, comandi rapidi, riferimento persistente, Reset AUTO/TEST e Reset allarmi distinti, registrazioni e diagnostica. Le funzioni di banco rimangono esplicite e temporanee; non si abilitano automaticamente dopo un riavvio. Non sono inclusi gli script esterni di reverse engineering o prove sul PLC.

Il supporto Fronius utilizza il catalogo e il dispatch standard, indipendentemente dalla schermata SINVERT. Nessuna modifica ai registri CCI pubblici o al significato del riferimento percentuale di flotta.

Le funzionalità Fronius sono verificate con test automatici e simulatore Modbus, non ancora su inverter fisico. Dettagli e configurazione in [FRONIUS_VERTO.md](FRONIUS_VERTO.md).

Installazione Docker ARM64 tramite immagini GHCR taggate `v1.3`. Prima dell'aggiornamento conservare `compose.env`, `app.env`, collegamento della release precedente e backup dei database. Nessuna scrittura di prova verso PLC o inverter è richiesta per installare la release.
