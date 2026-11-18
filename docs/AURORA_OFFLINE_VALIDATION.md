# Aurora: verifiche offline e vincolo sul comando 151

Verifica del 18 novembre 2026, inclusa nella prerelease v1.5.0-rc.1.
Nessuna connessione a inverter o IOT e nessun cambiamento al protocollo di
scrittura collaudato.

## Comando 151 preservato

Il file `backend/app/services/aurora_service.py` è invariato rispetto a HEAD.
Questo conserva conversione del limite, timeout, rampa, CRC, gestione degli
scambi e risultato del comando. La piccola differenza di quantizzazione rispetto
a Manager TL è intenzionalmente conservata, come richiesto dall'utente.

I test in `backend/tests/test_aurora_offline_verification.py` attraversano il
metodo pubblico `write_point` e la costruzione/scambio/decodifica dei frame,
sostituendo soltanto la porta fisica con una seriale emulata. I vettori fissi
verificano i frame completi del comportamento attuale a 0, 1, 25, 50, 75, 99 e
100%, compreso il CRC. Altri casi verificano frammentazione, rumore iniziale,
rifiuto del comando, CRC errato, silenzio e valori fuori intervallo.

Queste prove proteggono il comportamento software già approvato; non costituiscono
un nuovo collaudo fisico degli inverter né validano ogni firmware.

## Letture di riscontro ricostruite dal software del costruttore

Aurora Manager TL, SHA256
`f6383335512b710d27c94ff17806b74e4ff130bba0d4b10f8e1a08187f4c67ed`:
routine `APL_Read`, dizionario comandi, interprete delle risposte e
`Conversion.GetDoubleValue`.

| Opcode / selettore | Decodifica osservata nel software |
| --- | --- |
| 83 / 132 | Due byte alto-prima, divisi per 60 per visualizzare minuti; 255 minuti attiva la visualizzazione Forever |
| 83 / 133 | Il byte 2 della risposta indica PL-ON; zero significa disabilitato |
| 83 / 134 | Due byte alto-prima; percentuale memorizzata = valore × 100 / 32768 |
| 83 / 135 | Float a 32 bit alto-prima; il software visualizza un intero arrotondato verso il basso al multiplo di 4 |

Con PL-ON disabilitato, Manager TL visualizza 100% indipendentemente dal limite
memorizzato. Il decodificatore mantiene separati questi due valori. Non deduce
il comportamento dell'inverter alla scadenza del timeout.

Il nuovo modulo `aurora_capture_analysis.py` è solo offline: non importa seriale,
non apre connessioni e non è richiamato dal driver operativo. Non sono state
aggiunte letture al polling, né alterate le scritture. Controlla lunghezza, CRC,
stato di risposta e formato. Per gli scambi completi verifica anche opcode 83,
selettore, indirizzo unico e assenza di selettori duplicati.

Il protocollo non ripete indirizzo e selettore nella risposta: l'abbinamento
richiesta/risposta deve provenire dalla cattura. CRC valido non prova né
l'origine fisica né la freschezza del dato.

### Analizzare una cattura senza collegarsi a nulla

Preparare un JSON con quattro scambi realmente correlati:

```json
{
  "exchanges": [
    {"request": "frame completo di lettura 83/132", "reply": "risposta completa"},
    {"request": "frame completo di lettura 83/133", "reply": "risposta completa"},
    {"request": "frame completo di lettura 83/134", "reply": "risposta completa"},
    {"request": "frame completo di lettura 83/135", "reply": "risposta completa"}
  ]
}
```

Sostituire le descrizioni con byte esadecimali catturati, quindi dalla radice del
repository eseguire:

```powershell
python scripts/aurora_analyze_capture.py percorso/cattura.json
```

Il risultato lascia sempre `physical_execution_confirmed` e
`capture_freshness_confirmed` falsi: queste condizioni richiedono altre evidenze.

## Central: esistono percorsi differenti

Aurora Central CVI, SHA256
`e62c1158bbb63924f4c339988948e7ab3378258c6c9538db1827a0b65ba1d593`:

- Il percorso precedente `_ucSetPowerLimit` a 0x55360f passa dal dispatcher
  0x54adb4 al comando 60, selettore 46 e valore float alto-prima per modulo.
- Nel pannello di controllo potenza compare anche la costruzione del comando
  151: per esempio a 0x57de5b–0x57de73 vengono impostati opcode 151 e parametro
  di abilitazione 1; il percorso di reset usa parametro 0. La costruzione dei
  messaggi nei pannelli non basta a certificare ogni firmware.
- La tabella locale `rack_conf/AN101_COMPATIBLE_FW_LIST.ini`, datata 19/01/2016,
  contiene 19 regole che incrociano identificativo/revisione DSP e MCU. Le sigle
  sono sensibili alle maiuscole: `cC` non equivale a `CC`.

L'analisi ha controllato le estremità inferiore e superiore di tutte le 19 regole
del file installato: 38 combinazioni. Questo verifica il classificatore offline,
non prova l'esecuzione dei comandi sui dispositivi reali. La classificazione non
è collegata all'abilitazione delle scritture.

```powershell
python scripts/aurora_inspect_firmware.py --table "C:\Program Files (x86)\ABB\Aurora Central CVI\rack_conf\AN101_COMPATIBLE_FW_LIST.ini" --dsp-id CC --dsp-revision 13 --mcu-id DC --mcu-revision 25
```

I valori dell'esempio sono una combinazione di prova della tabella, non firmware
letti da un dispositivo. Il risultato specifica sempre che la compatibilità
effettiva del comando non è confermata.

## Identità del catalogo

Sono stati aggiunti ai metadati i codici modello osservati nel software, mantenendo
distinte maiuscole e minuscole. Nessun nuovo riconoscimento automatico è abilitato.
In particolare:

- `C` richiede anche il part number: `3M04`, `3M05` e `3L07` sono interpretati da
  Manager TL come PVI-MODULE-55.0; non identificano da soli la taglia del rack.
- `O` richiede un ulteriore byte per distinguere PVI-3000-OUTD e PVI-3600-OUTD.
- `G`/`g`, `Y`/`y`, `H`/`h` identificano modelli differenti nel software.

La vecchia associazione di alcuni part number di modulo al profilo CENTRAL330TL
è conservata per compatibilità, ma resta ambigua: non deve essere considerata
una nuova conferma della potenza nominale del rack. La matrice del catalogo
continua a indicare i nuovi profili come identificati, con letture da collaudare.

## Limiti e passi che richiedono hardware

Restano da verificare: letture supportate per modello, firmware effettivi,
distribuzione del riferimento fra master e slave, unità del percorso legacy dei
Central, comportamento alla scadenza/perdita di comunicazione e variazione della
potenza reale. Non sono state abilitate nuove scritture sulla base dei simulatori.

Gli estratti tecnici e i risultati sintetici di questa sessione sono conservati
fuori dal repository nella cartella di lavoro `indagine/aurora_software_20261118`.
Gli eseguibili del costruttore non sono inclusi nel progetto.

## Esito delle verifiche del progetto

- 393 test backend superati, di cui 27 dedicati ad Aurora.
- Compilazione Python di applicazione, test e strumenti completata.
- Build TypeScript/Vite completata.
- Configurazioni Docker production e pilot-ghcr validate con i file di esempio.
- CLI offline provate su una cattura sintetica e sulla tabella firmware locale.
- Driver Aurora operativo invariato; SHA256 con fine riga LF:
  `20913500037c37c3f34767a6b363aba34b0900ee566676c48e53da534c69b010`.

I test completi sono stati eseguiti con pymodbus 3.12.1, come richiesto dal
progetto, caricato da una cartella locale isolata di dipendenze. La precedente
installazione globale 3.11.4 non è stata sostituita.
