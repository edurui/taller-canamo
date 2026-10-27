import { EntityRow, RowActions, SortHeader, useListSort } from "./list-controls.js";
import * as React from "react";
import { EntityReference } from "./entity-navigation.js";
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

export function ReportsPage({ navigate }: Row) {
  const today = todayMadrid();
  const [start, setStart] = useState(today.slice(0, 4) + "-01-01"),
    [end, setEnd] = useState(today);
  const [period, setPeriod] = useState({ start, end });
  const [refresh, setRefresh] = useState(0);
  const [exporting, setExporting] = useState(""),
    [exportError, setExportError] = useState(""),
    [message, setMessage] = useState("");
  const [data, loading, error] = useLoad<Row>("reports", period, {
    months: [],
    overview_months: [],
    work: [],
    low_stock: [],
    cash_months: [],
  }, refresh);
  const periodMatches = data.period?.start === period.start && data.period?.end === period.end;
  const overviewOrder = useListSort<Row>(data.overview_months, {
    month: row => row.month, count: row => row.count,
    original_cents: row => row.original_count ? row.original_cents : null,
    verified_cents: row => row.verified_count ? row.verified_cents : null,
    estimated_cents: row => row.estimated_count ? row.estimated_cents : null,
    total_cents: row => row.total_cents, unknown_count: row => row.unknown_count,
  });
  const originalOrder = useListSort<Row>(data.months, {
    month: row => row.month, count: row => row.count, base_cents: row => row.base_cents,
    tax_cents: row => row.tax_cents, total_cents: row => row.total_cents,
  });
  const cashOrder = useListSort<Row>(data.cash_months, {
    month: row => row.month, method: row => methods[row.method] || row.method,
    received_cents: row => row.received_cents, returned_cents: row => row.returned_cents,
    net_cents: row => row.net_cents,
  });
  const workOrder = useListSort<Row>(data.work, {
    kind: row => row.kind === "quote" ? "Presupuestos" : "Órdenes",
    status: row => states[row.status] || row.status, count: row => row.count,
  });
  const stockOrder = useListSort<Row>(data.low_stock, {
    name: row => row.name, sku: row => row.sku, stock: row => Number(row.stock),
    min_stock: row => Number(row.min_stock), supplier_name: row => row.supplier_name,
    supplier_phone: row => row.supplier_phone,
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
            setRefresh(value => value + 1);
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
                setRefresh(value => value + 1);
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
      {error && <Button onClick={() => setRefresh(value => value + 1)}>Reintentar resumen</Button>}
      {message && <p role="status">{message}</p>}
      {loading || (!error && !periodMatches) ? (
        <Loading />
      ) : (
        !error && data.billing && (
          <>
            <Notice>{data.notice}</Notice>
            {!!data.billing_overview.unknown_count && (
              <Notice>
                {data.billing_overview.unknown_count} facturas del período siguen
                sin importe disponible. El total es parcial; esas facturas no se
                cuentan como cero.
              </Notice>
            )}
            {!!data.billing.undated_historical_count && (
              <Notice>
                {data.billing.undated_historical_count} históricos no conservan fecha
                confirmada y no se asignan a ningún período. Puedes consultarlos en el historial.
              </Notice>
            )}
            <div className="stat-grid">
              <div className="stat-card">
                <span>Importe de facturas del período</span>
                <strong>{money(data.billing_overview.total_cents)}</strong>
                <small>
                  {data.billing_overview.amount_count} de{" "}
                  {data.billing_overview.count} facturas con importe
                </small>
                {!!data.billing_overview.estimated_count && (
                  <small>
                    Incluye {money(data.billing_overview.estimated_cents)} estimados
                  </small>
                )}
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
                <h2>Importes de facturas por mes</h2>
                {exportButton("billing_overview", "Exportar importes de facturas")}
              </div>
              <p className="padded muted">
                Cada factura se suma una sola vez: su total original, si consta;
                en su defecto, la revisión contrastada con el original o la estimación.
                Las estimaciones son orientativas y no acreditan cobros ni importes fiscales.
              </p>
              {data.overview_months.length ? (
                <div className="table-scroll" role="region" aria-label="Tabla de importes de facturas" tabIndex={0}>
                  <table aria-label="Importes de facturas por mes">
                    <thead><tr>
                      <SortHeader label="Mes" field="month" sort={overviewOrder.sort} onSort={overviewOrder.toggle} secondary={{ label: "Facturas", field: "count" }} />
                      <SortHeader label="Originales" field="original_cents" sort={overviewOrder.sort} onSort={overviewOrder.toggle} className="right" />
                      <SortHeader label="Contrastados" field="verified_cents" sort={overviewOrder.sort} onSort={overviewOrder.toggle} className="right" />
                      <SortHeader label="Estimados" field="estimated_cents" sort={overviewOrder.sort} onSort={overviewOrder.toggle} className="right" />
                      <SortHeader label="Total disponible" field="total_cents" sort={overviewOrder.sort} onSort={overviewOrder.toggle} className="right" />
                      <SortHeader label="Sin importe" field="unknown_count" sort={overviewOrder.sort} onSort={overviewOrder.toggle} className="right" />
                    </tr></thead>
                    <tbody>
                      {overviewOrder.rows.map((row: Row) => (
                        <tr key={row.month}>
                          <td>
                            {monthName(row.month)}{" "}
                            <small className="block subtle">{row.count} facturas</small>
                          </td>
                          <td className="right">{row.original_count ? money(row.original_cents) : "—"}</td>
                          <td className="right">{row.verified_count ? money(row.verified_cents) : "—"}</td>
                          <td className="right">{row.estimated_count ? money(row.estimated_cents) : "—"}</td>
                          <td className="right amount">
                            {money(row.total_cents)}
                          </td>
                          <td className="right">{row.unknown_count}</td>
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
            <details className="panel padded reports-original">
              <summary>Desglose fiscal original</summary>
              <p className="muted">
                Base, IVA y total conservados en el documento. Las revisiones y
                estimaciones del resumen anterior se mantienen aparte.
              </p>
              {!!data.billing.excluded_incomplete_count && (
                <p>
                  {data.billing.excluded_incomplete_count} facturas del período no
                  conservan el desglose completo y se excluyen de esta tabla fiscal.
                </p>
              )}
              {exportButton("billing", "Exportar desglose fiscal original")}
              {data.months.length ? (
                <div className="table-scroll" role="region" aria-label="Tabla del desglose fiscal original" tabIndex={0}>
                  <table aria-label="Desglose fiscal original por mes">
                    <thead><tr>
                      <SortHeader label="Mes" field="month" sort={originalOrder.sort} onSort={originalOrder.toggle} />
                      <SortHeader label="Documentos" field="count" sort={originalOrder.sort} onSort={originalOrder.toggle} className="right" />
                      <SortHeader label="Base" field="base_cents" sort={originalOrder.sort} onSort={originalOrder.toggle} className="right" />
                      <SortHeader label="IVA" field="tax_cents" sort={originalOrder.sort} onSort={originalOrder.toggle} className="right" />
                      <SortHeader label="Total" field="total_cents" sort={originalOrder.sort} onSort={originalOrder.toggle} className="right" />
                    </tr></thead>
                    <tbody>
                      {originalOrder.rows.map((row: Row) => (
                        <tr key={row.month}>
                          <td>{monthName(row.month)}</td><td>{row.count}</td>
                          <td className="right">{money(row.base_cents)}</td>
                          <td className="right">{money(row.tax_cents)}</td>
                          <td className="right amount">{money(row.total_cents)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p>No hay facturas con desglose fiscal original completo en este período.</p>
              )}
            </details>
            <section className="panel">
              <div className="section-head">
                <h2>Cobros por mes y medio</h2>
                {exportButton("cash", "Exportar cobros reales")}
              </div>
              {data.cash_months.length ? (
                <div className="table-scroll">
                  <table>
                    <thead><tr>
                      <SortHeader label="Mes" field="month" sort={cashOrder.sort} onSort={cashOrder.toggle} />
                      <SortHeader label="Medio" field="method" sort={cashOrder.sort} onSort={cashOrder.toggle} />
                      <SortHeader label="Entradas" field="received_cents" sort={cashOrder.sort} onSort={cashOrder.toggle} className="right" />
                      <SortHeader label="Devoluciones / contrapartidas" field="returned_cents" sort={cashOrder.sort} onSort={cashOrder.toggle} className="right" />
                      <SortHeader label="Neto" field="net_cents" sort={cashOrder.sort} onSort={cashOrder.toggle} className="right" />
                    </tr></thead>
                    <tbody>
                      {cashOrder.rows.map((row: Row) => (
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
                    <thead><tr>
                      <SortHeader label="Documento" field="kind" sort={workOrder.sort} onSort={workOrder.toggle} />
                      <SortHeader label="Estado actual" field="status" sort={workOrder.sort} onSort={workOrder.toggle} />
                      <SortHeader label="Cantidad" field="count" sort={workOrder.sort} onSort={workOrder.toggle} className="right" />
                    </tr></thead>
                    <tbody>
                      {workOrder.rows.map((row: Row) => (
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
                    <thead><tr>
                      <SortHeader label="Artículo" field="name" sort={stockOrder.sort} onSort={stockOrder.toggle} secondary={{ label: "Referencia", field: "sku" }} />
                      <SortHeader label="Existencias" field="stock" sort={stockOrder.sort} onSort={stockOrder.toggle} className="right" />
                      <SortHeader label="Mínimo" field="min_stock" sort={stockOrder.sort} onSort={stockOrder.toggle} className="right" />
                      <SortHeader label="Proveedor" field="supplier_name" sort={stockOrder.sort} onSort={stockOrder.toggle} />
                      <SortHeader label="Teléfono" field="supplier_phone" sort={stockOrder.sort} onSort={stockOrder.toggle} />
                      <th scope="col"><span className="sr-only">Acciones</span></th>
                    </tr></thead>
                    <tbody>
                      {stockOrder.rows.map((row: Row) => (
                        <EntityRow key={row.id} onOpen={() => navigate("catalogue", { id: row.id })}>
                          <td>
                            <strong>
                              <EntityReference entity="product" id={row.id} navigate={navigate}>{row.name}</EntityReference>
                            </strong>
                            <small className="block subtle">{row.sku}</small>
                          </td>
                          <td className="right">{row.stock}</td>
                          <td className="right">{row.min_stock}</td>
                          <td>
                            <EntityReference entity="supplier" id={row.supplier_id} navigate={navigate}>{row.supplier_name || "—"}</EntityReference>
                          </td>
                          <td>{row.supplier_phone || "—"}</td>
                          <td><RowActions label={row.name} items={[
                            { label: "Ver artículo", onSelect: () => navigate("catalogue", { id: row.id }) },
                            ...(row.supplier_id ? [{ label: "Ver proveedor", onSelect: () => navigate("suppliers", { id: row.supplier_id }) }] : []),
                          ]} /></td>
                        </EntityRow>
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
