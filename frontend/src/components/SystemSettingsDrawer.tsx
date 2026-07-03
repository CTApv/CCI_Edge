import { useEffect, useState } from "react";

import {
  applyNetworkConfiguration,
  getNetworkConfiguration,
  updateNetworkInterfaceRole,
  type NetworkConfigInterface,
  type NetworkConfigSnapshot,
  type NetworkInterfaceRole,
  type PendingNetworkChange,
} from "../api";
import { getSettingsAccentClass, SETTINGS_SECTION_CONTENT } from "../settingsSections";

type SystemSettingsDrawerProps = {
  open: boolean;
  onClose: () => void;
  onPendingChange?: (pendingChange: PendingNetworkChange | null) => void;
};

type InterfaceFormState = {
  ipv4_method: "auto" | "manual";
  address: string;
  prefix_length: string;
  secondary_address: string;
  secondary_prefix_length: string;
  gateway: string;
  dns_servers: string;
  autoconnect: boolean;
  use_default_route: boolean;
};

type NetworkInterfacePurpose = {
  cardKicker: string;
  title: string;
  description: string;
  primaryLabel: string;
  primaryPlaceholder: string;
  prefixLabel: string;
  secondaryLabel?: string;
  secondaryPlaceholder?: string;
  secondaryPrefixLabel?: string;
};

const CCI_STATIC_IP_SUGGESTION = "10.56.69.100";
const DEFAULT_PREFIX_LENGTH = "24";
const NETWORK_ROLE_OPTIONS: Array<{ value: NetworkInterfaceRole; label: string }> = [
  { value: "unassigned", label: "Da assegnare" },
  { value: "cci", label: "CCI communication" },
  { value: "internet_inverter", label: "Internet + inverter" },
];

const GENERIC_INTERFACE_PURPOSE: NetworkInterfacePurpose = {
  cardKicker: "Scheda di rete",
  title: "Interfaccia LAN",
  description: "Profilo IPv4 gestito da NetworkManager.",
  primaryLabel: "Indirizzo IPv4",
  primaryPlaceholder: "192.168.2.249",
  prefixLabel: "Prefisso",
};

function getInterfacePurpose(role: NetworkInterfaceRole, index: number): NetworkInterfacePurpose {
  if (role === "cci") {
    return {
      cardKicker: "LAN 1",
      title: "CCI communication",
      description: `Porta dedicata alla comunicazione con il CCI. IP statico consigliato: ${CCI_STATIC_IP_SUGGESTION}/24.`,
      primaryLabel: "IP CCI communication",
      primaryPlaceholder: CCI_STATIC_IP_SUGGESTION,
      prefixLabel: "Prefisso CCI",
    };
  }

  if (role === "internet_inverter") {
    return {
      cardKicker: "LAN 2",
      title: "Internet + Inverter SLAVE communication",
      description:
        "La stessa scheda usa un IP per Internet/gateway e un secondo IP per la rete inverter Modbus TCP.",
      primaryLabel: "IP Internet",
      primaryPlaceholder: "192.168.2.249",
      prefixLabel: "Prefisso Internet",
      secondaryLabel: "IP Inverter SLAVE communication",
      secondaryPlaceholder: "192.168.x.249",
      secondaryPrefixLabel: "Prefisso rete inverter",
    };
  }

  return {
    ...GENERIC_INTERFACE_PURPOSE,
    cardKicker: `LAN ${index + 1}`,
    title: `Interfaccia LAN ${index + 1}`,
  };
}

function formatNetworkRole(role: NetworkInterfaceRole): string {
  return NETWORK_ROLE_OPTIONS.find((option) => option.value === role)?.label ?? "Da assegnare";
}

function buildFormState(item: NetworkConfigInterface): InterfaceFormState {
  const configuredAddresses = Array.isArray(item.configured_addresses) ? item.configured_addresses : [];
  const liveAddresses = Array.isArray(item.live_addresses) ? item.live_addresses : [];
  const configuredAddress = configuredAddresses[0] ?? liveAddresses[0] ?? null;
  const secondaryAddress = configuredAddresses[1] ?? liveAddresses[1] ?? null;
  const dnsServers = Array.isArray(item.dns_servers) ? item.dns_servers : [];
  return {
    ipv4_method: item.ipv4_method === "manual" ? "manual" : "auto",
    address: configuredAddress?.address ?? "",
    prefix_length:
      configuredAddress && Number.isFinite(configuredAddress.prefix_length)
        ? String(configuredAddress.prefix_length)
        : DEFAULT_PREFIX_LENGTH,
    secondary_address: secondaryAddress?.address ?? "",
    secondary_prefix_length:
      secondaryAddress && Number.isFinite(secondaryAddress.prefix_length)
        ? String(secondaryAddress.prefix_length)
        : DEFAULT_PREFIX_LENGTH,
    gateway: item.gateway ?? item.live_gateway ?? "",
    dns_servers: dnsServers.join(", "),
    autoconnect: item.autoconnect ?? true,
    use_default_route: item.use_default_route,
  };
}

function buildFormStates(
  interfaces: NetworkConfigInterface[],
): Record<string, InterfaceFormState> {
  return Object.fromEntries(interfaces.map((item) => [item.interface_name, buildFormState(item)]));
}

function applyRolePreset(
  form: InterfaceFormState,
  networkRole: NetworkInterfaceRole,
): InterfaceFormState {
  if (networkRole === "cci") {
    return {
      ...form,
      ipv4_method: "manual",
      address: CCI_STATIC_IP_SUGGESTION,
      prefix_length: DEFAULT_PREFIX_LENGTH,
      secondary_address: "",
      secondary_prefix_length: DEFAULT_PREFIX_LENGTH,
      gateway: "",
      dns_servers: "",
      use_default_route: false,
    };
  }
  if (networkRole === "internet_inverter") {
    return {
      ...form,
      use_default_route: true,
    };
  }
  return form;
}

function formatAddresses(addresses: Array<{ address: string; prefix_length: number }>): string {
  if (!Array.isArray(addresses) || addresses.length === 0) {
    return "--";
  }
  return addresses.map((item) => `${item.address}/${item.prefix_length}`).join(", ");
}

function formatInterfaceState(state: string): string {
  switch (state) {
    case "connected":
      return "Connessa";
    case "connecting":
      return "In connessione";
    case "disconnected":
      return "Disconnessa";
    case "unavailable":
      return "Non disponibile";
    default:
      return state || "Sconosciuto";
  }
}

function buildFormAddressEntries(form: InterfaceFormState) {
  if (form.ipv4_method !== "manual") {
    return [];
  }

  const addresses: Array<{ address: string; prefix_length: number }> = [];
  const primaryAddress = form.address.trim();
  const primaryPrefix = Number(form.prefix_length);
  if (primaryAddress !== "" && Number.isFinite(primaryPrefix)) {
    addresses.push({
      address: primaryAddress,
      prefix_length: primaryPrefix,
    });
  }

  const secondaryAddress = form.secondary_address.trim();
  const secondaryPrefix = Number(form.secondary_prefix_length);
  if (secondaryAddress !== "" && Number.isFinite(secondaryPrefix)) {
    addresses.push({
      address: secondaryAddress,
      prefix_length: secondaryPrefix,
    });
  }

  return addresses;
}

export function SystemSettingsDrawer({
  open,
  onClose,
  onPendingChange,
}: SystemSettingsDrawerProps) {
  const [snapshot, setSnapshot] = useState<NetworkConfigSnapshot | null>(null);
  const [forms, setForms] = useState<Record<string, InterfaceFormState>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  function replaceDrafts(response: NetworkConfigSnapshot) {
    setForms(buildFormStates(response.interfaces));
  }

  useEffect(() => {
    if (!open) {
      return;
    }

    let cancelled = false;

    async function loadSnapshot() {
      setLoading(true);
      setError(null);
      try {
        const response = await getNetworkConfiguration();
        if (cancelled) {
          return;
        }
        setSnapshot(response);
        replaceDrafts(response);
        onPendingChange?.(response.pending_change);
      } catch (loadError) {
        if (cancelled) {
          return;
        }
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Impossibile caricare la configurazione di rete.",
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSnapshot();
    return () => {
      cancelled = true;
    };
  }, [onPendingChange, open]);

  useEffect(() => {
    if (open) {
      return;
    }
    setSnapshot(null);
    setForms({});
    setLoading(false);
    setError(null);
    setActionError(null);
    setBusyAction(null);
  }, [open]);

  if (!open) {
    return null;
  }

  function updateForm(
    interfaceName: string,
    updater: (current: InterfaceFormState) => InterfaceFormState,
  ) {
    setActionError(null);
    setForms((current) => {
      const base = current[interfaceName];
      if (!base) {
        return current;
      }
      return {
        ...current,
        [interfaceName]: updater(base),
      };
    });
  }

  async function reloadSnapshot() {
    const response = await getNetworkConfiguration();
    setSnapshot(response);
    replaceDrafts(response);
  }

  async function handleApply(item: NetworkConfigInterface) {
    const form = forms[item.interface_name];
    if (!form) {
      return;
    }

    setBusyAction(`apply:${item.interface_name}`);
    setActionError(null);
    try {
      const addressEntries = buildFormAddressEntries(form);
      const response = await applyNetworkConfiguration({
        interface_name: item.interface_name,
        ipv4_method: form.ipv4_method,
        address:
          form.ipv4_method === "manual" && addressEntries.length > 0
            ? addressEntries[0].address
            : null,
        prefix_length:
          form.ipv4_method === "manual" && addressEntries.length > 0
            ? addressEntries[0].prefix_length
            : null,
        addresses: addressEntries,
        gateway: form.gateway.trim() || null,
        dns_servers: form.dns_servers
          .split(",")
          .map((entry) => entry.trim())
          .filter((entry) => entry.length > 0),
        autoconnect: form.autoconnect,
        use_default_route: form.use_default_route,
      });
      setSnapshot(response);
      replaceDrafts(response);
      onPendingChange?.(response.pending_change);
      if (response.pending_change !== null) {
        onClose();
      }
    } catch (applyError) {
      setActionError(
        applyError instanceof Error
          ? applyError.message
          : "Impossibile applicare la configurazione di rete.",
      );
    } finally {
      setBusyAction(null);
    }
  }

  async function handleRoleChange(item: NetworkConfigInterface, networkRole: NetworkInterfaceRole) {
    setBusyAction(`role:${item.interface_name}`);
    setActionError(null);
    try {
      const response = await updateNetworkInterfaceRole({
        interface_name: item.interface_name,
        network_role: networkRole,
      });
      setSnapshot(response);
      const nextForms = buildFormStates(response.interfaces);
      const selectedInterface = response.interfaces.find(
        (networkInterface) => networkInterface.interface_name === item.interface_name,
      );
      if (selectedInterface) {
        nextForms[item.interface_name] = applyRolePreset(
          nextForms[item.interface_name] ?? buildFormState(selectedInterface),
          networkRole,
        );
      }
      setForms(nextForms);
      onPendingChange?.(response.pending_change);
    } catch (roleError) {
      setActionError(
        roleError instanceof Error
          ? roleError.message
          : "Impossibile salvare il ruolo della scheda di rete.",
      );
    } finally {
      setBusyAction(null);
    }
  }

  const pendingChange = snapshot?.pending_change ?? null;
  const section = SETTINGS_SECTION_CONTENT.lan;

  return (
    <div className="settings-backdrop" role="presentation" onClick={onClose}>
      <aside
        aria-labelledby="system-settings-title"
        aria-modal="true"
        className={`settings-drawer system-settings-drawer settings-accent-shell ${getSettingsAccentClass(
          "lan",
        )}`}
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div className="modal-title-group">
            <p className="panel-kicker">{section.eyebrow}</p>
            <h2 id="system-settings-title">{section.drawerTitle}</h2>
            <p className="modal-copy">{section.drawerCopy}</p>
            <div className="settings-accent-pill-row">
              <span className={`settings-accent-pill ${getSettingsAccentClass("lan")}`}>
                {section.legendLabel}
              </span>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={onClose}>
            Chiudi
          </button>
        </div>

        <div className="settings-content">
          {loading ? <div className="panel-state">Caricamento configurazione di rete...</div> : null}
          {error ? <div className="panel-state panel-state--error">{error}</div> : null}
          {actionError ? <div className="panel-state panel-state--error">{actionError}</div> : null}

          {snapshot ? (
            <>
              <section className="settings-summary">
                <p className="panel-kicker">{section.eyebrow}</p>
                <h3>
                  {snapshot.supported ? "Gestione rete disponibile" : "Gestione rete in sola lettura"}
                </h3>
                <p className="settings-summary-meta">
                  Piattaforma {snapshot.platform} | manager {snapshot.manager}
                </p>
                <p className="settings-summary-meta">
                  {snapshot.message ?? "Nessuna nota operativa disponibile."}
                </p>
                <ul className="settings-guidance-list">
                  {section.guidance.slice(0, 3).map((item) => (
                    <li key={`${item.label}:${item.text}`}>
                      <strong>{item.label}</strong>
                      <span>{item.text}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="settings-section settings-section--network">
                <div className="settings-section-header">
                  <div>
                    <p className="panel-kicker">Rete</p>
                    <h3 className="detail-section-title">Schede di rete</h3>
                  </div>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void reloadSnapshot()}
                    disabled={busyAction !== null}
                  >
                    Aggiorna
                  </button>
                </div>

                <p className="confirm-note">
                  Consiglio operativo: una sola interfaccia dovrebbe avere la route predefinita.
                  La LAN di campo conviene lasciarla senza gateway predefinito.
                </p>

                {snapshot.interfaces.length > 0 ? (
                  <div className="settings-network-list">
                    {snapshot.interfaces.map((item, index) => {
                      const form = forms[item.interface_name] ?? buildFormState(item);
                      const purpose = getInterfacePurpose(item.network_role, index);
                      const applyingThisInterface = busyAction === `apply:${item.interface_name}`;
                      const assigningThisRole = busyAction === `role:${item.interface_name}`;
                      const disableInterfaceActions =
                        busyAction !== null || pendingChange !== null || !snapshot.apply_supported;
                      const disableRoleAction =
                        busyAction !== null || pendingChange !== null || !item.editable;

                      return (
                        <article key={item.interface_name} className="settings-network-card">
                          <div className="settings-network-head">
                            <div>
                              <p className="panel-kicker">
                                {purpose.cardKicker} | {item.device_type} |{" "}
                                {formatInterfaceState(item.state)}
                              </p>
                              <h3 className="detail-section-title">{purpose.title}</h3>
                              <p className="settings-network-note">
                                {purpose.description}
                              </p>
                              <p className="settings-network-note">
                                Interfaccia {item.interface_name} | Profilo{" "}
                                {item.connection_name ?? "non associato"} | MAC {item.mac_address ?? "--"}
                              </p>
                              <p className="settings-network-note">
                                Ruolo salvato: {formatNetworkRole(item.network_role)}
                              </p>
                            </div>
                            <span
                              className={`system-health-runtime-badge ${
                                item.editable
                                  ? "system-health-runtime-badge--positive"
                                  : "system-health-runtime-badge--warning"
                              }`}
                            >
                              {item.editable ? "Gestibile" : "Sola lettura"}
                            </span>
                          </div>

                          <div className="settings-network-live-grid">
                            <article className="settings-item">
                              <p className="settings-item-label">IP live</p>
                              <strong className="settings-item-value">
                                {formatAddresses(item.live_addresses)}
                              </strong>
                            </article>
                            <article className="settings-item">
                              <p className="settings-item-label">Gateway live</p>
                              <strong className="settings-item-value">
                                {item.live_gateway ?? "--"}
                              </strong>
                            </article>
                            <article className="settings-item">
                              <p className="settings-item-label">DNS live</p>
                              <strong className="settings-item-value">
                                {Array.isArray(item.live_dns_servers) && item.live_dns_servers.length > 0
                                  ? item.live_dns_servers.join(", ")
                                  : "--"}
                              </strong>
                            </article>
                            <article className="settings-item">
                              <p className="settings-item-label">Profilo configurato</p>
                              <strong className="settings-item-value">
                                {item.ipv4_method === "unknown"
                                  ? "Non disponibile"
                                  : item.ipv4_method === "manual"
                                    ? `Statico | ${formatAddresses(item.configured_addresses)}`
                                    : "DHCP"}
                              </strong>
                            </article>
                          </div>

                          {form ? (
                            <div className="settings-network-form">
                              <div className="form-grid">
                                <label className="field">
                                  <span className="field-label">Ruolo interfaccia</span>
                                  <select
                                    className="field-control"
                                    value={item.network_role}
                                    onChange={(event) => {
                                      void handleRoleChange(
                                        item,
                                        event.currentTarget.value as NetworkInterfaceRole,
                                      );
                                    }}
                                    disabled={disableRoleAction}
                                  >
                                    {NETWORK_ROLE_OPTIONS.map((option) => (
                                      <option key={option.value} value={option.value}>
                                        {option.label}
                                      </option>
                                    ))}
                                  </select>
                                </label>

                                <label className="field">
                                  <span className="field-label">Modalita IPv4</span>
                                  <select
                                    className="field-control"
                                    value={form.ipv4_method}
                                    onChange={(event) => {
                                      const nextValue = event.currentTarget.value;
                                      updateForm(item.interface_name, (current) => ({
                                        ...current,
                                        ipv4_method: nextValue === "manual" ? "manual" : "auto",
                                      }));
                                    }}
                                    disabled={!item.editable || disableInterfaceActions}
                                  >
                                    <option value="auto">DHCP</option>
                                    <option value="manual">Statico</option>
                                  </select>
                                </label>

                                <label className="field">
                                  <span className="field-label">Avvio automatico</span>
                                  <button
                                    className="secondary-button settings-toggle-button"
                                    type="button"
                                    onClick={() =>
                                      updateForm(item.interface_name, (current) => ({
                                        ...current,
                                        autoconnect: !current.autoconnect,
                                      }))
                                    }
                                    disabled={!item.editable || disableInterfaceActions}
                                  >
                                    {form.autoconnect ? "Attivo" : "Disattivo"}
                                  </button>
                                </label>

                                {item.network_role === "cci" ? (
                                  <label className="field">
                                    <span className="field-label">Preset CCI</span>
                                    <button
                                      className="secondary-button settings-toggle-button"
                                    type="button"
                                    onClick={() =>
                                      updateForm(item.interface_name, (current) =>
                                        applyRolePreset(current, "cci"),
                                      )
                                    }
                                    disabled={!item.editable || disableInterfaceActions}
                                  >
                                      Usa {CCI_STATIC_IP_SUGGESTION}/24
                                    </button>
                                  </label>
                                ) : null}

                                <label className="field">
                                  <span className="field-label">Route predefinita</span>
                                  <button
                                    className="secondary-button settings-toggle-button"
                                    type="button"
                                    onClick={() =>
                                      updateForm(item.interface_name, (current) => ({
                                        ...current,
                                        use_default_route: !current.use_default_route,
                                      }))
                                    }
                                    disabled={!item.editable || disableInterfaceActions}
                                  >
                                    {form.use_default_route ? "Abilitata" : "Disattivata"}
                                  </button>
                                </label>

                                <label className="field">
                                  <span className="field-label">DNS</span>
                                  <input
                                    className="field-control"
                                    type="text"
                                    value={form.dns_servers}
                                    onChange={(event) => {
                                      const nextValue = event.currentTarget.value;
                                      updateForm(item.interface_name, (current) => ({
                                        ...current,
                                        dns_servers: nextValue,
                                      }));
                                    }}
                                    disabled={!item.editable || disableInterfaceActions}
                                    placeholder="8.8.8.8, 1.1.1.1"
                                  />
                                </label>

                                {form.ipv4_method === "manual" ? (
                                  <>
                                    <label className="field">
                                      <span className="field-label">{purpose.primaryLabel}</span>
                                      <input
                                        className="field-control"
                                        type="text"
                                        value={form.address}
                                        onChange={(event) => {
                                          const nextValue = event.currentTarget.value;
                                          updateForm(item.interface_name, (current) => ({
                                            ...current,
                                            address: nextValue,
                                          }));
                                        }}
                                        disabled={!item.editable || disableInterfaceActions}
                                        placeholder={purpose.primaryPlaceholder}
                                      />
                                    </label>

                                    <label className="field">
                                      <span className="field-label">{purpose.prefixLabel}</span>
                                      <input
                                        className="field-control"
                                        type="number"
                                        min={1}
                                        max={32}
                                        value={form.prefix_length}
                                        onChange={(event) => {
                                          const nextValue = event.currentTarget.value;
                                          updateForm(item.interface_name, (current) => ({
                                            ...current,
                                            prefix_length: nextValue,
                                          }));
                                        }}
                                        disabled={!item.editable || disableInterfaceActions}
                                      />
                                    </label>

                                    {purpose.secondaryLabel ? (
                                      <>
                                        <label className="field">
                                          <span className="field-label">{purpose.secondaryLabel}</span>
                                          <input
                                            className="field-control"
                                            type="text"
                                            value={form.secondary_address}
                                            onChange={(event) => {
                                              const nextValue = event.currentTarget.value;
                                              updateForm(item.interface_name, (current) => ({
                                                ...current,
                                                secondary_address: nextValue,
                                              }));
                                            }}
                                            disabled={!item.editable || disableInterfaceActions}
                                            placeholder={purpose.secondaryPlaceholder}
                                          />
                                        </label>

                                        <label className="field">
                                          <span className="field-label">
                                            {purpose.secondaryPrefixLabel}
                                          </span>
                                          <input
                                            className="field-control"
                                            type="number"
                                            min={1}
                                            max={32}
                                            value={form.secondary_prefix_length}
                                            onChange={(event) => {
                                              const nextValue = event.currentTarget.value;
                                              updateForm(item.interface_name, (current) => ({
                                                ...current,
                                                secondary_prefix_length: nextValue,
                                              }));
                                            }}
                                            disabled={!item.editable || disableInterfaceActions}
                                          />
                                        </label>
                                      </>
                                    ) : null}

                                    <label className="field field--full">
                                      <span className="field-label">Gateway</span>
                                      <input
                                        className="field-control"
                                        type="text"
                                        value={form.gateway}
                                        onChange={(event) => {
                                          const nextValue = event.currentTarget.value;
                                          updateForm(item.interface_name, (current) => ({
                                            ...current,
                                            gateway: nextValue,
                                          }));
                                        }}
                                        disabled={!item.editable || disableInterfaceActions}
                                        placeholder="192.168.2.1"
                                      />
                                    </label>
                                  </>
                                ) : null}
                              </div>

                              <div className="settings-network-actions">
                                <button
                                  className="secondary-button"
                                  type="button"
                                  onClick={() => {
                                    setForms((current) => ({
                                      ...current,
                                      [item.interface_name]: buildFormState(item),
                                    }));
                                  }}
                                  disabled={disableInterfaceActions}
                                >
                                  Ripristina valori letti
                                </button>
                                <button
                                  className="action-button"
                                  type="button"
                                  onClick={() => void handleApply(item)}
                                  disabled={!item.editable || disableInterfaceActions}
                                >
                                  {applyingThisInterface || assigningThisRole
                                    ? "Salvataggio..."
                                    : "Applica configurazione"}
                                </button>
                              </div>
                            </div>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <div className="detail-empty">
                    Nessuna scheda di rete utile rilevata per questa piattaforma.
                  </div>
                )}
              </section>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
