# Dashboard SINVERT — anteprima locale

Anteprima di valutazione, 5 novembre 2026.

Aprire **http://127.0.0.1:5173/sinvert.html** con PV Guardian locale avviato.
L'indirizzo principale `http://127.0.0.1:5173/` conserva la vista precedente.
La nuova pagina usa API e dati reali esistenti; non è stata resa la dashboard
predefinita e non è stata pubblicata o installata su altri dispositivi.

## Percorso operatore

**Panoramica:** separa connessione al PLC, qualità dei feedback dei gruppi e
modalità dell'interfaccia. Quattro schede inverter, posizioni non configurate
ridotte, motivi di blocco comprensibili e riepiloghi con qualità esplicita.
Nessuna potenza o condizione fisica è inventata per riempire la grafica.

**Allarmi e avvisi:** tabella dei bit attivi dei gruppi configurati, filtro per
tipo e ricerca per descrizione, inverter o indirizzo. Le descrizioni conservano
la pagina del manuale e l'avvertenza sulla variante. Il conteggio riguarda le
finestre monitorate, non tutti gli allarmi dell'impianto. I bit residui delle
posizioni non configurate non entrano nei riepiloghi.

**Collaudo:** condizioni espresse in linguaggio operatore; attivazione manuale
limitata alla pagina; verifica preventiva; riepilogo della destinazione e
dell'ambito collettivo prima dell'invio. Il driver esistente esegue nuovamente
i controlli lato PLC. In apertura e dopo un ricaricamento la pagina è in
consultazione, anche se il profilo backend consente il collaudo.

Il riferimento numerico è confinato al collaudo tecnico. La pagina mostra
ricezione esterna, copia PLC, ingresso regolatore e valore dopo selezione/rampa.
Il limite locale si modifica in un pannello espandibile. Non vengono proposti
setpoint kW/% finché la conversione non è validata; il limite1000 precedentemente
salvato dall'utente non viene reinterpretato come potenza nominale.

**Diagnostica:** formula dei consensi, indirizzi, codici della variante,
provenienza dei feedback, qualità e telemetria grezza. Le indicazioni HMI ON
e contattore AC non sono presentate come due conferme indipendenti.

**Esito:** ogni operazione ha il nome del comando e l'ora. Le verifiche sono
esplicitamente in sola lettura; gli invii distinguono accettazione S7,
elaborazione PLC e conferma fisica, che rimane non validata. Gli errori di
backend e i campioni non aggiornati non producono valori sostitutivi a zero.

## Implementazione

- Entry separata: `frontend/sinvert.html` e `frontend/src/sinvert/main.tsx`.
- Dashboard: `frontend/src/sinvert/SinvertDashboard.tsx`.
- Regole di presentazione e qualità: `frontend/src/sinvert/presentation.ts`.
- Stile dedicato: `frontend/src/sinvert/sinvert.css`, senza dipendenze grafiche
  o font esterni e senza applicare lo stile alla pagina attuale.
- Build Vite con due entry, principale e SINVERT. Il backend e il driver non
  sono stati modificati per questa anteprima.

Il passaggio tra dispositivi azzera il collaudo e il riepilogo. Il riepilogo è
associato all'identificativo del dispositivo verificato. Il dialogo gestisce
focus da tastiera, Tab, Escape e annullamento. Navigazione mobile dedicata.

## Verifiche

`npm run build` genera entrambe le pagine.

`node scripts/check-sinvert-presentation.mjs` verifica20 condizioni su aggregati,
campioni mancanti/stale, backend offline, gruppi non configurati, valori non
finiti, codici sconosciuti e formulazioni degli operatori.

`node scripts/check-sinvert-dashboard.mjs` usa Chrome headless locale per7
scenari: consultazione iniziale; filtri allarmi; verifica OFF reale in sola
lettura; riepilogo e annullamento; riapertura con collaudo disattivato;
layout mobile390px; backend non raggiungibile. Gli endpoint di comando sono
bloccati nel browser di test, le richieste vengono contate e l'impronta del
registro delle scritture PLC viene confrontata prima/dopo. Nessun comando
PLC è stato inviato durante lo sviluppo o queste prove.

Risultati e screenshot desktop/mobile:
`indagine/rapporti/dashboard_sinvert/checks.json` e file PNG nella stessa cartella.
Lo script visuale richiede Chrome Windows e il modulo `ws` disponibili su
questo PC; non sono dipendenze della dashboard distribuita.

## Da valutare prima dell'integrazione definitiva

Valutare leggibilità, organizzazione e flusso di collaudo sulla pagina separata.
L'approvazione della dashboard non equivale alla validazione del protocollo:
rimangono aperti scala fisica del riferimento, funzionamento completo della
modulazione e verifica sul campo già descritti nei rapporti di reverse engineering.
