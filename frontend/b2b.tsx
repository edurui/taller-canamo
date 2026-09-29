import { Presence } from "./overlays.js";
import { Select, Textarea } from "./controls.js";
import * as React from "react";
import { api, useLoad, Button, Field, Input, Notice, Modal, Empty, Badge, money, dateText, localDate, uuid, saveExport, fileBase64 } from "./core.js";

type Direction = "outbound" | "inbound";
type State = "accepted" | "rejected" | "partially_accepted" | "partially_rejected" | "partially_paid" | "paid";
interface Summary {
  id: string; direction: Direction; invoice_number: string; issuer_nif: string;
  recipient_nif: string; issue_date: string; total_cents: number; test_document: boolean;
}
interface Event {
  id: string; state: string; occurred_on: string; evidence: string; paid_cents: number | null;
  corrects_event_id: string | null;
}
interface Details extends Summary {
  events: Event[]; commercial_state: string; payment_state: string; remote_delivered: boolean;
  limit: string; validation: { ok: boolean; semantic: string; warnings: { id: string; message: string }[] };
}
interface Capability { syntax: string; semantic_validator: string; limit: string; reviewed_on: string; scope: string }
interface Issued { id: string; full_number: string; customer_name: string; total_cents: number }
interface ExportFile { name: string; mime: string; content: string; sha256: string; remote_delivered: false }
const stateLabels: Record<string, string> = {
  unrecorded: "Sin estado registrado", prepared: "Preparada localmente", received: "Archivo recibido",
  exported: "Archivo exportado", accepted: "Aceptación comercial", rejected: "Rechazo comercial",
  partially_accepted: "Aceptación parcial", partially_rejected: "Rechazo parcial",
  partially_paid: "Pago parcial", paid: "Pago completo",
};
const states: State[] = ["accepted", "rejected", "partially_accepted", "partially_rejected", "partially_paid", "paid"];
function errorText(error: unknown) { return error instanceof Error ? error.message : String(error); }

function StateForm({ record, onSaved, onCancel, onBusy }: {
  record: Details; onSaved: (value: Details) => void; onCancel: () => void; onBusy: (busy: boolean) => void;
}) {
  const [state, setState] = React.useState<State>("accepted");
  const [occurred, setOccurred] = React.useState(localDate());
  const [evidence, setEvidence] = React.useState("");
  const [paid, setPaid] = React.useState("");
  const [correct, setCorrect] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const key = React.useRef(uuid());
  const payment = state === "paid" || state === "partially_paid";
  const previous = [...record.events].reverse().find(item => payment
    ? ["paid", "partially_paid"].includes(item.state)
    : ["accepted", "rejected", "partially_accepted", "partially_rejected"].includes(item.state));
  return <form onSubmit={async event => {
    event.preventDefault(); setBusy(true); onBusy(true); setError("");
    try {
      const normalized = paid.trim().replace(",", ".");
      if (payment && !/^\d+(\.\d{1,2})?$/.test(normalized)) throw new Error("Introduce el importe pagado con dos decimales como máximo.");
      const [whole, fraction = ""] = normalized.split(".");
      const paidCents = payment ? Number(whole) * 100 + Number(fraction.padEnd(2, "0")) : null;
      onSaved(await api<Details>("b2b.state", { identifier: record.id, state, occurred_on: occurred,
        evidence, idempotency_key: key.current, paid_cents: paidCents,
        corrects_event_id: correct ? previous?.id ?? null : null }));
    } catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); onBusy(false); }
  }}>
    <Notice>Registra lo ocurrido y su justificante. Este registro conserva la obligación de comunicación y no envía mensajes al destinatario ni a la AEAT. Los cobros contables se anotan en la factura.</Notice>
    <Field label="Estado observado"><Select value={state} onChange={event => { setState(event.target.value as State); setCorrect(false); }} disabled={busy}>
      {states.map(value => <option key={value} value={value}>{stateLabels[value]}</option>)}
    </Select></Field>
    <Input label="Fecha efectiva" type="date" value={occurred} min={record.issue_date} max={localDate()} onChange={event => setOccurred(event.target.value)} required disabled={busy} />
    {payment ? <Input label="Importe pagado acumulado (€)" inputMode="decimal" value={paid} onChange={event => setPaid(event.target.value)} required disabled={busy} /> : null}
    <Field label="Justificante o evidencia"><Textarea value={evidence} onChange={event => setEvidence(event.target.value)} required minLength={3} maxLength={1500} disabled={busy} /></Field>
    {previous ? <label className="check"><input type="checkbox" checked={correct} onChange={event => setCorrect(event.target.checked)} disabled={busy} /> Corregir expresamente el último estado de esta categoría, conservando el anterior</label> : null}
    {error ? <Notice tone="error">{error}</Notice> : null}
    <div className="form-actions"><Button onClick={onCancel} disabled={busy}>Cancelar</Button><Button type="submit" tone="primary" busy={busy}>Conservar estado</Button></div>
  </form>;
}

function B2BDetail({ record, onClose, onChanged }: { record: Details; onClose: () => void; onChanged: (value: Details) => void }) {
  const [editing, setEditing] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  return <Modal title={"Factura electrónica " + record.invoice_number} onClose={() => !busy && onClose()} wide>
    {record.test_document ? <Notice>Documento de prueba sin validez fiscal.</Notice> : null}
    <p>{dateText(record.issue_date)} · {money(record.total_cents)} · {record.direction === "outbound" ? "Preparada para entregar" : "Recibida desde un archivo"}</p>
    <p>UBL 2.1 y {record.validation.semantic}: {record.validation.ok ? "validación local superada" : "revisar validación"}. Entrega por servicio público: pendiente.</p>
    {record.direction === "inbound" ? <p>El formato y los importes se han validado. El origen del archivo y su posible firma deben comprobarse por separado.</p> : null}
    <p>{stateLabels[record.commercial_state]} · {stateLabels[record.payment_state]}</p>
    <Notice>{record.limit}</Notice>
    {error ? <Notice tone="error">{error}</Notice> : null}
    {editing ? <StateForm record={record} onBusy={setBusy} onCancel={() => setEditing(false)} onSaved={value => { setEditing(false); onChanged(value); }} /> : <>
      <div className="form-actions">
        <Button disabled={busy} onClick={() => setEditing(true)}>Registrar estado</Button>
        <Button busy={busy} onClick={async () => {
          setBusy(true); setError("");
          try { await saveExport(await api<ExportFile>("b2b.export", { identifier: record.id })); onChanged(await api<Details>("b2b.get", { identifier: record.id })); }
          catch (failure) { setError(errorText(failure)); } finally { setBusy(false); }
        }}>Guardar XML UBL</Button>
      </div>
      <h3>Historial conservado</h3>
      <ol>{record.events.map(event => <li key={event.id}>
        <strong>{stateLabels[event.state] || event.state}</strong> · {dateText(event.occurred_on)}
        {event.paid_cents !== null ? " · " + money(event.paid_cents) : ""}
        <p>{event.evidence}{event.corrects_event_id ? " · Corrige un estado anterior." : ""}</p>
      </li>)}</ol>
    </>}
  </Modal>;
}

export function B2BPanel() {
  const [refresh, setRefresh] = React.useState(0);
  const [direction, setDirection] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [page, setPage] = React.useState(0);
  const [invoiceQuery, setInvoiceQuery] = React.useState("");
  const [invoice, setInvoice] = React.useState("");
  const [business, setBusiness] = React.useState(false);
  const [record, setRecord] = React.useState<Details | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const selection = React.useRef(0);
  const [capabilities, capabilityLoading, capabilityError] = useLoad<Capability | null>("b2b.capabilities", {}, null);
  const [rows, loading, listError] = useLoad<{ items: Summary[]; total: number }>("b2b.list", { direction, query, page }, { items: [], total: 0 }, refresh);
  const [invoices, invoiceLoading, invoiceError] = useLoad<{ items: Issued[] }>("documents.list", { kind: "invoice", status: "issued", query: invoiceQuery }, { items: [] }, refresh);
  const changed = (value: Details) => { setRecord(value); setRefresh(value => value + 1); };
  return <section>
    <h2>Factura electrónica entre empresas</h2>
    <p>Prepara archivos estructurados, recibe facturas y conserva su aceptación, rechazo y pago.</p>
    {capabilityError || listError || invoiceError || error ? <Notice tone="error">{error || capabilityError || listError || invoiceError}</Notice> : null}
    {capabilities ? <><Notice>{capabilities.limit}</Notice><p>{capabilities.syntax} · {capabilities.semantic_validator}. {capabilities.scope}</p></> : capabilityLoading ? <p role="status">Comprobando validadores locales…</p> : null}
    <h3>Preparar una factura emitida</h3>
    <Input label="Buscar factura por número o cliente" value={invoiceQuery} onChange={event => { setInvoiceQuery(event.target.value); setInvoice(""); }} disabled={busy} />
    <Field label="Factura emitida"><Select value={invoice} onChange={event => setInvoice(event.target.value)} disabled={busy || invoiceLoading}>
      <option value="">Selecciona una factura</option>
      {invoices.items.map(item => <option key={item.id} value={item.id}>{item.full_number} · {item.customer_name} · {money(item.total_cents)}</option>)}
    </Select></Field>
    <label className="check"><input type="checkbox" checked={business} onChange={event => setBusiness(event.target.checked)} disabled={busy} /> El destinatario actúa como empresa o profesional en esta operación</label>
    <div className="form-actions"><Button tone="primary" busy={busy} disabled={!invoice || !business || invoiceLoading} onClick={async () => {
      setBusy(true); setError("");
      try { changed(await api<Details>("b2b.prepare", { document_id: invoice, recipient_business: business })); }
      catch (failure) { setError(errorText(failure)); } finally { setBusy(false); }
    }}>Preparar y validar UBL</Button></div>
    <h3>Recibir un archivo UBL</h3>
    <Input label="Factura recibida (.xml)" type="file" accept=".xml,application/xml,text/xml" disabled={busy} onChange={async event => {
      const file = event.target.files?.[0]; event.target.value = "";
      if (!file) return;
      setBusy(true); setError("");
      try {
        if (file.size > 5_000_000) throw new Error("El archivo supera 5 MB.");
        changed(await api<Details>("b2b.receive", { content: await fileBase64(file) }));
      } catch (failure) { setError(errorText(failure)); } finally { setBusy(false); }
    }} />
    <h3>Facturas electrónicas conservadas</h3>
    <Input label="Buscar por número o NIF" value={query} onChange={event => { setQuery(event.target.value); setPage(0); }} />
    <Field label="Origen"><Select value={direction} onChange={event => { setDirection(event.target.value); setPage(0); }}>
      <option value="">Todas</option><option value="outbound">Preparadas</option><option value="inbound">Recibidas</option>
    </Select></Field>
    {loading ? <p role="status">Cargando facturas…</p> : rows.items.length ? <div className="table-wrap"><table>
      <thead><tr><th>Factura</th><th>Fecha</th><th>Origen</th><th>Total</th><th>Acción</th></tr></thead>
      <tbody>{rows.items.map(item => <tr key={item.id}>
        <td>{item.invoice_number} {item.test_document ? <Badge value="local_only" /> : null}</td>
        <td>{dateText(item.issue_date)}</td><td>{item.direction === "inbound" ? "Recibida" : "Preparada"}</td><td>{money(item.total_cents)}</td>
        <td><Button disabled={busy} aria-label={"Abrir factura electrónica " + item.invoice_number} onClick={async () => {
          const request = ++selection.current; setBusy(true); setError("");
          try { const detail = await api<Details>("b2b.get", { identifier: item.id }); if (request === selection.current) setRecord(detail); }
          catch (failure) { if (request === selection.current) setError(errorText(failure)); }
          finally { if (request === selection.current) setBusy(false); }
        }}>Abrir</Button></td>
      </tr>)}</tbody>
    </table></div> : <Empty icon="invoice" title="Sin facturas electrónicas" text="Prepara una factura emitida o recibe un archivo UBL." />}
    {rows.total > 50 ? <div className="form-actions"><Button disabled={page === 0 || loading} onClick={() => setPage(value => value - 1)}>Anterior</Button><span>Página {page + 1}</span><Button disabled={(page + 1) * 50 >= rows.total || loading} onClick={() => setPage(value => value + 1)}>Siguiente</Button></div> : null}
    <Presence>{record ? <B2BDetail key={record.id} record={record} onChanged={changed} onClose={() => { selection.current++; setRecord(null); }} /> : null}</Presence>
  </section>;
}
