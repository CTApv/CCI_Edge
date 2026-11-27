# Xantrex GT500: famiglie e interfacce

Le famiglie GT500 non ereditano la mappa legacy `GT Series` via gateway/Xanbus.
Questa integrazione separa le otto varianti documentate e rende esplicito lo
stato effettivo del supporto. GT500 E e stato collaudato il 27 novembre 2026.

| Profilo | Interfaccia nel catalogo | Supporto attuale |
|---|---|---|
| GT500 E / PVGT12542EDI | Modbus TCP | Telemetria e limite MPPT collaudati |
| GT500 E GI / PVGT12542EDI | Modbus TCP | Stessa mappa; hardware da collaudare |
| GT500 MVX | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 MVX PG | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 480 | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 480 PG | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 600 | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |
| GT500 600 PG | Modbus RTU; TCP tramite gateway da verificare | Non operativo: mappa mancante |

## Driver europeo v1.6.2

Il 27 novembre 2026 sono stati collaudati due GT500 E dell'impianto RCA,
tramite convertitori Schneider XAGT10042ED, interfaccia web v1.1, firmware
inverter H=0x0710/L=0x0C0D. La variante GI condivide la mappa documentata ma
resta da collaudare sull'hardware.

FC03 legge il blocco PDU 0..33 in una richiesta. Gli stati comunicazione e
inverter, lunghezza e formato sono validati prima di pubblicare i dati.
Il guasto di un inverter non viene confuso con una perdita di comunicazione:
lo stato fault sospende i comandi flotta fino al rientro del guasto.
Anche i cicli rapidi conservano stati e riferimento.

| Valore | Offset PDU | Formato |
|---|---:|---|
| Gateway, obiettivo, sistema, guasto, inverter, FV | 0..5 | uint16 |
| Versioni firmware H/L | 6..7 | uint16 grezzi |
| Tensioni AC A-B/B-C/C-A | 12..14 | uint16 V |
| Potenza attiva | 18 | int16, 0.1 kW |
| Temperatura matrice | 19 | int16 C |
| Tensione DC | 21 | uint16 V |
| Corrente DC | 22 | int16 A |
| Potenza DC | 23 | int16, 0.1 kW |
| Frequenza | 24 | uint16, 0.1 Hz |
| Limite corrente MPPT | 31 (manuale 32) | uint16, 0..100% |

Le scale di potenza sono state confrontate con tensione/corrente DC e risposta
alla limitazione in campo; il collaudo non e una taratura metrologica.
Contatori energia e correnti AC restano esclusi in attesa di validazione.
Il polling non esegue scritture e non partecipa all'identificazione automatica.

## Comando e rilettura

Abilitare il booleano `connection_settings.xantrex_pvgt_control_enabled=true`
solo dopo conferma della mappa sul sito. Il default false evita di abilitare
comandi su siti non collaudati al solo aggiornamento della release.
Il driver verifica firmware 0710/0C0D, obiettivo MPPT e assenza di guasti.

Si scrive solo FC16, un registro a PDU 31, con passo 1%; le richieste frazionarie
sono arrotondate al punto percentuale piu vicino. Nessun reset, arresto, APC
ID 85/86, fattore di potenza o broadcast. Un riferimento gia corrispondente
non viene riscritto. Il limite e persistente, senza scadenza documentata:
il ripristino richiede un nuovo riferimento, normalmente 100%.

Polling e comandi condividono sessione e lock dello stesso endpoint. I gateway
provati accettano una sola connessione: non aprire una seconda sessione per
il controllo. Il timeout socket di scrittura coincide con quello di polling
per evitare che il connection manager ricrei la sessione.

La cache del gateway aggiorna i valori con ritardo. Dopo ACK, il driver rilegge
ogni 0.5 s fino a 12 s e conferma solo il riferimento effettivamente osservato.
Un timeout segnala esito incerto; un errore dopo invio non causa replay
automatico. `physical_execution_confirmed=false` distingue il riferimento
confermato dalla verifica fisica della produzione.

## Collaudo RCA

Endpoint 192.168.0.16, .26 e .36, TCP 502, Unit ID 1.
Su .16 e .26: sequenza 100 -> 2 -> 100, forte riduzione della potenza e
rilettura dei riferimenti ripristinati. Una lettura immediata era rimasta al
vecchio valore: questo ritardo ha motivato la conferma fino a 12 secondi.
Sul terzo inverter: sistema 7, guasto grezzo 53 (0x0035), nessuna produzione;
nessun reset o collaudo fisico di modulazione. Il suo canale e la firma firmware
sono stati verificati e il controllo resta pronto per il rientro del guasto.

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

## Compatibilita e verifiche

GT Series, MVX e 480/600 mantengono il proprio ambito. Le configurazioni GT500 E
esistenti ricevono la telemetria, ma i comandi richiedono il consenso di
commissioning descritto sopra. La release non inventa watchdog inverter.
I test coprono conferma ritardata, timeout incerto, ACK errato, perdita ACK
senza reinvio, firmware estraneo, override, guasti, idempotenza, risposta
tronca, formato firmato e stato fault distinto dalla comunicazione online.

## Fonti del produttore, ripubblicate da archivi terzi

- [GT500 E/GI e GT630 E: 975-0582-01-01, italiano, giugno 2010 Rev B](https://manualzilla.com/doc/6114549/manuale-uso-gt500e--gt630e), tabella 1-1, sezioni 1-18..1-27 e tabella 2-3.
- [GT500 MVX e MVX PG: 975-0554-01-01](https://iproduct.ils.org.tw/ProductClass/download.aspx?f=Manual%2FProduct%2F71%2FGT500_Operation_EN.pdf).
- [GT500 480/480 PG/600/600 PG: 975-0602-01-01 Rev B](https://manuals.plus/m/70d4e9da29e4257c43c19b8c40b4dc794c3466dfb278e4aadc56e9e7477f8f13.pdf).
- [Installazione GT500 480/600: 975-0601-01-01 Rev B](https://manualzz.com/doc/1512710/schneider-electric-xantrex-gt500-480--480-pg--600--600-pg...), sezione 4-13.
- [Protocollo legacy 503-0068-01-01 Rev E](https://www.scribd.com/document/87991154/Xantrex-Modbus-Serial-Communications-Protocol-Specification), appendice D: ambito GT gateway/Xanbus, non prova di compatibilita GT500.
