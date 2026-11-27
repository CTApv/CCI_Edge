# PV Guardian v1.6.2 - Xantrex GT500 E: telemetria e modulazione MPPT

Il profilo europeo GT500 E / PVGT12542EDI legge potenza attiva, dati DC,
frequenza, temperatura, stati e guasti e controlla il limite MPPT sul registro
manuale 32 (PDU 31), con conferma ritardata fino a 12 secondi.
Polling e comandi condividono la sessione TCP dei convertitori Schneider.
Un inverter in guasto viene mostrato come fault e sospeso dal controllo flotta,
anche quando la comunicazione Modbus e regolare.

Il controllo richiede `xantrex_pvgt_control_enabled=true` dopo collaudo della
mappa sul sito. Default disabilitato. Scritture limitate al firmware collaudato
0710/0C0D e al solo registro MPPT, passo 1%. Nessun reset, on/off, APC non
mappato o comando reattivo. Limite persistente, senza scadenza automatica.
Gli altri profili Xantrex mantengono il proprio ambito; GI da collaudare.

Prova fisica su due GT500 E RCA: riferimento 100 -> 2 -> 100, riduzione
misurata della potenza e ripristino dei riferimenti iniziali.
Il terzo inverter comunica ma presenta il guasto 0x0035 e non e stato resettato.
Il collaudo non equivale a una certificazione metrologica o normativa.

Test dedicati: letture incomplete, gateway non valido, formato firmato,
conferma ritardata, ACK errato, timeout incerto, perdita ACK senza replay,
firmware e mappa estranei, opt-in, guasto/manuale, arrotondamento,
idempotenza e stato fault nei cicli rapidi.

Procedura: [XANTREX_GT500_FAMILIES.md](XANTREX_GT500_FAMILIES.md).

Verifiche release: 490 test backend superati con le dipendenze dichiarate,
compilazione Python, build frontend e validazione Compose production/pilot.
