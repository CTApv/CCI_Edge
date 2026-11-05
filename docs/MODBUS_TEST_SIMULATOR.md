# Simulatore Modbus TCP multi-slave

Il simulatore genera telemetria plausibile e ripetibile per collaudare polling, dashboard,
qualita dati, timeout e gestione degli slave non raggiungibili.

Avvio consigliato dall'ambiente Python del backend:

```powershell
cd c:\progetti\pv-edge-manager\backend
.\.venv\Scripts\python.exe modbus_tcp_multi_slave_sim.py --profile ems1000 --units 50 --port 5020
```

Esempi di fault injection:

```powershell
.\.venv\Scripts\python.exe modbus_tcp_multi_slave_sim.py --profile ems1000 --units 50 --port 5020 --response-delay-ms 850
.\.venv\Scripts\python.exe modbus_tcp_multi_slave_sim.py --profile ems1000 --units 50 --port 5020 --offline-units 7,18,32
.\.venv\Scripts\python.exe modbus_tcp_multi_slave_sim.py --profile datahub --units 8 --port 5021 --drop-rate 0.05
```

Profili disponibili: `ems1000`, `datahub`, `generic`.

Il simulatore e uno strumento di test. Non deve essere avviato sulle porte di produzione di
un edge in servizio.
