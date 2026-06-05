# Dashboard Maintenance Guide

Questa guida serve quando un inverter reale restituisce dati diversi da quelli attesi in dashboard e bisogna correggere il progetto senza supporto esterno.

## 1. Capire dove sta il problema

Prima distinzione da fare:

- Se il valore letto dal backend e gia sbagliato, il problema e quasi sempre nel catalogo del modello o nella scala.
- Se il backend legge giusto ma la dashboard mostra il dato nel posto sbagliato o con etichetta errata, il problema e nel frontend.

Controllo rapido:

1. Apri il dettaglio dispositivo.
2. Verifica il valore dentro la telemetria grezza.
3. Confrontalo con il dato mostrato nel sinottico SVG o nella card.

Se il dato grezzo e corretto ma il sinottico e sbagliato, non toccare il catalogo.

## 2. Dove correggere i registri letti

Ogni marca ha il suo catalogo backend in `backend/app/catalog/`.

Esempi:

- Bonfiglioli: `backend/app/catalog/bonfiglioli_catalog.py`
- Ingeteam: `backend/app/catalog/ingeteam_catalog.py`
- Aurora: `backend/app/catalog/aurora_catalog.py`

Quando devi correggere una lettura:

1. Trova il punto in `build_*_telemetry()`.
2. Modifica:
   - `address`
   - `scale`
   - `unit`
   - eventualmente `datatype`
3. Se il dato deve influire sui KPI principali, verifica anche `summary_metric`.

Campi importanti:

- `summary_metric="power_kw"`: usato per potenza riassuntiva
- `summary_metric="temperature_c"`: usato per temperatura
- `summary_metric="total_energy_kwh"`: usato per energia totale
- `summary_metric="status"`: usato per stato dispositivo

## 3. Dove correggere i comandi

I comandi stanno nello stesso catalogo, in `build_*_commands()`.

Per un comando come il setpoint potenza:

1. Controlla `address`
2. Controlla `scale`
3. Controlla `unit`
4. Controlla eventuali metadati in `protocol_meta`

Per Bonfiglioli, il driver applica anche `parameter_offset`, quindi il parametro on-wire puo essere diverso da quello scritto nel catalogo.

Il driver Bonfiglioli e in:

- `backend/app/services/bonfiglioli_modbus_service.py`

Qui puoi verificare:

- `parameter_actual`
- `parameter_offset`
- `encoded_value`

nei dettagli diagnostici della scrittura.

## 4. Dove correggere etichette e raggruppamenti

Se il valore e giusto ma il nome mostrato non ti piace oppure il punto finisce nel gruppo sbagliato, guarda:

- `frontend/src/telemetryPresentation.ts`

Qui puoi cambiare:

- traduzione delle sezioni
- traduzione delle label
- priorita dei gruppi
- macro-gruppi usati nel dettaglio dispositivo

## 5. Dove correggere la scena SVG inverter

Se il dato giusto esiste ma non compare nel sinottico lato DC/AC, i punti principali sono:

- `frontend/src/App.tsx`
- `frontend/src/components/InverterFlowScene.tsx`

In pratica:

1. `App.tsx` sceglie quali chiavi telemetry usare per DC, AC e KPI.
2. `InverterFlowScene.tsx` decide come formattarle e visualizzarle.

Se una misura compare come `n.d.`:

- verifica che la chiave telemetry esista davvero nel catalogo
- verifica che `App.tsx` la stia cercando con il nome corretto

## 6. Metodo consigliato quando un dato non torna

Usa sempre questo ordine:

1. Verifica manuale del modello e dato reale.
2. Apri il catalogo della marca.
3. Correggi indirizzo, scala o unita.
4. Aggiorna il test del catalogo.
5. Lancia i test backend.
6. Se serve, correggi mapping frontend.
7. Fai build frontend.
8. Deploy su IOT2050.

## 7. Test minimi da lanciare

Dal backend:

```powershell
cd c:\progetti\pv-edge-manager\backend
python -m unittest tests.test_bonfiglioli_catalog
python -m unittest discover -s tests
python -m compileall app tests
```

Dal frontend:

```powershell
cd c:\progetti\pv-edge-manager\frontend
npm run build
```

## 8. Deploy rapido su IOT2050

Esempio backend:

```powershell
scp c:\progetti\pv-edge-manager\backend\app\catalog\bonfiglioli_catalog.py root@<IP_IOT>:/opt/pv-edge-manager/backend/app/catalog/
```

Esempio frontend:

```powershell
scp -r c:\progetti\pv-edge-manager\frontend\dist\* root@<IP_IOT>:/var/www/pv-edge-manager/
```

Poi sul dispositivo:

```bash
systemctl restart pv-edge-manager-backend
systemctl restart nginx
```

## 9. Regola pratica

Se devi correggere un inverter reale:

- prima sistema il catalogo
- poi sistema la dashboard

Non fare il contrario, altrimenti rischi di mascherare un dato letto male con una UI solo apparentemente corretta.
