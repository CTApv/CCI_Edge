# TEST SINVERT — aggiornamento laboratorio 8 novembre 2026

Il banco dichiarato dall'operatore contiene soltanto CPU e CP, senza inverter
o periferiche. Le prove verificano le scritture S7 e la logica PLC; non
convalidano l'esecuzione fisica di avvio, arresto o regolazione.

## Collaudo nella dashboard

1. Aprire SINVERT, scheda **Collaudo**.
2. Abilitare il profilo di collaudo. ON, OFF, Reset e riferimento si inviano
   con un clic, senza riepiloghi di conferma o abilitazioni aggiuntive della pagina.
3. Per il banco senza inverter, confermare esplicitamente **solo CPU e CP**
   e attivare **Banco sola CPU**. La sessione vale dieci minuti, è legata al
   dispositivo e all'endpoint e non sopravvive al riavvio del backend.
4. Impostare il massimo riferimento grezzo nel campo del limite locale.
   Il limite non rappresenta kW o percentuale e rimane obbligatorio.
5. Usare Reset per l'impulso sul bit AUTO/TEST: TRUE, attesa della rilettura
   TRUE, quindi immediatamente FALSE. La conferma del solo impulso non
   dimostra il reset degli allarmi. ON/OFF e potenza si inviano direttamente;
   il riferimento accetta anche Invio da tastiera.
6. Scaricare **traccia e comandi ZIP**. La registrazione dei campioni è
   automatica sul gateway, anche senza browser aperto. Lo ZIP contiene
   JSONL grezzi, audit e CSV della telemetria del dispositivo selezionato.

## Indirizzi e comportamento

- Reset mantiene l'impulso AUTO/TEST richiesto dall'operatore.
- Reset allarmi è un comando separato di riconoscimento collettivo su
  DB402.DBX0.1, documentato dal manuale HMI. Non richiede M55 di avvio.
  Il driver attende l'azzeramento da parte del controller; dopo il timeout
  rimuove il solo bit e segnala esito incerto, senza dichiarare allarmi cancellati.
  Sono sempre necessari profilo scritture abilitato e programma PLC verificato.

- AUTO/TEST posizione i: DB402.DBX(842+194*(i-1)).1; 0=AUTO, 1=TEST.
  Il valore resta impostato fino a un successivo comando o altro produttore.
- Pulsante operatore: stesso byte, bit 0. Impulso di circa 150 ms, poi
  azzeramento. Non si sovrappone un impulso a un bit già attivo.
- L'eco del selettore è nel byte +2, bit 1, della stessa posizione.
- Le posizioni usano una sequenza FB18 condivisa: non si promette controllo
  fisico indipendente di ciascun inverter.
- ON/OFF collettivi restano M34.2/M34.3. Una richiesta ON già attiva in
  modalità banco non viene cancellata per poterla ripetere.
- Il riferimento A resta DB511.DBD32, REAL. La copia attesa è DB944.DBD32,
  ingresso regolatore DB570.DBD2, valore dopo selezione/rampa DB570.DBD140.
- Il riferimento inviato resta scritto in DB511 anche sul banco: non viene
  ripristinato automaticamente. L'esito distingue source_matches, copied e
  regulator_input_confirmed. Nessuna copia non equivale a regolazione applicata.
- Fuori dal banco, il riferimento resta impostato e sono richiesti i
  consensi di campo previsti dal driver. Nessun M55, Local/Remote o watchdog
  viene forzato dal software. Anche sul banco identità CPU, checksum del
  programma (incluso FB18), RUN e dimensioni DB devono corrispondere.
- Il banco consente prove senza feedback inverter solo dopo dichiarazione
  esplicita dell'operatore: disattivarlo PRIMA di collegare periferiche.

## Registrazione e limiti

La traccia registra il polling esistente, senza connessioni S7 aggiuntive:
non cattura ogni ciclo PLC né tutti i pacchetti di rete. Rotazione dei
campioni: quattro file da circa 10 MiB. Il download dell'audit è limitato
agli ultimi 20 MiB del file, filtrati per dispositivo; il file originale
rimane sul gateway. Le scritture Node-RED non entrano nell'audit PV Guardian.
Per correlare Node-RED occorre conservare separatamente il suo journal.

Corretto il trattamento della qualità dei booleani. Esposti Manual ON,
Quick Stop e Local/Remote dal byte DB402.DBB14. Le misure predefinite del
riepilogo non sono considerate misure fisiche quando indisponibili.

## Prova reale di scrittura sul banco del giorno 8

- Verificato il programma prima della prima scrittura.
- OFF M34.3 accettato e consumato.
- Selettore DB402.DBX842.1 scritto TRUE e riletto, quindi ripristinato FALSE;
  eco 844.1 osservata TRUE.
- Pulsante DB402.DBX842.0 scritto TRUE e riletto, quindi ripristinato FALSE.
- M34.2 già attivo prima della prova: ON non riscritto e non cancellato.
- DB511.DBD32 scritto REAL 80 e riletto 80; DB944.DBD32 e DB570.DBD2 restano
  zero, mentre DB570.DBD140 resta 2500. Riferimento ripristinato a zero.
- Registrazione esterna al repository:
  indagine/acquisizioni/bench_writes_20261108/.

Questo aggiornamento è una build locale TEST, non una promozione della
release stabile né una validazione sul campo fotovoltaico.
