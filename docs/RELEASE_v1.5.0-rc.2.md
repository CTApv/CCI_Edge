# v1.5.0-rc.2 — Correzione identificazione PVS-100-TL B2

Gli inverter PVS-100-TL B2 con Common.Md `3Q4200` venivano rifiutati anche con
il profilo B2 corretto, perché il driver riconosceva soltanto il codice `3Q42`
del PICS. Questa prerelease aggiunge l'identificativo completo osservato sul campo
come alias esplicito del solo PVS-100-TL B2.

- Mantiene i controlli su costruttore, taglia e revisione: nessun riconoscimento
  per prefisso generico o suffisso arbitrario.
- Aggiunge test delle letture e del rifiuto di codici simili o profili errati.
- Il driver Aurora e il comando 151 collaudato sono invariati.
- Include il catalogo Aurora e gli strumenti offline della rc.1.

Prima dell'installazione, una lettura isolata con la correzione ha restituito
modello 3Q4200, firmware 2201B, potenza nominale 100 kW, sei MPPT e misure di
potenza e temperatura. Questa evidenza riguarda la telemetria: non certifica
il controllo della potenza, che non è stato provato sugli inverter.

Per i dispositivi che rispondono `3Q4200` selezionare **ABB/FIMER → PVS-100-TL B2**,
non il profilo PVS-100-TL standard. Parametri IP e Unit ID non cambiano.
