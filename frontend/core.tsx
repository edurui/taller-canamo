import * as React from "react";
import {
  Modal,
  Popup,
  Presence,
  useCompact,
  type ModalProps,
} from "./overlays.js";
import { TextInput, Textarea, Select, Autocomplete } from "./controls.js";
export { Modal, Presence } from "./overlays.js";
export {
  TextInput,
  Textarea,
  Select,
  NumberInput,
  DateInput,
} from "./controls.js";

export interface CustomerMatch {
  customer_id: string;
  vehicle_id: string | null;
  name: string;
  phone: string;
  legacy_code: string;
  plate: string | null;
  make: string | null;
  model: string | null;
}
type WithChildren = { children?: React.ReactNode };
type FieldProps = WithChildren & {
  label: React.ReactNode;
  hint?: React.ReactNode;
  required?: boolean;
  className?: string;
};
type InputProps = React.InputHTMLAttributes<HTMLInputElement> &
  Pick<FieldProps, "label" | "hint">;
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: string;
  tone?: string;
  busy?: boolean;
};
export type Row = Record<string, any>;
export type Setter<T> = (value: T | ((previous: T) => T)) => void;
export function useState<T>(initial: T | (() => T)): [T, Setter<T>] {
  return React.useState(initial);
}
export const useEffect: (
  effect: () => void | (() => void),
  deps?: unknown[],
) => void = React.useEffect;
export function useRef<T>(initial: T): { current: T } {
  return React.useRef(initial);
}
export const uuid = () => crypto.randomUUID();
export const money = (value: number | null = 0) =>
  value === null ? "No consta" :
  new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR" }).format(
    (value || 0) / 100,
  );
export const dateText = (v: string | null = "") =>
  v
    ? new Date(v.length === 10 ? v + "T12:00:00" : v).toLocaleDateString(
        "es-ES",
        { day: "2-digit", month: "short", year: "numeric" },
      )
    : v === null ? "No consta" : "\u2014";
export const localDate = (d = new Date()) =>
  [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
export const localDateTime = (d = new Date()) =>
  localDate(d) +
  "T" +
  String(d.getHours()).padStart(2, "0") +
  ":" +
  String(d.getMinutes()).padStart(2, "0");
export const normalize = (v: string) =>
  v
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
export const native = () => Boolean(window.__TAURI__);
type RpcReply<T> =
  | { ok: true; result: T }
  | {
      ok: false;
      error?: { message?: string; code?: string; details?: unknown };
    };
export class RpcError extends Error {
  constructor(
    message: string,
    public code = "transport",
    public details?: unknown,
  ) {
    super(message);
    this.name = "RpcError";
  }
}
export async function api<T = any>(
  action: string,
  params: Row = {},
): Promise<T> {
  try {
    let answer: RpcReply<T>;
    if (window.__TAURI__) {
      answer = await window.__TAURI__.core.invoke<RpcReply<T>>("rpc", {
        action,
        params,
      });
    } else {
      const response = await fetch("/api", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Canamo-Token": window.__CANAMO_DEV_TOKEN__ || "",
        },
        body: JSON.stringify({ action, params }),
      });
      if (!response.ok)
        throw new RpcError(
          "No se ha podido conectar con el servicio local. Reabre la aplicación y revisa el historial antes de repetir la operación.",
        );
      answer = await response.json();
    }
    if (!answer || typeof answer.ok !== "boolean")
      throw new RpcError(
        "Respuesta del servicio local no válida. Revisa el historial antes de repetir la operación.",
      );
    if (!answer.ok)
      throw new RpcError(
        answer.error?.message || "No se ha podido completar la operación.",
        answer.error?.code,
        answer.error?.details,
      );
    return answer.result;
  } catch (error: unknown) {
    if (error instanceof RpcError) throw error;
    throw new RpcError(
      typeof error === "string"
        ? error
        : "Se ha interrumpido la comunicación con el servicio local. Revisa el historial antes de repetir la operación.",
    );
  }
}
export function useLoad<T>(
  action: string,
  params: Row,
  initial: T,
  refresh = 0,
): [T, boolean, string] {
  const [data, setData] = useState<T>(initial),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const key = JSON.stringify(params);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    api<T>(action, params)
      .then((v) => {
        if (live) setData(v);
      })
      .catch((e) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [action, key, refresh]);
  return [data, loading, error];
}
export function Icon({
  name = "home",
  size = 20,
  ...rest
}: React.SVGProps<SVGSVGElement> & { name?: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    home: (
      <>
        <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" />
        <path d="M9 21v-8h6v8" />
      </>
    ),
    users: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 21v-2a6 6 0 0 1 12 0v2m1-16a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v2" />
      </>
    ),
    car: (
      <>
        <path d="m5 6-2 7v6h3v-3h12v3h3v-6l-2-7ZM3 12h18" />
        <path d="M6 14h2m8 0h2" />
      </>
    ),
    invoice: (
      <>
        <path d="M6 3h9l4 4v14H6ZM14 3v5h5M9 12h7m-7 4h5" />
      </>
    ),
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    x: <path d="m6 6 12 12M6 18 18 6" />,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    back: <path d="M19 12H5m6-6-6 6 6 6" />,
    down: <path d="m6 9 6 6 6-6" />,
    left: <path d="m15 5-7 7 7 7" />,
    right: <path d="m9 5 7 7-7 7" />,
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M7 3v4m10-4v4M3 10h18m-14 4h2m4 0h2m-8 3h2" />
      </>
    ),
    box: (
      <>
        <path d="m12 3 9 5v9l-9 5-9-5V8Zm-9 5 9 5 9-5m-9 5v9M7 5l10 6" />
      </>
    ),
    tool: (
      <>
        <path d="m15 6 3 3 3-3a6 6 0 0 1-8 8l-6 7-4-4 7-6a6 6 0 0 1 8-8Z" />
      </>
    ),
    settings: (
      <>
        <path d="m9 3-1 3-3 1v3l-2 2 2 2v3l3 1 1 3h6l1-3 3-1v-3l2-2-2-2V7l-3-1-1-3Z" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
    bell: (
      <>
        <path d="M18 8a6 6 0 0 0-12 0c0 7-2 7-2 9h16c0-2-2-2-2-9M10 21h4" />
      </>
    ),
    sun: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 1v2m0 18v2M1 12h2m18 0h2M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2" />
      </>
    ),
    moon: <path d="M20 14A8 8 0 0 1 10 4a9 9 0 1 0 10 10Z" />,
    shield: (
      <>
        <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    print: (
      <>
        <path d="M7 8V3h10v5M7 17H3V9h18v8h-4M7 14h10v7H7Zm10-3h1" />
      </>
    ),
    download: (
      <>
        <path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V4m-4 4 4-4 4 4M4 16v5h16v-5" />
      </>
    ),
    edit: (
      <>
        <path d="m15 4 5 5-11 11-6 1 1-6ZM13 6l5 5" />
      </>
    ),
    trash: (
      <>
        <path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7" />
      </>
    ),
    phone: <path d="m7 3 3 5-2 3 5 5 3-2 5 3-2 4C9 22 2 15 3 5Z" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    chart: (
      <>
        <path d="M4 3v18h17M8 17v-4m5 4V8m5 9V5" />
      </>
    ),
    dots: (
      <>
        <circle cx="5" cy="12" r="1" />
        <circle cx="12" cy="12" r="1" />
        <circle cx="19" cy="12" r="1" />
      </>
    ),
    mail: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m3 6 9 7 9-7" />
      </>
    ),
    sparkles: (
      <>
        <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4" />
      </>
    ),
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    lock: (
      <>
        <rect x="5" y="10" width="14" height="11" rx="2" />
        <path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v2" />
      </>
    ),
    euro: (
      <>
        <path d="M19 5a7 7 0 1 0 0 14M3 10h12M3 14h10" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {paths[name] || paths.invoice}
    </svg>
  );
}
export function Button({
  children,
  icon,
  tone = "",
  className = "",
  busy = false,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || busy}
      className={"button " + tone + " " + className}
    >
      {busy ? <span className="spinner" /> : icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
}
export function Badge({ value, children }: Row) {
  const labels: Row = {
    draft: "Borrador",
    issued: "Emitida",
    historical: "Hist\u00f3rica",
    void: "Anulada",
    sent: "Enviado",
    accepted: "Aceptado",
    rejected: "Rechazado",
    expired: "Caducado",
    received: "Recibido",
    repairing: "En reparaci\u00f3n",
    waiting_parts: "Esperando piezas",
    ready: "Terminado",
    delivered: "Entregado",
    local_only: "Prueba local",
    pending: "Pendiente",
    retry: "Reintento pendiente",
    sending: "Enviando",
    accepted_with_errors: "Aceptado con errores",
    duplicate_review: "Revisar duplicado",
    uncertain: "Resultado por confirmar",
    reconciliation_conflict: "Diferencia en la consulta",
    invalid_local: "Error de validación local",
    superseded: "Sustituido por subsanación",
  };
  return (
    <span className={"badge status-" + value}>
      {children || labels[value] || value}
    </span>
  );
}
export function Field({
  label,
  children,
  hint,
  required,
  ...rest
}: FieldProps) {
  const fieldId = React.useId();
  const controls = React.Children.map(children, (child) => {
    if (
      !React.isValidElement<Row>(child) ||
      ![
        "input",
        "select",
        "textarea",
        TextInput,
        Textarea,
        Select,
        Autocomplete,
      ].includes(child.type as any)
    )
      return child;
    return React.cloneElement(child, {
      id: child.props.id || fieldId,
      ...(!child.props["aria-label"] && !child.props["aria-labelledby"]
        ? { "aria-labelledby": fieldId + "-label" }
        : {}),
      ...(hint
        ? {
            "aria-describedby": [
              child.props["aria-describedby"],
              fieldId + "-hint",
            ]
              .filter(Boolean)
              .join(" "),
          }
        : {}),
    });
  });
  return (
    <div className={"field " + (rest.className || "")}>
      <label id={fieldId + "-label"} htmlFor={fieldId}>
        {label}
        {required && (
          <span className="required" aria-hidden="true">
            {" "}
            *
          </span>
        )}
      </label>
      {controls}
      {hint && <small id={fieldId + "-hint"}>{hint}</small>}
    </div>
  );
}
export function Input({ label, hint, ...props }: InputProps) {
  return (
    <Field label={label} hint={hint} required={props.required}>
      <TextInput {...props} />
    </Field>
  );
}
export function Toggle({
  checked,
  onChange,
  children,
  hint,
  disabled,
}: WithChildren & {
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className="toggle-row">
      <span>
        <strong>{children}</strong>
        {hint && <small>{hint}</small>}
      </span>
      <input
        type="checkbox"
        checked={!!checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <i aria-hidden="true" />
    </label>
  );
}
export function Notice({ children, tone = "info" }: Row) {
  return (
    <div
      className={"notice " + tone}
      role={tone === "error" ? "alert" : "note"}
    >
      <Icon name={tone === "error" ? "shield" : "info"} />
      <div>{children}</div>
    </div>
  );
}
export function Empty({
  title = "Todav\u00eda no hay nada aqu\u00ed",
  text,
  children,
  icon = "invoice",
}: Row) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={30} />
      </span>
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {children}
    </div>
  );
}
export function PageHead({ title, subtitle, children, eyebrow }: Row) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="actions">{children}</div>
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <span className="spinner" /> Cargando tus datos...
    </div>
  );
}
export function Confirm({
  title,
  text,
  confirm = "Confirmar",
  danger = false,
  onClose,
  onConfirm,
}: ModalProps & {
  text: React.ReactNode;
  confirm?: string;
  danger?: boolean;
  onConfirm: () => unknown | Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <Modal title={title} onClose={() => !busy && onClose()}>
      <p className="dialog-copy">{text}</p>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="form-actions">
        <Button onClick={onClose} disabled={busy}>
          Volver
        </Button>
        <Button
          busy={busy}
          tone={danger ? "danger" : "primary"}
          onClick={async () => {
            setBusy(true);
            try {
              await onConfirm();
              onClose();
            } catch (e: any) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {confirm}
        </Button>
      </div>
    </Modal>
  );
}
export async function fileBase64(file: File): Promise<string> {
  if (file.size > 200 * 1024 * 1024)
    throw new Error("El archivo supera 200 MB.");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("No se puede leer el archivo."));
    reader.readAsDataURL(file);
  });
}
export async function saveExport(
  data: Row,
): Promise<{ saved?: boolean; downloadStarted?: boolean }> {
  try {
    if (window.__TAURI__)
      return await window.__TAURI__.core.invoke<{ saved: boolean }>(
        "save_export",
        {
          name: data.name,
          content: data.content,
          capability: data.capability,
          bytes: data.bytes,
          sha256: data.sha256,
        },
      );
    // The browser is a development preview. The Windows application writes
    // chunks directly to the selected file, with a bounded memory footprint.
    if (data.capability && !data.content && data.bytes > 256 * 1024 ** 2)
      throw new Error(
        "Para guardar esta copia grande, abre la aplicación de escritorio.",
      );
    const parts: Uint8Array<ArrayBuffer>[] = [];
    if (typeof data.content === "string") {
      parts.push(Uint8Array.from(atob(data.content), (c) => c.charCodeAt(0)));
    } else if (data.capability) {
      let offset = 0;
      while (offset < data.bytes) {
        const chunk = await api("backup.download_chunk", {
          capability: data.capability,
          offset,
          length: Math.min(data.chunk_bytes || 1048576, data.bytes - offset),
        });
        const bytes = Uint8Array.from(atob(chunk.content), (c) =>
          c.charCodeAt(0),
        );
        const hash = Array.from(
          new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
          (v) => v.toString(16).padStart(2, "0"),
        ).join("");
        if (
          chunk.offset !== offset ||
          chunk.total_bytes !== data.bytes ||
          chunk.bytes !== bytes.length ||
          !bytes.length ||
          hash !== chunk.sha256
        )
          throw new Error(
            "La descarga no coincide con el archivo preparado. Vuelve a guardarlo.",
          );
        parts.push(bytes);
        offset += bytes.length;
        if (offset > data.bytes || chunk.eof !== (offset === data.bytes))
          throw new Error("La descarga está incompleta. Vuelve a guardarla.");
      }
    } else throw new Error("No se ha recibido un archivo para guardar.");
    const blob = new Blob(parts, {
      type: data.mime || "application/octet-stream",
    });
    if (data.sha256) {
      const hash = Array.from(
        new Uint8Array(
          await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()),
        ),
        (v) => v.toString(16).padStart(2, "0"),
      ).join("");
      if (
        hash !== data.sha256 ||
        (data.bytes !== undefined && blob.size !== data.bytes)
      )
        throw new Error(
          "La huella de la descarga no coincide. Vuelve a guardarla.",
        );
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = data.name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return { downloadStarted: true };
  } finally {
    if (data.capability)
      await api("backup.release_download", {
        capability: data.capability,
      }).catch(() => {});
  }
}
export function PdfPreview({ data, onClose }: Row) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<"" | "save" | "open" | "print">("");
  useEffect(() => {
    let u = "";
    setError("");
    setMessage("");
    try {
      const raw = atob(data.content);
      u = URL.createObjectURL(
        new Blob([Uint8Array.from(raw, (c) => c.charCodeAt(0))], {
          type: "application/pdf",
        }),
      );
      setUrl(u);
    } catch {
      setUrl("");
      setError("No se puede cargar el PDF recibido.");
    }
    return () => {
      if (u) URL.revokeObjectURL(u);
    };
  }, [data.content]);
  async function handlePdf(action: "open" | "print") {
    if (!window.__TAURI__ || busy) return;
    setBusy(action);
    setError("");
    setMessage("");
    try {
      await window.__TAURI__.core.invoke("handle_pdf", {
        name: data.name,
        content: data.content,
        action,
      });
      setMessage(
        action === "print"
          ? "Solicitud de impresión aceptada por el sistema. Comprueba la cola o el lector para confirmar el resultado."
          : "Se ha solicitado abrir el PDF en tu lector predeterminado.",
      );
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy("");
    }
  }
  return (
    <Modal
      title={data.name}
      subtitle="Revisa el documento antes de guardarlo o imprimirlo."
      onClose={onClose}
      wide
    >
      <div className="pdf-toolbar">
        <Button
          icon="download"
          busy={busy === "save"}
          disabled={Boolean(busy) || !url}
          onClick={async () => {
            setBusy("save");
            setError("");
            setMessage("");
            try {
              const result = await saveExport(data);
              if (result.saved) setMessage("PDF guardado.");
              else if (result.downloadStarted)
                setMessage("Se ha iniciado la descarga del PDF.");
            } catch (error: unknown) {
              setError(error instanceof Error ? error.message : String(error));
            } finally {
              setBusy("");
            }
          }}
        >
          Guardar PDF
        </Button>
        {native() ? (
          <>
            <Button
              busy={busy === "open"}
              disabled={Boolean(busy) || !url}
              onClick={() => handlePdf("open")}
            >
              Abrir en lector
            </Button>
            <Button
              icon="print"
              busy={busy === "print"}
              disabled={Boolean(busy) || !url}
              onClick={() => handlePdf("print")}
            >
              Imprimir
            </Button>
            <span>
              Se usa la impresora predeterminada del sistema. Abre el lector si
              necesitas elegir otra.
            </span>
          </>
        ) : (
          <span>
            Para imprimir, utiliza el botón de la vista previa o abre el PDF
            guardado.
          </span>
        )}
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      {message && <Notice>{message}</Notice>}
      <iframe
        title="Vista previa de la factura"
        className="pdf-frame"
        src={url}
      />
    </Modal>
  );
}
export function CustomerSearch({
  onSelect,
  placeholder = "Nombre, matrícula, teléfono o NIF",
  initial = "",
  global = false,
}: {
  onSelect: (customer: CustomerMatch) => void;
  placeholder?: string;
  initial?: string;
  global?: boolean;
}) {
  const [query, setQuery] = useState(initial);
  const [results, setResults] = useState<CustomerMatch[]>([]);
  const [resolvedQuery, setResolvedQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement | null>(null);
  const box = useRef<HTMLDivElement | null>(null);
  const serial = useRef(0);
  const suppressFocus = useRef(false);
  const id = React.useId();
  const compact = useCompact();
  const stale = query !== resolvedQuery || loading || !!error;
  const visible = open && !!query.trim();
  const first = stale ? undefined : results[active];
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (
        global &&
        (event.ctrlKey || event.metaKey) &&
        event.key.toLowerCase() === "k"
      ) {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
        setOpen(true);
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [global]);
  useEffect(() => {
    const request = ++serial.current;
    if (!query.trim()) {
      setResults([]);
      setResolvedQuery(query);
      setLoading(false);
      setSlow(false);
      setError("");
      return;
    }
    setLoading(true);
    setSlow(false);
    setError("");
    const timer = window.setTimeout(() => setSlow(true), 250);
    api<CustomerMatch[]>("customers.search", { query })
      .then((rows) => {
        if (request === serial.current) {
          setResults(rows);
          setResolvedQuery(query);
          setActive(0);
        }
      })
      .catch((reason: Error) => {
        if (request === serial.current) {
          setError(reason.message);
          setResults([]);
        }
      })
      .finally(() => {
        if (request === serial.current) {
          clearTimeout(timer);
          setLoading(false);
          setSlow(false);
        }
      });
    return () => {
      clearTimeout(timer);
      serial.current++;
    };
  }, [query]);
  useEffect(() => {
    if (visible)
      document
        .getElementById(id + "-" + active)
        ?.scrollIntoView({ block: "nearest" });
  }, [active, visible, id]);
  function close() {
    suppressFocus.current = compact;
    setOpen(false);
  }
  function updateQuery(value: string) {
    serial.current++;
    setActive(0);
    setQuery(value);
  }
  function choose(row: CustomerMatch) {
    if (stale) return;
    close();
    updateQuery(global ? "" : row.name);
    onSelect(row);
  }
  const suggestion = first
    ? normalize(first.plate || "")
        .replace(/[^a-z0-9]/g, "")
        .startsWith(normalize(query).replace(/[^a-z0-9]/g, ""))
      ? first.plate
      : first.name
    : "";
  const inline =
    suggestion && normalize(suggestion).startsWith(normalize(query))
      ? suggestion.slice(query.length)
      : "";
  const label = global ? "Buscar cliente o matrícula" : placeholder;
  function keys(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      if (!stale)
        setActive((index) =>
          Math.max(
            0,
            Math.min(
              index + (event.key === "ArrowDown" ? (open ? 1 : 0) : -1),
              results.length - 1,
            ),
          ),
        );
    }
    if (event.key === "Enter" && visible) {
      event.preventDefault();
      if (first) choose(first);
    }
    if (
      event.key === "ArrowRight" &&
      visible &&
      inline &&
      event.currentTarget.selectionStart === query.length
    ) {
      event.preventDefault();
      updateQuery(query + inline);
    }
    if (event.key === "Tab" && !compact) close();
    if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  }
  const combobox = {
    value: query,
    role: "combobox",
    "aria-label": label,
    "aria-autocomplete": "both" as const,
    "aria-expanded": visible,
    "aria-controls": visible ? id : undefined,
    "aria-activedescendant": visible && first ? id + "-" + active : undefined,
    placeholder,
    autoComplete: "off",
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => {
      updateQuery(event.target.value);
      setOpen(true);
    },
    onKeyDown: keys,
  };
  return (
    <div
      className={"customer-search " + (global ? "global-search" : "")}
      ref={box}
    >
      <div className="search-input-wrap">
        <Icon name="search" />
        {inline && open && (
          <div className="search-completion" aria-hidden="true">
            <span>{query}</span>
            {inline}
          </div>
        )}
        <TextInput
          {...combobox}
          ref={input}
          onFocus={() => {
            if (!suppressFocus.current) setOpen(true);
            suppressFocus.current = false;
          }}
        />
        {global && <kbd>Ctrl K</kbd>}
      </div>
      <Presence>
        {visible && (
          <Popup
            anchor={box}
            title={label}
            onClose={close}
            focusOnOpen={false}
            className="search-sheet"
          >
            {compact && (
              <div className="search-mobile-input">
                <TextInput {...combobox} data-autofocus />
              </div>
            )}
            <div className="search-popover" aria-busy={loading}>
              <div className="search-label">
                Clientes y vehículos
                <span className="search-status" role="status">
                  {slow ? "Actualizando…" : "Intro para abrir"}
                </span>
              </div>
              <div id={id} role="listbox" aria-label="Coincidencias">
                {results.map((row, index) => (
                  <button
                    type="button"
                    key={row.customer_id + "-" + (row.vehicle_id || "")}
                    id={id + "-" + index}
                    role="option"
                    tabIndex={-1}
                    aria-selected={!stale && active === index}
                    aria-disabled={stale}
                    className={
                      "search-result " +
                      (!stale && active === index ? "active" : "")
                    }
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => choose(row)}
                  >
                    <span className="result-icon">
                      <Icon name={row.plate ? "car" : "users"} />
                    </span>
                    <span className="result-main">
                      <strong>{row.name}</strong>
                      <small>
                        {row.plate ? (
                          <>
                            <b className="plate-text">{row.plate}</b> ·{" "}
                            {row.make} {row.model}
                          </>
                        ) : (
                          row.legacy_code || "Cliente sin vehículo"
                        )}
                      </small>
                    </span>
                    <span className="result-phone">
                      {row.phone || "Sin teléfono"}
                    </span>
                    <Icon name="arrow" size={16} />
                  </button>
                ))}
              </div>
              {!results.length && (
                <p className="search-no-results" role="status">
                  {loading
                    ? slow
                      ? "Buscando coincidencias…"
                      : "Escribe para buscar un cliente o vehículo."
                    : error || "No hay coincidencias. Prueba con otro dato."}
                </p>
              )}
            </div>
          </Popup>
        )}
      </Presence>
    </div>
  );
}
export function Avatar({ name, large = false }: Row) {
  return (
    <span className={"avatar " + (large ? "large" : "")}>
      {String(name || "?")
        .split(" ")
        .slice(0, 2)
        .map((x) => x[0])
        .join("")
        .toUpperCase()}
    </span>
  );
}
export function Pager({ total, page, onChange, size = 50 }: Row) {
  return total > size ? (
    <div className="pager">
      <span>
        {page * size + 1}&ndash;{Math.min((page + 1) * size, total)} de {total}
      </span>
      <Button icon="left" disabled={!page} onClick={() => onChange(page - 1)}>
        Anterior
      </Button>
      <Button
        icon="right"
        disabled={(page + 1) * size >= total}
        onClick={() => onChange(page + 1)}
      >
        Siguiente
      </Button>
    </div>
  ) : null;
}
