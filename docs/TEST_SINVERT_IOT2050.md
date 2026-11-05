# TEST SINVERT — IOT2050 muletto

Release sperimentale **v1.2.0-test-sinvert.2**, separata dalla serie stabile.
Include la base PV Guardian v1.2.0-rc2 e l'integrazione SINVERT S7 analizzata
sul banco. Non promuove né sostituisce la versione1.2.0. La convalida e una
successiva release stabile dopo1.2.0 sono attività future.

## Contenuto

- Ricerca nativa S7 TCP del PLC SINVERT, distinta dai SINVERT BOX Modbus.
- Selezionando il PLC S7 nell'elenco normale si apre la dashboard dedicata.
- Link diretto: `/sinvert.html?device=IDENTIFICATIVO_DEL_DISPOSITIVO`.
- Panoramica, allarmi, collaudo manuale, diagnostica e qualità dei dati.
- ON/OFF collettivi e riferimento grezzo con verifiche preventive e audit.
- Conserva le funzioni e i cataloghi della base1.2.0-rc2.

## Installazione isolata sul muletto

Richiede IOT2050 Linux ARM64 con Docker Engine e Docker Compose plugin.
Non è necessario installare Node o compilare il frontend sul gateway.
Le immagini sono costruite da GitHub Actions per `linux/arm64` e pubblicate
su GHCR con il tag specifico della release. Nessun tag `latest` viene aggiornato.

Scaricare dalla release GitHub:

1. `pv-guardian-TEST-SINVERT-v1.2.0-test-sinvert.2.tar.gz`.
2. `SHA256SUMS`.
3. `release-manifest.json`, per commit e immagini effettive.

Trasferire i file sul muletto e verificare l'archivio:

```sh
sha256sum -c SHA256SUMS
tar -xzf pv-guardian-TEST-SINVERT-v1.2.0-test-sinvert.2.tar.gz
cd pv-guardian-test-sinvert
cp deployment/sinvert/test.compose.env.example deployment/sinvert/test.compose.env
```

Il file `deployment/sinvert/test.compose.env` imposta:

```text
TEST_SINVERT_TAG=v1.2.0-test-sinvert.2
TEST_SINVERT_WEB_PORT=18080
TEST_SINVERT_API_PORT=18000
```

Se quelle porte sono già usate dal pilot, cambiarle nel file prima di avviare.
Lo script non libera le porte arrestando servizi estranei.

Se GHCR richiede autenticazione, usare sul muletto un token già predisposto
con `read:packages`, senza inserirlo nei file della release. Per il metodo
tramite file locale vedere `deployment/docker/FLEET_AUTH.md`; il login va
eseguito con lo stesso utente che esegue Docker. Non servono nuovi segreti
nel frontend o nel repository.

```sh
# Esempio con un file credenziali già esistente sul muletto:
sh deployment/docker/login-ghcr.sh /etc/pv-edge-manager/registry.env

sh deployment/sinvert/manage-test-sinvert.sh check
sh deployment/sinvert/manage-test-sinvert.sh start
sh deployment/sinvert/manage-test-sinvert.sh status
```

Aprire **http://IP_DEL_MULETTO:18080/**.
La dashboard SINVERT è anche raggiungibile da
**http://IP_DEL_MULETTO:18080/sinvert.html**.
Il link viene aggiornato con l'identificativo del PLC selezionato e può essere
salvato nei preferiti o aperto direttamente. Un identificativo sconosciuto
mostra un errore, senza selezionare automaticamente un altro PLC.

Questo stack usa progetto Compose `pv-guardian-test-sinvert`, volumi nominati
separati e API esposta solo sul loopback del muletto, porta18000. Il frontend
inoltra le richieste al backend interno. Non monta periferiche, D-Bus host,
database o directory della produzione; non attiva il Modbus TCP slave.
Le funzioni LAN del gateway restano gestite dall'host, non da questo stack S7.

## Configurazione iniziale

Lo stack parte con archivi vuoti. Non contiene configurazioni, database,
limiti o abilitazioni del PC usato per l'analisi.

1. Aggiungere il PLC dal browsing **SINVERT tramite PLC S7**, porta102,
   oppure inserirne l'indirizzo manualmente.
2. Selezionare **M/TL S7-300 - Diagnostica** per il monitoraggio o
   **M/TL S7-300 - Collaudo comandi** per predisporre le prove.
3. Verificare rack/slot per l'installazione; nel progetto analizzato sono0/2.
4. Controllare collegamento PLC, feedback dei gruppi, qualità delle misure e
   blocchi. La presenza del PLC non dimostra la comunicazione con gli inverter.
5. Per il collaudo, abilitare esplicitamente il profilo nelle impostazioni;
   la dashboard richiede inoltre l'attivazione manuale della pagina. Le
   verifiche preventive non inviano comandi.

## Limiti funzionali della release TEST

- Le scritture partono disabilitate e il limite grezzo parte da0.
- ON/OFF hanno ambito collettivo sull'intero PLC, non sul singolo inverter.
- Il driver confronta CPU, dimensioni e checksum dei blocchi con il programma
  analizzato. Un programma differente blocca le scritture, senza apprenderlo
  automaticamente o forzare consensi.
- M55, abilitazioni esterne e watchdog mantengono i loro controlli.
- La scala del comando di potenza e la modulazione fisica non sono validate.
  Il riferimento non è presentato come kW o percentuale.
- La conferma di ricezione S7/copia/ingresso nel regolatore è distinta dalla
  conferma fisica dell'inverter, che resta non dimostrata.
- Lo storico energetico SINVERT resta disattivato finché la qualità non è
  convalidata; non viene popolato con zeri di comodo.

Questa release serve alle prove sul muletto e al successivo collaudo fisico,
non costituisce una versione già approvata per il servizio in campo.

## Arresto e ritorno alla situazione precedente

```sh
sh deployment/sinvert/manage-test-sinvert.sh stop
```

Arresta e rimuove soltanto i container del progetto di test. I volumi dei
dati di test restano conservati; i servizi e i dati della produzione non
vengono modificati. Non usare `down -v` se si vogliono mantenere le prove.

## Validazioni prima della pubblicazione

Suite backend con le dipendenze fissate della release; compile Python;
build frontend delle due pagine; controlli di routing e qualità; validazione
Compose production, pilot e TEST; controlli del browser sul collegamento
dall'elenco normale e sui link diretti. Il workflow GitHub ripete i controlli
prima di pubblicare le immagini ARM64. Nessuna installazione remota viene
eseguita dall'attività di creazione della release.
