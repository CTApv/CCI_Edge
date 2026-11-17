# Xantrex GT500: famiglie e interfacce

Le famiglie GT500 non ereditano la mappa legacy `GT Series` via gateway/Xanbus.
Questa integrazione separa le otto varianti documentate e rende esplicito lo
stato effettivo del supporto. Nessuna variante e collaudata sull'hardware.

| Profilo | Interfaccia nel catalogo | Supporto attuale |
|---|---|---|
| GT500 E / PVGT12542EDI | Modbus TCP | Diagnostica passiva |
| GT500 E GI / PVGT12542EDI | Modbus TCP | Diagnostica passiva |
| GT500 MVX | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 MVX PG | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 480 | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 480 PG | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 600 | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 600 PG | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |

## Diagnostica europea

Il manuale italiano 975-0582-01-01 Rev B descrive il convertitore PVGT12542EDI,
che traduce il protocollo proprietario seriale RS422 in Modbus TCP. Il software
non implementa il protocollo proprietario e non presume che altri convertitori
forniscano la stessa mappa.

La tabella 1-1 e la verifica descritta a pagina 1-26 consentono un primo profilo
diagnostico: holding, funzione 03, primi otto registri, senza scritture.
Il registro 1 del manuale e trattato come PDU 0: la convenzione deve essere
confermata sul gateway reale. I campi successivi sono stato obiettivo, stato
sistema, guasto grezzo, stato inverter, stato FV e due parole versione software.
Non si deducono misure fisiche o identita inverter da questi campi.

Ogni lettura richiede l'intero blocco diagnostico e stato comunicazione zero.
Stato 4 o qualsiasi altro valore, eccezioni Modbus e risposte tronche bloccano
la pubblicazione dei dati. Indirizzi, lunghezze, scale e tipi dei punti sono
vincolati al profilo canonico anche in presenza di override. Le scritture e il
broadcast sono esclusi anche se viene passato un comando del profilo legacy.
Nessuna selezione di code storiche viene eseguita durante il polling.

Il profilo espone solo stati grezzi. Potenze, correnti, tensioni, contatori e
modulazione restano non disponibili finche formato, scale e indirizzi non sono
verificati. Il test connessione conferma la diagnostica del gateway, senza
confermare modello inverter o potenza. Il profilo non partecipa al riconoscimento
automatico: un registro zero non identifica un GT500.

Il valore iniziale software dell'Unit ID e 1 e deve essere verificato. L'indirizzo
IP 192.168.1.254 viene dal manuale del convertitore; non implica che un impianto
reale usi l'indirizzo predefinito. Il gateway puo sospendere Modbus durante una
sessione PV View, come descritto dal produttore.

## Famiglie native MVX e 480/600

I manuali individuano le sei varianti e descrivono il kit RS485/Modbus, ma le
fonti recuperate non documentano una mappa registri sufficiente per un driver.
Questi sono record di catalogo non operativi, non driver di telemetria completi.
Non contengono punti o comandi e non ereditano quelli di GT Series. Il wizard
mostra lo stato e blocca il proseguimento; backend e test connessione bloccano
anche richieste dirette, senza aprire connessioni. Un override non puo instradare
questi nomi al percorso legacy. Il protocollo TCP rappresenta l'eventuale
gateway Modbus, non una porta Ethernet nativa garantita sull'inverter.

Unit ID 200 e riportato per GT500 480/600 nel manuale di installazione; per MVX,
parametri seriali e indirizzo sono valori da confermare sul kit, non impostazioni
certificate. Nessuno di questi parametri viene utilizzato finche il profilo
rimane non operativo.

## Controllo di potenza: lavoro ancora necessario

Il manuale europeo documenta APC Enable ID 85 e APC percent ID 86, con
disponibilita dipendente dalla configurazione. Sono ID di parametri, non
indirizzi Modbus dimostrati. La percentuale APC e descritta come limite di
corrente nominale impiegato dal controllo di potenza: non viene convertita
automaticamente in kW. Anche il limite MPPT del gateway non viene equiparato
all'APC. La nota del gateway limita FC10 alla scrittura di un registro per
richiesta: una futura implementazione non deve copiarvi la scrittura coordinata
a due registri del driver Sungrow.

Per completare i driver servono mappa del kit/gateway e firmware corrispondenti,
formati e scale, identificazione del dispositivo, sequenza di abilitazione e
riferimento, rilettura e comportamento alla perdita di comunicazione. Quindi
simulatore di protocollo e collaudo fisico. Nessun watchdog viene inventato.

## Compatibilita, verifiche e distribuzione

Il vecchio nome GT Series rimane disponibile per le configurazioni esistenti,
con una nota che ne limita l'ambito. Non sono migrati dispositivi gia configurati.
I metadati di verifica vengono preservati dal resolver anche con override.
Test offline coprono catalogo, percorsi di blocco, override, assenza di scritture,
risposte tronche, perdita di comunicazione e descrizione delle capability.

Questo lavoro e successivo al tag v1.4: non ne riscrive il contenuto e non
costituisce una nuova release pubblicata. Non e stato eseguito alcun deploy IOT.

## Fonti del produttore, ripubblicate da archivi terzi

- [GT500 E/GI e GT630 E: 975-0582-01-01, italiano, giugno 2010 Rev B](https://manualzilla.com/doc/6114549/manuale-uso-gt500e--gt630e), tabella 1-1, sezioni 1-18..1-27 e tabella 2-3.
- [GT500 MVX e MVX PG: 975-0554-01-01](https://iproduct.ils.org.tw/ProductClass/download.aspx?f=Manual%2FProduct%2F71%2FGT500_Operation_EN.pdf).
- [GT500 480/480 PG/600/600 PG: 975-0602-01-01 Rev B](https://manuals.plus/m/70d4e9da29e4257c43c19b8c40b4dc794c3466dfb278e4aadc56e9e7477f8f13.pdf).
- [Installazione GT500 480/600: 975-0601-01-01 Rev B](https://manualzz.com/doc/1512710/schneider-electric-xantrex-gt500-480--480-pg--600--600-pg...), sezione 4-13.
- [Protocollo legacy 503-0068-01-01 Rev E](https://www.scribd.com/document/87991154/Xantrex-Modbus-Serial-Communications-Protocol-Specification), appendice D: ambito GT gateway/Xanbus, non prova di compatibilita GT500.
