import * as React from "react";
import {
  Row,
  api,
  useState,
  useLoad,
  Button,
  Input,
  Notice,
  Empty,
  PageHead,
  Loading,
  money,
  saveExport,
} from "./core.js";

const methods: Record<string, string> = {
  cash: "Efectivo",
  card: "Tarjeta",
  transfer: "Transferencia",
  bizum: "Bizum",
  other: "Otro",
};
const states: Record<string, string> = {
  draft: "Borrador",
  sent: "Enviado",
  accepted: "Aceptado",
  rejected: "Rechazado",
  expired: "Caducado",
  received: "Recibido",
  repairing: "En reparación",
  waiting_parts: "Esperando piezas",
  ready: "Terminado",
  delivered: "Entregado",
};
const monthName = (month: string) =>
  new Date(month + "-01T12:00:00Z").toLocaleDateString("es-ES", {
    month: "long",
    year: "numeric",
    timeZone: "Europe/Madrid",
  });
const todayMadrid = () =>
  new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Madrid" }).format(
    new Date(),
  );

export function ReportsPage() {
  const today = todayMadrid();
  const [start, setStart] = useState(today.slice(0, 4) + "-01-01"),
    [end, setEnd] = useState(today);
  const [period, setPeriod] = useState({ start, end });
  const [exporting, setExporting] = useState(""),
    [exportError, setExportError] = useState(""),
    [message, setMessage] = useState("");
  const [data, loading, error] = useLoad<Row>("reports", period, {
    months: [],
    work: [],
    low_stock: [],
    cash_months: [],
  });
  async function download(kind: string) {
    setExporting(kind);
    setExportError("");
    setMessage("");
    try {
      const result = await api("data.export", { kind, ...period });
      const saved = await saveExport(result);
      setMessage(
        saved.saved === false
          ? "Guardado cancelado."
          : saved.saved
            ? "Archivo guardado."
            : "Descarga iniciada. Revisa la carpeta de descargas.",
      );
    } catch (err: any) {
      setExportError(err.message);
    } finally {
      setExporting("");
    }
  }
  const exportButton = (kind: string, label: string) => (
    <Button
      icon="download"
      disabled={!!exporting}
      busy={exporting === kind}
      onClick={() => download(kind)}
    >
      {label}
    </Button>
  );
  return (
    <>
      <PageHead
        title="Resumen del taller"
        subtitle="Facturación, cobros, trabajos y existencias."
        eyebrow="MÁS HERRAMIENTAS"
      />
      <section className="panel padded">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setPeriod({ start, end });
          }}
        >
          <div className="form-grid">
            <Input
              label="Desde"
              type="date"
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
            <Input
              label="Hasta"
              type="date"
              value={end}
              min={start || undefined}
              onChange={(event) => setEnd(event.target.value)}
            />
          </div>
          <div className="actions">
            <Button type="submit" tone="primary">
              Aplicar período
            </Button>
            <Button
              onClick={() => {
                setStart("");
                setEnd("");
                setPeriod({ start: "", end: "" });
              }}
            >
              Todo el historial
            </Button>
          </div>
        </form>
      </section>
      {(error || exportError) && (
        <Notice tone="error">{error || exportError}</Notice>
      )}
      {message && <p role="status">{message}</p>}
      {loading ? (
        <Loading />
      ) : (
        data.billing && (
          <>
            <Notice>{data.notice}</Notice>
            <div className="stat-grid">
              <div className="stat-card">
                <span>Facturación del período</span>
                <strong>{money(data.billing.total_cents)}</strong>
                <small>
                  {data.billing.count} documentos ·{" "}
                  {data.billing.rectifications} rectificativas
                </small>
              </div>
              <div className="stat-card">
                <span>Cobros netos del período</span>
                <strong>{money(data.cash.net_cents)}</strong>
                <small>Entradas menos devoluciones y contrapartidas</small>
              </div>
              <div className="stat-card">
                <span>Pendiente de cobro hoy</span>
                <strong>{money(data.receivables.receivable_cents)}</strong>
                <small>Documentos del período con saldo conocido</small>
              </div>
              <div className="stat-card">
                <span>Pendiente de devolver hoy</span>
                <strong>{money(data.receivables.refund_due_cents)}</strong>
                <small>Se muestra separado de la deuda de clientes</small>
              </div>
            </div>
            {!!data.billing.test_count && (
              <Notice>
                {data.billing.test_count} documentos del período están marcados
                como pruebas.
              </Notice>
            )}
            {!!data.receivables.unknown_documents && (
              <Notice>
                {data.receivables.unknown_documents} facturas históricas tienen
                cobro no documentado y se excluyen de los saldos pendientes.
              </Notice>
            )}
            <section className="panel">
              <div className="section-head">
                <h2>Facturación por mes</h2>
                {exportButton("billing", "Exportar facturación")}
              </div>
              {data.months.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Mes</th>
                        <th>Documentos</th>
                        <th className="right">Base</th>
                        <th className="right">IVA</th>
                        <th className="right">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.months.map((row: Row) => (
                        <tr key={row.month}>
                          <td>{monthName(row.month)}</td>
                          <td>{row.count}</td>
                          <td className="right">{money(row.base_cents)}</td>
                          <td className="right">{money(row.tax_cents)}</td>
                          <td className="right amount">
                            {money(row.total_cents)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  title="Sin facturas en este período"
                  text="Amplía las fechas para consultar el historial."
                />
              )}
            </section>
            <section className="panel">
              <div className="section-head">
                <h2>Cobros por mes y medio</h2>
                {exportButton("cash", "Exportar cobros reales")}
              </div>
              {data.cash_months.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Mes</th>
                        <th>Medio</th>
                        <th className="right">Entradas</th>
                        <th className="right">Devoluciones / contrapartidas</th>
                        <th className="right">Neto</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.cash_months.map((row: Row) => (
                        <tr key={row.month + row.method}>
                          <td>{monthName(row.month)}</td>
                          <td>{methods[row.method] || row.method}</td>
                          <td className="right">{money(row.received_cents)}</td>
                          <td className="right">{money(row.returned_cents)}</td>
                          <td className="right amount">
                            {money(row.net_cents)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  title="Sin movimientos de cobro en este período"
                  text="Los cobros aparecen por su fecha de pago."
                />
              )}
              <div className="padded">
                <p>
                  Saldos iniciales documentados de las facturas del período:{" "}
                  <strong>{money(data.opening_balances.paid_cents)}</strong>.
                  Ajustes documentales registrados en el período:{" "}
                  <strong>
                    {money(data.opening_adjustments.amount_cents)}
                  </strong>
                  . Se conservan con su evidencia y se excluyen de caja.
                </p>
              </div>
            </section>
            <section className="panel">
              <div className="section-head">
                <h2>Presupuestos y trabajos por estado actual</h2>
                {exportButton("work", "Exportar trabajos")}
              </div>
              {data.work.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Documento</th>
                        <th>Estado actual</th>
                        <th className="right">Cantidad</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.work.map((row: Row) => (
                        <tr key={row.kind + row.status}>
                          <td>
                            {row.kind === "quote" ? "Presupuestos" : "Órdenes"}
                          </td>
                          <td>{states[row.status] || row.status}</td>
                          <td className="right">{row.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  title="Sin presupuestos ni órdenes en este período"
                  text="Estas herramientas son opcionales."
                />
              )}
            </section>
            <section className="panel">
              <div className="section-head">
                <h2>Artículos en mínimo o por debajo</h2>
                {exportButton("low_stock", "Exportar mínimos")}
              </div>
              {data.low_stock.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Artículo</th>
                        <th className="right">Existencias</th>
                        <th className="right">Mínimo</th>
                        <th>Proveedor</th>
                        <th>Teléfono</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.low_stock.map((row: Row) => (
                        <tr key={row.id}>
                          <td>
                            <strong>{row.name}</strong>
                            <small className="block subtle">{row.sku}</small>
                          </td>
                          <td className="right">{row.stock}</td>
                          <td className="right">{row.min_stock}</td>
                          <td>{row.supplier_name || "—"}</td>
                          <td>{row.supplier_phone || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty
                  title="Sin artículos por debajo del mínimo"
                  text="El inventario es opcional y refleja las existencias actuales."
                />
              )}
            </section>
          </>
        )
      )}
      <section className="panel padded">
        <h2>Datos para otras herramientas</h2>
        <p>
          La exportación portable incluye originales, snapshots, líneas, cobros,
          ajustes, trazabilidad y recursos en un ZIP con JSON y CSV. Contiene
          datos del taller y se guarda sin cifrar en la ubicación que elijas. La
          recuperación operativa del programa se realiza desde Copias y
          traslado.
        </p>
        <div className="actions">
          {exportButton("portable", "Exportación portable completa")}
          {exportButton("invoices", "Facturas y snapshots CSV")}
          {exportButton("document_lines", "Líneas de documentos CSV")}
        </div>
      </section>
    </>
  );
}
