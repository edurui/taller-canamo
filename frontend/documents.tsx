import { Presence } from "./overlays.js";
import { Select, Textarea, TextInput, Autocomplete } from "./controls.js";
import * as React from "react";
import {
  Row,
  api,
  useState,
  useEffect,
  useRef,
  useLoad,
  uuid,
  localDate,
  money,
  dateText,
  Button,
  Icon,
  Field,
  Input,
  Notice,
  Modal,
  Confirm,
  Empty,
  PageHead,
  Loading,
  Pager,
  Badge,
  CustomerSearch,
  PdfPreview,
} from "./core.js";
import { TextAssistance, MessageButton } from "./assistant.js";
import { CustomerForm, VehicleForm } from "./people.js";
const nouns: Row = {
  invoice: ["Factura", "Facturas", "Nueva factura"],
  quote: ["Presupuesto", "Presupuestos", "Nuevo presupuesto"],
  order: [
    "Orden de reparaci\u00f3n",
    "\u00d3rdenes de reparaci\u00f3n",
    "Nueva orden",
  ],
};
export const methods: Row = {
  cash: "Efectivo",
  card: "Tarjeta",
  transfer: "Transferencia",
  bizum: "Bizum",
  other: "Otro",
};
const decimalCents = (value: number) => {
  const v = BigInt(value);
  return (
    (v < 0n ? "-" : "") +
    String((v < 0n ? -v : v) / 100n) +
    "." +
    String((v < 0n ? -v : v) % 100n).padStart(2, "0")
  );
};
function parsedCents(value: string): number {
  const text = value.trim().replace(",", ".");
  if (!/^-?\d{1,8}(\.\d{1,2})?$/.test(text))
    throw new Error(
      "Introduce una cuota en euros, con signo y un máximo de dos decimales.",
    );
  const [whole, fraction = ""] = text.replace("-", "").split(".");
  return (
    Number(BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"))) *
    (text.startsWith("-") ? -1 : 1)
  );
}
function addDateDays(date: string, days: number): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return "";
  const value = new Date(date + "T12:00:00Z");
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}
export function DocumentsPage({ kind = "invoice", navigate }: Row) {
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [page, setPage] = useState(0);
  const [data, loading, error] = useLoad<Row>(
    "documents.list",
    { kind, query, status, page },
    { items: [], total: 0 },
  );
  const filters =
    kind === "invoice"
      ? [
          ["", "Todas"],
          ["draft", "Borradores"],
          ["issued", "Emitidas"],
          ["historical", "Hist\u00f3ricas"],
          ["void", "Anuladas"],
        ]
      : kind === "quote"
        ? [
            ["", "Todos"],
            ["draft", "Borradores"],
            ["sent", "Enviados"],
            ["accepted", "Aceptados"],
            ["rejected", "Rechazados"],
          ]
        : [
            ["", "Todas"],
            ["received", "Recibidas"],
            ["repairing", "En reparaci\u00f3n"],
            ["waiting_parts", "Esperando piezas"],
            ["ready", "Terminadas"],
            ["delivered", "Entregadas"],
          ];
  return (
    <>
      <PageHead
        title={nouns[kind][1]}
        subtitle={
          kind === "invoice"
            ? "Crea, encuentra e imprime. Sin pasos de m\u00e1s."
            : kind === "quote"
              ? "Prepara una propuesta y convi\u00e9rtela en factura cuando toque."
              : "Del primer ruido a la entrega. A tu ritmo."
        }
        eyebrow={kind !== "invoice" ? "M\u00c1S HERRAMIENTAS" : undefined}
      >
        <Button
          tone="primary"
          icon="plus"
          onClick={() => navigate("editor", { kind })}
        >
          {nouns[kind][2]}
        </Button>
      </PageHead>
      <section className="panel">
        <div className="list-toolbar">
          <div className="filter-input">
            <Icon name="search" />
            <TextInput
              aria-label="Buscar documentos"
              placeholder="N&uacute;mero, cliente o matr&iacute;cula"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </div>
          <Select
            aria-label="Estado de los documentos"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(0);
            }}
          >
            {filters.map(([v, l]) => (
              <option value={v} key={v}>
                {l}
              </option>
            ))}
          </Select>
          <span className="subtle">{data.total} documentos</span>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        {loading ? (
          <Loading />
        ) : data.items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>N&uacute;mero / fecha</th>
                  <th>Cliente</th>
                  <th>Matr&iacute;cula</th>
                  <th>Estado</th>
                  <th className="right">Total</th>
                  {kind === "invoice" && <th className="right">Pendiente</th>}
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((d: Row) => (
                  <tr
                    key={d.id}
                    className="clickable"
                    onClick={() => navigate("editor", { id: d.id, kind })}
                  >
                    <td>
                      <button
                        className="text-button"
                        onClick={() => navigate("editor", { id: d.id, kind })}
                      >
                        <strong>
                          {d.full_number || "Borrador sin n\u00famero"}
                        </strong>
                      </button>
                      <small className="block subtle">
                        {dateText(d.issue_date)}
                      </small>
                    </td>
                    <td>
                      {d.customer_name ||
                        "Cliente no conservado en el original"}
                    </td>
                    <td>
                      <span className="plate-text">{d.plate || "\u2014"}</span>
                    </td>
                    <td>
                      <Badge value={d.status} />
                    </td>
                    <td className="right amount">{money(d.total_cents)}</td>
                    {kind === "invoice" && (
                      <td className="right subtle">
                        {d.status === "issued" || d.status === "historical"
                          ? d.payment_known
                            ? money(d.total_cents - d.paid_cents)
                            : "Cobro no documentado"
                          : "\u2014"}
                      </td>
                    )}
                    <td>
                      <Icon name="right" size={16} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={
              query
                ? "No encontramos ese documento"
                : "Todo preparado para empezar"
            }
            text={
              query
                ? "Prueba con otra fecha, n\u00famero o cliente."
                : "Los documentos se guardan aqu\u00ed y en el historial del cliente."
            }
          >
            <Button
              icon="plus"
              tone="primary"
              onClick={() => navigate("editor", { kind })}
            >
              {nouns[kind][2]}
            </Button>
          </Empty>
        )}
        <Pager total={data.total} page={page} onChange={setPage} />
      </section>
    </>
  );
}
function PaymentForm({
  doc,
  onClose,
  onSaved,
}: {
  doc: Row;
  onClose: () => void;
  onSaved: (document: Row) => void;
}) {
  const [value, setValue] = useState(decimalCents(doc.pending_cents)),
    [method, setMethod] = useState(doc.payload.payment_method || "cash"),
    [date, setDate] = useState(localDate()),
    [notes, setNotes] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const key = useRef(uuid());
  return (
    <Modal
      title={
        doc.pending_cents < 0 ? "Registrar devoluci\u00f3n" : "Registrar cobro"
      }
      onClose={() => !busy && onClose()}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            onSaved(
              await api("payments.add", {
                identifier: doc.id,
                value: value.replace(",", "."),
                method,
                paid_on: date,
                notes,
                idempotency_key: key.current,
              }),
            );
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="payment-balance">
          <span>Pendiente</span>
          <strong>{money(doc.pending_cents)}</strong>
        </div>
        <div className="form-grid">
          <Input
            label="Importe"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            inputMode="decimal"
            required
            autoFocus
          />
          <Field label="Forma de pago">
            <Select value={method} onChange={(e) => setMethod(e.target.value)}>
              {Object.entries(methods).map(([k, v]) => (
                <option key={k} value={k}>
                  {String(v)}
                </option>
              ))}
            </Select>
          </Field>
          <Input
            label="Fecha del cobro"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
          />
          <Input
            label="Nota / referencia (opcional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" tone="primary" busy={busy}>
            Guardar cobro
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function CorrectionForm({
  doc,
  mode,
  onClose,
  onSaved,
}: {
  doc: Row;
  mode: string;
  onClose: () => void;
  onSaved: (document: Row) => void;
}) {
  const [reason, setReason] = useState(""),
    [confirmation, setConfirmation] = useState(""),
    [invoiceType, setInvoiceType] = useState("R4"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const taxOnly = invoiceType === "R2" || invoiceType === "R3";
  const [operationDate, setOperationDate] = useState(
    doc.payload.operation_date ||
      (doc.status === "historical" ? "" : doc.issue_date),
  );
  const [quotas, setQuotas] = useState<Row[]>(() => {
    const taxes = doc.payload.taxes.filter(
      (tax: Row) => tax.kind === "S1" && tax.rate && tax.tax_cents > 0,
    );
    return (taxes.length ? taxes : [{ rate: "" }]).map((tax: Row) => ({
      tax_rate: tax.rate,
      amount: "",
    }));
  });
  const incomplete = doc.payload.lines.some(
    (line: Row) =>
      line.quantity == null ||
      line.unit_price == null ||
      !line.tax_rate ||
      line.tax_kind === "historical",
  );
  const [manualLines, setManualLines] = useState<Row[]>(
    doc.payload.lines.map((line: Row) => ({
      description: line.description,
      quantity: "",
      unit_price: "",
      tax_rate: "",
      tax_kind: "",
      tax_reason: "",
      discount: "0",
    })),
  );
  const editLine = (index: number, field: string, next: string) =>
    setManualLines((old) =>
      old.map((line, i) => (i === index ? { ...line, [field]: next } : line)),
    );
  return (
    <Modal
      title={
        mode === "void"
          ? "Anular por error material"
          : "Crear factura rectificativa"
      }
      onClose={() => !busy && onClose()}
      wide={(incomplete || taxOnly) && mode !== "void"}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            onSaved(
              await api(
                mode === "void" ? "documents.void" : "documents.rectify",
                mode === "void"
                  ? { identifier: doc.id, reason, confirmation }
                  : {
                      identifier: doc.id,
                      reason,
                      invoice_type: invoiceType,
                      operation_date: operationDate,
                      ...(taxOnly
                        ? {
                            tax_adjustments: quotas.map((item) => ({
                              tax_rate: item.tax_rate,
                              tax_cents: parsedCents(item.amount),
                            })),
                          }
                        : incomplete
                          ? { lines: manualLines }
                          : {}),
                    },
              ),
            );
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Notice tone="warning">
          {mode === "void"
            ? "No borra el documento ni permite reutilizar su n\u00famero. Para devoluciones, descuentos o correcciones comerciales, crea una rectificativa."
            : taxOnly
              ? "R2/R3 rectifica exclusivamente la cuota de IVA por diferencias; la base permanece en cero. Documenta el motivo legal y revisa las cuotas disponibles del original antes de emitir."
              : incomplete
                ? "El histórico no conserva datos suficientes para invertir sus líneas. Introduce los importes y el tratamiento fiscal de esta corrección según los documentos originales. No se completarán automáticamente."
                : "Se crea un borrador con las cantidades invertidas y referencia a la factura original. Revísalo y confirma el motivo fiscal con tu asesor."}
        </Notice>
        <Field label="Motivo" required>
          <Textarea
            required
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
        {mode === "void" ? (
          <Input
            label="Escribe ANULAR para confirmar"
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            required
          />
        ) : (
          <Field label="Tipo de rectificaci&oacute;n">
            <Select
              value={invoiceType}
              onChange={(e) => setInvoiceType(e.target.value)}
            >
              <option value="R4">R4 &middot; Resto de rectificaciones</option>
              <option value="R1">
                R1 &middot; Error fundado en derecho / art. 80.1, 80.2, 80.6
              </option>
              <option value="R2">R2 &middot; Art. 80.3</option>
              <option value="R3">R3 &middot; Art. 80.4</option>
            </Select>
          </Field>
        )}
        {mode !== "void" && (
          <Input
            label="Fecha de operación original"
            type="date"
            value={operationDate}
            required
            max={localDate()}
            onChange={(event) => setOperationDate(event.target.value)}
            hint="Fecha del trabajo facturado originalmente. Si no consta en el histórico, compruébala en el original; no se deduce de la fecha de emisión."
          />
        )}
        {taxOnly && mode !== "void" && (
          <section>
            <h3>Cuotas de IVA a rectificar</h3>
            <p>
              Introduce la cuota con signo negativo para reducirla. No se
              modifica la base ni se vuelven a descontar existencias.
            </p>
            {quotas.map((item, index) => (
              <div className="form-grid" key={index}>
                <Input
                  label={"Tipo de IVA de cuota " + (index + 1)}
                  value={item.tax_rate}
                  inputMode="decimal"
                  required
                  onChange={(event) =>
                    setQuotas((old) =>
                      old.map((row, i) =>
                        i === index
                          ? {
                              ...row,
                              tax_rate: event.target.value.replace(",", "."),
                            }
                          : row,
                      ),
                    )
                  }
                />
                <Input
                  label={"Cuota rectificativa en EUR " + (index + 1)}
                  value={item.amount}
                  inputMode="decimal"
                  required
                  placeholder="Por ejemplo, -21,00"
                  onChange={(event) =>
                    setQuotas((old) =>
                      old.map((row, i) =>
                        i === index
                          ? { ...row, amount: event.target.value }
                          : row,
                      ),
                    )
                  }
                />
              </div>
            ))}
          </section>
        )}
        {incomplete && mode !== "void" && !taxOnly && (
          <section>
            <h3>Conceptos e impuestos de la rectificación</h3>
            <p>
              Usa cantidades negativas para abonos. Los campos vacíos requieren
              revisión del original; el nuevo borrador conserva su referencia.
            </p>
            {manualLines.map((line, index) => (
              <div className="panel padded" key={index}>
                <Input
                  label={"Concepto rectificativo " + (index + 1)}
                  value={line.description}
                  required
                  maxLength={1500}
                  onChange={(event) =>
                    editLine(index, "description", event.target.value)
                  }
                />
                <div className="form-grid">
                  <Input
                    label={"Cantidad rectificativa " + (index + 1)}
                    inputMode="decimal"
                    value={line.quantity}
                    required
                    onChange={(event) =>
                      editLine(
                        index,
                        "quantity",
                        event.target.value.replace(",", "."),
                      )
                    }
                  />
                  <Input
                    label={"Precio rectificativo " + (index + 1)}
                    inputMode="decimal"
                    value={line.unit_price}
                    required
                    onChange={(event) =>
                      editLine(
                        index,
                        "unit_price",
                        event.target.value.replace(",", "."),
                      )
                    }
                  />
                  <Field label={"Tratamiento fiscal " + (index + 1)} required>
                    <Select
                      required
                      value={line.tax_kind}
                      onChange={(event) => {
                        const value = event.target.value;
                        editLine(index, "tax_kind", value);
                        if (value && value !== "S1")
                          editLine(index, "tax_rate", "0");
                      }}
                    >
                      <option value="">Seleccionar según original</option>
                      <option value="S1">Sujeta a IVA</option>
                      {["E1", "E2", "E3", "E4", "E5", "E6"].map((kind) => (
                        <option key={kind} value={kind}>
                          Exención {kind}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Input
                    label={"IVA rectificativo " + (index + 1)}
                    inputMode="decimal"
                    value={line.tax_rate}
                    required
                    onChange={(event) =>
                      editLine(
                        index,
                        "tax_rate",
                        event.target.value.replace(",", "."),
                      )
                    }
                  />
                </div>
                {line.tax_kind && line.tax_kind !== "S1" && (
                  <Input
                    label={"Causa legal " + (index + 1)}
                    value={line.tax_reason}
                    required
                    onChange={(event) =>
                      editLine(index, "tax_reason", event.target.value)
                    }
                  />
                )}
                <Button
                  disabled={manualLines.length === 1}
                  onClick={() =>
                    setManualLines((old) => old.filter((_, i) => i !== index))
                  }
                >
                  Quitar concepto {index + 1}
                </Button>
              </div>
            ))}
            <Button
              onClick={() =>
                setManualLines((old) => [
                  ...old,
                  {
                    description: "",
                    quantity: "",
                    unit_price: "",
                    tax_rate: "",
                    tax_kind: "",
                    tax_reason: "",
                    discount: "0",
                  },
                ])
              }
            >
              Añadir concepto rectificativo
            </Button>
          </section>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose}>Volver</Button>
          <Button
            type="submit"
            tone={mode === "void" ? "danger" : "primary"}
            busy={busy}
          >
            {mode === "void"
              ? "Anular documento"
              : "Crear borrador rectificativo"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function PaymentStateForm({
  doc,
  onClose,
  onSaved,
}: {
  doc: Row;
  onClose: () => void;
  onSaved: (doc: Row) => void;
}) {
  const [amount, setAmount] = useState(
    doc.payment_known ? decimalCents(doc.paid_cents) : "",
  );
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef(uuid());
  return (
    <Modal
      title={
        doc.payment_known
          ? "Corregir saldo documentado"
          : "Documentar cobro histórico"
      }
      onClose={() => !busy && onClose()}
    >
      <p>
        Indica cuánto consta cobrado de esta factura según una fuente
        comprobable. Se conserva la factura original y se registra esta
        conciliación por separado.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          const normalized = amount.trim().replace(",", ".");
          if (!/^-?\d{1,8}(\.\d{1,2})?$/.test(normalized)) {
            setError("Introduce un importe con un máximo de dos decimales.");
            return;
          }
          const [whole, fraction = ""] = normalized.replace("-", "").split(".");
          const cents =
            Number(BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"))) *
            (normalized.startsWith("-") ? -1 : 1);
          setBusy(true);
          try {
            onSaved(
              await api(
                doc.payment_known
                  ? "documents.adjust_payment_state"
                  : "documents.record_payment_state",
                {
                  identifier: doc.id,
                  paid_cents: cents,
                  evidence,
                  idempotency_key: key.current,
                },
              ),
            );
          } catch (e: unknown) {
            setError(e instanceof Error ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Input
          label="Importe cobrado documentado (EUR)"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          inputMode="decimal"
          required
          autoFocus
        />
        <Input
          label="Fuente y motivo de la conciliación"
          value={evidence}
          onChange={(e) => setEvidence(e.target.value)}
          minLength={5}
          maxLength={2000}
          required
          hint="Por ejemplo, número de recibo o extracto revisado y su fecha. No introduzcas contraseñas ni datos bancarios innecesarios."
        />
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button type="submit" tone="primary" busy={busy}>
            Guardar saldo documentado
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function DocumentEditor({
  id,
  kind = "invoice",
  customerId = "",
  vehicleId = "",
  vehicleKilometres = 0,
  config,
  productionReleased = false,
  series,
  navigate,
  notify,
  onDirty,
}: Row) {
  const newId = useRef(uuid());
  // Editor-only identities keep focus attached to the same line when it moves.
  const withLineKeys = (lines: Row[]) =>
    lines.map((line) => ({ ...line, _uiKey: line._uiKey || uuid() }));
  const persistedLines = (lines: Row[]) =>
    lines.map(({ _uiKey, ...line }) => line);
  const defaults = () => ({
    id: id || newId.current,
    kind,
    status: "draft",
    customer_id: customerId,
    vehicle_id: vehicleId,
    issue_date: localDate(),
    operation_date: localDate(),
    due_date:
      kind === "order"
        ? ""
        : addDateDays(
            localDate(),
            kind === "quote"
              ? config.billing.quote_days
              : config.billing.due_days,
          ),
    series_id: "",
    version: undefined,
    invoice_type: "F1",
    reference_id: null,
    origin_id: null,
    kilometres: vehicleId ? vehicleKilometres : 0,
    payment_method: config.billing.payment_method,
    notes: "",
    footer: config.billing.footer,
    stock_affect: false,
    lines: [
      {
        _uiKey: uuid(),
        description: "",
        quantity: "1",
        unit_price: "0",
        discount: "0",
        tax_rate: config.billing.vat,
        tax_kind: "S1",
        tax_reason: "",
      },
    ],
  });
  const [value, setValue] = useState<Row>(defaults),
    [doc, setDoc] = useState<Row | null>(null),
    [loading, setLoading] = useState(!!id),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false),
    [customer, setCustomer] = useState<Row | null>(null),
    [newCustomer, setNewCustomer] = useState(false),
    [newVehicle, setNewVehicle] = useState(false),
    [confirm, setConfirm] = useState(""),
    [correction, setCorrection] = useState(""),
    [pdf, setPdf] = useState<Row | null>(null),
    [payment, setPayment] = useState(false),
    [paymentState, setPaymentState] = useState(false),
    [showProducts, setShowProducts] = useState(false),
    [totals, setTotals] = useState<Row>({
      base_cents: 0,
      tax_cents: 0,
      total_cents: 0,
      lines: [],
      taxes: [],
    }),
    [calcError, setCalcError] = useState(""),
    [advanced, setAdvanced] = useState(false);
  const [draggedLine, setDraggedLine] = useState<string | null>(null);
  const [dragTarget, setDragTarget] = useState<string | null>(null);
  const [orderMessage, setOrderMessage] = useState("");
  const [products] = useLoad<Row[]>("products.list", {}, []);
  const [concepts] = useLoad<Row[]>("documents.concepts", {}, []);
  const serial = useRef(0),
    saving = useRef(false),
    current = useRef(value);
  current.current = value;
  function hydrate(d: Row) {
    setDoc(d);
    setValue({ ...d, ...d.payload, lines: withLineKeys(d.payload.lines) });
    setTotals(d.payload);
    setDirty(false);
    setError("");
  }
  useEffect(() => {
    let active = true;
    if (id)
      api("documents.get", { identifier: id })
        .then((d) => {
          if (active) hydrate(d);
        })
        .catch((e) => {
          if (active) setError(e.message);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    return () => {
      active = false;
    };
  }, [id]);
  useEffect(() => {
    let active = true;
    if (value.customer_id)
      api("customers.get", { identifier: value.customer_id })
        .then((c) => {
          if (active) setCustomer(c);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    else setCustomer(null);
    return () => {
      active = false;
    };
  }, [value.customer_id, newVehicle]);
  useEffect(() => {
    onDirty?.(dirty);
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => {
      onDirty?.(false);
      window.removeEventListener("beforeunload", handler);
    };
  }, [dirty]);
  const editable =
    !doc ||
    doc.status === "draft" ||
    (kind === "order" && doc.status !== "delivered");
  const isDraft = !doc || doc.status === "draft";
  const historical =
    doc?.status === "historical" || doc?.status === "import_reverted";
  const identityEditable =
    editable && !doc?.conversion_identity_locked && !doc?.reference_id;
  const editVersion = useRef(0);
  const kilometresRevision = useRef(0);
  const displayedCustomer = editable ? customer : doc?.payload.customer;
  const displayedVehicles = editable
    ? [
        ...(customer?.vehicles ?? []),
        ...((doc?.reference_id || doc?.conversion_identity_locked) &&
        doc.payload.vehicle &&
        !(customer?.vehicles ?? []).some((v: Row) => v.id === doc.vehicle_id)
          ? [{ ...doc.payload.vehicle, id: doc.vehicle_id }]
          : []),
      ]
    : doc?.payload.vehicle
      ? [{ ...doc.payload.vehicle, id: doc.vehicle_id }]
      : [];
  const change = (key: string, next: any) => {
    editVersion.current++;
    if (key === "kilometres") kilometresRevision.current++;
    setValue((v) => ({
      ...v,
      [key]: key === "lines" ? withLineKeys(next) : next,
    }));
    setDirty(true);
  };
  const lineChange = (index: number, key: string, next: any) => {
    editVersion.current++;
    setValue((v) => ({
      ...v,
      lines: v.lines.map((l: Row, i: number) =>
        i === index ? { ...l, [key]: next } : l,
      ),
    }));
    setDirty(true);
  };
  function moveLine(from: number, to: number) {
    if (
      !editable ||
      value.correction_mode === "tax_only" ||
      from < 0 ||
      to < 0 ||
      to >= value.lines.length ||
      from === to
    )
      return;
    const lines = [...value.lines];
    const [moved] = lines.splice(from, 1);
    lines.splice(to, 0, moved);
    serial.current++;
    change("lines", lines);
    setTotals((previous) => {
      const calculated = [...(previous.lines || [])];
      if (calculated.length !== lines.length) return previous;
      const [total] = calculated.splice(from, 1);
      calculated.splice(to, 0, total);
      return { ...previous, lines: calculated };
    });
    setOrderMessage(`Línea ${from + 1} movida a la posición ${to + 1}.`);
  }
  useEffect(() => {
    const n = ++serial.current;
    if (!editable) return;
    const t = setTimeout(() => {
      api("documents.calculate", {
        lines: persistedLines(value.lines),
        corrective: value.invoice_type.startsWith("R"),
        invoice_type: value.invoice_type,
        tax_adjustments: value.tax_adjustments || null,
      })
        .then((tot) => {
          if (n === serial.current) {
            setTotals(tot);
            setCalcError("");
          }
        })
        .catch((e) => {
          if (n === serial.current) setCalcError(e.message);
        });
    }, 120);
    return () => {
      clearTimeout(t);
      serial.current++;
    };
  }, [
    JSON.stringify(value.lines),
    JSON.stringify(value.tax_adjustments),
    value.invoice_type,
    editable,
  ]);
  async function save(quiet = false) {
    if (saving.current) return null;
    saving.current = true;
    setBusy(true);
    setError("");
    const submittedVersion = editVersion.current;
    try {
      const d = await api("documents.save", {
        data: {
          ...current.current,
          lines: persistedLines(current.current.lines),
        },
      });
      if (submittedVersion !== editVersion.current) {
        setDoc(d);
        setValue((latest) => ({ ...latest, version: d.version }));
        setError(
          "Has seguido editando durante el guardado. Guarda los cambios nuevos antes de revisar o imprimir.",
        );
        return null;
      }
      hydrate(d);
      if (!quiet) notify("Borrador guardado");
      return d;
    } catch (e: any) {
      setError(e.message);
      return null;
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (editable) void save();
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p") {
        e.preventDefault();
        void preview();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [editable, doc, dirty]);
  async function preview() {
    let d = doc;
    if (!d || dirty) {
      d = await save(true);
      if (!d) return;
    }
    setBusy(true);
    try {
      setPdf(await api("documents.pdf", { identifier: d.id }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function convert(target: string) {
    setBusy(true);
    try {
      const d = await api("documents.convert", { identifier: doc!.id, target });
      navigate("editor", { kind: target, id: d.id });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  function selectCustomer(c: Row) {
    const selectedCustomer = c.customer_id || c.id;
    const selectedVehicle = c.vehicle_id || "";
    change("customer_id", selectedCustomer);
    change("vehicle_id", selectedVehicle);
    change("kilometres", 0);
    if (selectedVehicle) {
      const revision = kilometresRevision.current;
      const stillSelected = () =>
        revision === kilometresRevision.current &&
        current.current.customer_id === selectedCustomer &&
        current.current.vehicle_id === selectedVehicle;
      api<Row>("vehicles.get", { identifier: selectedVehicle })
        .then((vehicle) => {
          if (stillSelected()) change("kilometres", vehicle.km);
        })
        .catch((error) => {
          if (stillSelected()) setError(error.message);
        });
    }
  }
  if (loading) return <Loading />;
  const docTitle = doc?.full_number || nouns[kind][2];
  const options = series.filter(
    (s: Row) =>
      !s.archived &&
      s.kind ===
        (value.invoice_type.startsWith("R") ? "rectification" : kind) &&
      (s.year === 0 || s.year === Number(value.issue_date.slice(0, 4))),
  );
  return (
    <>
      <button
        className="back-link"
        onClick={() => navigate("documents", { kind })}
      >
        <Icon name="back" size={17} />
        {nouns[kind][1]}
      </button>
      <PageHead
        title={docTitle}
        subtitle={
          isDraft
            ? "El n\u00famero se asigna al confirmar, nunca al guardar el borrador."
            : nouns[kind][0] + " guardado en el historial."
        }
      >
        <Badge value={doc?.status || "draft"} />
        <Button icon="print" onClick={preview} busy={busy}>
          Vista previa / PDF
        </Button>
        {editable && (
          <Button icon="check" onClick={() => save()} busy={busy}>
            {dirty ? "Guardar cambios" : "Guardar borrador"}
          </Button>
        )}
        {isDraft && (
          <Button
            icon="arrow"
            tone="primary"
            busy={busy}
            onClick={async () => {
              const d = await save(true);
              if (d) setConfirm("publish");
            }}
          >
            {kind === "invoice"
              ? "Revisar y emitir"
              : kind === "quote"
                ? "Confirmar presupuesto"
                : "Abrir orden"}
          </Button>
        )}
      </PageHead>
      {error && <Notice tone="error">{error}</Notice>}
      {doc &&
        !isDraft &&
        !["void", "import_reverted"].includes(doc.status) &&
        (kind === "invoice" ||
          kind === "quote" ||
          ["ready", "delivered"].includes(doc.status)) && (
          <div className="row-actions">
            <MessageButton
              identifier={doc.id}
              purpose={
                kind === "order"
                  ? "vehicle_ready"
                  : kind === "quote"
                    ? "quote"
                    : "invoice"
              }
            />
          </div>
        )}
      {!isDraft && kind === "invoice" && (
        <div className="document-statusbar">
          <span>
            <Icon name="lock" size={17} /> Datos de emisi&oacute;n protegidos
          </span>
          <span>
            {historical ? (
              "No remitido como nuevo"
            ) : (
              <Badge value={doc?.fiscal_status?.status || "local_only"} />
            )}
          </span>
          <span>
            {historical
              ? "Histórico importado · conserve el original"
              : doc?.payload.test_document !== false
                ? "Entorno de pruebas · Sin validez fiscal"
                : "Documento emitido"}
          </span>
        </div>
      )}
      <div className="editor-layout">
        <div className="editor-main">
          <section className="panel padded">
            <div className="section-head flush">
              <h2>1. Cliente y veh&iacute;culo</h2>
              {identityEditable && (
                <Button
                  icon="plus"
                  tone="ghost"
                  onClick={() => setNewCustomer(true)}
                >
                  Nuevo cliente
                </Button>
              )}
            </div>
            {identityEditable && (
              <CustomerSearch
                onSelect={selectCustomer}
                placeholder="Busca por nombre o matr&iacute;cula"
              />
            )}
            {editable && !identityEditable && (
              <p className="small subtle">
                Cliente y vehículo conservados del documento de origen. Puedes
                editar los trabajos y las notas.
              </p>
            )}
            {displayedCustomer?.name ? (
              <div className="selected-customer">
                <div>
                  <strong>{displayedCustomer.name}</strong>
                  <span>
                    {displayedCustomer.tax_id} &middot;{" "}
                    {displayedCustomer.phone || "Sin tel\u00e9fono"}
                  </span>
                  <small>{displayedCustomer.address}</small>
                </div>
                <Button
                  tone="ghost"
                  icon="users"
                  onClick={() =>
                    navigate("customer", { id: value.customer_id })
                  }
                >
                  Ver ficha
                </Button>
              </div>
            ) : (
              <p className="subtle">
                {editable
                  ? "Selecciona un cliente para empezar. No es necesario crear una orden."
                  : "Los datos del cliente no se conservan en el documento original. La ficha actual se consulta por separado."}
              </p>
            )}
            <div className="vehicle-fields">
              <Field label="Veh&iacute;culo (opcional)">
                <Select
                  value={value.vehicle_id || ""}
                  disabled={!identityEditable || !customer}
                  onChange={(e) => {
                    change("vehicle_id", e.target.value);
                    const v = customer?.vehicles.find(
                      (x: Row) => x.id === e.target.value,
                    );
                    change("kilometres", v?.km || 0);
                  }}
                >
                  {!editable &&
                    value.vehicle_id &&
                    !displayedVehicles.length && (
                      <option value={value.vehicle_id}>
                        Vehículo original no documentado
                      </option>
                    )}
                  <option value="">Sin veh&iacute;culo</option>
                  {displayedVehicles.map((v: Row) => (
                    <option value={v.id} key={v.id}>
                      {v.plate} &middot; {v.make} {v.model}
                    </option>
                  ))}
                </Select>
              </Field>
              <Input
                label="Kil&oacute;metros"
                value={value.kilometres}
                type="number"
                min={0}
                max={10000000}
                disabled={!editable}
                onChange={(e) => change("kilometres", Number(e.target.value))}
              />
              {identityEditable && customer ? (
                <div className="align-end">
                  <Button icon="plus" onClick={() => setNewVehicle(true)}>
                    A&ntilde;adir veh&iacute;culo
                  </Button>
                </div>
              ) : null}
            </div>
          </section>
          <section className="panel">
            <div className="section-head">
              <h2>2. Trabajos y materiales</h2>
              {editable && (
                <Button
                  icon="box"
                  tone="ghost"
                  onClick={() => setShowProducts(true)}
                >
                  Del cat&aacute;logo
                </Button>
              )}
            </div>
            <div className="line-items">
              <span className="sr-only" role="status">
                {orderMessage}
              </span>
              {value.lines.map((line: Row, i: number) => (
                <div
                  className={
                    "invoice-line" +
                    (draggedLine === line._uiKey ? " dragging" : "") +
                    (dragTarget === line._uiKey ? " drag-target" : "")
                  }
                  key={line._uiKey}
                  onDragOver={(event) => {
                    if (draggedLine && editable) {
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                      setDragTarget(line._uiKey);
                    }
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    if (draggedLine)
                      moveLine(
                        value.lines.findIndex(
                          (item: Row) => item._uiKey === draggedLine,
                        ),
                        i,
                      );
                    setDraggedLine(null);
                    setDragTarget(null);
                  }}
                >
                  {editable &&
                    value.correction_mode !== "tax_only" &&
                    value.lines.length > 1 && (
                      <div className="line-order">
                        <span>Línea {i + 1}</span>
                        <Button
                          tone="ghost icon-only drag-handle"
                          aria-label={"Arrastrar línea " + (i + 1)}
                          title="Arrastra para ordenar; también puedes usar las flechas"
                          draggable
                          onDragStart={(event) => {
                            setDraggedLine(line._uiKey);
                            event.dataTransfer.effectAllowed = "move";
                            event.dataTransfer.setData(
                              "text/plain",
                              line._uiKey,
                            );
                          }}
                          onDragEnd={() => {
                            setDraggedLine(null);
                            setDragTarget(null);
                          }}
                          onKeyDown={(event) => {
                            if (
                              event.key === "ArrowUp" ||
                              event.key === "ArrowDown"
                            ) {
                              event.preventDefault();
                              moveLine(
                                i,
                                i + (event.key === "ArrowUp" ? -1 : 1),
                              );
                            }
                          }}
                        >
                          ⠿
                        </Button>
                        <Button
                          tone="ghost icon-only"
                          aria-label={"Subir línea " + (i + 1)}
                          disabled={i === 0}
                          onClick={() => moveLine(i, i - 1)}
                        >
                          ↑
                        </Button>
                        <Button
                          tone="ghost icon-only"
                          aria-label={"Bajar línea " + (i + 1)}
                          disabled={i === value.lines.length - 1}
                          onClick={() => moveLine(i, i + 1)}
                        >
                          ↓
                        </Button>
                      </div>
                    )}
                  <div className="line-description">
                    <span className="line-number">{i + 1}</span>
                    <Field label="Concepto">
                      <Autocomplete
                        aria-label={"Concepto " + (i + 1)}
                        suggestions={concepts.map((item) => item.description)}
                        onSuggestion={(description) => {
                          const match = concepts.find(
                            (item) => item.description === description,
                          );
                          if (editable && match && line.unit_price === "0") {
                            lineChange(i, "unit_price", match.unit_price);
                            lineChange(i, "tax_rate", match.tax_rate);
                          }
                        }}
                        value={line.description}
                        disabled={!editable}
                        placeholder="Por ejemplo, cambio de aceite y filtro"
                        onChange={(e) =>
                          lineChange(i, "description", e.target.value)
                        }
                        onBlur={(e) => {
                          const match = concepts.find(
                            (c) => c.description === e.target.value,
                          );
                          if (editable && match && line.unit_price === "0") {
                            lineChange(i, "unit_price", match.unit_price);
                            lineChange(i, "tax_rate", match.tax_rate);
                          }
                        }}
                      />
                    </Field>
                  </div>
                  <div className="line-values">
                    <Input
                      label="Cantidad"
                      aria-label={"Cantidad " + (i + 1)}
                      inputMode="decimal"
                      value={line.quantity ?? ""}
                      placeholder={editable ? undefined : "No consta"}
                      disabled={
                        !editable || value.correction_mode === "tax_only"
                      }
                      onChange={(e) =>
                        lineChange(
                          i,
                          "quantity",
                          e.target.value.replace(",", "."),
                        )
                      }
                    />
                    <Input
                      label="Precio sin IVA"
                      aria-label={"Precio " + (i + 1)}
                      inputMode="decimal"
                      value={line.unit_price ?? ""}
                      placeholder={editable ? undefined : "No consta"}
                      disabled={
                        !editable || value.correction_mode === "tax_only"
                      }
                      onChange={(e) =>
                        lineChange(
                          i,
                          "unit_price",
                          e.target.value.replace(",", "."),
                        )
                      }
                    />
                    <Field label="IVA">
                      <Select
                        aria-label={"IVA " + (i + 1)}
                        disabled={
                          !editable || value.correction_mode === "tax_only"
                        }
                        value={line.tax_rate ?? ""}
                        onChange={(e) =>
                          lineChange(i, "tax_rate", e.target.value)
                        }
                      >
                        {!line.tax_rate && <option value="">No consta</option>}
                        {Array.from(
                          new Set([
                            "21",
                            "10",
                            "4",
                            "0",
                            ...(line.tax_rate ? [String(line.tax_rate)] : []),
                          ]),
                        ).map((x) => (
                          <option value={x} key={x}>
                            {x}%
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <div className="line-total">
                      <small>Base</small>
                      <strong>
                        {money(totals.lines?.[i]?.base_cents || 0)}
                      </strong>
                    </div>
                    {editable && value.correction_mode !== "tax_only" && (
                      <Button
                        icon="trash"
                        tone="ghost icon-only"
                        aria-label={"Quitar l\u00ednea " + (i + 1)}
                        disabled={value.lines.length === 1}
                        onClick={() =>
                          change(
                            "lines",
                            value.lines.filter((_: Row, n: number) => n !== i),
                          )
                        }
                      />
                    )}
                  </div>
                  {advanced && (
                    <div className="line-advanced">
                      <Input
                        label="Descuento %"
                        value={line.discount || "0"}
                        disabled={
                          !editable || value.correction_mode === "tax_only"
                        }
                        inputMode="decimal"
                        onChange={(e) =>
                          lineChange(
                            i,
                            "discount",
                            e.target.value.replace(",", "."),
                          )
                        }
                      />
                      <Field label="Tratamiento del IVA">
                        <Select
                          disabled={
                            !editable || value.correction_mode === "tax_only"
                          }
                          value={line.tax_kind || "S1"}
                          onChange={(e) => {
                            lineChange(i, "tax_kind", e.target.value);
                            if (e.target.value !== "S1")
                              lineChange(i, "tax_rate", "0");
                          }}
                        >
                          <option value="S1">Sujeta y no exenta</option>
                          {["E1", "E2", "E3", "E4", "E5", "E6"].map((x) => (
                            <option key={x} value={x}>
                              Exenta {x} (revisar causa)
                            </option>
                          ))}
                        </Select>
                      </Field>
                      {line.tax_kind && line.tax_kind !== "S1" && (
                        <Input
                          label="Motivo legal de exenci&oacute;n"
                          value={line.tax_reason || ""}
                          disabled={
                            !editable || value.correction_mode === "tax_only"
                          }
                          onChange={(e) =>
                            lineChange(i, "tax_reason", e.target.value)
                          }
                        />
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div className="lines-footer">
              {editable && value.correction_mode !== "tax_only" && (
                <Button
                  icon="plus"
                  tone="ghost"
                  onClick={() =>
                    change("lines", [
                      ...value.lines,
                      {
                        description: "",
                        quantity: "1",
                        unit_price: "0",
                        tax_rate: config.billing.vat,
                        discount: "0",
                        tax_kind: "S1",
                      },
                    ])
                  }
                >
                  A&ntilde;adir concepto
                </Button>
              )}
              {editable && value.correction_mode !== "tax_only" && (
                <Button
                  tone="ghost"
                  icon="tool"
                  onClick={() => {
                    const line = {
                      description: "Mano de obra",
                      quantity: "1",
                      unit_price: config.billing.labor_rate || "0",
                      discount: "0",
                      tax_rate: config.billing.vat,
                      tax_kind: "S1",
                      tax_reason: "",
                    };
                    change(
                      "lines",
                      value.lines.length === 1 && !value.lines[0].description
                        ? [line]
                        : [...value.lines, line],
                    );
                  }}
                >
                  Mano de obra
                </Button>
              )}
              <Button
                tone="ghost"
                icon="settings"
                onClick={() => setAdvanced(!advanced)}
              >
                {advanced ? "Ocultar opciones" : "Descuentos y exenciones"}
              </Button>
            </div>
            {value.correction_mode === "tax_only" && (
              <div className="padded">
                <Notice>
                  Rectificación exclusiva de cuota de IVA. Bases, precios y
                  existencias permanecen sin cambio.
                </Notice>
                {value.tax_adjustments.map((item: Row, index: number) => (
                  <Input
                    key={index}
                    label={"Cuota IVA " + item.tax_rate + " % (EUR)"}
                    disabled={!editable}
                    inputMode="decimal"
                    value={
                      value.quota_inputs?.[index] ??
                      decimalCents(item.tax_cents)
                    }
                    onChange={(event) => {
                      const input = event.target.value;
                      change("quota_inputs", {
                        ...(value.quota_inputs || {}),
                        [index]: input,
                      });
                      let cents: number | null = null;
                      try {
                        cents = parsedCents(input);
                      } catch {
                        /* Invalid partial input is also rejected by the backend. */
                      }
                      change(
                        "tax_adjustments",
                        value.tax_adjustments.map((row: Row, i: number) =>
                          i === index ? { ...row, tax_cents: cents } : row,
                        ),
                      );
                    }}
                  />
                ))}
              </div>
            )}
            {calcError && (
              <div className="inline-validation" role="status">
                {calcError}
              </div>
            )}
          </section>
          <section className="panel padded">
            <Field
              label={
                kind === "order"
                  ? "Motivo de entrada / observaciones"
                  : "Observaciones (opcional)"
              }
            >
              <Textarea
                rows={3}
                value={value.notes}
                disabled={!editable}
                placeholder="Solo lo que necesites anotar."
                onChange={(e) => change("notes", e.target.value)}
              />
            </Field>
            {editable && (
              <TextAssistance
                enabled={config.assistant.enabled}
                value={value.notes}
                onApply={(text) => change("notes", text)}
              />
            )}
            {editable && value.correction_mode !== "tax_only" && (
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={value.stock_affect}
                  onChange={(e) => change("stock_affect", e.target.checked)}
                />{" "}
                Descontar del almac&eacute;n los art&iacute;culos del
                cat&aacute;logo al emitir.
                <small>Opcional. No afecta a conceptos escritos a mano.</small>
              </label>
            )}
          </section>
          {!isDraft && kind === "invoice" && (
            <section className="panel">
              <div className="section-head">
                <h2>Cobros y devoluciones</h2>
                {doc!.status !== "void" &&
                  doc!.payment_known &&
                  doc!.pending_cents !== 0 && (
                    <Button
                      icon="plus"
                      tone="primary"
                      onClick={() => setPayment(true)}
                    >
                      Registrar cobro
                    </Button>
                  )}
              </div>
              {!doc!.payment_known && (
                <div className="padded">
                  <Notice>
                    El archivo histórico no acredita el cobro. Esta factura se
                    excluye del pendiente hasta documentar su saldo.
                  </Notice>
                  <Button onClick={() => setPaymentState(true)}>
                    Documentar saldo inicial
                  </Button>
                </div>
              )}
              {doc!.payment_baseline && (
                <div className="padded">
                  <p>
                    Saldo inicial acreditado:{" "}
                    <strong>{money(doc!.payment_baseline.paid_cents)}</strong>.{" "}
                    {doc!.payment_baseline.evidence}
                  </p>
                  <Button tone="ghost" onClick={() => setPaymentState(true)}>
                    Corregir saldo documentado
                  </Button>
                </div>
              )}
              {doc!.payments.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Forma</th>
                        <th>Nota</th>
                        <th className="right">Importe</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {doc!.payments.map((p: Row) => (
                        <tr key={p.id}>
                          <td>{dateText(p.paid_on)}</td>
                          <td>
                            {methods[p.method] ||
                              (p.method === "opening_adjustment"
                                ? "Ajuste documental"
                                : p.method)}
                          </td>
                          <td>
                            {p.method === "opening_adjustment"
                              ? JSON.parse(p.notes).evidence
                              : p.notes || "\u2014"}
                          </td>
                          <td className="right">{money(p.amount_cents)}</td>
                          <td>
                            {p.method !== "opening_adjustment" &&
                              !p.reversal_of &&
                              !doc!.payments.some(
                                (x: Row) => x.reversal_of === p.id,
                              ) && (
                                <Button
                                  tone="ghost"
                                  onClick={() => setConfirm("reverse:" + p.id)}
                                >
                                  Revertir
                                </Button>
                              )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="padded subtle">
                  Todav&iacute;a no se ha registrado ning&uacute;n cobro.
                </p>
              )}
            </section>
          )}
        </div>
        <aside className="editor-side">
          <section className="panel padded">
            <h2>Resumen</h2>
            <div className="summary-line">
              <span>Base imponible</span>
              <span>{money(totals.base_cents)}</span>
            </div>
            {totals.taxes?.map((t: Row, i: number) => (
              <div className="summary-line" key={i}>
                <span>
                  {t.kind === "historical"
                    ? "IVA histórico (tipo no conservado)"
                    : t.kind === "S1"
                      ? "IVA " + t.rate + "%"
                      : "Exento " + t.kind}
                </span>
                <span>{money(t.tax_cents)}</span>
              </div>
            ))}
            <div className="summary-total">
              <span>Total</span>
              <strong>{money(totals.total_cents)}</strong>
            </div>
            {(doc?.status === "issued" || doc?.status === "historical") &&
              doc?.payment_known && (
                <div className="summary-line">
                  <span>Pendiente de cobro</span>
                  <strong>{money(doc.pending_cents)}</strong>
                </div>
              )}
            <div className="divider" />
            <Input
              label="Fecha del documento"
              type="date"
              value={value.issue_date}
              disabled={!editable}
              onChange={(e) => {
                const days =
                  kind === "quote"
                    ? config.billing.quote_days
                    : config.billing.due_days;
                if (
                  value.due_date &&
                  value.due_date === addDateDays(value.issue_date, days) &&
                  e.target.value
                )
                  change("due_date", addDateDays(e.target.value, days));
                if (
                  !value.reference_id &&
                  value.operation_date === value.issue_date
                )
                  change("operation_date", e.target.value);
                change("issue_date", e.target.value);
              }}
            />
            <Input
              label={
                value.reference_id
                  ? "Fecha de operación original"
                  : "Fecha del trabajo / operación"
              }
              type="date"
              value={value.operation_date || ""}
              disabled={!editable}
              required={!historical}
              hint={
                historical && !value.operation_date
                  ? "No conservada en el original"
                  : "Si el trabajo se realizó otro día, indica su fecha real."
              }
              onChange={(event) => change("operation_date", event.target.value)}
            />
            <Input
              label={
                kind === "quote"
                  ? "V&aacute;lido hasta"
                  : "Vencimiento (opcional)"
              }
              type="date"
              value={value.due_date || ""}
              disabled={!editable}
              onChange={(e) => change("due_date", e.target.value)}
            />
            <Field label="Serie">
              <Select
                value={value.series_id || ""}
                disabled={!isDraft}
                onChange={(e) => change("series_id", e.target.value)}
              >
                <option value="">
                  {historical
                    ? "Numeración importada"
                    : "Automática (anual o continua)"}
                </option>
                {options.map((s: Row) => (
                  <option value={s.id} key={s.id}>
                    {s.label} &middot; {s.prefix}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Forma de pago">
              <Select
                value={value.payment_method}
                disabled={!editable}
                onChange={(e) => change("payment_method", e.target.value)}
              >
                {!methods[value.payment_method] && (
                  <option value={value.payment_method || ""}>No consta</option>
                )}
                {Object.entries(methods).map(([k, v]) => (
                  <option key={k} value={k}>
                    {String(v)}
                  </option>
                ))}
              </Select>
            </Field>
            <p className="small subtle">
              <Icon name="shield" size={14} />{" "}
              {dirty
                ? "Hay cambios sin guardar."
                : "Los cambios confirmados est\u00e1n guardados en este equipo."}
            </p>
          </section>
          {!isDraft && kind !== "invoice" && (
            <section className="panel padded">
              <h3>Siguiente paso</h3>
              <Field label="Estado">
                <Select
                  value={doc!.status}
                  onChange={async (e) => {
                    try {
                      hydrate(
                        await api("documents.status", {
                          identifier: doc!.id,
                          status: e.target.value,
                        }),
                      );
                      notify("Estado actualizado");
                    } catch (err: any) {
                      setError(err.message);
                    }
                  }}
                >
                  {(kind === "quote"
                    ? ["sent", "accepted", "rejected", "expired"]
                    : [
                        "received",
                        "repairing",
                        "waiting_parts",
                        "ready",
                        "delivered",
                      ]
                  ).map((x) => (
                    <option value={x} key={x}>
                      {
                        {
                          sent: "Enviado",
                          accepted: "Aceptado",
                          rejected: "Rechazado",
                          expired: "Caducado",
                          received: "Recibido",
                          repairing: "En reparaci\u00f3n",
                          waiting_parts: "Esperando piezas",
                          ready: "Terminado",
                          delivered: "Entregado",
                        }[x]
                      }
                    </option>
                  ))}
                </Select>
              </Field>
              <Button
                tone="primary full"
                icon="invoice"
                busy={busy}
                onClick={() => convert("invoice")}
              >
                Convertir en factura
              </Button>
              {kind === "quote" && (
                <Button
                  tone="full"
                  icon="tool"
                  onClick={() => convert("order")}
                >
                  Crear orden de reparaci&oacute;n
                </Button>
              )}
            </section>
          )}
          {!isDraft && kind === "invoice" && doc!.status !== "void" && (
            <section className="panel padded">
              <h3>Correcciones</h3>
              <p className="small subtle">
                La factura original se conserva siempre.
              </p>
              <Button tone="full" onClick={() => setCorrection("rectify")}>
                Crear rectificativa
              </Button>
              {doc!.status === "issued" && (
                <Button
                  tone="ghost full"
                  disabled={Boolean(doc!.active_rectifications?.length)}
                  onClick={() => setCorrection("void")}
                >
                  Anular por error material
                </Button>
              )}
              {Boolean(doc!.active_rectifications?.length) && (
                <p className="small subtle">
                  Antes de anular, revisa las rectificativas emitidas y elimina
                  los borradores rectificativos vinculados.
                </p>
              )}
            </section>
          )}
          {isDraft && doc && (
            <Button
              tone="ghost full"
              icon="trash"
              onClick={() => setConfirm("delete")}
            >
              Eliminar borrador
            </Button>
          )}
          {!productionReleased && (
            <div className="small side-note">
              <Icon name="shield" /> Edici&oacute;n de validaci&oacute;n. Los
              PDF y registros son de prueba. La emisi&oacute;n fiscal real no
              est&aacute; habilitada.
            </div>
          )}
        </aside>
      </div>
      <Presence>
        {confirm === "publish" && (
          <Confirm
            title={
              kind === "invoice"
                ? productionReleased
                  ? "Confirmar emisión"
                  : "Confirmar emisi\u00f3n de prueba"
                : "Confirmar documento"
            }
            text={
              kind === "invoice"
                ? productionReleased
                  ? "Se asignará un número, los datos quedarán protegidos y se preparará el registro fiscal para envío. Revisa cliente, fecha e importe."
                  : "Se asignar\u00e1 un n\u00famero y los datos quedar\u00e1n protegidos. Esta edici\u00f3n NO emite facturas fiscalmente v\u00e1lidas. Revisa cliente, fecha e importe."
                : "Se asignar\u00e1 un n\u00famero al documento. Los presupuestos y las \u00f3rdenes no son facturas."
            }
            confirm={
              kind === "invoice"
                ? productionReleased
                  ? "Emitir factura"
                  : "Emitir prueba"
                : "Confirmar"
            }
            onClose={() => setConfirm("")}
            onConfirm={async () => {
              const d = await api("documents.publish", {
                identifier: doc!.id,
                expected_version: doc!.version,
              });
              hydrate(d);
              notify("Documento guardado con su n\u00famero");
            }}
          />
        )}
      </Presence>
      <Presence>
        {confirm === "delete" && (
          <Confirm
            title="Eliminar borrador"
            text="Solo se borrar&aacute; este borrador sin n&uacute;mero. Las facturas emitidas no se pueden borrar."
            danger
            confirm="Eliminar borrador"
            onClose={() => setConfirm("")}
            onConfirm={async () => {
              await api("documents.delete", { identifier: doc!.id });
              onDirty?.(false);
              navigate("documents", { kind, force: true });
            }}
          />
        )}
      </Presence>
      <Presence>
        {confirm.startsWith("reverse:") && (
          <Confirm
            title="Revertir cobro"
            text="Se a&ntilde;adir&aacute; un movimiento inverso. El cobro original permanecer&aacute; en el historial."
            confirm="Revertir cobro"
            onClose={() => setConfirm("")}
            onConfirm={async () => {
              hydrate(
                await api("payments.reverse", {
                  payment_id: confirm.split(":")[1],
                  reason: "Reversi\u00f3n confirmada por el usuario",
                }),
              );
              notify("Cobro revertido");
            }}
          />
        )}
      </Presence>
      <Presence>
        {newCustomer && (
          <CustomerForm
            onClose={() => setNewCustomer(false)}
            onSaved={(c) => {
              setNewCustomer(false);
              selectCustomer(c);
              setCustomer(c);
            }}
          />
        )}
      </Presence>
      <Presence>
        {newVehicle && (
          <VehicleForm
            customerId={customer?.id}
            onClose={() => setNewVehicle(false)}
            onSaved={(v) => {
              setNewVehicle(false);
              selectCustomer({ customer_id: customer?.id, vehicle_id: v.id });
            }}
          />
        )}
      </Presence>
      <Presence>
        {pdf && <PdfPreview data={pdf} onClose={() => setPdf(null)} />}
      </Presence>
      <Presence>
        {paymentState && doc && (
          <PaymentStateForm
            doc={doc}
            onClose={() => setPaymentState(false)}
            onSaved={(d) => {
              hydrate(d);
              setPaymentState(false);
              notify("Saldo documentado sin modificar la factura histórica");
            }}
          />
        )}
      </Presence>
      <Presence>
        {payment && doc && (
          <PaymentForm
            doc={doc}
            onClose={() => setPayment(false)}
            onSaved={(d) => {
              hydrate(d);
              setPayment(false);
              notify("Cobro guardado");
            }}
          />
        )}
      </Presence>
      <Presence>
        {correction && doc && (
          <CorrectionForm
            doc={doc}
            mode={correction}
            onClose={() => setCorrection("")}
            onSaved={(d) => {
              setCorrection("");
              if (d.id === doc!.id) hydrate(d);
              else navigate("editor", { id: d.id, kind: "invoice" });
            }}
          />
        )}
      </Presence>
      <Presence>
        {showProducts && (
          <Modal
            title="A&ntilde;adir del cat&aacute;logo"
            onClose={() => setShowProducts(false)}
          >
            {!products.length ? (
              <Empty
                icon="box"
                title="Cat&aacute;logo vac&iacute;o"
                text="Puedes seguir escribiendo conceptos a mano."
              />
            ) : (
              <div className="pick-list">
                {products.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => {
                      const lines = value.lines.filter((l: Row) =>
                        l.description.trim(),
                      );
                      change("lines", [
                        ...lines,
                        {
                          description: p.name,
                          quantity: "1",
                          unit_price: p.unit_price,
                          tax_rate: p.tax_rate,
                          discount: "0",
                          tax_kind: "S1",
                          product_id: p.id,
                        },
                      ]);
                      setShowProducts(false);
                    }}
                  >
                    <span>
                      <strong>{p.name}</strong>
                      <small>
                        {p.sku}{" "}
                        {p.track_stock
                          ? "\u00b7 Stock " + p.stock
                          : "\u00b7 Servicio"}
                      </small>
                    </span>
                    <span>{p.unit_price} &euro;</span>
                    <Icon name="plus" />
                  </button>
                ))}
              </div>
            )}
          </Modal>
        )}
      </Presence>
    </>
  );
}
