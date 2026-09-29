import { Presence } from "./overlays.js";
import { Select } from "./controls.js";
import { useEffect, useRef, useState } from "react";
import {
  api,
  Button,
  Confirm,
  Field,
  Input,
  Notice,
  Pager,
  saveExport,
  money,
} from "./core";

type Entity = "customers" | "vehicles" | "invoices" | "lines";
type Mapping = {
  table: string;
  key?: string[];
  customer_key?: string[];
  vehicle_key?: string[];
  invoice_key?: string[];
  fields: Record<string, string>;
  snapshots?: Record<string, Record<string, string>>;
  joins?: {
    table: string;
    local: string;
    foreign: string;
    fields: Record<string, string>;
  }[];
  ignore_blank?: string;
  order_by?: string[];
};
type Profile = {
  version: number;
  canonical?: boolean;
  customers?: Mapping;
  vehicles?: Mapping;
  invoices?: Mapping;
  lines?: Mapping;
  options?: { decimal_separator: string; date_format: string };
  historical_calculation?: { tax_rate: string; evidence: string } | null;
};
type Source = { id: string; name: string };
type Table = {
  name: string;
  linked: boolean;
  rows: number | null;
  primary_key?: string[];
  columns: { name: string; type: string }[];
};
type Incident = {
  id: number;
  level: string;
  entity: string;
  source_key: string;
  message: string;
};
type Resolution = {
  skip?: boolean;
  replace?: boolean;
  accept_difference?: boolean;
  link?: string;
  reason: string;
};
type Review = {
  batch_id: string;
  source_id: string;
  status: string;
  cursor: number;
  capacity: {
    used_bytes: number;
    limit_bytes: number;
    within_limit: boolean;
    files: number;
    file_limit: number;
    projected_after_import: boolean;
  };
  counts: Record<string, number>;
  actions: Record<string, number>;
  profile: Profile;
  diagnostic: {
    name: string;
    engine: string;
    tables: Table[];
    database_format?: string;
    source_sha256: string;
    source_bytes: number;
  };
  incident_counts: { error: number; warning: number };
  incidents: Incident[];
  page: number;
  page_size: number;
  summary: {
    resolutions?: Record<string, Resolution>;
    simulation?: { done: boolean };
    counts?: Record<string, number>;
  };
};
type Reconciliation = {
  balanced: boolean;
  status: string;
  totals: Record<string, number>;
  items: {
    source_key: string;
    full_number: string;
    differences: Record<string, number>;
    excluded: boolean;
  }[];
  page: number;
};
type RecordPreview = {
  entity: string;
  source_key: string;
  action: string;
  payload: Record<string, unknown>;
  original: unknown;
};
type Props = {
  refresh: () => Promise<unknown> | void;
  notify: (message: string) => void;
};
const labels: Record<string, string> = {
  customers: "Clientes",
  vehicles: "Vehículos",
  invoices: "Facturas históricas",
  lines: "Líneas de factura",
  legacy_code: "Código antiguo",
  name: "Nombre",
  tax_id: "NIF",
  address: "Dirección",
  postal_code: "Código postal",
  city: "Población",
  province: "Provincia",
  country: "País",
  phone: "Teléfono",
  phone2: "Otro teléfono",
  email: "Correo",
  notes: "Notas",
  plate: "Matrícula",
  make: "Marca",
  model: "Modelo",
  vin: "Bastidor",
  kind: "Tipo",
  km: "Kilómetros",
  full_number: "Número original",
  issue_date: "Fecha",
  base: "Base original",
  tax: "Cuota IVA original",
  total: "Total original",
  paid: "Cobrado documentado",
  quantity: "Cantidad",
  description: "Concepto",
  unit_price: "Precio",
  tax_rate: "Porcentaje IVA histórico",
  legal_name: "Nombre fiscal",
  insert: "Nuevos",
  unchanged: "Sin cambios",
  replace: "Cambios de origen",
  skip: "Excluidos",
  link: "Vinculados",
};
const fields: Record<Entity, string[]> = {
  customers: [
    "legacy_code",
    "name",
    "tax_id",
    "address",
    "postal_code",
    "city",
    "province",
    "country",
    "phone",
    "phone2",
    "email",
    "notes",
  ],
  vehicles: ["plate", "make", "model", "vin", "kind", "km", "notes"],
  invoices: ["full_number", "issue_date", "base", "tax", "total", "paid"],
  lines: ["description", "quantity", "unit_price", "base", "tax", "tax_rate"],
};
const blankMapping = (): Mapping => ({ table: "", key: [], fields: {} });
const message = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
const statusText: Record<string, string> = {
  diagnosed: "Diagnosticado",
  previewed: "Pendiente de simulación",
  simulated: "Simulación terminada",
  running: "En curso",
  paused: "Pausado",
  completed: "Importado",
  reverted: "Revertido",
  failed: "Requiere revisión",
};

function ColumnSelect({
  label,
  columns,
  value,
  onChange,
  extra = [],
}: {
  label: string;
  columns: string[];
  value?: string;
  onChange: (value: string) => void;
  extra?: string[];
}) {
  return (
    <Field label={label}>
      <Select
        value={value || ""}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">No conservado / sin mapear</option>
        {[...columns, ...extra].map((column) => (
          <option key={column} value={column}>
            {column}
          </option>
        ))}
      </Select>
    </Field>
  );
}
function KeyColumns({
  label,
  columns,
  value = [],
  onChange,
}: {
  label: string;
  columns: string[];
  value?: string[];
  onChange: (value: string[]) => void;
}) {
  return (
    <fieldset
      style={{
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 12,
        marginBlock: 12,
      }}
    >
      <legend>{label}</legend>
      <p>
        Orden de la clave: {value.join(" + ") || "Selecciona columnas"}. El
        orden debe coincidir en ambas tablas.
      </p>
      <div className="form-grid">
        {columns.map((column) => (
          <label
            key={column}
            style={{ display: "flex", gap: 8, alignItems: "center" }}
          >
            <input
              type="checkbox"
              checked={value.includes(column)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...value, column]
                    : value.filter((item) => item !== column),
                )
              }
            />
            {column}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function ProfileEditor({
  profile,
  tables,
  onChange,
}: {
  profile: Profile;
  tables: Table[];
  onChange: (profile: Profile) => void;
}) {
  if (profile.canonical)
    return (
      <Notice>
        Este paquete ya declara clientes, vehículos, claves, instantáneas e
        importes. Se validará su contenido completo.
      </Notice>
    );
  const update = (entity: Entity, change: Partial<Mapping>) =>
    onChange({
      ...profile,
      [entity]: { ...(profile[entity] || blankMapping()), ...change },
    });
  return (
    <>
      <p>
        El perfil sugerido se basa en nombres de tablas y columnas. Revisa las
        claves compuestas y los importes antes de continuar. Una tabla vinculada
        se debe aportar como copia local independiente.
      </p>
      {(["customers", "vehicles", "invoices", "lines"] as Entity[]).map(
        (entity) => {
          const config = profile[entity] || blankMapping();
          const columns =
            tables
              .find((table) => table.name === config.table)
              ?.columns.map((column) => column.name) || [];
          const lineColumns =
            tables
              .find((table) => table.name === profile.lines?.table)
              ?.columns.map((column) => "@lines." + column.name) || [];
          return (
            <details key={entity} open={entity === "customers"}>
              <summary>
                <strong>{labels[entity]}</strong> ·{" "}
                {config.table || "No importar"}
              </summary>
              <div className="panel padded">
                <Field label={`Tabla de ${labels[entity].toLowerCase()}`}>
                  <Select
                    value={config.table}
                    onChange={(event) =>
                      update(entity, {
                        ...blankMapping(),
                        table: event.target.value,
                        customer_key: [],
                        invoice_key: [],
                        ignore_blank:
                          entity === "vehicles" ? "plate" : undefined,
                      })
                    }
                  >
                    <option value="">No importar esta entidad</option>
                    {tables.map((table) => (
                      <option
                        key={table.name}
                        value={table.name}
                        disabled={table.linked}
                      >
                        {table.name}
                        {table.linked
                          ? " · vinculada, no se abre"
                          : ` · ${table.rows} filas`}
                      </option>
                    ))}
                  </Select>
                </Field>
                {config.table && (
                  <>
                    <KeyColumns
                      label={
                        entity === "lines"
                          ? "Clave de la factura a la que pertenece cada línea"
                          : `Clave estable de ${labels[entity].toLowerCase()}`
                      }
                      columns={columns}
                      value={
                        entity === "lines" ? config.invoice_key : config.key
                      }
                      onChange={(value) =>
                        update(
                          entity,
                          entity === "lines"
                            ? { invoice_key: value }
                            : { key: value },
                        )
                      }
                    />
                    {(entity === "vehicles" || entity === "invoices") && (
                      <KeyColumns
                        label="Columnas que identifican al cliente"
                        columns={columns}
                        value={config.customer_key}
                        onChange={(value) =>
                          update(entity, { customer_key: value })
                        }
                      />
                    )}
                    <div className="form-grid">
                      {fields[entity].map((field) => (
                        <ColumnSelect
                          key={field}
                          label={`${labels[entity]} · ${labels[field]}`}
                          columns={columns}
                          extra={entity === "invoices" ? lineColumns : []}
                          value={config.fields[field]}
                          onChange={(value) =>
                            update(entity, {
                              fields: { ...config.fields, [field]: value },
                            })
                          }
                        />
                      ))}
                    </div>
                    {entity === "customers" && (
                      <details>
                        <summary>
                          Relación opcional con códigos postales
                        </summary>
                        {(() => {
                          const join = config.joins?.[0] || {
                            table: "",
                            local: "",
                            foreign: "",
                            fields: { city: "", province: "" },
                          };
                          const related =
                            tables
                              .find((table) => table.name === join.table)
                              ?.columns.map((column) => column.name) || [];
                          const change = (patch: Partial<typeof join>) =>
                            update(entity, { joins: [{ ...join, ...patch }] });
                          return (
                            <div className="form-grid">
                              <Field label="Tabla de códigos postales">
                                <Select
                                  value={join.table}
                                  onChange={(event) =>
                                    event.target.value
                                      ? change({ table: event.target.value })
                                      : update(entity, { joins: [] })
                                  }
                                >
                                  <option value="">Sin relación postal</option>
                                  {tables
                                    .filter((table) => !table.linked)
                                    .map((table) => (
                                      <option key={table.name}>
                                        {table.name}
                                      </option>
                                    ))}
                                </Select>
                              </Field>
                              <ColumnSelect
                                label="Código postal en clientes"
                                columns={columns}
                                value={join.local}
                                onChange={(local) => change({ local })}
                              />
                              <ColumnSelect
                                label="Clave en tabla postal"
                                columns={related}
                                value={join.foreign}
                                onChange={(foreign) => change({ foreign })}
                              />
                              {["city", "province"].map((field) => (
                                <ColumnSelect
                                  key={field}
                                  label={`Dato relacionado: ${labels[field]}`}
                                  columns={related}
                                  value={join.fields[field]}
                                  onChange={(value) =>
                                    change({
                                      fields: {
                                        ...join.fields,
                                        [field]: value,
                                      },
                                    })
                                  }
                                />
                              ))}
                            </div>
                          );
                        })()}
                      </details>
                    )}
                    {entity === "invoices" && (
                      <>
                        <details>
                          <summary>
                            Vehículo de origen e instantáneas históricas
                          </summary>
                          <KeyColumns
                            label="Clave del vehículo (opcional)"
                            columns={columns}
                            value={config.vehicle_key}
                            onChange={(vehicle_key) =>
                              update(entity, { vehicle_key })
                            }
                          />
                          <Notice>
                            Selecciona únicamente datos que se conservaron con
                            la factura. Si faltan, figurará «No consta»; no se
                            copiará la ficha actual.
                          </Notice>
                          {(
                            [
                              [
                                "customer",
                                "Receptor",
                                [
                                  "name",
                                  "tax_id",
                                  "address",
                                  "postal_code",
                                  "city",
                                  "province",
                                ],
                              ],
                              [
                                "issuer",
                                "Emisor",
                                [
                                  "legal_name",
                                  "tax_id",
                                  "address",
                                  "postal_code",
                                  "city",
                                ],
                              ],
                              [
                                "vehicle",
                                "Vehículo",
                                ["plate", "make", "model", "vin"],
                              ],
                            ] as [string, string, string[]][]
                          ).map(([part, label, names]) => (
                            <fieldset key={part}>
                              <legend>{label} original</legend>
                              <div className="form-grid">
                                {names.map((name) => (
                                  <ColumnSelect
                                    key={name}
                                    label={`${label} original · ${labels[name]}`}
                                    columns={columns}
                                    value={config.snapshots?.[part]?.[name]}
                                    onChange={(value) =>
                                      update(entity, {
                                        snapshots: {
                                          ...config.snapshots,
                                          [part]: {
                                            ...config.snapshots?.[part],
                                            [name]: value,
                                          },
                                        },
                                      })
                                    }
                                  />
                                ))}
                              </div>
                            </fieldset>
                          ))}
                        </details>
                      </>
                    )}
                  </>
                )}
              </div>
            </details>
          );
        },
      )}
      <div className="form-grid">
        <Field label="Separador decimal">
          <Select
            value={profile.options?.decimal_separator || "."}
            onChange={(event) =>
              onChange({
                ...profile,
                options: {
                  date_format: profile.options?.date_format || "iso",
                  decimal_separator: event.target.value,
                },
              })
            }
          >
            <option value=".">Punto (10.50; Access nativo)</option>
            <option value=",">Coma (10,50; CSV)</option>
          </Select>
        </Field>
        <Field label="Formato de fecha">
          <Select
            value={profile.options?.date_format || "iso"}
            onChange={(event) =>
              onChange({
                ...profile,
                options: {
                  decimal_separator: profile.options?.decimal_separator || ".",
                  date_format: event.target.value,
                },
              })
            }
          >
            <option value="iso">Año-mes-día / fecha Access</option>
            <option value="dmy">Día/mes/año</option>
          </Select>
        </Field>
      </div>
      <details>
        <summary>Importes calculados por el informe antiguo</summary>
        <Notice tone="warning">
          Solo si el Access guardaba importes de línea y calculaba la cabecera
          al imprimir. La reconstrucción se marcará y conservará su evidencia.
          No se sustituyen importes que sí existen.
        </Notice>
        <label>
          <input
            type="checkbox"
            checked={Boolean(profile.historical_calculation)}
            onChange={(event) =>
              onChange({
                ...profile,
                historical_calculation: event.target.checked
                  ? { tax_rate: "", evidence: "" }
                  : null,
              })
            }
          />{" "}
          El informe usaba una fórmula histórica única confirmada
        </label>
        {profile.historical_calculation && (
          <div className="form-grid">
            <Input
              label="IVA del informe antiguo (%)"
              value={profile.historical_calculation.tax_rate}
              onChange={(event) =>
                onChange({
                  ...profile,
                  historical_calculation: {
                    ...profile.historical_calculation!,
                    tax_rate: event.target.value,
                  },
                })
              }
            />
            <Input
              label="Evidencia de esa fórmula y periodo de aplicación"
              value={profile.historical_calculation.evidence}
              onChange={(event) =>
                onChange({
                  ...profile,
                  historical_calculation: {
                    ...profile.historical_calculation!,
                    evidence: event.target.value,
                  },
                })
              }
            />
          </div>
        )}
      </details>
    </>
  );
}

function ResolveIncident({
  incident,
  initial,
  onSave,
  disabled,
}: {
  incident: Incident;
  initial?: Resolution;
  onSave: (value: Resolution) => void;
  disabled: boolean;
}) {
  const [action, setAction] = useState(
    initial?.skip
      ? "skip"
      : initial?.replace
        ? "replace"
        : initial?.accept_difference
          ? "difference"
          : initial?.link
            ? "link"
            : "",
  );
  const [reason, setReason] = useState(initial?.reason || ""),
    [query, setQuery] = useState("");
  const [matches, setMatches] = useState<{ id: string; name: string }[]>([]),
    [selected, setSelected] = useState(initial?.link || ""),
    [error, setError] = useState("");
  const canLink =
    incident.entity === "customers" || incident.entity === "vehicles";
  return (
    <details>
      <summary>
        {incident.level === "error" ? "Revisar" : "Advertencia"} ·{" "}
        {labels[incident.entity] || incident.entity} {incident.source_key}:{" "}
        {incident.message}
      </summary>
      <div className="panel padded">
        <Field label="Resolución">
          <Select
            disabled={disabled}
            value={action}
            onChange={(event) => setAction(event.target.value)}
          >
            <option value="">Revisar el mapeo / conservar advertencia</option>
            <option value="skip">
              Excluir este registro y conservar su evidencia
            </option>
            <option value="replace">
              Aceptar cambio del origen con sustitución protegida
            </option>
            {incident.entity === "invoices" && (
              <option value="difference">
                Conservar discrepancia de importes del original
              </option>
            )}
            {canLink && (
              <option value="link">
                Vincular explícitamente una ficha existente
              </option>
            )}
          </Select>
        </Field>
        {action === "link" && (
          <>
            <Input
              label="Buscar ficha para vincular"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <Button
              disabled={!query || disabled}
              onClick={async () => {
                try {
                  setError("");
                  if (incident.entity === "customers") {
                    const result = await api<{
                      items: {
                        id: string;
                        name: string;
                        legacy_code: string;
                      }[];
                    }>("customers.list", { query });
                    setMatches(
                      result.items.map((item) => ({
                        id: item.id,
                        name: `${item.name} · ${item.legacy_code || "sin código"}`,
                      })),
                    );
                  } else {
                    const result = await api<
                      { id: string; plate: string; customer_name: string }[]
                    >("vehicles.list", { query });
                    setMatches(
                      result.map((item) => ({
                        id: item.id,
                        name: `${item.plate} · ${item.customer_name}`,
                      })),
                    );
                  }
                } catch (error) {
                  setError(message(error));
                }
              }}
            >
              Buscar ficha
            </Button>
            <Field label="Ficha que has comprobado">
              <Select
                value={selected}
                onChange={(event) => setSelected(event.target.value)}
              >
                <option value="">Seleccionar coincidencia</option>
                {matches.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
            </Field>
          </>
        )}
        {action && (
          <>
            <Input
              label="Motivo documentado"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <Button
              disabled={
                disabled || !reason.trim() || (action === "link" && !selected)
              }
              onClick={() =>
                onSave({
                  reason,
                  ...(action === "skip"
                    ? { skip: true }
                    : action === "replace"
                      ? { replace: true }
                      : action === "difference"
                        ? { accept_difference: true }
                        : { link: selected }),
                })
              }
            >
              Aplicar resolución y revisar
            </Button>
          </>
        )}
        {error && <Notice tone="error">{error}</Notice>}
      </div>
    </details>
  );
}

export function ImportPanel({ refresh, notify }: Props) {
  const [sources, setSources] = useState<Source[]>([]),
    [sourceId, setSourceId] = useState(""),
    [sourceName, setSourceName] = useState("Access del taller");
  const [profiles, setProfiles] = useState<
      { id: string; name: string; profile: Profile }[]
    >([]),
    [profileName, setProfileName] = useState("Mi mapeo Access"),
    [profile, setProfile] = useState<Profile | null>(null);
  const [batches, setBatches] = useState<
      { id: string; status: string; created_at: string }[]
    >([]),
    [batchTotal, setBatchTotal] = useState(0),
    [batchPage, setBatchPage] = useState(0);
  const [file, setFile] = useState<File | null>(null),
    [encoding, setEncoding] = useState("utf-8-sig"),
    [delimiter, setDelimiter] = useState("auto");
  const [review, setReview] = useState<Review | null>(null),
    [reconciliation, setReconciliation] = useState<Reconciliation | null>(null),
    [records, setRecords] = useState<RecordPreview[]>([]),
    [recordTotal, setRecordTotal] = useState(0),
    [recordPage, setRecordPage] = useState(0);
  const [busy, setBusy] = useState(false),
    [progress, setProgress] = useState(""),
    [error, setError] = useState(""),
    [ack, setAck] = useState(false),
    [confirm, setConfirm] = useState<"import" | "rollback" | "discard" | null>(
      null,
    ),
    [reason, setReason] = useState("");
  const stop = useRef(false),
    mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      stop.current = true;
    };
  }, []);
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Source[]>("import.sources"),
      api<{ id: string; name: string; profile: Profile }[]>("import.profiles"),
    ])
      .then(([origins, saved]) => {
        if (active) {
          setSources(origins);
          setProfiles(saved);
          setSourceId((current) => current || origins[0]?.id || "");
        }
      })
      .catch((error) => active && setError(message(error)));
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    api<{
      items: { id: string; status: string; created_at: string }[];
      total: number;
    }>("import.batches", { source_id: sourceId || null, page: batchPage })
      .then((value) => {
        if (active) {
          setBatches(value.items);
          setBatchTotal(value.total);
        }
      })
      .catch((error) => active && setError(message(error)));
    return () => {
      active = false;
    };
  }, [sourceId, batchPage, review?.status]);
  const editable = Boolean(
    review &&
    ["diagnosed", "previewed", "simulated"].includes(review.status) &&
    review.cursor === 0,
  );
  async function guarded(work: () => Promise<void>) {
    setError("");
    setBusy(true);
    stop.current = false;
    try {
      await work();
    } catch (error) {
      if (mounted.current) setError(message(error));
    } finally {
      if (mounted.current) {
        setBusy(false);
        setProgress("");
      }
    }
  }
  async function showRecords(batchId: string, page = 0) {
    const value = await api<{ items: RecordPreview[]; total: number }>(
      "import.records",
      { batch_id: batchId, page },
    );
    if (mounted.current) {
      setRecords(value.items);
      setRecordTotal(value.total);
      setRecordPage(page);
    }
  }
  async function loadBatch(batchId: string) {
    const value = await api<Review>("import.review", { batch_id: batchId });
    if (!mounted.current) return;
    setReview(value);
    setProfile(value.profile);
    setAck(Boolean(value.summary.simulation));
    setReconciliation(null);
    await showRecords(batchId);
    if (value.status === "completed" || value.status === "reverted")
      setReconciliation(
        await api<Reconciliation>("import.reconcile", { batch_id: batchId }),
      );
  }
  async function map(resolutions = review?.summary.resolutions || {}) {
    if (!review || !profile) return;
    const value = await api<Review>("import.map", {
      batch_id: review.batch_id,
      profile,
      resolutions,
    });
    setReview(value);
    setAck(false);
    setReconciliation(null);
    await showRecords(value.batch_id);
  }
  async function upload() {
    if (!file || !sourceId) return;
    let uploaded: { upload_id: string; chunk_bytes: number };
    const storageKey = "canamo-import-upload:" + sourceId;
    const previous = localStorage.getItem(storageKey);
    if (previous) {
      try {
        const status = await api<{
          upload_id: string;
          chunk_bytes: number;
          name: string;
          size: number;
        }>("import.upload_status", { upload_id: previous });
        uploaded =
          status.name === file.name && status.size === file.size
            ? status
            : await api("import.upload_start", {
                name: file.name,
                size: file.size,
                source_id: sourceId,
              });
      } catch {
        uploaded = await api("import.upload_start", {
          name: file.name,
          size: file.size,
          source_id: sourceId,
        });
      }
    } else
      uploaded = await api("import.upload_start", {
        name: file.name,
        size: file.size,
        source_id: sourceId,
      });
    localStorage.setItem(storageKey, uploaded.upload_id);
    // Recheck already received fragments too: a same-name, same-size file is not proof of identity.
    for (let offset = 0; offset < file.size; offset += uploaded.chunk_bytes) {
      if (stop.current) return;
      const bytes = new Uint8Array(
        await file.slice(offset, offset + uploaded.chunk_bytes).arrayBuffer(),
      );
      let binary = "";
      for (let i = 0; i < bytes.length; i += 32768)
        binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
      await api("import.upload_chunk", {
        upload_id: uploaded.upload_id,
        offset,
        content: btoa(binary),
      });
      setProgress(
        `Copia comprobada: ${Math.min(offset + bytes.length, file.size).toLocaleString()} de ${file.size.toLocaleString()} bytes`,
      );
    }
    setProgress("Diagnosticando la copia local…");
    const value = await api<Review>("import.diagnose", {
      upload_id: uploaded.upload_id,
      encoding,
      delimiter,
    });
    localStorage.removeItem(storageKey);
    setReview(value);
    setProfile(value.profile);
    setReconciliation(null);
    setAck(false);
    await showRecords(value.batch_id);
  }
  async function simulate() {
    if (!review) return;
    let done = false;
    while (!done && !stop.current) {
      const value = await api<{
        done: boolean;
        cursor: number;
        remaining: number;
      }>("import.simulate", {
        batch_id: review.batch_id,
        acknowledge_warnings: ack,
      });
      done = value.done;
      setProgress(
        `Simulación: ${value.cursor} revisados, ${value.remaining} pendientes`,
      );
    }
    await loadBatch(review.batch_id);
  }
  async function run() {
    if (!review) return;
    let done = false;
    while (!done && !stop.current) {
      const value = await api<{
        done: boolean;
        cursor: number;
        remaining: number;
      }>("import.run", { batch_id: review.batch_id });
      done = value.done;
      setProgress(
        `Importación: ${value.cursor} revisados, ${value.remaining} pendientes`,
      );
    }
    if (!done) await api("import.pause", { batch_id: review.batch_id });
    await loadBatch(review.batch_id);
    await refresh();
    notify(
      done
        ? "Importación terminada. Revisa la conciliación."
        : "Lote pausado y conservado.",
    );
  }
  async function report() {
    if (!review) return;
    let offset = 0;
    const parts: string[] = [];
    let name = "";
    while (true) {
      const chunk = await api<{
        content: string;
        next_offset: number;
        size: number;
        done: boolean;
        name: string;
      }>("import.export_report_chunk", { batch_id: review.batch_id, offset });
      if (chunk.size > 100 * 1024 * 1024)
        throw new Error(
          "El informe supera 100 MiB. Usa la herramienta de exportación incluida para guardar el informe completo desde la carpeta de datos; no se ha truncado.",
        );
      parts.push(atob(chunk.content));
      offset = chunk.next_offset;
      name = chunk.name;
      if (chunk.done) break;
    }
    await saveExport({
      name,
      mime: "application/x-ndjson",
      content: btoa(parts.join("")),
    });
  }
  return (
    <>
      <div className="settings-title">
        <h2>Traer los datos de Access</h2>
        <p>
          Copia → diagnóstico → mapeo → simulación → importación → conciliación.
        </p>
      </div>
      <Notice>
        Trabaja con una copia cerrada. Conservamos el original y los campos sin
        mapear. El lector MDB/ACCDB abre tablas locales sin ejecutar macros,
        consultas ni vínculos. Los históricos no consumen numeración nueva ni se
        envían a AEAT.
      </Notice>
      <section className="panel padded">
        <h3>1. Seleccionar la copia y su origen</h3>
        <p>
          Usa el mismo origen para copias sucesivas del mismo Access: así se
          detectan registros repetidos y cambios.
        </p>
        <div className="form-grid">
          <Field label="Origen de los datos">
            <Select
              value={sourceId}
              disabled={busy}
              onChange={(event) => {
                setSourceId(event.target.value);
                setBatchPage(0);
              }}
            >
              <option value="">Crear o seleccionar origen</option>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.name}
                </option>
              ))}
            </Select>
          </Field>
          <Input
            label="Nombre de un nuevo origen"
            value={sourceName}
            onChange={(event) => setSourceName(event.target.value)}
          />
        </div>
        <Button
          disabled={busy || !sourceName.trim()}
          onClick={() =>
            guarded(async () => {
              const source = await api<Source>("import.source_save", {
                name: sourceName,
              });
              setSources([...sources, source]);
              setSourceId(source.id);
            })
          }
        >
          Crear origen
        </Button>
        <Field label="Copia Access o archivo intermedio">
          <input
            type="file"
            accept=".mdb,.accdb,.csv,.json,.zip"
            disabled={busy}
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
        </Field>
        <p>
          MDB/ACCDB y CSV hasta 2 GiB. Paquete JSON hasta 64 MiB. Paquetes ZIP
          con tablas JSONL hasta 2 GiB comprimidos. Todos los registros se
          conservan o se informa un error.
        </p>
        <details>
          <summary>Opciones de CSV</summary>
          <div className="form-grid">
            <Field label="Codificación del CSV">
              <Select
                value={encoding}
                onChange={(event) => setEncoding(event.target.value)}
              >
                <option value="utf-8-sig">UTF-8</option>
                <option value="cp1252">Windows-1252</option>
                <option value="utf-16">UTF-16</option>
              </Select>
            </Field>
            <Field label="Separador de columnas CSV">
              <Select
                value={delimiter}
                onChange={(event) => setDelimiter(event.target.value)}
              >
                <option value="auto">Detectar</option>
                <option value=";">Punto y coma</option>
                <option value=",">Coma</option>
                <option value={"\t"}>Tabulación</option>
              </Select>
            </Field>
          </div>
        </details>
        <Button
          tone="primary"
          disabled={busy || !file || !sourceId}
          onClick={() => guarded(upload)}
        >
          Diagnosticar copia
        </Button>
      </section>
      {error && <Notice tone="error">{error}</Notice>}
      {busy && (
        <div role="status">
          <p>{progress || "Procesando…"}</p>
          <Button
            onClick={() => {
              stop.current = true;
              setProgress("Terminando el paso actual antes de pausar…");
            }}
          >
            Pausar después de este paso
          </Button>
        </div>
      )}
      {batches.length > 0 && (
        <details>
          <summary>Lotes conservados de este origen ({batchTotal})</summary>
          <ul>
            {batches.map((batch) => (
              <li key={batch.id}>
                <Button
                  disabled={busy}
                  onClick={() => guarded(() => loadBatch(batch.id))}
                >
                  {batch.created_at} ·{" "}
                  {statusText[batch.status] || batch.status} ·{" "}
                  {batch.id.slice(0, 8)}
                </Button>
              </li>
            ))}
          </ul>
          <Pager total={batchTotal} page={batchPage} onChange={setBatchPage} />
        </details>
      )}
      {review && profile && (
        <>
          <section className="panel padded">
            <h3>2. Diagnóstico y mapeo</h3>
            <Notice tone={review.capacity.within_limit ? "info" : "error"}>
              Copia de seguridad completa:{" "}
              {Math.ceil(review.capacity.used_bytes / 1024 / 1024)} MiB de{" "}
              {Math.floor(review.capacity.limit_bytes / 1024 / 1024)} MiB
              admitidos; {review.capacity.files} archivos.{" "}
              {review.capacity.projected_after_import
                ? "Incluye el crecimiento calculado en la simulación."
                : "Se volverá a comprobar tras simular."}{" "}
              {!review.capacity.within_limit &&
                "La importación se detendrá antes de aplicar el siguiente paso; no se recortan datos."}
            </Notice>
            <p>
              <strong>{review.diagnostic.name}</strong> ·{" "}
              {review.diagnostic.engine} ·{" "}
              {review.diagnostic.database_format ||
                statusText[review.status] ||
                review.status}
            </p>
            <p style={{ overflowWrap: "anywhere" }}>
              SHA-256 de la copia: {review.diagnostic.source_sha256}
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Tabla</th>
                    <th>Filas</th>
                    <th>Lectura</th>
                  </tr>
                </thead>
                <tbody>
                  {review.diagnostic.tables.map((table) => (
                    <tr key={table.name}>
                      <td>{table.name}</td>
                      <td>{table.rows ?? "No leída"}</td>
                      <td>{table.linked ? "Vínculo bloqueado" : "Local"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {editable && (
              <>
                <Field label="Cargar perfil guardado">
                  <Select
                    defaultValue=""
                    onChange={(event) => {
                      const found = profiles.find(
                        (item) => item.id === event.target.value,
                      );
                      if (found) setProfile(found.profile);
                    }}
                  >
                    <option value="">Perfil sugerido / actual</option>
                    {profiles.map((saved) => (
                      <option key={saved.id} value={saved.id}>
                        {saved.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <fieldset disabled={busy} style={{ border: 0, padding: 0 }}>
                  <ProfileEditor
                    profile={profile}
                    tables={review.diagnostic.tables}
                    onChange={setProfile}
                  />
                  <Input
                    label="Nombre del perfil para guardar"
                    value={profileName}
                    onChange={(event) => setProfileName(event.target.value)}
                  />
                  <Button
                    onClick={() =>
                      guarded(async () => {
                        await api("import.profile_save", {
                          name: profileName,
                          profile,
                        });
                        setProfiles(await api("import.profiles"));
                        notify("Perfil guardado");
                      })
                    }
                  >
                    Guardar perfil
                  </Button>
                  <Button tone="primary" onClick={() => guarded(() => map())}>
                    Validar mapeo y previsualizar
                  </Button>
                </fieldset>
              </>
            )}
          </section>
          {review.status !== "diagnosed" && (
            <section className="panel padded">
              <h3>3. Vista previa e incidencias</h3>
              <div className="mini-stats">
                {Object.entries(review.counts).map(([entity, count]) => (
                  <span key={entity}>
                    <strong>{count}</strong>
                    {labels[entity]}
                  </span>
                ))}
              </div>
              <p>
                {Object.entries(review.actions)
                  .map(
                    ([action, count]) =>
                      `${labels[action] || action}: ${count}`,
                  )
                  .join(" · ")}
              </p>
              <Notice tone={review.incident_counts.error ? "error" : "info"}>
                {review.incident_counts.error} incidencias bloqueantes ·{" "}
                {review.incident_counts.warning} advertencias. Se muestran 50
                por página; la descarga incluye todas.
              </Notice>
              {review.incidents.map((incident) => (
                <ResolveIncident
                  key={`${review.batch_id}:${incident.id}`}
                  incident={incident}
                  initial={
                    review.summary.resolutions?.[
                      incident.entity + ":" + incident.source_key
                    ]
                  }
                  disabled={busy || !editable}
                  onSave={(value) =>
                    guarded(() =>
                      map({
                        ...review.summary.resolutions,
                        [incident.entity + ":" + incident.source_key]: value,
                      }),
                    )
                  }
                />
              ))}
              <Pager
                total={
                  review.incident_counts.error + review.incident_counts.warning
                }
                page={review.page}
                onChange={(page: number) =>
                  guarded(async () =>
                    setReview(
                      await api("import.review", {
                        batch_id: review.batch_id,
                        page,
                      }),
                    ),
                  )
                }
              />
              <details>
                <summary>
                  Ver registros y campos originales ({recordTotal})
                </summary>
                {records.map((record, index) => (
                  <details
                    key={`${record.entity}:${record.source_key}:${index}`}
                  >
                    <summary>
                      {labels[record.entity]} · {record.source_key} ·{" "}
                      {labels[record.action] || record.action}
                    </summary>
                    <pre
                      style={{
                        whiteSpace: "pre-wrap",
                        overflowWrap: "anywhere",
                        maxHeight: 360,
                        overflow: "auto",
                      }}
                    >
                      {JSON.stringify(
                        { destino: record.payload, original: record.original },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                ))}
                <Pager
                  total={recordTotal}
                  page={recordPage}
                  onChange={(page: number) =>
                    guarded(() => showRecords(review.batch_id, page))
                  }
                />
              </details>
              <Button disabled={busy} onClick={() => guarded(report)}>
                Guardar informe completo
              </Button>
              {editable && (
                <>
                  <label style={{ display: "flex", gap: 10, marginBlock: 16 }}>
                    <input
                      type="checkbox"
                      checked={ack}
                      onChange={(event) => setAck(event.target.checked)}
                    />{" "}
                    He revisado las advertencias, discrepancias aceptadas y
                    datos desconocidos.
                  </label>
                  <Button
                    disabled={busy || review.incident_counts.error > 0 || !ack}
                    onClick={() => guarded(simulate)}
                  >
                    Simular sin cambiar fichas
                  </Button>
                </>
              )}
            </section>
          )}
          {review.status === "simulated" && (
            <section className="panel padded">
              <h3>4. Simulación terminada</h3>
              <Notice>
                La simulación ha aplicado el mismo importador en una copia
                aislada. Se verificará de nuevo cada registro al confirmar.
              </Notice>
              <Button
                tone="primary"
                disabled={busy}
                onClick={() => setConfirm("import")}
              >
                Continuar con la importación
              </Button>
            </section>
          )}
          {["running", "paused"].includes(review.status) && (
            <section className="panel padded">
              <h3>Lote conservado: {review.cursor} registros revisados</h3>
              <Button
                tone="primary"
                disabled={busy}
                onClick={() => guarded(run)}
              >
                Reanudar importación
              </Button>
            </section>
          )}
          {reconciliation && (
            <section className="panel padded">
              <h3>5. Conciliación</h3>
              <Notice tone={reconciliation.balanced ? "success" : "warning"}>
                {reconciliation.balanced
                  ? "Lote conciliado: registros e importes coinciden con el origen seleccionado."
                  : "Revisa las diferencias o el estado revertido del lote."}
              </Notice>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Dato</th>
                      <th>Origen incluido</th>
                      <th>Destino activo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      "invoices",
                      "lines",
                      "base_cents",
                      "tax_cents",
                      "total_cents",
                    ].map((key) => (
                      <tr key={key}>
                        <th>
                          {
                            {
                              invoices: "Facturas",
                              lines: "Líneas",
                              base_cents: "Base",
                              tax_cents: "Cuota IVA",
                              total_cents: "Total",
                            }[key]
                          }
                        </th>
                        <td>
                          {key.endsWith("cents")
                            ? money(reconciliation.totals["source_" + key])
                            : reconciliation.totals["source_" + key]}
                        </td>
                        <td>
                          {key.endsWith("cents")
                            ? money(reconciliation.totals["destination_" + key])
                            : reconciliation.totals["destination_" + key]}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p>
                Facturas con cobro no documentado:{" "}
                {reconciliation.totals.unknown_payment}. Excluidas
                explícitamente: {reconciliation.totals.excluded}. Documentos con
                diferencias: {reconciliation.totals.differences}.
              </p>
              <details>
                <summary>Diferencias por documento</summary>
                <ul>
                  {reconciliation.items.map((item) => (
                    <li key={item.source_key}>
                      {item.source_key} · {item.full_number} ·{" "}
                      {item.excluded
                        ? "Excluido"
                        : Object.values(item.differences).some(Boolean)
                          ? JSON.stringify(item.differences)
                          : "Coincide"}
                    </li>
                  ))}
                </ul>
                <Pager
                  total={
                    reconciliation.totals.source_invoices +
                    reconciliation.totals.excluded
                  }
                  page={reconciliation.page}
                  onChange={(page: number) =>
                    guarded(async () =>
                      setReconciliation(
                        await api("import.reconcile", {
                          batch_id: review.batch_id,
                          page,
                        }),
                      ),
                    )
                  }
                />
              </details>
            </section>
          )}
          {editable && (
            <section className="panel padded">
              <h3>Descartar este ensayo sin importar</h3>
              <p>
                Elimina la copia temporal y su mapeo de este ensayo. El archivo
                que seleccionaste fuera de la aplicación permanece intacto. Los
                lotes aplicados solo se pueden revertir conservando su
                evidencia.
              </p>
              <Input
                label="Motivo para descartar el ensayo"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <Button
                disabled={busy || !reason.trim()}
                onClick={() => setConfirm("discard")}
              >
                Descartar ensayo
              </Button>
            </section>
          )}
          {["completed", "running", "paused"].includes(review.status) && (
            <section className="panel padded">
              <h3>Revertir este lote</h3>
              <p>
                Se conservan originales y auditoría. Si una ficha o factura
                tiene actividad posterior, la reversión se detiene para
                protegerla.
              </p>
              <Input
                label="Motivo de reversión"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <Button
                disabled={busy || !reason.trim()}
                onClick={() => setConfirm("rollback")}
              >
                Revisar reversión del lote
              </Button>
            </section>
          )}
        </>
      )}
      <Presence>{confirm && (
        <Confirm
          title={
            confirm === "import"
              ? "Confirmar importación"
              : confirm === "discard"
                ? "Descartar ensayo"
                : "Revertir lote"
          }
          text={
            confirm === "import"
              ? "Se guardará una copia previa. Cada paso de hasta 250 registros es transaccional y puede reanudarse. Revisa después la conciliación."
              : confirm === "discard"
                ? "Este ensayo no tiene cambios aplicados. Se eliminará su almacenamiento temporal; el archivo seleccionado originalmente no se modifica."
                : "Se desactivarán los históricos y fichas creados por este lote si no tienen actividad posterior. Se conservarán los originales y la auditoría."
          }
          confirm={
            confirm === "import"
              ? "Importar datos"
              : confirm === "discard"
                ? "Descartar copia temporal"
                : "Revertir con comprobación"
          }
          onClose={() => setConfirm(null)}
          onConfirm={async () => {
            const action = confirm;
            setConfirm(null);
            await guarded(async () => {
              if (action === "import") await run();
              else if (action === "discard" && review) {
                await api("import.discard", {
                  upload_id: review.batch_id,
                  reason,
                });
                setReview(null);
                setProfile(null);
                setRecords([]);
                setReconciliation(null);
                setReason("");
                notify(
                  "Ensayo descartado; el archivo original no se ha modificado.",
                );
              } else if (review) {
                await api("import.rollback", {
                  batch_id: review.batch_id,
                  reason,
                });
                await loadBatch(review.batch_id);
                await refresh();
                notify("Lote revertido; originales conservados.");
              }
            });
          }}
        />
      )}</Presence>
    </>
  );
}
