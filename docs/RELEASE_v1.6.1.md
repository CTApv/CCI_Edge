# PV Guardian v1.6.1 — Nome impianto dalla Control Room

La dashboard mostra **Nome impianto** al posto del campo Host con il nome automatico del container. Il valore proviene dalla configurazione dell'impianto nella Control Room, viene conservato sul dispositivo e resta disponibile anche senza connessione alla Control Room. Se non è ancora configurato appare «Impianto da configurare». Il nome è visibile anche nel footer mobile, con troncamento dei nomi lunghi e testo completo nel titolo.

L'ID edge e l'hostname tecnico restano invariati; quest'ultimo rimane disponibile nelle API diagnostiche. La nuova etichetta non rinomina Linux, Docker o il nodo Tailscale.

## Sincronizzazione

Il collector della Control Room legge il nome registrato durante la messa in servizio e lo invia all'edge al successivo ciclo utile. Una rinomina viene propagata allo stesso modo. Se il dispositivo è offline, il nome già memorizzato sull'edge resta disponibile e il collector ritenta nei cicli successivi. Il rientro a magazzino cancella il nome sull'edge quando questo torna raggiungibile. Il tempo effettivo dipende dall'intervallo del collector e dalla dimensione della flotta.

La sorgente principale è `custom_name` dei metadati di commissioning della Control Room. Il campo `plant_name` del catalogo flotta viene usato per i dispositivi configurati manualmente che non hanno ancora uno storico di commissioning. L'assenza di metadati autorevoli non cancella un nome già presente.

Gli edge precedenti alla v1.6.1 non ricevono richieste di aggiornamento del nome: la presenza di `identity.plant_name` nella risposta health segnala il supporto. Un errore di sincronizzazione non blocca la raccolta della telemetria. Non vengono inviati credenziali amministrative o token della Control Room agli edge.

## Persistenza e API

- File `plant_identity.json` accanto al database applicativo, normalmente `/var/lib/pv-edge-manager/plant_identity.json`, nel volume dati persistente esistente.
- Salvataggio atomico, nome di massimo 200 caratteri e verifica dell'ID edge destinatario.
- Revisione dei metadati per respingere aggiornamenti superati o conflittuali. Il controllo dell'ID evita errori di destinatario e non sostituisce l'autenticazione di rete.
- `PUT /api/system/plant-identity`: JSON con `edge_id`, `plant_name` e `revision` opzionale; nome vuoto per cancellare l'associazione. Il canale di gestione usa la stessa rete fidata delle API edge esistenti: mantenerne limitato l'accesso tramite le ACL di rete.
- `GET /api/system/health`: aggiunge `identity.plant_name` senza rimuovere `identity.hostname`. Non serve riavviare il backend dopo una rinomina.

## Control Room

La modifica companion del collector è inclusa in `deployment/control-room`: helper, patch di integrazione e test. Va installata sul backend Control Room, non sugli edge. Il servizio Control Room su `100.120.132.11` è stato aggiornato e riavviato dopo backup e test. Gli edge richiedono la v1.6.1 per esporre il nuovo campo e la relativa API.

## Verifiche

- 477 test backend edge, inclusi sette dedicati al nome impianto e i dodici SMA già presenti.
- 82 test della Control Room, inclusi quattro sulla sincronizzazione.
- Prova HTTP locale del vero helper Control Room contro la nuova API edge: primo salvataggio, rinomina, lettura health e rifiuto di un ID edge diverso; verifica della persistenza dopo l'arresto del server simulato.
- Build frontend, controlli di presentazione/routing/profilo SINVERT e configurazioni Docker Compose.

La v1.6.1 mantiene il supporto SMA della v1.6.0; non modifica mappe o comandi inverter, il protocollo Aurora 151 o le pagine SINVERT. Il collaudo SMA sull'hardware rimane da eseguire. La pubblicazione della release non installa automaticamente questo aggiornamento sugli IOT.
