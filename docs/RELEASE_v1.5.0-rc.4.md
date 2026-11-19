# v1.5.0-rc.4 ? Collaudo SINVERT RA1

Aggiunge alla pagina RA1 il collaudo tecnico dedicato al progetto test sinvert 420.

- Preflight in sola lettura con programma, CPU, condizioni e riscontri.
- Prova S7 del riferimento A su banco CPU/CP isolato con ripristino controllato.
- Sessione CP con TSAP obbligatori e confermati, telegrammi ogni 0,8 s,
  riscontro del regolatore/watchdog e lease di 60 s con rinnovo manuale.
- Arresto per perdita condizioni/riscontro/cadenza; nessun reconnect automatico.
- Verifica aggiuntiva di FC500, confrontato byte per byte con il progetto.
- Nessuna forzatura di consensi, gate, uscite o watchdog; nessun comando di flotta.

Scala fisica, parametri CP e fallback effettivo richiedono collaudo sul campo.
Installazione e avvio dei servizi non inviano comandi al PLC. La prova S7 non
certifica il canale CP; fermare gli invii CP non equivale a un comando OFF.
Il vecchio catalogo/driver SINVERT e Aurora 151 rimangono invariati.

Dettagli: docs/SINVERT_RA1.md.

Verifiche locali: 430 test backend (24 del collaudo RA1), build TypeScript/Vite e
controlli SINVERT esistenti superati. Nessuna scrittura eseguita sul PLC reale.
