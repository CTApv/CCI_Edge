# PV Guardian v1.4.1

Include la definitiva SINVERT della v1.3.7-test-sinvert-definitivo, con sessione
nativa, watchdog e interfaccia unificata, gia compresa nella v1.4.
Include il profilo Sungrow SG110CX Premium e le correzioni dei valori Sungrow
a 32 bit introdotte nella v1.4.

Aggiunge la separazione delle otto sottofamiglie Xantrex GT500:

- GT500 E / E GI con PVGT12542EDI: sola diagnostica passiva degli stati, con
  verifica della salute gateway. Nessuna misura di potenza o modulazione abilitata.
- MVX / MVX PG, 480 / 480 PG, 600 / 600 PG: record di catalogo non operativi,
  con test e provisioning bloccati finche manca la mappa registri verificata.
- Nessun riutilizzo automatico della mappa legacy GT Series/Xanbus, nessuna
  scrittura durante il polling dei nuovi profili e nessun riconoscimento da un
  semplice registro zero.

Lo stato del supporto e visibile nel wizard. I metadati del catalogo sono
preservati anche quando vengono applicati override di profilo.

## Validazione e limiti

346 test backend, compilazione Python, build frontend, controlli UI SINVERT e
configurazioni Compose produzione, pilot e test. Immagini ufficiali Linux ARM64
prodotte dal workflow GitHub, con manifest e checksum.

I test offline non costituiscono collaudo fisico Sungrow o Xantrex. La conferma
SINVERT di scrittura/copia/riferimento rimane distinta dall'effettiva potenza.
Non sono aggiunte nuove autorizzazioni di comando agli inverter.

Dettagli in [XANTREX_GT500_FAMILIES.md](XANTREX_GT500_FAMILIES.md) e
[SUNGROW_SG110CX_PREMIUM.md](SUNGROW_SG110CX_PREMIUM.md).

## Distribuzione

Versione app e tag v1.4.1, frontend 1.4.1. Archivi ufficiali backend/web ARM64,
manifest di release e SHA256SUMS. Il tag v1.4 resta immutato. Il deploy sul solo
IOT 192.168.0.100 e autorizzato separatamente dall'utente e viene eseguito con
verifica identita, backup e rollback; non viene avviata una sessione di comando
SINVERT come parte dell'aggiornamento.
