# v1.5.0-rc.6 ? Dashboard e collaudo SINVERT RA1

Adegua al progetto test sinvert 420 il collaudo della v1.4.2, mantenendo separati
catalogo e driver SINVERT precedenti.

- Dashboard SINVERT dedicata con Panoramica, Allarmi e avvisi, Diagnostica, Collaudo.
- ON/OFF collettivi, AUTO/TEST, pulsante e reset per ciascuno dei quattro gruppi.
- Reset generale dei gruppi configurati; nessuna scrittura dell'ACK non identificato.
- Sorgente HMI DB511 con copia FC501 attiva oppure DB402 con ramo disattivo.
- Riferimento A e watchdog CP della rc.5, abilitazione e limite persistenti.
- 106 punti di lettura, finestre allarmi/avvisi e tracce ZIP/CSV dedicate.
- Verifica aggiuntiva di cinque blocchi, confrontati byte per byte con il progetto.
- Impulsi ritirati anche su ACK perso; nessun reinvio automatico dopo una scrittura.

Il profilo resta disabilitato di default. Controlli e riscontri PLC non certificano
un'esecuzione fisica. Nessun comando di flotta o forzatura di consensi/gate.
Il vecchio protocollo SINVERT e Aurora 151 sono invariati.

Scala fisica, collegamento CP e fallback richiedono collaudo sul campo.
Dettagli e differenze rispetto alla v1.4.2: docs/SINVERT_RA1.md.

Verifiche: 458 test backend (63 RA1), build frontend, controlli SINVERT esistenti
e 11 controlli del modello RA1. Browser desktop/mobile: quattro schede, impostazioni,
preflight, ON/OFF e reset verificati con API locali simulate. Nessuna scrittura
eseguita sul PLC reale durante lo sviluppo.
