import { useEffect, useState, type FormEvent } from "react";

import {
  deleteDevice,
  getCatalogModels,
  getSerialPorts,
  getSystemOptions,
  testProtocolConnection,
  updateDevice,
  type CatalogModel,
  type Device,
  type ProtocolTestResult,
  type SerialPortInfo,
  type SystemOptions,
} from "../api";
import {
  buildConnectionSettingsError,
  buildConnectionTestPayload,
  buildFormStateFromDevice,
  getGuidedConnectionFields,
  buildSerialPortOptions,
  buildUpdatePayload,
  buildProtocolSettings,
  buildTestResultTitle,
  compareLabels,
  findCatalogEntry,
  formatConnectionSettingsText,
  formatDiagnosticValue,
  getGuidedFieldValue,
  getSerialPortDisplayName,
  listCatalogBrands,
  listCatalogModelsForBrand,
  isTransportAllowedForProtocol,
  parseConnectionSettingsSafe,
  PROTOCOL_DEFAULT_SETTINGS,
  PROTOCOL_TRANSPORTS,
  translateDiagnosticLabel,
  translateStatusLabel,
  translateTestMessage,
  type GuidedFieldConfig,
  type ProvisionFormState,
} from "./deviceProvisioningShared";

type DeviceConnectionDrawerProps = {
  device: Device;
  onClose: () => void;
  onDeleted: (deviceId: string) => Promise<void>;
  onUpdated: () => Promise<void>;
};

function formatConnectionKey(key: string): string {
  return key.split("_").join(" ");
}

function formatConnectionValue(
  key: string,
  value: string | number | boolean,
  transport: string,
): string {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (transport === "serial" && key === "port" && typeof value === "string") {
    return getSerialPortDisplayName(value);
  }

  return String(value);
}

export function DeviceConnectionDrawer({
  device,
  onClose,
  onDeleted,
  onUpdated,
}: DeviceConnectionDrawerProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [catalogModels, setCatalogModels] = useState<CatalogModel[]>([]);
  const [systemOptions, setSystemOptions] = useState<SystemOptions | null>(null);
  const [serialPorts, setSerialPorts] = useState<SerialPortInfo[]>([]);
  const [form, setForm] = useState<ProvisionFormState>(() => buildFormStateFromDevice(device));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ProtocolTestResult | null>(null);

  useEffect(() => {
    setForm(buildFormStateFromDevice(device));
    setEditing(false);
    setSubmitError(null);
    setTestError(null);
    setTestResult(null);
    setConfirmDelete(false);
  }, [device.device_id]);

  useEffect(() => {
    let isActive = true;

    async function loadOptions() {
      setLoadError(null);

      try {
        const [nextCatalogModels, nextSystemOptions, nextSerialPorts] = await Promise.all([
          getCatalogModels(),
          getSystemOptions(),
          getSerialPorts(),
        ]);

        if (!isActive) {
          return;
        }

        setCatalogModels(nextCatalogModels);
        setSystemOptions(nextSystemOptions);
        setSerialPorts(nextSerialPorts.ports);
      } catch (error) {
        if (!isActive) {
          return;
        }

        setLoadError(
          error instanceof Error
            ? error.message
            : "Impossibile caricare le opzioni del dispositivo.",
        );
      }
    }

    void loadOptions();
    return () => {
      isActive = false;
    };
  }, []);

  function updateFormField<Key extends keyof ProvisionFormState>(
    key: Key,
    value: ProvisionFormState[Key],
  ) {
    setSubmitError(null);
    setTestError(null);
    setTestResult(null);
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleProtocolChange(protocol: string) {
    setSubmitError(null);
    setTestError(null);
    setTestResult(null);
    setForm((current) => {
      const selectedCatalogModel =
        current.brand && current.model
          ? findCatalogEntry(catalogModels, current.brand, current.model, protocol)
          : null;

      return {
        ...current,
        protocol,
        transport:
          selectedCatalogModel?.transport ??
          (isTransportAllowedForProtocol(protocol, current.transport)
            ? current.transport
            :
          PROTOCOL_TRANSPORTS[protocol] ??
          current.transport),
        connectionSettingsText: selectedCatalogModel
          ? formatConnectionSettingsText(selectedCatalogModel.defaults)
          : PROTOCOL_DEFAULT_SETTINGS[protocol]
            ? formatConnectionSettingsText(
                buildProtocolSettings(
                  protocol,
                  parseConnectionSettingsSafe(current.connectionSettingsText),
                  current.transport,
                ),
              )
            : current.connectionSettingsText,
      };
    });
  }

  function handleGuidedFieldChange(field: GuidedFieldConfig, rawValue: string) {
    setSubmitError(null);
    setTestError(null);
    setTestResult(null);

    setForm((current) => {
      const nextSettings = buildProtocolSettings(
        current.protocol,
        parseConnectionSettingsSafe(current.connectionSettingsText),
        current.transport,
      );

      for (const alias of field.aliases ?? []) {
        delete nextSettings[alias];
      }

      if (rawValue === "") {
        delete nextSettings[field.key];
      } else if (field.type === "number") {
        nextSettings[field.key] = Number(rawValue);
      } else {
        nextSettings[field.key] = rawValue;
      }

      return {
        ...current,
        connectionSettingsText: formatConnectionSettingsText(nextSettings),
      };
    });
  }

  function handleBrandChange(brand: string) {
    setSubmitError(null);
    setTestError(null);
    setTestResult(null);
    setForm((current) => ({
      ...current,
      brand,
      model: "",
      protocol: "",
      transport: "",
      connectionSettingsText: "{}",
    }));
  }

  function handleModelChange(model: string) {
    setSubmitError(null);
    setTestError(null);
    setTestResult(null);

    if (!form.brand) {
      return;
    }

    const selectedCatalogModel = findCatalogEntry(
      catalogModels,
      form.brand,
      model,
      form.protocol || undefined,
    );
    if (!selectedCatalogModel) {
      setForm((current) => ({ ...current, model }));
      return;
    }

    setForm((current) => ({
      ...current,
      model: selectedCatalogModel.model,
      protocol: selectedCatalogModel.protocol,
      transport: selectedCatalogModel.transport,
      name: current.name || selectedCatalogModel.model,
      connectionSettingsText: formatConnectionSettingsText(selectedCatalogModel.defaults),
    }));
  }

  async function handleDelete() {
    setDeleting(true);
    setSubmitError(null);

    try {
      await deleteDevice(device.device_id);
      await onDeleted(device.device_id);
    } catch (deleteError) {
      setSubmitError(
        deleteError instanceof Error
          ? deleteError.message
          : "Impossibile eliminare il dispositivo.",
      );
    } finally {
      setDeleting(false);
    }
  }

  async function handleTestConnection() {
    setTestError(null);
    setTestResult(null);
    setTesting(true);

    try {
      const payload = buildConnectionTestPayload(form);
      const result = await testProtocolConnection(payload);
      setTestResult(result);
    } catch (error) {
      setTestError(
        error instanceof Error
          ? error.message
          : "Impossibile eseguire il test di connessione.",
      );
    } finally {
      setTesting(false);
    }
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    setSaving(true);

    try {
      await updateDevice(device.device_id, buildUpdatePayload(form));
      await onUpdated();
      onClose();
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Impossibile aggiornare il dispositivo.",
      );
    } finally {
      setSaving(false);
    }
  }

  const connectionSettings = parseConnectionSettingsSafe(form.connectionSettingsText);
  const hasCoreConfiguration =
    form.name.trim() !== "" &&
    form.brand.trim() !== "" &&
    form.model.trim() !== "" &&
    form.protocol.trim() !== "" &&
    form.transport.trim() !== "" &&
    form.status.trim() !== "";
  const connectionSettingsError =
    form.protocol && form.transport
      ? buildConnectionSettingsError(form.protocol, form.transport, form.connectionSettingsText)
      : null;
  const canValidateOrSave =
    hasCoreConfiguration && connectionSettings !== null && connectionSettingsError === null;
  const guidedFields = getGuidedConnectionFields(form.protocol, form.transport);
  const brandOptions = listCatalogBrands(catalogModels, form.brand);
  const modelOptions = form.brand
    ? listCatalogModelsForBrand(catalogModels, form.brand, form.model)
    : [];

  return (
    <div className="settings-backdrop">
      <aside
        aria-labelledby="settings-drawer-title"
        aria-modal="true"
        className="settings-drawer"
        role="dialog"
      >
        <div className="modal-header">
          <div className="modal-title-group">
            <p className="panel-kicker">Gestione dispositivo</p>
            <h2 id="settings-drawer-title">
              {editing ? "Modifica configurazione" : "Impostazioni connessione"}
            </h2>
            <p className="modal-copy">
              Parametri di comunicazione, modifica profilo e azioni di gestione per il
              dispositivo selezionato.
            </p>
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={onClose}
            disabled={deleting || saving || testing}
          >
            Chiudi
          </button>
        </div>

        <div className="settings-content">
          {loadError ? <div className="panel-state panel-state--error">{loadError}</div> : null}
          {submitError ? <div className="panel-state panel-state--error">{submitError}</div> : null}
          {testError ? <div className="panel-state panel-state--error">{testError}</div> : null}

          <section className="settings-summary">
            <p className="panel-kicker">Dispositivo</p>
            <h3>{device.name}</h3>
            <p className="settings-summary-meta">{device.brand} | {device.model}</p>
            <p className="settings-summary-meta">
              {device.protocol} | {device.transport} | {translateStatusLabel(device.status)}
            </p>
          </section>

          {editing ? (
            <section className="settings-section settings-section--edit">
              <div className="settings-section-header">
                <div>
                  <p className="panel-kicker">Configurazione</p>
                  <h3 className="detail-section-title">Profilo e connessione</h3>
                </div>
              </div>

              <form className="modal-form settings-edit-form" onSubmit={handleSave}>
                <div className="form-grid">
                  <label className="field">
                    <span className="field-label">Nome</span>
                    <input
                      className="field-control"
                      type="text"
                      value={form.name}
                      onChange={(event) => updateFormField("name", event.currentTarget.value)}
                      disabled={saving || testing}
                    />
                  </label>

                  <label className="field">
                    <span className="field-label">Marchio</span>
                    <select
                      className="field-control"
                      value={form.brand}
                      onChange={(event) => handleBrandChange(event.currentTarget.value)}
                      disabled={saving || testing}
                    >
                      <option value="">Seleziona produttore</option>
                      {brandOptions.map((brand) => (
                        <option key={brand} value={brand}>
                          {brand}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="field">
                    <span className="field-label">Modello</span>
                    <select
                      className="field-control"
                      value={form.model}
                      onChange={(event) => handleModelChange(event.currentTarget.value)}
                      disabled={saving || testing || !form.brand}
                    >
                      <option value="">Seleziona modello</option>
                      {modelOptions.map((catalogModel) => (
                        <option
                          key={`${catalogModel.brand}|${catalogModel.model}|${catalogModel.protocol}`}
                          value={catalogModel.model}
                        >
                          {catalogModel.model}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="field">
                    <span className="field-label">Stato</span>
                    <select
                      className="field-control"
                      value={form.status}
                      onChange={(event) => updateFormField("status", event.currentTarget.value)}
                      disabled={saving || testing}
                    >
                      <option value="">Seleziona stato</option>
                      {(systemOptions?.device_statuses ?? [device.status])
                        .slice()
                        .sort(compareLabels)
                        .map((status) => (
                          <option key={status} value={status}>
                            {translateStatusLabel(status)}
                          </option>
                        ))}
                    </select>
                  </label>

                  <label className="field">
                    <span className="field-label">Protocollo</span>
                    <select
                      className="field-control"
                      value={form.protocol}
                      onChange={(event) => handleProtocolChange(event.currentTarget.value)}
                      disabled={saving || testing}
                    >
                      <option value="">Seleziona protocollo</option>
                      {(systemOptions?.protocols ?? [device.protocol])
                        .slice()
                        .sort(compareLabels)
                        .map((protocol) => (
                          <option key={protocol} value={protocol}>
                            {protocol}
                          </option>
                        ))}
                    </select>
                  </label>

                  <label className="field">
                    <span className="field-label">Trasporto</span>
                    <select
                      className="field-control"
                      value={form.transport}
                      onChange={(event) => updateFormField("transport", event.currentTarget.value)}
                      disabled={saving || testing}
                    >
                      <option value="">Seleziona trasporto</option>
                      {(systemOptions?.transports ?? [device.transport])
                        .slice()
                        .sort(compareLabels)
                        .map((transport) => (
                          <option key={transport} value={transport}>
                            {transport}
                          </option>
                        ))}
                    </select>
                  </label>

                  {guidedFields.length > 0 ? (
                    <div className="field field--full">
                      <span className="field-label">Parametri guidati</span>
                      <div className="form-grid">
                        {guidedFields.map((field) => (
                          <label key={field.key} className="field">
                            <span className="field-label">{field.label}</span>
                            {form.transport === "serial" && field.key === "port" ? (
                              <select
                                className="field-control"
                                value={getGuidedFieldValue(connectionSettings, field)}
                                onChange={(event) =>
                                  handleGuidedFieldChange(field, event.currentTarget.value)
                                }
                                disabled={saving || testing}
                              >
                                <option value="">Seleziona porta seriale</option>
                                {buildSerialPortOptions(
                                  serialPorts,
                                  getGuidedFieldValue(connectionSettings, field),
                                ).map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            ) : field.options ? (
                              <select
                                className="field-control"
                                value={getGuidedFieldValue(connectionSettings, field)}
                                onChange={(event) =>
                                  handleGuidedFieldChange(field, event.currentTarget.value)
                                }
                                disabled={saving || testing}
                              >
                                <option value="">Seleziona valore</option>
                                {field.options.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <input
                                className="field-control"
                                type={field.type === "number" ? "number" : "text"}
                                value={getGuidedFieldValue(connectionSettings, field)}
                                onChange={(event) =>
                                  handleGuidedFieldChange(field, event.currentTarget.value)
                                }
                                disabled={saving || testing}
                              />
                            )}
                          </label>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <label className="field field--full">
                    <span className="field-label">Impostazioni di connessione (JSON avanzato)</span>
                    <textarea
                      className="field-control field-control--code"
                      rows={10}
                      value={form.connectionSettingsText}
                      onChange={(event) =>
                        updateFormField("connectionSettingsText", event.currentTarget.value)
                      }
                      disabled={saving || testing}
                    />
                  </label>
                </div>

                {connectionSettingsError ? (
                  <div className="panel-state panel-state--error">{connectionSettingsError}</div>
                ) : null}

                {testResult ? (
                  <section
                    className={`test-result test-result--${
                      testResult.success ? "success" : "failure"
                    }`}
                  >
                    <div className="test-result-header">
                      <div>
                        <p className="panel-kicker">Test connessione</p>
                        <h3>{buildTestResultTitle(testResult)}</h3>
                      </div>
                      <span
                        className={`test-badge test-badge--${
                          testResult.success ? "success" : "failure"
                        }`}
                      >
                        {testResult.success ? "Successo" : "Errore"}
                      </span>
                    </div>
                    <p className="test-result-message">
                      {translateTestMessage(testResult.message)}
                    </p>
                    <div className="test-diagnostics">
                      {Object.entries(testResult.diagnostics).map(([key, value]) => (
                        <article key={key} className="test-diagnostic-card">
                          <p className="test-diagnostic-key">
                            {translateDiagnosticLabel(key)}
                          </p>
                          <strong className="test-diagnostic-value">
                            {formatDiagnosticValue(key, value)}
                          </strong>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}

                <div className="modal-footer">
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => {
                      setEditing(false);
                      setSubmitError(null);
                      setTestError(null);
                      setTestResult(null);
                      setForm(buildFormStateFromDevice(device));
                    }}
                    disabled={saving || testing}
                  >
                    Annulla modifica
                  </button>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void handleTestConnection()}
                    disabled={saving || testing || !canValidateOrSave}
                  >
                    {testing ? "Test in corso..." : "Test connessione"}
                  </button>
                  <button
                    className="action-button"
                    type="submit"
                    disabled={saving || testing || !canValidateOrSave}
                  >
                    {saving ? "Salvataggio..." : "Salva modifiche"}
                  </button>
                </div>
              </form>
            </section>
          ) : (
            <>
              <section className="settings-section">
                <div className="settings-section-header">
                  <div>
                    <p className="panel-kicker">Connessione</p>
                    <h3 className="detail-section-title">Parametri di comunicazione</h3>
                  </div>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => setEditing(true)}
                    disabled={deleting}
                  >
                    Modifica configurazione
                  </button>
                </div>

                {Object.entries(device.connection_settings).length > 0 ? (
                  <div className="settings-list">
                    {Object.entries(device.connection_settings).map(([key, value]) => (
                      <article key={key} className="settings-item">
                        <p className="settings-item-label">{formatConnectionKey(key)}</p>
                        <strong className="settings-item-value">
                          {formatConnectionValue(key, value, device.transport)}
                        </strong>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="detail-empty">
                    Nessuna impostazione di connessione definita per questo dispositivo.
                  </p>
                )}
              </section>

              <section className="settings-section settings-delete-box">
                <div className="settings-section-header">
                  <div>
                    <p className="panel-kicker">Azioni dispositivo</p>
                    <h3 className="detail-section-title">Eliminazione dispositivo</h3>
                  </div>
                </div>

                <p className="confirm-note">
                  Questa azione rimuove il dispositivo dal parco inverter configurato e richiede
                  una conferma esplicita prima di procedere.
                </p>

                {!confirmDelete ? (
                  <button
                    className="danger-outline-button"
                    type="button"
                    onClick={() => setConfirmDelete(true)}
                  >
                    Elimina dispositivo
                  </button>
                ) : (
                  <div className="confirm-actions">
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => setConfirmDelete(false)}
                      disabled={deleting}
                    >
                      Annulla
                    </button>
                    <button
                      className="danger-button"
                      type="button"
                      onClick={() => void handleDelete()}
                      disabled={deleting}
                    >
                      {deleting ? "Eliminazione..." : "Conferma eliminazione"}
                    </button>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
