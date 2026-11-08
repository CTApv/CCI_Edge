# Fronius Verto e Verto Plus — catalogo standard

Disponibili nel normale catalogo Fronius, senza una dashboard dedicata. Il riferimento percentuale esterno ricevuto da PV Guardian segue il normale percorso CCI/Modbus slave → target di flotta → comando `active_power_limit` → inverter Fronius. Anche il comando manuale standard usa lo stesso driver. Non esistono collegamenti con i DB o i consensi del PLC SINVERT.

## Serie e protocolli

| Serie ROW | Modelli nel catalogo | Canali fotovoltaici | Accumulo |
| --- | --- | --- | --- |
| Verto | 15.0, 17.5, 20.0 | 3 MPPT | No |
| Verto | 25.0, 27.0, 30.0, 33.3 | 4 MPPT | No |
| Verto Plus | 15.0, 17.5, 20.0, 25.0, 27.0, 30.0, 33.3 | 3 MPPT | Telemetria batteria |

Ogni modello ha un profilo Modbus TCP e un profilo Modbus RTU seriale separati (28 voci). È supportato anche il trasporto RTU su gateway TCP previsto dal provisioning standard. Le varianti regionali 208–240 V e 480 V non sono dichiarate come profili validati di questa release.

Il driver rileva la catena SunSpec a partire dalla firma `SunS`, identifica il modello trifase 103 (`int + SF`) oppure 113 (`float`) e risolve gli indirizzi relativi ai modelli. Non assume che gli indirizzi siano identici tra le due modalità. I dati provenienti da registri non supportati o con sentinella SunSpec non vengono presentati come misure valide.

## Configurazione inverter

Nell'interfaccia Fronius, Comunicazione → Modbus:

1. Abilitare il server TCP oppure assegnare una porta RTU dedicata al controllo esterno.
2. Impostare in PV Guardian IP/porta e Unit ID inverter, oppure porta seriale, baud rate, parità e slave ID corrispondenti.
3. Abilitare **Allow Control / Controllo inverter tramite Modbus**.
4. Se è configurata una restrizione IP, includere l'indirizzo dell'IOT.
5. Verificare le priorità di controllo dell'inverter: altri controllori o prescrizioni di rete possono prevalere sul comando Modbus.

Il formato `float` oppure `int + SF` viene riconosciuto automaticamente. L'indirizzo del contatore (normalmente 200) non sostituisce quello dell'inverter (normalmente 1). Le letture del precedente profilo Smart Meter non vengono riutilizzate per Verto.

## Limitazione potenza

Un riferimento 60 significa **60% della base WMax dell'inverter**, non una richiesta di produrre 60 kW e non il 60% della misura istantanea. Irraggiamento e altri limiti possono mantenere la produzione sotto il tetto richiesto.

Il modello Controls 123 fornisce `WMaxLimPct`, il relativo fattore di scala e `WMaxLim_Ena`. Il driver:

- riscopre la mappa e verifica identità Fronius/Verto e compatibilità della serie prima delle scritture;
- valida il riferimento nell'intervallo 0–100%;
- legge il fattore di scala effettivo;
- scrive tramite una sola FC16 il riferimento, la finestra temporale a zero, il timeout e la rampa già configurati, e l'abilitazione a 1;
- rilegge i registri e distingue l'accettazione del comando dalla risposta fisica;
- usa comandi indirizzati, senza broadcast e senza ritrasmissione automatica di una scrittura incerta.

Timeout e rampa non vengono arbitrariamente azzerati: se il timeout configurato scade, l'inverter può revocare la limitazione secondo la propria logica. Il normale dispatch di PV Guardian confronta il riferimento letto e il bit di abilitazione, quindi un limite disabilitato non risulta allineato.

Sono disponibili anche ON, OFF e disabilitazione della limitazione nel pannello comandi standard. ON/OFF richiedono connessione/disconnessione tramite il modello 123; non simulano un sezionatore fisico. La release non scrive parametri di rete o impostazioni batteria.

## Monitoraggio

Potenza AC/DC, energia cumulata, tensioni e correnti trifase, frequenza, temperatura supportata, stato operativo, eventi Fronius, misure MPPT, riferimento e abilitazione del limite. Sui Plus: canali batteria, stato di carica e limiti di accumulo in lettura. L'energia giornaliera non viene inventata se non fornita dal dispositivo.

## Fonti e verifica

- Mappe ufficiali Fronius: <https://www.fronius.com/QR-link/0024>, archivio versione **1.2.7-2**.
- SHA-256 archivio consultato: `dc4c5d49362ee0c9721f21886f17fa18497e54c4d92bb5cc2c50472deb266b55`.
- Sei workbook Verto: 3 MPPT, 4 MPPT e 3 MPPT storage, ciascuno float e int+SF. I nomi e gli hash dei workbook sono nel file di mappa del catalogo.
- Manuale Verto Plus: <https://manuals.fronius.com/html/4204260552/en-US.html>, sezione Modbus.
- Serie commerciali: <https://www.fronius.com/fr-fr/france/energie-solaire/commerce/produits-et-solutions/verto-plus-onduleur-puissant>.

Verifiche automatiche: parsing float/int+SF, indirizzi traslati, scritture e riletture, timeout/rampa preservati, errori e valori non disponibili, modello/serie errati, trasporti TCP/seriale/gateway, integrazione nel target di flotta e dialogo Modbus TCP reale con simulatore locale. Nessun inverter Fronius fisico era collegato durante queste verifiche; il catalogo dichiara `field_tested=false`.
