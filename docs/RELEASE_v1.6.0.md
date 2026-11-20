# PV Guardian v1.6.0 — SMA Sunny Tripower 60

La v1.6.0 aggiunge il supporto documentato agli SMA STP 60-10 attraverso SMA Inverter Manager. Include le funzionalità già presenti nella v1.5.0-rc.6, compresa la dashboard SINVERT RA1. Non cambia il protocollo Aurora 151 né le mappe SINVERT precedenti.

## Profili nel catalogo

| Profilo SMA | Uso | Comandi |
| --- | --- | --- |
| Inverter Manager — STP 60 (gruppo) | Telemetria aggregata del gruppo | Limite potenza 0–100% di WMax, consenso ON e arresto OFF dell'intero gruppo |
| STP 60-10 — via Inverter Manager (lettura) | Telemetria del singolo inverter | Nessuno |

Il client si collega all'IP dell'Inverter Manager, normalmente sulla porta TCP 502. Non usare l'IP del singolo STP60 come server Modbus. Il Manager usa Unit ID 125, i singoli inverter 126–167. I firmware precedenti alla 1.45 utilizzano rispettivamente 1 e 2–43; confermare l'assegnazione con LCS Tool. La verifica dell'identità controlla anche il ruolo e l'Unit ID restituito dal dispositivo.

Scegliere il profilo di gruppo per comandare e visualizzare l'impianto come un unico inverter. I profili individuali consentono il monitoraggio separato. L'applicazione impedisce di registrare contemporaneamente gruppo e singoli sullo stesso endpoint, per evitare duplicazioni nei totali. Non è ancora una vista gerarchica gruppo/figli.

## Driver e limiti documentati

- Letture di identità, potenza, energia, correnti, tensioni, frequenza, temperature e diagnostica SMA; letture del riferimento e dello stato di limitazione sul Manager.
- Mappa SunSpec fissa del documento SMA 1.5, con conversione dei registri del manuale in indirizzi Modbus a base zero. Controllo di firma SunSpec, intestazioni dei modelli e fattori di scala; valori non disponibili esclusi dai dati validi.
- Massimo una richiesta Modbus al secondo, condiviso fra tutti gli Unit ID dello stesso Manager all'interno di questa istanza PV Guardian. Eventuali altri client esterni non sono coordinati da questo limite.
- Prima di ogni comando: identità aggiornata e verifica IC123. Scrittura del solo registro consentito, seguita da rilettura. Una risposta incerta non provoca la ripetizione automatica della scrittura.
- Il limite di potenza è il registro del manuale 40349 (indirizzo 40348), int16 con fattore -2. Non vengono scritti enable, timeout o rampe: nel profilo SMA questi registri sono di sola lettura. La conferma del limite tiene conto anche dello stato di abilitazione letto.
- ON/OFF usa il registro 40348 (indirizzo 40347) e riguarda l'intero gruppo. Nessun comando broadcast. Non sono esposti restart, protezioni di rete, parametri di accumulo, setpoint reattivi o fattore di potenza in scrittura.
- La temporizzazione SMA rende un comando con identificazione e rilettura più lento del normale obiettivo di due secondi: quattro richieste richiedono almeno circa tre secondi, oltre al tempo di rete/elaborazione. Il risultato distingue accettazione/rilettura dall'esecuzione fisica.

Il profilo non abilita automaticamente il controllo del Manager e non modifica le priorità dei regolatori già presenti nell'impianto. La disponibilità del riferimento in lettura non dimostra la modulazione fisica della potenza.

## Verifica

Test con fixture indipendente della mappa SMA e server Modbus TCP locale: codifica, fattori di scala, valori indisponibili, identità errata, ruoli/Unit ID, scritture limitate ai registri RW, rifiuto ed esito incerto, rilettura, nessun broadcast, ritmi condivisi e integrazione nel controllo di flotta. Stato catalogo: `documented_not_field_tested`.

Verifiche di release: 470 test backend (12 specifici SMA), compilazione Python, build frontend e validazione delle configurazioni Docker Compose production/pilot. Dipendenze del backend installate in un ambiente virtuale isolato dai pacchetti globali del PC.

Prima dell'impiego sul campo verificare firmware e Unit ID, confrontare le misure con LCS Tool e collaudare separatamente limite di potenza e ON/OFF in condizioni concordate. Non è stato contattato né comandato alcun dispositivo SMA reale durante lo sviluppo.

Fonte: [SMA — STP60 / SHP75 / STPS60 SunSpec Modbus Interface, versione 1.5](https://files.sma.de/downloads/STP60_SHP75_STPS60-SunSpec_Modbus-TI-en-15.pdf), §§3.3–3.4, 5.2, 5.3 e 7.2. Il supporto introdotto riguarda STP60 e il relativo Manager; non dichiara supportate le funzioni di accumulo STPS60 o tutta la gamma SMA.
