# PV Guardian v1.4

Introduzione del profilo dedicato **SUNGROW / SG110CX Premium**, con nove MPPT,
diciotto stringhe, controllo identita e scrittura coordinata del limite di potenza.
Corretta la lettura dei valori Sungrow a 32 bit anche nei profili generici.
I valori non disponibili non vengono piu convertiti in misure apparentemente valide.

Il limite e confermato solo con abilitazione e riferimento riletti concordi.
Le scritture del profilo dedicato sono indirizzate al singolo inverter e non
vengono ripetute dalla stessa operazione dopo un esito incerto. La conferma dei
registri resta distinta dalla conferma della potenza fisica.

Include le funzionalita SINVERT e l'interfaccia unificata della precedente
v1.3.7-test-sinvert-definitivo. Nessuna modifica alle autorizzazioni fisiche SINVERT.

Per la mappa, le fonti, i trasporti supportati e il collaudo da completare vedere
[SUNGROW_SG110CX_PREMIUM.md](SUNGROW_SG110CX_PREMIUM.md).
Il profilo Sungrow e verificato su documentazione e simulatori, ancora da
collaudare sull'hardware reale.

## Validazione

- Backend: 331 test unitari/integrati, inclusa comunicazione TCP su loopback.
- Compilazione Python e build frontend.
- Controlli di presentazione, navigazione e profilo SINVERT.
- Configurazioni Compose produzione, pilot e test SINVERT.
- Immagini di rilascio Linux ARM64 costruite dal workflow GitHub.

## Distribuzione

Tag `v1.4`, versione frontend `1.4.0`. Pacchetto sorgente ottenuto dal tag Git,
manifest e checksum SHA256; immagini backend/web GHCR con tag `v1.4`.
Installazione Docker tramite `deployment/docker/deploy-compose-release.sh`,
seguendo il runbook e mantenendo configurazione e database fuori dal pacchetto.
La pubblicazione non modifica il tag GHCR `latest` e non esegue deploy remoti.

**Per questa release non viene caricato o installato nulla sull'IOT in rete.**
