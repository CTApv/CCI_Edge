# Nome impianto — integrazione Control Room

Questi file sono destinati al progetto Tailscale Control Center, separato da PV Guardian Edge. La patch si riferisce al collector letto il 20 novembre 2026; non applicarla alla cieca a un collector diverso.

1. Salvare il codice corrente e un backup coerente di `backend/data/device_metadata.sqlite3` e dell'inventario flotta. Conservare i segreti solo sul server.
2. Copiare `plant_identity_sync.py` in `backend/app/services/` del Control Center.
3. Integrare `fleet_inventory.patch`: dopo il recupero della health edge, leggere i metadati di commissioning e chiamare l'helper prima di proseguire con la telemetria. Il blocco deve restare opzionale e isolare gli errori di rete.
4. Copiare `test_plant_identity_sync.py` nella directory `backend/tests/` del Control Center ed eseguire la sua suite completa.
5. Riavviare solo il backend Control Room e verificarne l'API. Per un ripristino, rimettere il collector salvato e riavviare il servizio; i nomi già salvati sugli edge restano presenti.

Il collector ripete gli aggiornamenti non riusciti nei cicli ordinari. Non invia richieste ai vecchi edge che non dichiarano il campo `plant_name`. La stessa modifica è stata installata sul Control Center Windows esistente dopo 82 test superati.

Non configurare polling dell'edge verso il Control Center né copiare le credenziali del Control Center negli IOT. Tutti i trasferimenti del nome sono avviati dal collector già presente; le autorizzazioni utente per modificare i metadati nella Control Room restano quelle esistenti.
