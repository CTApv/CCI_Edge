# SINVERT RA1

Driver e catalogo separati dal SINVERT M/TL precedente. IdentitÃ  nel catalogo:
**SINVERT RA1 / 420 S7-300 - KOMM 3.0 / REGEL 3.9**, protocollo S7 TCP, porta 102.

La base Ã¨ il progetto `test sinvert 420` TIA V18. Dodici blocchi applicativi sono
stati confrontati byte per byte con il PLC: OB1, FC30, FC55, FC120, FC501, FB64,
FB570, FB572, FC10, FC60, FC402, FB18. Il nome 420 non certifica la potenza nominale.
Le versioni KOMM 3.0 e REGEL 3.9 sono intestazioni dei singoli blocchi.

Il driver verifica tipo CPU, dimensione/checksum dei 12 blocchi e dimensioni di
11 DB prima della prima acquisizione. La verifica viene ripetuta almeno ogni
60 secondi di polling; questa cache Ã¨ usata solo per letture. Un programma diverso
viene rifiutato. Il risultato non costituisce una certificazione del programma
intero: gli altri blocchi e le configurazioni hardware non sono identificati
integralmente da questa firma.

Le mappe sono canoniche: override di indirizzi, tipi o metadati vengono rifiutati
prima della connessione. Le letture condividono il mutex dell'endpoint S7 con
gli altri adattatori, raggruppano intervalli entro 200 byte e conservano errori
e valori mancanti. Le letture non sono atomiche rispetto al ciclo PLC.

## Canale specifico RA1

- Connessione CP ID 1, LADDR 440.
- Ricezione diretta in DB944, offset 0, 64 byte.
- Invio da DB504, offset 0, 1864 byte.
- OB1 richiama FC500/FC501 se DB400.DBX16.7 Ã¨ attivo.
- Riferimenti A/B: DB944.DBD32/36 â†’ DB570.DBD2/6.
- La copia alternativa DB511 â†’ DB944 Ã¨ distinta dal trasporto CP diretto.
- FC500 usa il temporizzatore T170 a 5 s; FB570 contiene anche la selezione di
  fallback temporizzata con T163 a 1 minuto.

La pagina del dispositivo ha un pannello RA1 con identificazione, parametri CP,
riferimenti ricevuti e ingressi del regolatore, oltre alle condizioni mancanti.
Le misure e i riferimenti sono esplicitamente grezzi; non si deducono kW o
percentuali dal nome o dalla taglia presunta. I dati PLC non sono un riscontro
fisico indipendente. Anche il valore dopo rampa resta espresso in unitÃ  PLC.

## Collaudo tecnico (rc.5)

La pagina RA1 espone un collaudo dedicato, distinto dai comandi generici. Il catalogo
non espone comandi di flotta, ON/OFF, TEST o reset. La barriera I/O generale rimane
attiva e il vecchio collaudo SINVERT non viene riutilizzato.

Prima di ogni operazione si verificano CPU in RUN mediante SZL 0424, firma dei 12
blocchi, layout degli 11 DB e anche FC500 (MC7Size 732, CheckSum 40259).
Il codice MC7 completo di FC500 ? stato acquisito in sola lettura e ritrovato byte
per byte nel PEData originale del progetto 420. La verifica per scrivere non usa
la cache delle letture.

### Prova S7 temporanea

Riservata a un banco dichiarato con sola CPU e CP, senza inverter o periferiche.
Richiede CP disabilitato, M55 e M102..105 a zero. Questi controlli software non
sostituiscono la conferma dell'isolamento fisico. L'operatore inserisce riferimento
A e limite grezzi: nessun valore massimo viene dedotto da kW o percentuale.

Scrive solo quattro byte in DB944.DBD32, controlla il valore ricevuto e quello in
DB570.DBD2, poi ripristina il valore originale. Il risultato distingue accettazione,
riscontro del regolatore e ripristino. Una risposta di scrittura persa non provoca
il reinvio del riferimento richiesto. Il ripristino avviene solo se permangono le
condizioni di isolamento e il buffer contiene ancora il valore scritto (oppure ?
gi? tornato all'originale). Se il canale cade o il contenuto cambia, il ripristino
pu? risultare non confermato: serve una verifica locale prima di ripetere la prova.
La prova non alimenta n? certifica il watchdog CP.

### Sessione CP continua

L'operatore deve confermare partner/TSAP e apertura attiva dall'IOT, controllo
esclusivo e idoneit? dei valori grezzi. TSAP locale e remoto sono obbligatori, in
esadecimale, senza valori predefiniti. Il collaudo non indovina parametri mancanti.

Richiede ramo CP gi? attivo, DB100.DBX135.1 attivo e DB100.DBX135.0 disattivo,
consensi di gruppo/esterno presenti, parametri DB600 conformi, campi diversi dal
riferimento A neutri e nessun comando HMI/TEST attivo. Nessun gate, consenso,
uscita o bit del watchdog viene scritto dal driver.

Il primo riferimento deve differire da quello attuale per confermare una variazione.
Trasmette telegrammi di 64 byte con solo A a offset 32, ogni 0,8 secondi. B resta
zero: il controllo del secondo riferimento non ? incluso. Verifica tramite S7
DB944.DBD32, DB570.DBD2 e i flag di errore/watchdog DB600.DBX24.1/.4.
Il riscontro PLC non ? un feedback fisico indipendente dell'inverter.

La sessione dura 60 secondi, rinnovabili esplicitamente. Cambiare riferimento non
rinnova la scadenza. Il pannello non rinnova automaticamente. Perdita dei consensi,
profilo/endpoint cambiato, riferimento modificato da altri, firma non conforme,
riscontro mancante o intervallo superiore a 3,5 secondi chiudono il canale senza
riconnessione o reinvio automatici. Il programma viene ricontrollato ogni 15 s.
Letture e invii condividono il mutex S7; contesa o rete lenta possono arrestare
il collaudo per mancata cadenza. I controlli non sono atomici rispetto al ciclo PLC.

Arresto e shutdown chiudono il canale e interrompono gli invii. **Non sono OFF**
e non inviano zero n? ripristinano un precedente setpoint. Il watchdog/fallback
PLC deve essere collaudato fisicamente, compreso il fallback temporizzato a un
minuto: il software non ne dichiara un esito automatico.

`/api/devices/{id}/sinvert-ra1/lab` espone stato; le azioni POST sono `preflight`,
`probe`, `start`, `reference`, `stop`. Solo `preflight` e stato sono in sola lettura.
Il registro `sinvert_ra1_audit.jsonl` conserva preparazione, esiti, variazioni e
arresti nel volume dati. Nessuna sessione sopravvive al riavvio del backend.

## Limiti e distribuzione

Restano da validare scala fisica, collegamento CP effettivo e comportamento del
fallback sull'inverter. Installare il software non avvia prove o trasmissioni.
Il catalogo e i driver SINVERT precedenti restano invariati.

Nessun progetto TIA, sorgente Siemens proprietario, binario MC7 o dato runtime
del cliente viene distribuito nel repository; vengono inclusi solo la mappa
dell'adattatore e le firme necessarie all'interoperabilit?.
