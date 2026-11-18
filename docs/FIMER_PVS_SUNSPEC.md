# ABB/FIMER PVS-100/120-TL SunSpec

Introdotto nella v1.4.2, con profili distinti per taglia e revisione hardware.

| Modello nel catalogo ABB/FIMER | Identificatore nel campo Common.Md | Potenza nominale |
|---|---|---|
| PVS-100-TL | 3P80 | 100 kW |
| PVS-100-TL B | 3Q15 | 100 kW |
| PVS-100-TL B2 | 3Q42 | 100 kW |
| PVS-120-TL | 3P20 | 120 kW |
| PVS-120-TL B | 3Q14 | 120 kW |
| PVS-120-TL B2 | 3Q41 | 120 kW |

Dalla v1.5.0-rc.2 il profilo PVS-100-TL B2 riconosce anche l'identificativo
completo `3Q4200`, osservato sui dispositivi reali con firmware `2201B`.
L'alias è esplicito: altri suffissi, taglie e revisioni restano rifiutati.
Il collaudo del 18/11/2026 riguarda le letture; nessun comando di potenza è stato
eseguito sugli inverter durante questa verifica.

Ogni profilo e disponibile in Modbus TCP e RTU seriale; RTU su TCP usa il
gateway compatibile con framer RTU. Non sono alias della mappa TRIO GT03.
Stato: verificato su documentazione e simulatore, **non collaudato su hardware**.

## Fonte e convenzioni

La mappa in `backend/app/catalog/fimer_pvs_sunspec_map.json` deriva dai fogli
1, 103, 120, 121, 122, 123 e 160 del PICS ufficiale FIMER Rev 005 (15/02/2021).
Contiene offset relativi al modello, tipi, lunghezze e riferimenti ai fattori
di scala; esclude i campi dichiarati non implementati. Dove la colonna Name e
vuota, il foglio usa Label per il nome del campo. Il file registra URL e SHA256
del workbook originale. Gli indirizzi assoluti di riferimento non sono usati
come indirizzi fissi del dispositivo.

Il driver richiede firma `SunS` a PDU 40000 e individua la catena di modelli,
con limiti su numero, lunghezza e indirizzi e controllo di duplicati e terminatore.
Sono richiesti Common 1 lunghezza 66 e inverter 103 lunghezza 50. Modelli nuovi
o formati differenti richiedono verifica, senza ripiego silenzioso sul generico.
Le letture sono holding FC03; byte e parole multi-registro big endian secondo
SunSpec. Sono gestite le sentinelle distinte di interi, scale e accumulatori.

L'identita viene verificata a ogni polling, anche usando la mappa in cache per
30 secondi. Il codice prodotto deve corrispondere alla variante scelta. Ogni
comando esegue una nuova discovery; la potenza WRtg deve corrispondere alla
taglia e WMax deve essere leggibile, positivo e coerente con WRtg. Gli override
non possono modificare mappa, tipo, scala o politica dei comandi verificati.
Il discovery generico non attribuisce una variante sulla sola firma SunSpec.

## Telemetria

- Common: costruttore, codice modello, firmware e seriale.
- 103: potenza attiva/reattiva/apparente, correnti, tensioni trifase, frequenza,
  fattore di potenza, stati, eventi, potenza/corrente DC, temperature wiring box
  e dissipatore.
- 120/121: potenza nominale WRtg e base di limitazione WMax.
- 122: energia totale esportata ActWh, accumulatore a 64 bit in Wh convertito
  in kWh. Il campo WH del modello 103 non viene usato come energia totale.
- 123: riferimento percentuale, abilitazione, rampa, finestra e timeout.
- 160: numero reale di canali e misure di tensione/corrente/potenza/stato fino
  a sei MPPT. I canali oltre N e i modelli opzionali assenti restituiscono dato
  non disponibile, senza zeri artificiali. La tensione DC non viene ricavata
  dal campo DCV non implementato del modello 103.

## Limitazione attiva

Sono esposti solo il limite attivo 0..100% e la disabilitazione del limite.
Non sono implementati comandi di avvio/arresto, regolazione reattiva o modifica
delle protezioni. La percentuale e riferita al WMax effettivo del modello 121,
non automaticamente ai 100/120 kW di targa. WMax non viene scritto dal driver.

Un comando 55.5%, con fattore percentuale letto -1, codifica il riferimento 555.
Un'unica richiesta FC16 scrive dal modello 123 offset 5:

`[riferimento, finestra=0, ripristino=120, rampa=0, abilitazione=1]`.

L'abilitazione viene riscritta anche per i rinnovi. La rampa del comando tecnico
e zero, mentre le limitazioni/protezioni interne dell'inverter restano efficaci.
Il firmware gestisce il ripristino in multipli di 60 secondi: 120 e rappresentabile
senza arrotondamento. Non viene usato timeout zero per il controllo dinamico,
per evitare la persistenza ripetuta in memoria non volatile descritta da FIMER.
La disabilitazione esplicita scrive solo zero al registro di abilitazione.

Il comando manuale e temporaneo: senza rinnovi, dopo 120 s l'inverter ripristina
i propri valori predefiniti, che devono essere verificati durante il collaudo.
Con target flotta attivo, la riconciliazione rinnova dopo 45 s dall'ultimo invio
(al ciclo successivo). Nessun thread driver continua a inviare dopo l'arresto
del backend o la rimozione del target. Ritardi di comunicazione, backoff o cicli
molto lunghi possono far scadere il limite: non e un vincolo di tempo reale.

Le scritture richiedono un indirizzo 1..247; nessun broadcast. Il driver valida
l'ACK FC16 e rilegge tutti i registri scritti. Dopo risposta persa o discordante
la singola operazione restituisce esito incerto senza ritentare la scrittura;
successivi cicli flotta seguono il backoff esistente. La conferma telemetrica
richiede valore di buona qualita, enable=1, timeout=120, rampa=0 e finestra=0.
La conferma dei registri non dimostra la potenza fisica erogata.

## Configurazione e collaudo

Sul firmware storico abilitare Modbus TCP Server e Modbus Power Control, quando
presenti. Sul firmware B2 configurare il ruolo server; per RTU scegliere Modbus
SunSpec Server, non Device Acquisition (ruolo master). Indirizzo, baud rate,
parita, accessi e priorita di controllo vanno confermati sull'inverter reale.
19200 8N1 e Unit ID 1 sono valori iniziali software, non una configurazione
hardware certificata per ogni revisione.

Prima dell'esercizio: verificare targhetta/codice/firmware, confrontare misure
con interfaccia inverter, provare limiti e disabilitazione, rinnovi e perdita
di comunicazione, e osservare ripristino e potenza con misura indipendente.
I test offline coprono i sei identificatori, offset spostati, due/sei MPPT,
sentinelle, energia a 64 bit, ACK perso, rifiuti, rilettura discordante, guardie
di trasporto e comandi, rinnovo flotta e Modbus TCP reale su loopback.

## Fonti

- [Pagina ufficiale FIMER e documenti PVS-100/120-TL](https://www.fimer.com/three-phase/pvs-100120-tl).
- [PICS ufficiale Rev 005, XLSX in ZIP](https://www.fimer.com/sites/default/files/SUNSPEC_PVS-100_120_PICS_Rev_005.zip).
- [Manuale ufficiale B2 Rev H](https://www.fimer.com/sites/default/files/FIMER_PVS-100_120-TL%20B2%20Version_Product%20manual_EN_Rev%20H.pdf).
- [Definizione SunSpec modello 123](https://github.com/sunspec/models/blob/master/json/model_123.json).
