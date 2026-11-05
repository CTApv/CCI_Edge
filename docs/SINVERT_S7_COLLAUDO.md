# SINVERT S7: ricerca e comandi di collaudo

Aggiornamento del 5 novembre 2026: [Monitoraggio, consensi e verifica preventiva](SINVERT_MONITOR_20261105.md).
La nuova vista legge128 punti e distingue feedback HMI, qualità delle misure
e ingresso del regolatore;209 test backend superati. Le informazioni di prova
del 4 novembre riportate sotto restano storiche.

Questa versione rimane locale su questo PC. URL: http://127.0.0.1:5173.
Il dispositivo già presente è stato aggiornato al modello
**SINVERT / M/TL S7-300 - Collaudo comandi**, conservando il suo identificativo.
Le scritture sono inizialmente **disabilitate**.

## Ricerca del PLC

La ricerca precedente inviava soltanto sonde Modbus e filtrava i profili S7.
Ora è presente una ricerca S7 nativa, in sola lettura.

Nel browsing avanzato scegliere **Protocollo di ricerca → SINVERT tramite PLC S7**.
Nella procedura guidata scegliere il modello M/TL S7-300, Diagnostica o Collaudo.
La porta proposta è102. Il collegamento S7 usa rack0, slot2. Quando disponibile,
viene proposto l'IP del dispositivo S7 già configurato.

Su questo banco l'indirizzo è **192.168.0.245**. La ricerca identifica il PLC
che gestisce i convertitori; non enumera separatamente gli inverter dietro
quel PLC. Gli unit ID Modbus non sono usati dalla sonda S7.

Per riconoscere il profilo si leggono identità CPU e dimensioni dei DB100,
120,126,511 e944; viene verificata anche la leggibilità di DB100. Una porta
TCP aperta da sola non produce un risultato SINVERT. L'identificazione del
layout non certifica il funzionamento fisico del controllo.

I retry della ricerca sono soltanto letture, fino a3 retry. Gli errori di
sonda sono restituiti all'interfaccia, evitando un risultato vuoto privo di
spiegazione. La selezione esplicita dei vecchi modelli SINVERT Modbus conserva
la precedente ricerca Modbus.

## Preparazione della prova fisica

1. Ricaricare la pagina e aprire il dispositivo con modello **Collaudo comandi**.
2. Nel dettaglio sono visibili i pulsanti **Invia richiesta ON**, **Invia
   richiesta OFF** e il riferimento di potenza in **valore PLC**.
3. Quando si intende eseguire la prova, modificare le impostazioni del
   dispositivo e scegliere **Comandi SINVERT → Collaudo manuale abilitato**.
4. Per la potenza impostare anche **Massimo riferimento PLC per collaudo**
   secondo il valore/scala confermati per il PLC da provare. Con massimo0
   la scrittura del riferimento resta disabilitata.

Il riferimento non è una percentuale. Non è implementata una conversione
automatica100%=potenza nominale, perché le unità fisiche non sono ancora
dimostrate. Il profilo non viene usato dal regolatore percentuale di flotta.

**Ambito dei comandi:** ON/OFF sono richieste collettive per le posizioni
gestite dall'intero PLC. Il profilo non seleziona il singolo inverter.

## Operazioni del driver

| Comando | Scrittura |
|---|---|
|ON | Impulso nativo sul solo bit M34.2; rimozione del bit dopo la verifica |
|OFF | Impostazione del solo bit M34.3; consumo a cura del PLC |
|Riferimento di potenza | Un REAL big-endian a DB511.DBD32; verifica della copia a DB944.DBD32 |

Le scritture a bit non riscrivono l'intero byte M34 e preservano gli altri
bit del programma. Il driver non abilita consensi, non cambia watchdog,
non modifica programma, stato CPU o uscite. Non usa DB511.DBX1.0/.1 come
ON/OFF: la loro elaborazione tramite FC521 non è stata dimostrata.

Prima di ogni comando si verificano:

- modello Collaudo e abilitazione esplicita delle scritture;
- CPU in RUN, tipo CPU e versione dei blocchi attesi, tramite dimensioni e
  checksum; dimensioni dei DB previste dal profilo;
- modo M/TL e numero di posizioni nel dominio1..32;
- per ON/potenza, consensi M55 presenti e nessuna sequenza/reinizializzazione
  o richiesta già in corso;
- per la potenza, entrambi i consensi di copia esterna, consenso esterno
  DB3.DBX0.7 e assenza di errori del canale/watchdog.

Se una condizione manca, il comando viene rifiutato con il motivo. I file di
riferimento del programma non vengono appresi automaticamente da un PLC
sconosciuto. Un programma diverso richiede la verifica della sua mappatura.

## Canale esterno e scala: limiti ancora aperti

La scrittura a DB511 non sostituisce automaticamente il protocollo di
comunicazione originale. FC500 genera il watchdog da eventi AG_RECV; il driver
non simula tali eventi e non cancella il relativo errore. Se il canale esterno
non è sano, il riferimento è rifiutato. La gestione/assegnazione del produttore
del riferimento sul campo resta quindi da verificare.

Se un altro PLC/SCADA riscrive il riferimento durante il controllo di lettura,
il driver segnala che il valore non è mantenuto. La sola riuscita di una
scrittura e della copia non dimostra che il regolatore abbia selezionato quel
valore anziché un fallback o che l'inverter lo abbia applicato.

Il ramo numerico alternativo comprende formule compatibili con reattiva/cosφ
e una conversione finale ×10. Per questo DB511.DBD10 non è stato usato come
limite percentuale di potenza attiva. DB511.DBD32 è esposto come riferimento A
di collaudo; la sua etichettatura fisica rimane da confermare.

## Esiti e tracciabilità

Il messaggio di successo è **«Richiesta inviata al PLC; esecuzione fisica non
confermata»**. Le diagnostiche distinguono tentativo di scrittura, ACK del
PLC, consumo della richiesta o copia del riferimento. Non mostrano una
conferma fisica di marcia inventata.

Una scrittura dall'esito incerto non viene ritentata automaticamente. Il
log `sinvert_command_audit.jsonl`, nella directory del database dell'app,
conserva l'intenzione prima della scrittura e l'esito della sessione. Le
richieste di potenza non attivano un produttore ciclico né un heartbeat.

Il profilo **Diagnostica** continua a rifiutare tutte le scritture, anche
con override dei punti. Il profilo Collaudo legge gli stessi29 punti grezzi.
Le misure elettriche non validate restano indicate con `--`.

## Verifiche eseguite

- 198 test backend superati con archivi temporanei isolati;
- build TypeScript/Vite superata;
- browsing reale tramite API: trovato il PLC315-2DP a192.168.0.245:102;
- API del dispositivo:3 comandi visibili, scritture non abilitate rifiutate
  prima di qualsiasi tentativo di scrittura;
- driver sul banco dichiarato CPU+CP senza periferiche: una richiesta OFF
  nativa a bit, consumata dal PLC; ON e potenza bloccati per consensi assenti;
- maschere d'uscita logiche rimaste a zero e campi DB controllati invariati.

ON e modulazione fisica non sono stati validati con un inverter collegato.
Le prove positive della scrittura del riferimento del nuovo driver sono
automatiche con client simulato; le precedenti prove di banco hanno verificato
DB511.DBD32/36→DB944→ingressi FB570 senza attribuire unità fisiche.

Rapporto API: `indagine/rapporti/VERIFICA_BROWSING_E_COLLAUDO_API.json`.
Prova driver: `indagine/acquisizioni/commissioning_driver_20261104_160509/`.
