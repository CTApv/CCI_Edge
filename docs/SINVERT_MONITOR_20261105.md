# Monitoraggio e collaudo SINVERT locale

Correzione salvataggio limite: il payload dell'interfaccia includeva
device_id e created_at, vietati dallo schema DeviceUpdate (422 Extra inputs).
Il salvataggio ora seleziona i soli campi ammessi e conserva profile_overrides.
Verificato tramite lo stesso helper frontend e proxy reale: salvataggio del
limite corrente0 con HTTP200, configurazione invariata, nessun comando PLC.
Script: `frontend/scripts/check-sinvert-settings.mjs`.

Correzione successiva agli screenshot329/330: il valore1000000 nel campo
comando era un placeholder del catalogo, non un valore scritto. Sostituito
con un testo che indica il blocco. Con limite0 l'invio rimane disabilitato.
Il driver registra ora la fase del controllo e ripete una sola volta la
preparazione in caso di reset della connessione prima di qualsiasi scrittura.
Dopo un tentativo di scrittura non reinvia automaticamente il comando.
Questa gestione non dimostra la causa originaria del reset10054 del CP.
Verificati214 test backend e verifica frontend attraverso il proxy, senza
nuove scritture al PLC.

Aggiornamento del 5 novembre 2026. Applicazione: http://127.0.0.1:5173.
Aprire il dispositivo SINVERT e ricaricare con Ctrl+F5.

## Cosa è disponibile

- Monitor dei quattro gruppi gestiti dal PLC, con indicazione dei gruppi configurati.
- Stato HMI secondo il programma acquisito: 4=allarmi,3=avvisi,2=in marcia
  secondo la logica PLC,1=non in marcia,0=non determinato/non aggiornato.
  La vecchia codifica del manuale non è applicata alla variante.
- Feedback ON e contattore AC, con origine dichiarata: entrambi dipendono
  dalla formula M55 e non rappresentano due sensori indipendenti.
- Potenza attiva/reattiva, frequenza, tensione AC L1, tensione e corrente DC.
  Le scale sono incrociate con manuale e produttori del software. Le misure
  restano da validare sul campo; dati mancanti, gruppi non configurati e
  segnali di comunicazione non validi producono `--`, non zero.
- Tutti i 128 bit di avvisi e i primi128 bit di allarmi per ciascun inverter,
  corrispondenti alle finestre considerate dalla rete di stato17. Gli altri
  messaggi del DB401 non sono inclusi in questa vista. Le descrizioni sono
  estratti delle righe del manuale con pagina; il significato nella variante
  resta da verificare. Il solo conteggio allarmi non certifica la condizione fisica.
- Dettaglio delle sorgenti di ciascun consenso M55 e dei blocchi del riferimento.
- Catena del riferimento A: DB511→DB944→ingresso FB570→valore dopo selezione/rampa,
  con fallback configurato visibile.

Il profilo acquisisce128 punti per campione mediante letture raggruppate.
Le letture non sono atomiche rispetto al ciclo PLC; eventuali discrepanze
M55/formula sono segnalate e non corrette scrivendo.

## Verifiche senza inviare comandi

Nella sezione **Monitoraggio SINVERT e consensi** sono presenti:

1. **Verifica ON senza inviare**.
2. **Verifica OFF senza inviare**.
3. **Verifica riferimento senza inviare**, con un valore PLC da verificare.

Ogni verifica controlla prima la configurazione locale e, se applicabile,
rilegge identità del programma e condizioni dal PLC, senza
scrivere, senza registrare un comando come eseguito e senza modificare
la configurazione del dispositivo. Un esito positivo non prenota i consensi:
all'invio reale il driver li rilegge. Nel profilo Diagnostica non ci sono
comandi: per le verifiche utilizzare il profilo Collaudo comandi.

## Invio manuale

Correzione successiva del 5 novembre: le verifiche dell'interfaccia ora inviano
esplicitamente Content-Type application/json; l'errore422 è stato riprodotto
nei log e corretto. La verifica usa anche il wrapper frontend reale attraverso
il proxy locale (`frontend/scripts/check-sinvert-preflight.mjs`).
Corretto inoltre il conteggio dello spazio dello storico quando SQLite elimina
un file WAL/SHM tra due operazioni. Suite aggiornata:211 test backend superati.

Restano presenti ON/OFF collettivi e riferimento A grezzo nel profilo Collaudo.
Il dispositivo esistente conserva il collaudo manuale abilitato dall'utente;
il massimo del riferimento resta0, quindi l'invio del riferimento è disabilitato.

Il limite è modificabile direttamente nella vista: **Massimo valore PLC
consentito** → **Salva limite locale senza inviare**. Zero disabilita l'invio;
un limite positivo abilita l'inserimento nell'interfaccia senza inviare nulla.
La configurazione non supera i controlli M55, copia, consenso esterno e watchdog.
Non è stato scelto automaticamente un limite positivo o una scala percentuale.

Le richieste ON/OFF riguardano l'intero PLC. Il comando numerico non è una
percentuale: non impostare un limite o una conversione percentuale basandosi
soltanto sulle scale delle misure. Il ramo A partecipa anche a inserzione e
disinserzione delle posizioni; non è dimostrato un controllo continuo P%.

Dopo una scrittura del riferimento il driver verifica separatamente:

- accettazione S7;
- mantenimento del valore in DB511;
- copia a DB944;
- ricezione all'ingresso FB570.

Anche quattro verifiche positive non dimostrano che il regolatore abbia
selezionato quel valore al posto del fallback o che l'inverter lo abbia
applicato. Gli errori successivi a un tentativo di scrittura sono esiti incerti,
senza reinvio automatico. L'esito distingue ricezione ed esecuzione fisica.

## Stato del banco osservato

PLC192.168.0.245 leggibile;128 punti senza errori nell'API, circa1,3 secondi.
M51 configura i gruppi1 e2. Su entrambi manca DB120.59.5 /133.5; i gruppi3
e4 sono non configurati. I segnali DB120.6.1 /80.1 alimentano il timeout
di comunicazione. Le descrizioni del manuale per i bit attivi includono
Fast OFF; sono mostrate come attribuzioni documentali, senza dedurre che
un pulsante sia fisicamente premuto sul banco privo di periferiche.

Verifica reale preventiva: ON bloccato; OFF verificabile; riferimento bloccato
dal limite0. Nessuna scrittura PLC eseguita durante questo aggiornamento.

## Limiti aperti

Restano da chiudere la scala fisica e la funzione completa del canale A,
la gestione del produttore AG_RECV/watchdog esterno e l'applicazione fisica
dei comandi. È stata individuata una differenza tra sorgente offline e
programma online nel ramo FB570 a0410h: la versione online usa un confronto
numerico dopo la moltiplicazione per1000, anziché il bit DB944.41.0 del sorgente.
Nessun timer, consenso, fallback o arresto PLC è stato modificato per superarla.

Il riepilogo energetico di impianto e lo storico automatico restano esclusi
per questo profilo finché non è validata la qualità delle misure. La vista
dedicata conserva i dati grezzi per la verifica.

Validazione:209 test backend con archivi isolati e build TypeScript/Vite.
Sono stati inoltre verificati quattro segmenti MC7 M55, otto assegnazioni
dei feedback e64 combinazioni booleane; non è una simulazione completa S7.

Rapporti: `indagine/rapporti/VERIFICA_MONITOR_API_20261105.json`,
`VERIFICA_HMI_NATIVA_20261105.json` e `RAPPORTO_MONITOR_E_CONTROLLO_20261105.md`.
