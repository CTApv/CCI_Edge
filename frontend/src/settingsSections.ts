export type SettingsSectionAccent =
  | "cci"
  | "hsm"
  | "com"
  | "lan"
  | "health"
  | "control"
  | "history"
  | "dashboard";

export type SettingsGuidanceItem = {
  label: string;
  text: string;
};

export type SettingsSectionContent = {
  legendLabel: string;
  eyebrow: string;
  title: string;
  description: string;
  menuHintLabel: string;
  menuHint: string;
  drawerTitle: string;
  drawerCopy: string;
  guidance: SettingsGuidanceItem[];
};

export const SETTINGS_SECTION_CONTENT: Record<SettingsSectionAccent, SettingsSectionContent> = {
  cci: {
    legendLabel: "Slave CCI",
    eyebrow: "Slave CCI",
    title: "Slave Modbus TCP del CCI",
    description:
      "Host, porta, ID unita e lettura stabile del setpoint per lasciare spazio al polling quando il target si assesta.",
    menuHintLabel: "Configurazione consigliata",
    menuHint:
      "Lascia attiva la lettura stabile; usa sola potenza attiva solo quando vuoi alleggerire il bus durante il ramping.",
    drawerTitle: "Slave Modbus TCP del CCI",
    drawerCopy:
      "Espone il nostro slave Modbus TCP al CCI, riceve i setpoint flotta e gestisce la lettura stabile vicino al target.",
    guidance: [
      {
        label: "A cosa serve",
        text: "Il CCI scrive qui il target flotta e il backend lo riallinea agli inverter mantenendo la priorita del comando.",
      },
      {
        label: "Settaggio consigliato",
        text: "Host 0.0.0.0, ID unita dedicato e lettura stabile attiva con banda Y stretta e 2-3 secondi di permanenza.",
      },
      {
        label: "Solo potenza attiva",
        text: "Attivalo quando vuoi una lettura di conferma leggera senza riaprire subito la telemetria completa degli inverter.",
      },
    ],
  },
  hsm: {
    legendLabel: "Bridge HSM",
    eyebrow: "Bridge HSM",
    title: "Bridge seriale HSM",
    description:
      "Inoltro COM-to-COM tra HSM e linea inverter con controllo di frame, ACK e stato runtime della linea RTU.",
    menuHintLabel: "Configurazione consigliata",
    menuHint:
      "Porta HSM e porta inverter devono essere diverse; la porta inverter deve gia corrispondere a una linea RTU valida.",
    drawerTitle: "Traffico HSM verso inverter",
    drawerCopy:
      "Configura il bridge seriale HSM, monitora ACK e usa la diagnostica runtime per capire se la linea inverter e davvero pronta.",
    guidance: [
      {
        label: "A cosa serve",
        text: "Riceve i frame dall'HSM e li inoltra sulla linea inverter gestita dall'app senza uscire dal controllo centralizzato della RTU.",
      },
      {
        label: "Settaggio consigliato",
        text: "Parti da frame gap 20-40 ms, forward delay 100-300 ms e ACK timeout coerente con la reattivita reale del campo.",
      },
      {
        label: "Verifica linea",
        text: "Se la linea non e pronta, controlla che su quella COM esistano device seriali coerenti per protocollo e parametri RTU.",
      },
    ],
  },
  com: {
    legendLabel: "COM Settings",
    eyebrow: "COM Settings",
    title: "Configurazione dispositivi",
    description:
      "Browsing, profili seriali e TCP, timeout e salvataggio del nodo in un unico percorso operativo.",
    menuHintLabel: "Configurazione consigliata",
    menuHint:
      "Definisci collegamento, timeout e parametri base prima dello scan; sui bus lenti parti con valori conservativi.",
    drawerTitle: "Browsing e aggiunta dispositivi",
    drawerCopy:
      "Qui si definiscono identita, collegamento, timeout e criteri di scansione prima di salvare un nuovo nodo in campo.",
    guidance: [
      {
        label: "Prima della scansione",
        text: "Conferma protocollo, collegamento e timeout: gran parte dei falsi negativi nasce da parametri seriali o TCP incoerenti.",
      },
      {
        label: "Strategia pratica",
        text: "Su seriale parti con baud e timeout prudenziali; se il bus e stabile puoi stringere il timeout dopo il primo commissioning.",
      },
    ],
  },
  lan: {
    legendLabel: "LAN Settings",
    eyebrow: "LAN Settings",
    title: "Reti CCI e inverter",
    description:
      "Interfacce di rete, IP, gateway e DNS del nodo edge con conferma protetta prima del commit definitivo.",
    menuHintLabel: "Configurazione consigliata",
    menuHint:
      "Una sola interfaccia dovrebbe avere il gateway predefinito; la rete di campo conviene lasciarla senza route di default.",
    drawerTitle: "Configurazione LAN",
    drawerCopy:
      "Gestisce le interfacce del nodo edge e rende visibili le scelte che impattano raggiungibilita del CCI, internet e rete di campo.",
    guidance: [
      {
        label: "A cosa serve",
        text: "Separa bene rete di supervisione, internet e rete di campo per evitare instradamenti ambigui durante il polling.",
      },
      {
        label: "Settaggio consigliato",
        text: "Lascia una sola scheda con gateway predefinito e tieni la LAN di campo con indirizzo statico ma senza route di default.",
      },
      {
        label: "Prima del commit",
        text: "Verifica IP, subnet, gateway e DNS perche una modifica errata puo isolare il nodo fino al rollback.",
      },
    ],
  },
  health: {
    legendLabel: "Health System",
    eyebrow: "Health System",
    title: "Diagnostica impianto",
    description:
      "Polling, endpoint condivisi, cache live, storico e servizi runtime in una vista di controllo unico.",
    menuHintLabel: "Quando aprirlo",
    menuHint:
      "Usalo quando compaiono timeout, offline, dati parziali o quando vuoi capire se il collo di bottiglia e nel bus o nel runtime.",
    drawerTitle: "Stato motore applicativo",
    drawerCopy:
      "Raccoglie i segnali di salute del sistema per distinguere i problemi di rete, polling, cache o endpoint condivisi.",
    guidance: [
      {
        label: "A cosa guardare",
        text: "Controlla prima polling engine, endpoint condivisi e startup error dello slave Modbus TCP per capire dove si blocca la catena.",
      },
      {
        label: "Segnale utile",
        text: "Offline, timeout e runtime in cooldown sono i primi indizi da correlare con COM, LAN o bridge HSM.",
      },
    ],
  },
  control: {
    legendLabel: "Controllo",
    eyebrow: "Controllo",
    title: "Controllo e audit comandi",
    description:
      "Vista dedicata a comandabilita impianto, piano broadcast, ultimo dispatch e conferma del target flotta.",
    menuHintLabel: "Quando aprirlo",
    menuHint:
      "Usalo prima o dopo un setpoint per capire se il comando andra in broadcast, quali endpoint sono pronti e cosa e successo nell'ultimo invio.",
    drawerTitle: "Controllo e audit comandi",
    drawerCopy:
      "Raccoglie in una sola pagina le verifiche operative sul comando impianto senza appesantire la dashboard live.",
    guidance: [
      {
        label: "Prima del comando",
        text: "Controlla impianto comandabile e piano broadcast per intercettare endpoint bloccati o profili comando non omogenei.",
      },
      {
        label: "Dopo il comando",
        text: "Leggi ultimo dispatch e confidenza target per distinguere comandi inviati, device in errore e conferme telemetriche.",
      },
    ],
  },
  history: {
    legendLabel: "Storico",
    eyebrow: "Storico",
    title: "Storico avanzato",
    description:
      "Trend impianto e inverter, filtri rapidi ed export CSV quando serve analizzare andamento e campioni raccolti.",
    menuHintLabel: "Uso consigliato",
    menuHint:
      "Parti dai preset 24h o 7 giorni; usa l'export CSV solo quando devi confrontare o archiviare all'esterno.",
    drawerTitle: "Analisi storico",
    drawerCopy:
      "Serve per rileggere il comportamento nel tempo, confrontare intervalli e portare fuori i dati solo quando serve davvero.",
    guidance: [
      {
        label: "Partenza rapida",
        text: "Usa i preset rapidi per verifiche operative e passa all'intervallo custom solo quando hai gia capito dove guardare.",
      },
      {
        label: "Quando esportare",
        text: "Il CSV ha senso quando devi condividere i campioni, fare correlazioni esterne o conservare una fotografia del periodo.",
      },
    ],
  },
  dashboard: {
    legendLabel: "Dashboard",
    eyebrow: "Dashboard",
    title: "Sfondo solare",
    description:
      "Animazione ambientale del cielo in base all'orario locale, con overlay blu coerente con l'app.",
    menuHintLabel: "Uso consigliato",
    menuHint:
      "Lascialo spento se vuoi la dashboard classica; abilitalo quando vuoi un riferimento visivo leggero alla fase del giorno.",
    drawerTitle: "Sfondo dashboard",
    drawerCopy:
      "Controlla solo lo sfondo dell'app e non modifica polling, comandi o viste operative.",
    guidance: [
      {
        label: "Comportamento",
        text: "Quando e disattivo non viene renderizzata nessuna animazione e la dashboard mantiene lo sfondo attuale.",
      },
      {
        label: "Persistenza",
        text: "La scelta resta salvata sul browser dell'operatore, senza impattare gli altri client.",
      },
    ],
  },
};

export function getSettingsAccentClass(section: SettingsSectionAccent): string {
  return `settings-accent settings-accent--${section}`;
}
