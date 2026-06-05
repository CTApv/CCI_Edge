import { type ReactNode } from "react";

type SceneSignal = {
  label: string;
  value: string;
  estimated?: boolean;
  estimateNote?: string;
};

type SceneMetric = {
  label: string;
  value: string;
  note: string;
};

type InverterFlowSceneProps = {
  eyebrow: string;
  title: string;
  caption: string;
  status: string;
  statusLabel: string;
  powerLabel: string;
  powerValue: string;
  powerNote: string;
  dcSignals: SceneSignal[];
  acSignals: SceneSignal[];
  metrics: SceneMetric[];
  headerAction?: ReactNode;
  canvasAction?: ReactNode;
};

const sceneNumberFormatter = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 3,
});

function normalizeNumberLiteral(value: string): string {
  const compactValue = value.replace(/\s+/g, "").replace(/'/g, "");
  const dotCount = (compactValue.match(/\./g) ?? []).length;
  const commaCount = (compactValue.match(/,/g) ?? []).length;
  const lastDotIndex = compactValue.lastIndexOf(".");
  const lastCommaIndex = compactValue.lastIndexOf(",");

  if (dotCount > 0 && commaCount > 0) {
    return lastCommaIndex > lastDotIndex
      ? compactValue.replace(/\./g, "").replace(",", ".")
      : compactValue.replace(/,/g, "");
  }

  if (commaCount > 1) {
    const groups = compactValue.split(",");
    const looksGrouped = groups.slice(1).every((group) => group.length === 3);
    return looksGrouped
      ? compactValue.replace(/,/g, "")
      : `${groups.slice(0, -1).join("")}.${groups[groups.length - 1] ?? ""}`;
  }

  if (commaCount === 1) {
    return compactValue.replace(",", ".");
  }

  if (dotCount > 1) {
    const groups = compactValue.split(".");
    const looksGrouped = groups.slice(1).every((group) => group.length === 3);
    return looksGrouped
      ? compactValue.replace(/\./g, "")
      : `${groups.slice(0, -1).join("")}.${groups[groups.length - 1] ?? ""}`;
  }

  return compactValue;
}

function parseSceneNumber(value: string): { numericPart: string; parsed: number } | null {
  const match = value.match(/-?[\d.,'\s]+/);
  if (!match) {
    return null;
  }

  const numericPart = match[0];
  const parsed = Number(normalizeNumberLiteral(numericPart));
  if (!Number.isFinite(parsed)) {
    return null;
  }

  return { numericPart, parsed };
}

function parsePowerMagnitude(value: string): number | null {
  return parseSceneNumber(value)?.parsed ?? null;
}

function normalizeSceneElectricalValue(label: string, value: number): number {
  const normalizedLabel = label
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const absoluteValue = Math.abs(value);

  if (normalizedLabel.includes("frequenza")) {
    if (absoluteValue >= 4_000 && absoluteValue <= 7_000) {
      return value / 100;
    }
    if (absoluteValue >= 400 && absoluteValue <= 700) {
      return value / 10;
    }
  }

  if (normalizedLabel.includes("tensione ac")) {
    if (absoluteValue > 1_000 && absoluteValue <= 10_000) {
      return value / 10;
    }
  }

  if (normalizedLabel.includes("tensione dc")) {
    if (absoluteValue > 1_500 && absoluteValue <= 15_000) {
      return value / 10;
    }
  }

  return value;
}

function formatSceneMeasurement(rawValue: string, label = ""): string {
  const sceneNumber = parseSceneNumber(rawValue);
  if (!sceneNumber) {
    return rawValue;
  }

  const { numericPart, parsed } = sceneNumber;
  const unit = rawValue.replace(numericPart, "").trim();
  const displayValue = normalizeSceneElectricalValue(label, parsed);

  if (!unit) {
    return sceneNumberFormatter.format(displayValue);
  }

  return `${sceneNumberFormatter.format(displayValue)} ${unit}`;
}

function SignalCard({
  label,
  value,
  estimated,
  estimateNote,
  side,
}: SceneSignal & { side: "dc" | "ac" }) {
  return (
    <article className={`flow-signal-inline-card flow-signal-inline-card--${side}`}>
      <div className="flow-signal-inline-head">
        <p className="flow-signal-inline-label">{label}</p>
        {estimated ? (
          <span className="flow-signal-inline-badge" title={estimateNote}>
            Stimata
          </span>
        ) : null}
      </div>
      <strong className="flow-signal-inline-value">{formatSceneMeasurement(value, label)}</strong>
    </article>
  );
}

function MetricCard({
  label,
  value,
  note,
  tone,
}: SceneMetric & { tone: "primary" | "cool" | "warm" | "neutral" }) {
  return (
    <article className={`scene-metric-card scene-metric-card--${tone}`}>
      <p className="scene-metric-label">{label}</p>
      <strong className="scene-metric-value">{value}</strong>
      <p className="scene-metric-note">{note}</p>
    </article>
  );
}

export function InverterFlowScene({
  eyebrow,
  title,
  caption,
  status,
  statusLabel,
  powerLabel,
  powerValue,
  powerNote: _powerNote,
  dcSignals,
  acSignals,
  metrics,
  headerAction,
  canvasAction,
}: InverterFlowSceneProps) {
  const dcRows = [
    ...dcSignals,
    ...Array.from({ length: Math.max(0, 3 - dcSignals.length) }, (_, index) => ({
      label: `Canale DC ${index + dcSignals.length + 1}`,
      value: "n.d.",
    })),
  ].slice(0, 3);
  const acRows = [
    ...acSignals,
    ...Array.from({ length: Math.max(0, 3 - acSignals.length) }, (_, index) => ({
      label: `Canale AC ${index + acSignals.length + 1}`,
      value: "n.d.",
    })),
  ].slice(0, 3);
  const metricTones: Array<"primary" | "cool" | "warm" | "neutral"> = [
    "primary",
    "cool",
    "warm",
    "neutral",
  ];

  const powerMagnitude = parsePowerMagnitude(powerValue);
  const hasLivePower = powerMagnitude !== null && Math.abs(powerMagnitude) > 0.05;
  const isAlert = ["warning", "fault"].includes(status.toLowerCase());
  const scenePowerLabel = powerLabel.length > 18 ? "POTENZA" : powerLabel.toUpperCase();
  const scenePowerDisplay = formatSceneMeasurement(powerValue);

  const dcUpperPath = "M 88 154 C 162 154, 236 166, 332 198";
  const dcLowerPath = "M 88 266 C 162 266, 236 254, 332 222";
  const dcSpinePath = "M 116 210 C 198 210, 262 210, 332 210";
  const acUpperPath = "M 428 198 C 524 166, 598 154, 672 154";
  const acLowerPath = "M 428 222 C 524 254, 598 266, 672 266";
  const acSpinePath = "M 428 210 C 500 210, 564 210, 644 210";

  return (
    <section
      className={`inverter-scene ${hasLivePower ? "" : "inverter-scene--idle"} ${
        isAlert ? "inverter-scene--alert" : ""
      }`.trim()}
      aria-label="Schema inverter lato DC e AC"
    >
      <div className="inverter-scene-header">
        <div className="inverter-scene-copy">
          <p className="panel-kicker">{eyebrow}</p>
          <h2>{title}</h2>
          <p className="inverter-scene-caption">{caption}</p>
        </div>
        <div className="inverter-scene-summary">
          {headerAction ? <div className="inverter-scene-action">{headerAction}</div> : null}
          <span className={`status-badge status-badge--${status.toLowerCase()}`}>
            {statusLabel}
          </span>
        </div>
      </div>

      <div className="inverter-scene-shell">
        <section className="inverter-scene-panel inverter-scene-panel--dc">
          <div className="inverter-scene-panel-head">
            <span className="premium-scene-label premium-scene-label--dc">DC</span>
            <small>Campo FV / accumulo</small>
          </div>
          <div className="inverter-scene-panel-grid">
            {dcRows.map((signal, index) => (
              <SignalCard
                key={`${signal.label}-${signal.value}`}
                {...signal}
                side="dc"
              />
            ))}
          </div>
        </section>

        <div className="inverter-scene-canvas">
          <div className="premium-scene-overlay" aria-hidden="true">
            <div className="premium-scene-centerplate">
              <div className="premium-scene-powerplate">
                <span>{scenePowerLabel}</span>
                <strong>{scenePowerDisplay}</strong>
              </div>
            </div>
          </div>

          <svg
            className="inverter-flow-svg"
            viewBox="0 0 760 420"
            role="img"
            aria-label="Flusso energetico tra lato DC, inverter e lato AC"
          >
            <defs>
              <linearGradient id="premium-stage-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#0d1826" />
                <stop offset="50%" stopColor="#09131f" />
                <stop offset="100%" stopColor="#050b14" />
              </linearGradient>
              <linearGradient id="premium-stage-sheen" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#ffffff" stopOpacity="0.04" />
                <stop offset="42%" stopColor="#ffffff" stopOpacity="0.01" />
                <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
              </linearGradient>
              <pattern id="premium-stage-grid" width="34" height="34" patternUnits="userSpaceOnUse">
                <path d="M 34 0 L 0 0 0 34" fill="none" stroke="rgba(124, 184, 255, 0.05)" />
              </pattern>
              <linearGradient id="premium-dc-shell" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#5cd4bd" stopOpacity="0.04" />
                <stop offset="62%" stopColor="#89f6e0" stopOpacity="0.22" />
                <stop offset="100%" stopColor="#d8fff7" stopOpacity="0.52" />
              </linearGradient>
              <linearGradient id="premium-dc-core" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#67ead1" stopOpacity="0.18" />
                <stop offset="46%" stopColor="#8ff5de" stopOpacity="0.84" />
                <stop offset="100%" stopColor="#f1fffc" stopOpacity="1" />
              </linearGradient>
              <linearGradient id="premium-ac-shell" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#f0f7ff" stopOpacity="0.52" />
                <stop offset="38%" stopColor="#cce6ff" stopOpacity="0.22" />
                <stop offset="100%" stopColor="#7cb8ff" stopOpacity="0.05" />
              </linearGradient>
              <linearGradient id="premium-ac-core" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#ffffff" stopOpacity="0.96" />
                <stop offset="42%" stopColor="#d9ecff" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#98ccff" stopOpacity="0.22" />
              </linearGradient>
              <radialGradient id="premium-core-glow" cx="50%" cy="50%" r="60%">
                <stop offset="0%" stopColor="#9ad2ff" stopOpacity="0.32" />
                <stop offset="36%" stopColor="#5cd4bd" stopOpacity="0.16" />
                <stop offset="100%" stopColor="#02060c" stopOpacity="0" />
              </radialGradient>
              <radialGradient id="premium-core-hub" cx="50%" cy="50%" r="60%">
                <stop offset="0%" stopColor="#ffffff" stopOpacity="0.16" />
                <stop offset="48%" stopColor="#7cc2ff" stopOpacity="0.1" />
                <stop offset="100%" stopColor="#02060c" stopOpacity="0" />
              </radialGradient>
              <linearGradient id="premium-body-shell" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#17354f" />
                <stop offset="54%" stopColor="#0b1826" />
                <stop offset="100%" stopColor="#06111b" />
              </linearGradient>
              <linearGradient id="premium-body-face" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#13273a" />
                <stop offset="100%" stopColor="#08121b" />
              </linearGradient>
              <linearGradient id="premium-body-energy" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="26%" stopColor="#b9dcff" />
                <stop offset="54%" stopColor="#7ecbff" />
                <stop offset="100%" stopColor="#5cd4bd" />
              </linearGradient>
              <linearGradient id="premium-orbit-dc" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#5cd4bd" stopOpacity="0.12" />
                <stop offset="100%" stopColor="#d8fff7" stopOpacity="0.72" />
              </linearGradient>
              <linearGradient id="premium-orbit-ac" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#f4f9ff" stopOpacity="0.72" />
                <stop offset="100%" stopColor="#7cb8ff" stopOpacity="0.14" />
              </linearGradient>
              <filter id="premium-soft-glow" x="-60%" y="-60%" width="220%" height="220%">
                <feGaussianBlur stdDeviation="8" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <rect className="premium-stage-shell" x="18" y="18" width="724" height="384" rx="32" />
            <rect className="premium-stage-sheen" x="18" y="18" width="724" height="384" rx="32" />
            <rect className="premium-stage-gridfill" x="18" y="18" width="724" height="384" rx="32" />
            <g className="premium-side-art premium-side-art--dc" transform="translate(58 158)">
              <g className="premium-panel-icon" transform="rotate(-12 56 42)">
                <rect className="premium-panel-icon__frame" x="18" y="16" width="76" height="50" rx="8" />
                <path
                  className="premium-panel-icon__grid"
                  d="M 34 16 V 66 M 50 16 V 66 M 66 16 V 66 M 82 16 V 66 M 18 32 H 94 M 18 48 H 94"
                />
                <path className="premium-panel-icon__stand" d="M 50 66 L 42 88 M 62 66 L 70 88 M 34 88 H 78" />
                <path className="premium-panel-icon__accent" d="M 26 24 L 86 24" />
              </g>
            </g>

            <g className="premium-side-art premium-side-art--ac" transform="translate(618 126)">
              <g className="premium-tower-icon">
                <path className="premium-tower-icon__main" d="M 42 8 L 16 164 M 42 8 L 68 164 M 42 8 V 164" />
                <path className="premium-tower-icon__cross" d="M 10 44 H 74 M 16 84 H 68 M 22 120 H 62 M 28 148 H 56" />
                <path className="premium-tower-icon__brace" d="M 22 44 L 42 84 L 62 44" />
                <path className="premium-tower-icon__brace" d="M 28 84 L 42 120 L 56 84" />
                <path className="premium-tower-icon__brace" d="M 32 120 L 42 148 L 52 120" />
                <path className="premium-tower-icon__arm" d="M 10 44 L 0 58 M 74 44 L 84 58" />
                <path className="premium-tower-icon__arm" d="M 16 84 L 6 98 M 68 84 L 78 98" />
                <circle className="premium-tower-icon__node" cx="0" cy="58" r="3.2" />
                <circle className="premium-tower-icon__node" cx="84" cy="58" r="3.2" />
                <circle className="premium-tower-icon__node premium-tower-icon__node--soft" cx="6" cy="98" r="2.8" />
                <circle className="premium-tower-icon__node premium-tower-icon__node--soft" cx="78" cy="98" r="2.8" />
              </g>
            </g>
            <rect className="premium-stage-window" x="42" y="86" width="676" height="248" rx="28" />
            <text className="premium-side-caption premium-side-caption--dc" x="86" y="126">STRINGHE DC</text>
            <text className="premium-side-caption premium-side-caption--ac" x="674" y="126">VERSO RETE</text>

            <ellipse className="premium-stage-aura" cx="380" cy="210" rx="170" ry="98" />
            <ellipse className="premium-stage-ring premium-stage-ring--outer" cx="380" cy="210" rx="158" ry="88" />
            <ellipse className="premium-stage-ring premium-stage-ring--inner" cx="380" cy="210" rx="124" ry="64" />
            <ellipse className="premium-stage-hub" cx="380" cy="210" rx="98" ry="52" />

            <path className="premium-stream-shell premium-stream-shell--dc" d={dcUpperPath} />
            <path className="premium-stream-shell premium-stream-shell--dc" d={dcLowerPath} />
            <path className="premium-stream-shell premium-stream-shell--dc premium-stream-shell--spine" d={dcSpinePath} />
            <path className="premium-stream-shell premium-stream-shell--ac" d={acUpperPath} />
            <path className="premium-stream-shell premium-stream-shell--ac" d={acLowerPath} />
            <path className="premium-stream-shell premium-stream-shell--ac premium-stream-shell--spine" d={acSpinePath} />

            <path className="premium-stream-core premium-stream-core--dc" d={dcUpperPath} />
            <path className="premium-stream-core premium-stream-core--dc" d={dcLowerPath} />
            <path className="premium-stream-core premium-stream-core--dc premium-stream-core--spine" d={dcSpinePath} />
            <path className="premium-stream-core premium-stream-core--ac" d={acUpperPath} />
            <path className="premium-stream-core premium-stream-core--ac" d={acLowerPath} />
            <path className="premium-stream-core premium-stream-core--ac premium-stream-core--spine" d={acSpinePath} />

            <circle className="premium-stream-node premium-stream-node--dc" cx="92" cy="158" r="5.2" />
            <circle className="premium-stream-node premium-stream-node--dc" cx="92" cy="262" r="5.2" />
            <circle className="premium-stream-node premium-stream-node--dc premium-stream-node--inner" cx="158" cy="210" r="4.2" />
            <circle className="premium-stream-node premium-stream-node--ac" cx="668" cy="158" r="5.2" />
            <circle className="premium-stream-node premium-stream-node--ac" cx="668" cy="262" r="5.2" />
            <circle className="premium-stream-node premium-stream-node--ac premium-stream-node--inner" cx="602" cy="210" r="4.2" />

            {hasLivePower ? (
              <>
                <circle className="premium-stream-particle premium-stream-particle--dc" r="4.4">
                  <animateMotion dur="3.7s" repeatCount="indefinite" path={dcUpperPath} />
                </circle>
                <circle className="premium-stream-particle premium-stream-particle--dc" r="4">
                  <animateMotion
                    dur="4.4s"
                    begin="0.9s"
                    repeatCount="indefinite"
                    path={dcLowerPath}
                  />
                </circle>
                <circle className="premium-stream-particle premium-stream-particle--dc premium-stream-particle--spine" r="3.6">
                  <animateMotion
                    dur="3.9s"
                    begin="0.4s"
                    repeatCount="indefinite"
                    path={dcSpinePath}
                  />
                </circle>
                <circle className="premium-stream-particle premium-stream-particle--ac" r="4.4">
                  <animateMotion dur="3.6s" repeatCount="indefinite" path={acUpperPath} />
                </circle>
                <circle className="premium-stream-particle premium-stream-particle--ac" r="4">
                  <animateMotion
                    dur="4.2s"
                    begin="0.8s"
                    repeatCount="indefinite"
                    path={acLowerPath}
                  />
                </circle>
                <circle className="premium-stream-particle premium-stream-particle--ac premium-stream-particle--spine" r="3.6">
                  <animateMotion
                    dur="3.8s"
                    begin="0.6s"
                    repeatCount="indefinite"
                    path={acSpinePath}
                  />
                </circle>
                <circle className="premium-stage-pulse" cx="380" cy="210" r="52">
                  <animate attributeName="r" values="54;96;54" dur="4.3s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.08;0.18;0.08" dur="4.3s" repeatCount="indefinite" />
                </circle>
                <circle className="premium-stage-pulse" cx="380" cy="210" r="76">
                  <animate
                    attributeName="r"
                    values="78;138;78"
                    dur="5.4s"
                    begin="0.9s"
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="opacity"
                    values="0.04;0.1;0.04"
                    dur="5.4s"
                    begin="0.9s"
                    repeatCount="indefinite"
                  />
                </circle>
              </>
            ) : null}

            <g className="premium-orbit-shell premium-orbit-shell--dc">
              <path d="M 296 158 C 324 126, 352 116, 380 116" />
              <path d="M 296 262 C 324 294, 352 304, 380 304" />
            </g>
            <g className="premium-orbit-shell premium-orbit-shell--ac">
              <path d="M 464 116 C 494 116, 522 126, 548 158" />
              <path d="M 464 304 C 494 304, 522 294, 548 262" />
            </g>

            {hasLivePower ? (
              <>
                <g className="premium-orbit-spinner premium-orbit-spinner--dc">
                  <circle className="premium-orbit-dot premium-orbit-dot--dc" cx="380" cy="116" r="3.6" />
                  <circle className="premium-orbit-dot premium-orbit-dot--dc premium-orbit-dot--soft" cx="380" cy="304" r="2.8" />
                </g>
                <g className="premium-orbit-spinner premium-orbit-spinner--ac">
                  <circle className="premium-orbit-dot premium-orbit-dot--ac" cx="380" cy="116" r="3.6" />
                  <circle className="premium-orbit-dot premium-orbit-dot--ac premium-orbit-dot--soft" cx="380" cy="304" r="2.8" />
                </g>
              </>
            ) : null}

            <g className="premium-monolith" filter="url(#premium-soft-glow)">
              <rect className="premium-monolith-shell" x="320" y="118" width="120" height="184" rx="40" />
              <rect className="premium-monolith-face" x="344" y="144" width="72" height="130" rx="24" />
              <rect className="premium-monolith-energy" x="374" y="164" width="12" height="92" rx="6" />
              <path className="premium-monolith-cut" d="M 356 166 C 370 156, 392 156, 404 166" />
              <path className="premium-monolith-cut premium-monolith-cut--lower" d="M 356 252 C 372 260, 392 260, 404 252" />
              <rect className="premium-monolith-base" x="352" y="284" width="56" height="8" rx="4" />
              <g className="premium-monolith-leds">
                <circle cx="362" cy="258" r="3.1" />
                <circle cx="380" cy="254" r="3.3" />
                <circle cx="398" cy="258" r="3.1" />
              </g>
            </g>
          </svg>
          {canvasAction ? (
            <div className="inverter-scene-canvas-action">{canvasAction}</div>
          ) : null}
        </div>

        <section className="inverter-scene-panel inverter-scene-panel--ac">
          <div className="inverter-scene-panel-head inverter-scene-panel-head--ac">
            <span className="premium-scene-label premium-scene-label--ac">AC</span>
            <small>Uscita verso rete</small>
          </div>
          <div className="inverter-scene-panel-grid">
            {acRows.map((signal, index) => (
              <SignalCard
                key={`${signal.label}-${signal.value}`}
                {...signal}
                side="ac"
              />
            ))}
          </div>
        </section>
      </div>

      <div className="scene-metric-strip">
        {metrics.map((metric, index) => (
          <MetricCard key={metric.label} {...metric} tone={metricTones[index] ?? "neutral"} />
        ))}
      </div>
    </section>
  );
}
