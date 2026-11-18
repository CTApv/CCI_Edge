# Catalogo Power-One Aurora: copertura e validazione

Aggiunti 40 profili con identità documentata. Totale Aurora: 49 profili, compresi gli 8 PowerOne preesistenti e il generico.

La presenza nel catalogo non equivale a un collaudo del driver. I nuovi profili espongono la telemetria Aurora generica da verificare sul dispositivo e non espongono comandi di potenza. I profili precedenti conservano nomi e comandi per compatibilità con le configurazioni esistenti; questo lavoro non ne certifica il controllo su ogni firmware.

Le etichette dei software proprietari sono conservate senza dedurre equivalenze commerciali: PVI-TRIO-30-OUTD non viene automaticamente trattato come TRIO-27.6-TL-OUTD. Le varianti paese, le opzioni e il firmware devono essere acquisiti dal dispositivo. Nessuna nuova associazione automatica a part number è stata inventata.

## Profili aggiunti

| Famiglia | Modello / identità | Evidenza |
| --- | --- | --- |
| pvi_legacy | PVI-2000 | manufacturer_software_label |
| pvi_legacy | PVI-3600 | manufacturer_software_label |
| pvi_outd | PVI-1700-OUTD | manufacturer_software_label |
| pvi_outd | PVI-2000-OUTD | manufacturer_software_label |
| pvi_outd | PVI-3000-OUTD | manufacturer_software_label |
| pvi_outd | PVI-3600-OUTD | manufacturer_software_label |
| pvi_outd | PVI-5000-OUTD | manufacturer_software_label |
| pvi_outd | PVI-6000-OUTD | manufacturer_software_label |
| pvi_outd | PVI-3.0-OUTD | manufacturer_software_label |
| pvi_outd | PVI-3.3-OUTD | manufacturer_software_label |
| pvi_outd | PVI-3.6-OUTD | manufacturer_software_label |
| pvi_outd | PVI-3.8-OUTD | manufacturer_software_label |
| pvi_outd | PVI-4.2-OUTD | manufacturer_software_label |
| pvi_outd | PVI-10.0-OUTD | manufacturer_software_label |
| pvi_outd | PVI-12.5-OUTD | manufacturer_software_label |
| pvi_indoor | PVI-1700-IND | manufacturer_software_label |
| pvi_isolated | PVI-3.8-I-OUTD | manufacturer_software_label |
| pvi_isolated | PVI-4.6-I-OUTD | manufacturer_software_label |
| pvi_isolated | PVI-10.0-I-OUTD | manufacturer_software_label |
| pvi_isolated | PVI-12.5-I-OUTD | manufacturer_software_label |
| uno_isolated | UNO-2.0-I | manufacturer_software_label |
| uno_isolated | UNO-2.5-I | manufacturer_software_label |
| trio_software_identity | PVI-TRIO-20-OUTD | manufacturer_software_label |
| trio_software_identity | PVI-TRIO-30-OUTD | manufacturer_software_label |
| central_module | PVI-MODULE-50 | manufacturer_software_label |
| central_module | PVI-MODULE-55.0 | manufacturer_software_label |
| central_software_identity | PVI-CENTRAL-50 | manufacturer_software_label |
| central_software_identity | PVI-CENTRAL-250 | manufacturer_software_label |
| central_software_identity | PVI-CENTRAL-350 | manufacturer_software_label |
| pvi_tl_outd | PVI-3.0-TL-OUTD | manufacturer_manual |
| pvi_tl_outd | PVI-3.6-TL-OUTD | manufacturer_manual |
| pvi_tl_outd | PVI-4.2-TL-OUTD | manufacturer_manual |
| trio_tl_outd | TRIO-20.0-TL-OUTD | manufacturer_manual |
| trio_tl_outd | TRIO-27.6-TL-OUTD | manufacturer_manual |
| central_modular_tl | PVI-CENTRAL-50-TL-YY | manufacturer_manual |
| central_modular_tl | PVI-CENTRAL-100-TL-YY | manufacturer_manual |
| central_modular_tl | PVI-CENTRAL-150-TL-YY | manufacturer_manual |
| central_modular_tl | PVI-CENTRAL-200-TL-YY | manufacturer_manual |
| central_modular_tl | PVI-CENTRAL-250-TL-YY | manufacturer_manual |
| central_modular_tl | PVI-CENTRAL-300-TL-YY | manufacturer_manual |

## Fonti

- Software locali del costruttore: Aurora Communicator e Aurora Manager TL. Inventario SHA256 e analisi statica conservati fuori dal repository, in indagine/aurora_software_20261118.
- Manuale Power-One PVI-CENTRAL-XXX-TL-YY Rev 1.1 del 30 maggio 2008, fornito dall'utente. I profili Central rappresentano identità di rack ma il collegamento del driver resta a un singolo indirizzo di modulo; aggregazione del rack non implementata.
- [PVI-3.0/3.6/4.2-TL-OUTD, guida del costruttore Rev F](https://www.fimer.com/sites/default/files/PVI-3.0_3.6_4.2-TL-OUTD-Quick%20Installation%20Guide%20EN-RevF.pdf).
- [TRIO-20.0/27.6-TL-OUTD, guida del costruttore BCM.00202.1](https://www.fimer.com/sites/default/files/TRIO-20.0-27.6_Quick-Installation-Guide_BCM.00202.1.pdf): la porta deve essere impostata su Aurora, non sulla modalità alternativa Modbus RTU.

## Lavoro ancora necessario per una copertura completa

Aggiornamento offline: vedere [AURORA_OFFLINE_VALIDATION.md](AURORA_OFFLINE_VALIDATION.md).
Il comando 151 collaudato resta invariato. Sono disponibili strumenti per leggere
catture già registrate e classificare evidenze firmware, senza aprire connessioni.
I codici modello del software sono ora presenti nei metadati del catalogo, senza
abilitare nuove associazioni automatiche.

- Verificare per famiglia le misure supportate: il template generico non dimostra che ogni TOM esista su ogni revisione.
- Ricostruire identificativi e firmware dai software per riconoscimento non ambiguo.
- Manager TL conferma opcode 151 e letture 83/132–135; completare il collaudo reale di decodifica, timeout, rampa e riscontro del limite.
- Central CVI contiene anche un percorso legacy opcode 60, selettore 46 e float: completare unità, inizializzazione, riscontro e selezione firmware prima di abilitarlo.
- Gestire Central come rack composto da moduli, con aggregazione senza doppio conteggio e corretta distribuzione del limite.
- Ampliare la ricerca alle ulteriori varianti UNO/TRIO/PVI e alle generazioni successive con protocolli diversi. Il catalogo non è ancora dichiarato esaustivo di tutti i prodotti venduti sotto i marchi Power-One, ABB e FIMER.

La copertura è inclusa nella prerelease v1.5.0-rc.1. Nessun deploy sull'IOT.
