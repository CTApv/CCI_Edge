# Sungrow SG110CX Premium

Profilo dedicato introdotto in PV Guardian v1.4, disponibile Modbus RTU seriale,
RTU su gateway TCP e Modbus TCP. Identita attesa: input 5000 = `0x2C06`.
Il modello SG110CX-P2 richiede un profilo distinto. Il collegamento Ethernet
dipende dagli accessori/logger/gateway installati: la presenza della presa o del
profilo software non garantisce che il dispositivo esponga Modbus TCP.

## Mappa verificata sulla documentazione

I numeri sotto sono quelli del manuale; l'indirizzo PDU e sempre numero meno uno.
Input: funzione 04; holding: funzione 03; scritture: funzione 10 esadecimale.
Byte big endian, valori a 32 bit con parola meno significativa per prima.

| Misura | Registro manuale | Formato e scala |
|---|---|---|
| Tipo dispositivo | input 5000 | U16, atteso 0x2C06 |
| Energia totale | input 5004-5005 | U32, kWh |
| Potenza DC | input 5017-5018 | U32, W convertiti in kW |
| Potenza attiva | input 5031-5032 | U32, W convertiti in kW |
| Potenza reattiva | input 5033-5034 | S32, var convertiti in kvar |
| MPPT 1/2/3 | input 5011/5013/5015 e successivo | 0.1 V / 0.1 A |
| MPPT 4/5/6/7/8 | input 5115/5117/5119/5121/5123 e successivo | 0.1 V / 0.1 A |
| MPPT 9 | input 5130-5131 | 0.1 V / 0.1 A |
| Correnti stringhe 1..18 | input 7013..7030 | 0.01 A |
| Riferimento regolazione potenza | input 5077-5078 | U32, W convertiti in kW |
| Abilitazione limite | holding 5007 | 0xAA abilitato, 0x55 disabilitato |
| Limite potenza | holding 5008 | U16, 0.1%, intervallo 0..110% |

Gli ultimi MPPT, le stringhe e il riferimento di regolazione sono letture
opzionali, per non invalidare tutta la telemetria se il firmware le rifiuta.
I valori indisponibili U16=FFFF, S16=7FFF, U32=FFFFFFFF, S32=7FFFFFFF
sono rimossi prima della conversione di scala. La correzione dell'ordine delle
parole a 32 bit riguarda anche i tre profili generici Sungrow gia presenti.
Verificare eventuali override personalizzati e discontinuita negli storici.

## Scritture e conferme

Ogni comando del profilo dedicato richiede una lettura fresca del codice modello.
Un codice diverso o una lettura fallita blocca la scrittura. Indirizzi, formati e
scale dei comandi devono corrispondere alla mappa canonica. Nessun broadcast.
Un limite del 55.5% scrive insieme `[0xAA, 555]` a partire da PDU 5006,
quindi verifica entrambi i registri holding. Il controllo flotta continua ad
accettare riferimenti percentuali 0..100, mentre il comando tecnico ammette
0..110 secondo il protocollo.

La conferma della flotta richiede sia il riferimento richiesto sia l'abilitazione
0xAA. La rilettura certifica la configurazione, non l'erogazione fisica. Una
risposta persa o una rilettura non concorde lascia esito incerto; la singola
operazione non ritenta automaticamente la scrittura. Questo non elimina nuove
richieste esplicite o successivi cicli di riconciliazione della flotta.

Start/Stop accetta solo 0xCF/0xCE e restituisce la conferma di ricezione, senza
dichiarare avvio/arresto fisico. Il fattore di potenza usa holding 5019 S16,
scala 0.001 e intervalli -1..-0.8 oppure 0.8..1. Il comando verifica prima che
holding 5036 sia gia 0xA1; la selezione delle modalita reattive resta fuori da questo profilo.
Il contatore Heart Beat input 5143 e una lettura, non un watchdog da scrivere.

## Evidenze e collaudo ancora necessario

Stato catalogo: `documented_not_field_tested`, `field_tested=false`.
Verifiche offline: catalogo, conversioni, sentinelle, identita errata, valori
non validi, risposta persa, rilettura discordante e scambio Modbus TCP reale su
loopback con la versione pymodbus fissata nelle dipendenze.

Prima dell'impiego in campo occorre verificare targhetta, firmware, accessorio di
comunicazione e autorizzazioni di controllo, confrontare le misure con il display
e provare limiti e ripristino osservando la potenza fisica. Nessuna prova offline
costituisce collaudo di inverter o gateway reali.

Fonti del produttore:

- [Protocollo Sungrow V1.1.53, 2023-01-13, copia pubblicata da KP Energy](https://shop.kpenergy.se/globalassets/product-sheets/inverters/sungrow/130675/ti_20230117_communication-protocol-of--residential-and-commerical-pv-grid-connected-inverter_v1.1.53_en.pdf): convenzioni, tabelle input/holding e appendice 5 SG110CX.
- [Scheda SG110CX Premium AU V11](https://info-support.sungrowpower.com/application/pdf/2022/04/25/DS_20220310_%20%20SG110CX%20Premium%20AU_V11_EN.pdf): nove MPPT, due stringhe per MPPT, comunicazioni opzionali.
- [Manuale SG110CX](https://ger.sungrowpower.com/upload/file/20231025/EN_UM_SG110CX_User%20Manual.pdf).
