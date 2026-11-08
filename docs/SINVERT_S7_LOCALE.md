# SINVERT S7 sul banco locale

Questa copia di PV Guardian aggiunge il profilo **SINVERT / M/TL S7-300 - Diagnostica**, protocollo `s7_tcp`.

Il profilo legge29 punti del PLC tramite S7 nativo: consensi alla copia esterna, riferimenti grezzi, eventi interni, selettori dei banchi e feedback logici. È disponibile anche il profilo **M/TL S7-300 - Collaudo comandi**, inizialmente in sola lettura: vedere [ricerca e collaudo](SINVERT_S7_COLLAUDO.md). Non è ancora un controllo fisico validato sul SINVERT.

## Avvio su questo PC

Dalla cartella SINVERT MODULATION:

```powershell
.\AVVIA_PV_GUARDIAN_LOCALE.cmd
```

Aprire <http://127.0.0.1:5173>. Il backend ascolta soltanto su 127.0.0.1:8000. Il frontend ascolta soltanto su 127.0.0.1:5173. Database, storico, log e PID sono in `pv_guardian/local_runtime/`, separati da qualsiasi installazione esistente.

Per fermare esclusivamente questi processi:

```powershell
.\FERMA_PV_GUARDIAN_LOCALE.cmd
```

Lo script controlla PID e ora di avvio, evitando di terminare processi diversi che abbiano riutilizzato lo stesso PID. Le porte occupate da altri programmi non vengono liberate automaticamente.

Sono necessari Python 3.11 o successivo, le dipendenze di `backend/requirements.txt`, Node e le dipendenze frontend (`npm ci`). Su questo PC sono già disponibili. Non è stata avviata alcuna installazione su IOT2050. Il remote Git origin è stato rimosso da questa copia; nessuna modifica è stata pubblicata.

## Dispositivo configurato

- Nome: SINVERT - banco CPU e CP
- Host: 192.168.0.245
- Porta: 102
- Rack: 0
- Slot: 2
- Polling: 15 secondi
- Retry: 0 di default

Il profilo Diagnostica legge soltanto dati. Il profilo Collaudo può inviare richieste manuali solo quando esplicitamente abilitato; non abilita consensi PLC. Il Modbus TCP slave e il bridge HSM sono disabilitati nell'istanza locale. La configurazione del dispositivo persiste nel database locale.

## Significato dei valori

Una connessione online significa **PLC raggiungibile e dati diagnostici leggibili**. Non significa inverter presente, inserito o in produzione. Il banco dichiarato dall'utente contiene soltanto CPU e CP, senza periferiche, contattori o inverter collegati.

Il riferimento REAL e le WORD sono visualizzati come valori grezzi senza kW o percentuale. I29 punti non includono misure elettriche validate. Le schede mostrano `--` per queste misure e non generano storico di potenza sintetico.

Per compatibilità con le API esistenti, i contenitori metrici mantengono i campi numerici precedenti, ma `physical_measurements_available=false` ne indica esplicitamente la non validità come misure. I client API devono rispettare questo flag. I valori dei punti PLC sono invece quelli realmente letti; un punto non leggibile diventa `null`, con errore associato, mai zero inventato. Se nessun punto è leggibile il campione fallisce.

Le letture sono sequenziali, non atomiche. Punti nello stesso byte vengono letti una sola volta per campione. Un campione conserva gli istanti di inizio/fine e il numero di punti falliti. Il timeout limita l'acquisizione; python-snap7 3.3.1 usa un handshake iniziale con timeout interno di 5 secondi. I retry delle letture rispettano il budget residuo del campione.

## Comandi

Il profilo Diagnostica non espone comandi e rifiuta scritture anche con override. Il nuovo profilo Collaudo espone richieste collettive ON/OFF e riferimento A grezzo, con abilitazione esplicita e controlli sul programma/consensi. Le istruzioni e i limiti sono in [SINVERT_S7_COLLAUDO.md](SINVERT_S7_COLLAUDO.md).

Riscontri del banco del 4 novembre 2026:

- La copia DB511→DB402 è stata verificata confrontando il consenso disabilitato con quello temporaneamente abilitato.
- DB3.DBX0.7 è ricalcolato da I4.0; una scrittura di simulazione viene sovrascritta dal programma.
- Anche M55 è gestito dal programma e la simulazione non resta stabile.
- Non è stata osservata l'elaborazione dei bit DB511.DBX1.0/.1: nessun fronte acquisito in DB310.DBX15.4/.5 e nessuna variazione M34. Non è stata trovata una chiamata diretta a FC521 nei riferimenti estratti.

Questi limiti impediscono di chiamare i due bit START/STOP o il REAL un limite di potenza. Per completare il controllo servono sorgente/firmware e riscontri con le periferiche e l'inverter reali.

## Verifiche

Suite backend:198 test superati. Build frontend TypeScript/Vite superata. Verifica API:29 punti e3 comandi nel profilo Collaudo, con scritture disabilitate. Browsing nativo S7 verificato sul PLC reale. Lo storico non registra potenza per questi profili diagnostici.

Per i dati grezzi e il giornale di ogni scrittura sperimentale consultare `indagine/acquisizioni/` e il rapporto fase3 nella cartella di lavoro superiore.
