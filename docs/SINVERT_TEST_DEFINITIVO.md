# test sinvert definitivo

Prerelease `v1.3.1-test-sinvert-definitivo`, basata su PV Guardian v1.3.

Include la dashboard di collaudo SINVERT, le funzioni già presenti in v1.3 e lo strumento di prova finita del canale nativo ISO-on-TCP. Non avvia un mittente ciclico al riavvio del gateway e non modifica automaticamente il programma o i consensi del PLC.

## Risultati verificati il 16 novembre 2026

Sul banco con sola CPU 315-2 DP e CP 343-1 Lean, senza inverter o periferiche:

- Connessione nativa riuscita sia dal PC sia dal container backend dell'IOT2050.
- Marcatori REAL 346 e 347 ricevuti in DB511.DBD32, copiati in DB944.DBD32 e confermati all'ingresso DB570.DBD2.
- Watchdog DB600.DBX24.4 valido durante la trasmissione; perdita rilevata circa 5,1 secondi dopo l'interruzione dall'IOT.
- Valori temporanei, campi HMI coinvolti e bit di copia ripristinati e riletti identici.

Il consenso remoto era assente e il riferimento dopo selezione/rampa è rimasto a 2500. La scala kW/% e la modulazione fisica non sono validate. Il nome della release identifica il pacchetto di test, non una certificazione per l'impianto.

## Configurazione del banco verificato

La configurazione è stata preparata e caricata separatamente con TIA: non viene applicata dall'app o dallo strumento Python.

| Parametro | Valore del banco |
|---|---|
| PLC | 192.168.0.245, rack 0, slot 2 |
| CPU verificata | seriale S C-FODC12442015 |
| Connessione CP | ISO-on-TCP, ID locale 1, passiva |
| TSAP CP / client | SINVERT / PVGUARDIAN |
| Indirizzo logico CP | 440, 01B8h |
| Telegramma | 64 byte verso DB511 offset 0 |
| Clock del programma | MB10, fronti prodotti in MB11 |

La CPU di banco è stata configurata senza password su richiesta dell'operatore. Questi parametri non sono una configurazione di campo da replicare automaticamente.

## Prova manuale finita dal gateway

Solo sul banco CPU+CP confermato, senza inverter o periferiche:

```sh
docker exec pv-guardian-backend python tools/sinvert_native_bench.py \
  --cpu-cp-only --output-dir /tmp/sinvert-native-probe-results
```

Lo strumento verifica identità e metadati del programma, assenza dei comandi attivi attesi nel telegramma, stabilità della sorgente e consensi del banco. Invia riferimenti temporanei sul canale nativo per nove secondi, osserva otto secondi di silenzio e ripristina i campi salvati. Conserva un journal JSON con invii, campioni e verifiche di ripristino. Esito 0 richiede che tutte le verifiche e il ripristino siano riusciti.

Il riferimento cambia soltanto di +1/+2 rispetto al valore iniziale, senza attribuire unità fisiche. Il codice non forza I4.0, M55, uscite o fallback. Un'interruzione forzata del processo può impedire il ripristino: verificare il journal e i valori PLC prima di proseguire.

## Confine con il controllo nell'app

Il pulsante di riferimento dell'app continua a usare il percorso S7 di collaudo esistente. La sua scrittura non alimenta da sola il watchdog AG_RECV. Questa release non lo sostituisce con un servizio nativo permanente: il telegramma contiene anche comandi HMI, che devono essere coordinati prima di introdurre un nuovo proprietario ciclico del canale.

La prima verifica su inverter deve confermare consenso remoto, selezione del riferimento, scala fisica e risposta misurata, compreso il comportamento in perdita di comunicazione.
