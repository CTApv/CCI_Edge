# test sinvert definitivo

Prerelease `v1.3.3-test-sinvert-definitivo`, basata su PV Guardian v1.3.

Include la dashboard di collaudo SINVERT, il mittente nativo ISO-on-TCP con watchdog e lo strumento separato di prova finita. La sessione nativa viene avviata esplicitamente dall'operatore e non riparte al riavvio del gateway. Non modifica il programma, M55, il selettore remoto, le uscite o i parametri di rampa/fallback del PLC.

## Sessione nativa nell'app (nuovo in v1.3.3)

Nella scheda **Collaudo**, usare **Canale nativo e watchdog**:

1. Abilitare il profilo di collaudo, configurare un limite locale appropriato e inserire il riferimento PLC iniziale nel campo potenza. La scala kW/% resta da confermare.
2. Per il banco CPU+CP, dichiarare e attivare la sessione "sola CPU". Con inverter o periferiche collegati, questa modalita deve essere disattivata: il percorso di campo richiede M55 e DB3.0.7 validi, oltre ai controlli del programma verificato.
3. Verificare che il canale sia di proprieta esclusiva di PV Guardian: nessun altro SCADA/mittente nativo o comando HMI/TEST. Confermare la casella e premere **Avvia con il riferimento inserito**. Questo pulsante scrive il riferimento iniziale e abilita esplicitamente DB100.DBX135.0/.1, salvandone il valore precedente.
4. L'avvio riesce solo se sorgente DB511.DBD32, copia DB944.DBD32 e ingresso DB570.DBD2 corrispondono al REAL inviato e il watchdog/canale DB600 non presenta errori. Dopo l'avvio, **Invia potenza** usa lo stesso mittente nativo, non una scrittura diretta S7.
5. **Ferma canale nativo** termina la trasmissione e ripristina soltanto i due bit di copia precedenti, preservando gli altri bit. Non ripristina un vecchio riferimento e non invia ON/OFF. OFF resta disponibile e tenta prima l'arresto del canale. Per ON, Reset o comandi HMI/TEST occorre prima fermarlo: un vecchio telegramma non deve annullare o ripetere impulsi HMI.

La sessione dura al massimo 10 minuti anche se si chiude la pagina. Non viene rinnovata dai polling del browser, da un nuovo setpoint o da un riavvio. Scadenza del banco, disabilitazione del profilo, variazione dell'endpoint, perdita dei consensi, conflitti sul buffer, errori di lettura/ricezione o cadenza oltre 3,5 secondi arrestano il mittente senza riconnessione automatica. Il programma viene verificato prima dell'avvio e periodicamente durante la sessione. Gli aggiornamenti usano una connessione S7 dedicata con il lock dell'endpoint, senza ripetere a ogni clic l'intera preparazione che potrebbe ritardare il watchdog.

Il trasporto invia un telegramma di 64 byte ogni circa 0,8 secondi e legge il feedback tramite S7. Sono accettati soltanto telegrammi con campi di comando neutri e altri campi gia allineati alla copia; viene modificato il solo riferimento A. Non si coordinano mittenti esterni con un lock distribuito: il controllo esclusivo deve essere garantito dall'operatore e le modifiche rilevate provocano l'arresto.

Un errore nella sessione nativa non causa un ripiego automatico su scritture dirette S7. Il percorso S7 storico resta compatibile per i client API che non hanno mai aperto una sessione nativa nel processo corrente; la dashboard richiede sempre l'avvio nativo esplicito prima di inviare potenza.

Un arresto ordinato ripristina subito i bit di copia; con bit originariamente disattivi puo interrompere anche la chiamata del watchdog PLC. Il test di perdita del mittente deve invece lasciare attive ricezione e copie e verificare il watchdog dopo il silenzio. La risposta fisica, la selezione del riferimento e il comportamento di fallback vanno provati sull'inverter muletto.

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

## Verifica della nuova integrazione sul banco

Il servizio applicativo nativo e il percorso dei comandi dell'app sono stati provati sulla CPU+CP verificata: riferimenti 450, 451, 452 e ritorno a 450 confermati all'ingresso del regolatore, con watchdog valido. Simulando il blocco del mittente senza disabilitare le copie, il watchdog e scaduto dopo circa 5 secondi. Al termine, buffer, campi HMI coinvolti e bit di copia sono stati ripristinati e riletti. Nessun inverter era collegato; il riferimento dopo selezione/rampa e rimasto a 2500.

La prima verifica su inverter deve confermare consenso remoto, selezione del riferimento, scala fisica e risposta misurata, compreso il comportamento in perdita di comunicazione.
