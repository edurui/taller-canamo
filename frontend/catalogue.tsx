import { Presence } from "./overlays.js";
import { Select, Textarea, TextInput } from "./controls.js";
import * as React from "react";
import {
  Row,
  api,
  useState,
  useLoad,
  useRef,
  uuid,
  Button,
  Icon,
  Field,
  Input,
  Toggle,
  Notice,
  Modal,
  Empty,
  PageHead,
  Loading,
  dateText,
  normalize,
} from "./core.js";
function ProductForm({ product, suppliers, onClose, onSaved }: Row) {
  const [v, setV] = useState<Row>({
      id: uuid(),
      name: "",
      sku: "",
      unit_price: "0",
      cost_price: "0",
      tax_rate: "21",
      min_stock: "0",
      supplier_id: "",
      track_stock: true,
      notes: "",
      ...product,
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const set = (k: string, x: any) => setV((o) => ({ ...o, [k]: x }));
  return (
    <Modal
      title={
        product ? "Editar art\u00edculo" : "Nuevo art\u00edculo o servicio"
      }
      onClose={() => !busy && onClose()}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("products.save", { data: v });
            onSaved();
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Input
          label="Nombre"
          value={v.name}
          onChange={(e) => set("name", e.target.value)}
          required
          autoFocus
        />
        <div className="form-grid">
          <Input
            label="Referencia (opcional)"
            value={v.sku || ""}
            onChange={(e) => set("sku", e.target.value)}
          />
          <Field label="Proveedor">
            <Select
              value={v.supplier_id || ""}
              onChange={(e) => set("supplier_id", e.target.value)}
            >
              <option value="">Sin proveedor</option>
              {suppliers.map((s: Row) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.archived ? " (archivado)" : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Input
            label="Precio de venta sin IVA"
            inputMode="decimal"
            value={v.unit_price}
            onChange={(e) =>
              set("unit_price", e.target.value.replace(",", "."))
            }
          />
          <Input
            label="Precio de coste sin IVA"
            inputMode="decimal"
            value={v.cost_price}
            onChange={(e) =>
              set("cost_price", e.target.value.replace(",", "."))
            }
          />
          <Field label="IVA">
            <Select
              value={v.tax_rate}
              onChange={(e) => set("tax_rate", e.target.value)}
            >
              {["21", "10", "4", "0"].map((n) => (
                <option key={n} value={n}>
                  {n}%
                </option>
              ))}
            </Select>
          </Field>
          <Input
            label="Avisar por debajo de"
            inputMode="decimal"
            value={v.min_stock}
            onChange={(e) => set("min_stock", e.target.value.replace(",", "."))}
          />
        </div>
        <Toggle
          checked={v.track_stock}
          onChange={(x) => set("track_stock", x)}
          hint="Desact&iacute;valo para mano de obra y otros servicios."
        >
          Controlar existencias
        </Toggle>
        <Field label="Notas">
          <Textarea
            rows={3}
            value={v.notes}
            onChange={(e) => set("notes", e.target.value)}
          />
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button type="submit" tone="primary" busy={busy}>
            Guardar art&iacute;culo
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function StockForm({ product, onClose, onSaved }: Row) {
  const [operation, setOperation] = useState("entry"),
    [page, setPage] = useState(0),
    [quantity, setQuantity] = useState(""),
    [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const key = useRef(uuid());
  const [movements] = useLoad<Row[]>(
    "products.movements",
    { product_id: product.id, page },
    [],
  );
  return (
    <Modal
      title={"Existencias \u00b7 " + product.name}
      onClose={() => !busy && onClose()}
      wide
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const amount = quantity.replace(",", ".");
            if (!/^\d+(?:\.\d{1,3})?$/.test(amount))
              throw new Error(
                "Escribe unidades positivas con hasta tres decimales.",
              );
            if (operation === "adjust")
              await api("products.adjust", {
                product_id: product.id,
                target: amount,
                expected_stock: product.stock,
                reason,
                idempotency_key: key.current,
              });
            else
              await api("products.move", {
                product_id: product.id,
                quantity: operation === "exit" ? "-" + amount : amount,
                reason:
                  ({
                    entry: "Entrada",
                    exit: "Salida",
                    return: "Devolución al almacén",
                  }[operation] || "Movimiento") +
                  " · " +
                  reason,
                idempotency_key: key.current,
              });
            onSaved();
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="number-preview">
          <span>Existencias actuales</span>
          <strong>{product.stock} unidades</strong>
        </div>
        <Field label="Tipo de movimiento">
          <Select
            value={operation}
            onChange={(e) => setOperation(e.target.value)}
          >
            <option value="entry">Entrada</option>
            <option value="exit">Salida</option>
            <option value="return">Devolución al almacén</option>
            <option value="adjust">Recuento / ajuste</option>
          </Select>
        </Field>
        <div className="form-grid">
          <Input
            label={
              operation === "adjust"
                ? "Unidades contadas"
                : "Unidades del movimiento"
            }
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            inputMode="decimal"
            required
            placeholder="Ejemplo: 10 o 2,5"
          />
          <Input
            label="Motivo"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            placeholder="Compra, recuento, ajuste..."
          />
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose} disabled={busy}>
            Volver
          </Button>
          <Button type="submit" tone="primary" busy={busy}>
            Registrar movimiento
          </Button>
        </div>
      </form>
      <h3>Historial de movimientos</h3>
      {movements.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Motivo</th>
                <th className="right">Unidades</th>
              </tr>
            </thead>
            <tbody>
              {movements.map((m) => (
                <tr key={m.id}>
                  <td>{dateText(m.created_at)}</td>
                  <td>{m.reason}</td>
                  <td className="right amount">{m.quantity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="subtle">
          Registra las existencias iniciales con una entrada.
        </p>
      )}
      <div className="actions">
        <Button disabled={page === 0} onClick={() => setPage(page - 1)}>
          Más recientes
        </Button>
        <span>Página {page + 1}</span>
        <Button
          disabled={movements.length < 200}
          onClick={() => setPage(page + 1)}
        >
          Más antiguos
        </Button>
      </div>
    </Modal>
  );
}
export function CataloguePage({ notify }: Row) {
  const [tick, setTick] = useState(0),
    [query, setQuery] = useState(""),
    [low, setLow] = useState(false),
    [archived, setArchived] = useState(false),
    [actionError, setActionError] = useState(""),
    [edit, setEdit] = useState<Row | null>(null),
    [move, setMove] = useState<Row | null>(null);
  const [products, loading, error] = useLoad<Row[]>(
    "products.list",
    { include_archived: archived },
    [],
    tick,
  );
  const [suppliers] = useLoad<Row[]>(
    "suppliers.list",
    { include_archived: true },
    [],
  );
  const rows = products.filter(
    (p) =>
      (!low || p.low_stock) &&
      normalize(p.name + " " + (p.sku || "")).includes(normalize(query)),
  );
  return (
    <>
      <PageHead
        title="Art&iacute;culos y almac&eacute;n"
        subtitle="Recambios cuando los necesitas. Sin obligarte a llevar inventario."
        eyebrow="M&Aacute;S HERRAMIENTAS"
      >
        <Button tone="primary" icon="plus" onClick={() => setEdit({})}>
          Nuevo art&iacute;culo
        </Button>
      </PageHead>
      <section className="panel">
        <div className="list-toolbar">
          <div className="filter-input">
            <Icon name="search" />
            <TextInput
              aria-label="Buscar art&iacute;culos"
              placeholder="Nombre o referencia"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={low}
              onChange={(e) => setLow(e.target.checked)}
            />{" "}
            Solo stock bajo
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => setArchived(e.target.checked)}
            />{" "}
            Mostrar archivados
          </label>
          <span className="subtle">{rows.length} art&iacute;culos</span>
        </div>
        {(error || actionError) && (
          <Notice tone="error">{error || actionError}</Notice>
        )}
        {loading ? (
          <Loading />
        ) : rows.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Art&iacute;culo / referencia</th>
                  <th className="right">Precio sin IVA</th>
                  <th className="right">Existencias</th>
                  <th>Tipo</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.name}</strong>
                      {p.archived ? (
                        <small className="block subtle">Archivado</small>
                      ) : null}
                      <small className="block subtle">
                        {p.sku || "Sin referencia"}
                      </small>
                    </td>
                    <td className="right">{p.unit_price} &euro;</td>
                    <td className="right">
                      {p.track_stock ? (
                        <span className={p.low_stock ? "stock-low" : "amount"}>
                          {p.stock} {p.low_stock ? "\u00b7 Bajo" : ""}
                        </span>
                      ) : (
                        "\u2014"
                      )}
                    </td>
                    <td>{p.track_stock ? "Material" : "Servicio"}</td>
                    <td>
                      <div className="actions nowrap">
                        {p.track_stock && !p.archived ? (
                          <Button
                            tone="ghost"
                            icon="box"
                            onClick={() => setMove(p)}
                          >
                            Existencias
                          </Button>
                        ) : null}
                        <Button
                          tone="ghost icon-only"
                          icon="edit"
                          aria-label={"Editar " + p.name}
                          onClick={() => setEdit(p)}
                        />
                        <Button
                          tone="ghost"
                          onClick={async () => {
                            setActionError("");
                            try {
                              await api("products.archive", {
                                identifier: p.id,
                                archived: !p.archived,
                              });
                              setTick((t) => t + 1);
                            } catch (err: any) {
                              setActionError(err.message);
                            }
                          }}
                        >
                          {p.archived ? "Restaurar" : "Archivar"}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon="box"
            title="Tu cat&aacute;logo, a tu ritmo"
            text="A&ntilde;ade los recambios y servicios habituales. No es obligatorio para facturar."
          />
        )}
      </section>
      <Presence>{edit && (
        <ProductForm
          product={edit.id ? edit : null}
          suppliers={suppliers}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            setTick((t) => t + 1);
            notify("Art\u00edculo guardado");
          }}
        />
      )}</Presence>
      <Presence>{move && (
        <StockForm
          product={move}
          onClose={() => setMove(null)}
          onSaved={() => {
            setMove(null);
            setTick((t) => t + 1);
            notify("Movimiento de almac\u00e9n registrado");
          }}
        />
      )}</Presence>
    </>
  );
}
function SupplierForm({ supplier, onClose, onSaved }: Row) {
  const [v, setV] = useState<Row>({
      id: uuid(),
      name: "",
      tax_id: "",
      phone: "",
      email: "",
      notes: "",
      ...supplier,
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <Modal
      title={supplier ? "Editar proveedor" : "Nuevo proveedor"}
      onClose={() => !busy && onClose()}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("suppliers.save", { data: v });
            onSaved();
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="form-grid">
          {[
            ["name", "Nombre"],
            ["tax_id", "NIF / CIF"],
            ["phone", "Tel\u00e9fono"],
            ["email", "Correo electr\u00f3nico"],
          ].map(([k, l]) => (
            <Input
              key={k}
              label={l}
              required={k === "name"}
              type={k === "email" ? "email" : k === "phone" ? "tel" : "text"}
              value={v[k]}
              onChange={(e) => setV((o) => ({ ...o, [k]: e.target.value }))}
            />
          ))}
        </div>
        <Field label="Notas">
          <Textarea
            value={v.notes}
            rows={4}
            onChange={(e) => setV((o) => ({ ...o, notes: e.target.value }))}
          />
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button type="submit" tone="primary" busy={busy}>
            Guardar proveedor
          </Button>
        </div>
      </form>
    </Modal>
  );
}
export function SuppliersPage({ notify }: Row) {
  const [tick, setTick] = useState(0),
    [edit, setEdit] = useState<Row | null>(null),
    [query, setQuery] = useState(""),
    [archived, setArchived] = useState(false),
    [actionError, setActionError] = useState("");
  const [data, loading, error] = useLoad<Row[]>(
    "suppliers.list",
    { include_archived: archived },
    [],
    tick,
  );
  const rows = data.filter((row) =>
    normalize(row.name + " " + row.tax_id + " " + row.phone).includes(
      normalize(query),
    ),
  );
  return (
    <>
      <PageHead
        title="Proveedores"
        subtitle="Tus contactos para piezas y materiales."
        eyebrow="M&Aacute;S HERRAMIENTAS"
      >
        <Button icon="plus" tone="primary" onClick={() => setEdit({})}>
          Nuevo proveedor
        </Button>
      </PageHead>
      <section className="panel">
        <div className="list-toolbar">
          <Input
            label="Buscar proveedores"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <label className="check-row">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => setArchived(e.target.checked)}
            />{" "}
            Mostrar archivados
          </label>
        </div>
        {(error || actionError) && (
          <Notice tone="error">{error || actionError}</Notice>
        )}
        {loading ? (
          <Loading />
        ) : rows.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Proveedor</th>
                  <th>Tel&eacute;fono</th>
                  <th>Correo</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.name}</strong>
                      {s.archived ? (
                        <small className="block subtle">Archivado</small>
                      ) : null}
                      <small className="block subtle">{s.tax_id}</small>
                    </td>
                    <td>{s.phone || "\u2014"}</td>
                    <td>{s.email || "\u2014"}</td>
                    <td>
                      <Button
                        icon="edit"
                        tone="ghost"
                        onClick={() => setEdit(s)}
                      >
                        Editar
                      </Button>
                      <Button
                        tone="ghost"
                        onClick={async () => {
                          setActionError("");
                          try {
                            await api("suppliers.archive", {
                              identifier: s.id,
                              archived: !s.archived,
                            });
                            setTick((t) => t + 1);
                          } catch (err: any) {
                            setActionError(err.message);
                          }
                        }}
                      >
                        {s.archived ? "Restaurar" : "Archivar"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon="users"
            title="A&ntilde;ade a tus proveedores habituales"
            text="La agenda de contactos del taller, sin m&aacute;s complicaciones."
          />
        )}
      </section>
      <Presence>{edit && (
        <SupplierForm
          supplier={edit.id ? edit : null}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            setTick((t) => t + 1);
            notify("Proveedor guardado");
          }}
        />
      )}</Presence>
    </>
  );
}
