# v1.5.0-rc.3 — SINVERT RA1

Aggiunge il driver **SINVERT RA1**, basato sul progetto `test sinvert 420`,
con catalogo e diagnostica separati dal SINVERT precedente.

- Profilo 420 S7-300, KOMM 3.0 / REGEL 3.9.
- Verifica della firma PLC: 12 blocchi e 11 dimensioni DB.
- Lettura del canale CP diretto DB944, riferimenti A/B e ingressi del regolatore.
- Pannello RA1 nella pagina dispositivo, con condizioni e parametri del canale.
- Mappe non modificabili tramite override, letture raggruppate e qualità per punto.
- Scritture non implementate e bloccate anche nel percorso I/O: scala fisica e
  connessione CP richiedono collaudo prima del controllo.

Il catalogo SINVERT M/TL, i relativi comandi e il protocollo Aurora 151 sono
invariati. La prima lettura isolata RA1 sul PLC reale ha riconosciuto il programma
e acquisito i dati senza errori. Nessun comando è stato inviato durante questa prova.

Include le funzionalità delle rc.1 e rc.2. Documentazione: `docs/SINVERT_RA1.md`.

Verifiche: 406 test backend superati e build TypeScript/Vite completata.
