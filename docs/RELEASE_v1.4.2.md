# PV Guardian v1.4.2

Aggiunge il driver ABB/FIMER PVS-100/120-TL SunSpec con sei profili distinti:
PVS-100-TL e PVS-120-TL, ciascuno nelle versioni standard, B e B2, disponibili
Modbus TCP e RTU, inclusa risoluzione RTU tramite gateway TCP compatibile.

Il driver identifica il codice prodotto prima di leggere o comandare, individua
gli offset SunSpec sul dispositivo, legge i canali MPPT effettivi e usa il
contatore a 64 bit del modello 122 per l'energia totale.

Il limite attivo e temporaneo, con ripristino a 120 secondi e rinnovo della
gestione flotta dopo 45 secondi. Riferimento, temporizzazioni e abilitazione
vengono scritti insieme e riletti; nessun broadcast o retry automatico della
singola scrittura incerta. La conferma della configurazione rimane distinta
dalla potenza fisica. Nessun comando reattivo, on/off o di protezione aggiunto.

Dettagli, prerequisiti e collaudo in [FIMER_PVS_SUNSPEC.md](FIMER_PVS_SUNSPEC.md).
Il supporto e verificato su documentazione ufficiale e simulatore, ancora da
collaudare sull'hardware reale e sul firmware installato.

Include SINVERT definitivo, Sungrow SG110CX Premium e lo stato di supporto
parziale Xantrex della v1.4.1. Corretto il metadato versione loose-envify nel
lockfile frontend, mantenendo il pacchetto effettivo 1.4.0 gia utilizzato.

Validazione: 372 test backend, compilazione Python, installazione dipendenze e
build frontend, controlli UI SINVERT, Compose produzione/pilot/test, immagini
ufficiali Linux ARM64 con manifest e checksum SHA256.

Tag v1.4.2 e frontend 1.4.2. Il deploy autorizzato riguarda solo l'IOT locale
192.168.0.100, con verifica identita, backup e rollback. Nessun nuovo dispositivo
o comando fisico di potenza viene configurato o avviato durante l'aggiornamento.
