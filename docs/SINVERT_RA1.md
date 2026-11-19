# SINVERT RA1

Driver e catalogo separati dal SINVERT M/TL precedente. Identità nel catalogo:
**SINVERT RA1 / 420 S7-300 - KOMM 3.0 / REGEL 3.9**, protocollo S7 TCP, porta 102.

La base è il progetto `test sinvert 420` TIA V18. Dodici blocchi applicativi sono
stati confrontati byte per byte con il PLC: OB1, FC30, FC55, FC120, FC501, FB64,
FB570, FB572, FC10, FC60, FC402, FB18. Il nome 420 non certifica la potenza nominale.
Le versioni KOMM 3.0 e REGEL 3.9 sono intestazioni dei singoli blocchi.

Il driver verifica tipo CPU, dimensione/checksum dei 12 blocchi e dimensioni di
11 DB prima della prima acquisizione. La verifica viene ripetuta almeno ogni
60 secondi di polling; questa cache è usata solo per letture. Un programma diverso
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
- OB1 richiama FC500/FC501 se DB400.DBX16.7 è attivo.
- Riferimenti A/B: DB944.DBD32/36 → DB570.DBD2/6.
- La copia alternativa DB511 → DB944 è distinta dal trasporto CP diretto.
- FC500 usa il temporizzatore T170 a 5 s; FB570 contiene anche la selezione di
  fallback temporizzata con T163 a 1 minuto.

La pagina del dispositivo ha un pannello RA1 con identificazione, parametri CP,
riferimenti ricevuti e ingressi del regolatore, oltre alle condizioni mancanti.
Le misure e i riferimenti sono esplicitamente grezzi; non si deducono kW o
percentuali dal nome o dalla taglia presunta. I dati PLC non sono un riscontro
fisico indipendente. Anche il valore dopo rampa resta espresso in unità PLC.

## Scritture

Questa versione è **in sola lettura**: non espone comandi numerici, ON/OFF,
TEST, reset o setpoint. La barriera nell'I/O blocca anche eventuali comandi
costruiti con i metadati del vecchio SINVERT: nessuna scrittura di ripiego.
Il profilo è ineligible per il dispatch dei limiti di flotta.

Restano da validare scala fisica e priorità dei riferimenti, partner/TSAP e
verso di apertura della connessione CP, modalità di abilitazione e comportamento
fisico del fallback. Il driver non abilita il ramo CP, non forza consensi e non
avvia sessioni native. Il catalogo e i driver SINVERT precedenti restano invariati.

Nessun progetto TIA, sorgente Siemens proprietario, binario MC7 o dato runtime
del cliente viene distribuito nel repository; vengono inclusi solo la mappa
dell'adattatore e le firme necessarie all'interoperabilità.
