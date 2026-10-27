import { Presence } from "./overlays.js";
import { Select, Textarea, TextInput } from "./controls.js";
import * as React from "react";
import { EntityReference } from "./entity-navigation.js";
import { EntityRow, RowActions, SortHeader, useListSort, useListData } from "./list-controls.js";
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
  Confirm,
  Empty,
  PageHead,
  Loading,
  dateText,
  normalize,
} from "./core.js";
const productSortValues = {
  name: (row: Row) => row.name,
  sku: (row: Row) => row.sku,
  unit_price: (row: Row) => Number(row.unit_price),
  stock: (row: Row) => row.track_stock ? Number(row.stock) : null,
  type: (row: Row) => row.track_stock ? "Material" : "Servicio",
  supplier: (row: Row) => row.supplier_name,
};
const supplierSortValues = {
  name: (row: Row) => row.name,
  tax_id: (row: Row) => row.tax_id,
  phone: (row: Row) => row.phone,
  email: (row: Row) => row.email,
};
function ProductForm({ product, suppliers, onClose, onSaved }: Row) {
  const [showSupplier, setShowSupplier] = useState(false);
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
  const supplier = suppliers.find((item: Row) => item.id === v.supplier_id);
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
            {supplier && (
              <button type="button" className="entity-reference" disabled={busy} onClick={() => setShowSupplier(true)}>
                Consultar {supplier.name}
              </button>
            )}
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
      <Presence>{showSupplier && supplier && (
        <Modal title={supplier.name} onClose={() => setShowSupplier(false)}>
          {supplier.archived ? <Notice>Proveedor archivado. Su ficha se conserva.</Notice> : null}
          <dl className="details-list">
            <dt>NIF / CIF</dt><dd>{supplier.tax_id || "No consta"}</dd>
            <dt>Teléfono</dt><dd>{supplier.phone || "No consta"}</dd>
            <dt>Correo</dt><dd>{supplier.email || "No consta"}</dd>
            <dt>Dirección</dt><dd>{supplier.address || "No consta"}</dd>
            <dt>Notas</dt><dd>{supplier.notes || "Sin notas"}</dd>
          </dl>
          <Button onClick={() => setShowSupplier(false)}>Volver al artículo</Button>
        </Modal>
      )}</Presence>
    </Modal>
  );
}
function StockForm({ product, onClose, onSaved, navigate }: Row) {
  const [operation, setOperation] = useState("entry"),
    [page, setPage] = useState(0),
    [quantity, setQuantity] = useState(""),
    [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [pendingDocument, setPendingDocument] = useState<string | null>(null);
  const key = useRef(uuid());
  const [selectedMovement, setSelectedMovement] = useState<Row | null>(null);
  const { sort, toggle } = useListSort();
  const sortBy = (field: string) => { toggle(field); setPage(0); };
  const [movements, movementsLoading, movementsError, movementsStale] = useListData<Row[]>(
    "products.movements",
    { product_id: product.id, page, sort_by: sort?.key || "", sort_direction: sort?.direction || "asc" },
    [],
  );
  function requestDocument(identifier: string) {
    setSelectedMovement(null);
    if (quantity.trim() || reason.trim()) setPendingDocument(identifier);
    else void openDocument(identifier);
  }
  async function openDocument(identifier: string) {
    setBusy(true);
    setError("");
    try {
      // A movement stores the document ID, but not its kind. Resolve it only
      // when requested, without guessing its route or loading every row.
      const document = await api("documents.get", { identifier });
      navigate("editor", { id: document.id, kind: document.kind });
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }
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
      {movementsError && <Notice tone="error">{movementsError}</Notice>}
      {movementsStale && movements.length > 0 && <p className="subtle" role="status">{movementsLoading ? "Actualizando movimientos…" : "Resultados anteriores de movimientos."}</p>}
      {movementsLoading && !movements.length ? <Loading /> : movements.length ? (
        <div className="table-scroll">
          <table aria-busy={movementsLoading}>
            <thead>
              <tr>
                <SortHeader label="Fecha" field="created_at" sort={sort} onSort={sortBy} />
                <SortHeader label="Motivo" field="reason" sort={sort} onSort={sortBy} />
                <SortHeader label="Unidades" field="quantity" className="right" sort={sort} onSort={sortBy} />
                <th><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {movements.map((m) => (
                <EntityRow key={m.id} onOpen={() => setSelectedMovement(m)} disabled={busy || movementsStale}>
                  <td>{dateText(m.created_at)}</td>
                  <td>
                    <button type="button" className="entity-reference" disabled={busy || movementsStale} onClick={() => setSelectedMovement(m)}>{m.reason}</button>
                    {m.document_id && (
                      <p>
                        <button
                          type="button"
                          className="entity-reference"
                          disabled={busy || movementsStale}
                          onClick={() => requestDocument(m.document_id)}
                        >
                          Consultar documento del movimiento
                        </button>
                      </p>
                    )}
                  </td>
                  <td className="right amount">{m.quantity}</td>
                  <td><RowActions label={`movimiento ${m.reason}`} disabled={busy || movementsStale} items={[
                    { label: "Ver movimiento", onSelect: () => setSelectedMovement(m) },
                    ...(m.document_id ? [{ label: "Consultar documento", onSelect: () => requestDocument(m.document_id) }] : []),
                  ]} /></td>
                </EntityRow>
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
        <Button disabled={page === 0 || movementsStale} onClick={() => setPage(page - 1)}>
          {sort ? "Anterior" : "Más recientes"}
        </Button>
        <span>Página {page + 1}</span>
        <Button
          disabled={movements.length < 200 || movementsStale}
          onClick={() => setPage(page + 1)}
        >
          {sort ? "Siguiente" : "Más antiguos"}
        </Button>
      </div>
      <Presence>{selectedMovement && (
        <Modal title="Detalle del movimiento" onClose={() => setSelectedMovement(null)}>
          <dl className="details-list">
            <dt>Artículo</dt><dd>{product.name}</dd>
            <dt>Referencia</dt><dd>{product.sku || "Sin referencia"}</dd>
            <dt>Fecha</dt><dd>{new Date(selectedMovement.created_at).toLocaleString("es-ES", { timeZone: "Europe/Madrid" })}</dd>
            <dt>Motivo</dt><dd>{selectedMovement.reason}</dd>
            <dt>Unidades</dt><dd>{selectedMovement.quantity}</dd>
          </dl>
          <div className="actions">
            <Button onClick={() => setSelectedMovement(null)}>Volver al almacén</Button>
            {selectedMovement.document_id && <Button onClick={() => requestDocument(selectedMovement.document_id)}>Consultar documento</Button>}
          </div>
        </Modal>
      )}</Presence>
      <Presence>{pendingDocument && (
        <Confirm
          title="Movimiento sin registrar"
          text="La cantidad y el motivo que has escrito aún no se han registrado. Puedes volver para conservarlos o salir al documento."
          confirm="Salir sin registrar"
          danger
          onClose={() => setPendingDocument(null)}
          onConfirm={() => {
            const identifier = pendingDocument;
            setPendingDocument(null);
            void openDocument(identifier);
          }}
        />
      )}</Presence>
    </Modal>
  );
}
export function CataloguePage({ notify, navigate, id }: Row) {
  const [tick, setTick] = useState(0),
    [query, setQuery] = useState(""),
    [low, setLow] = useState(false),
    [archived, setArchived] = useState(Boolean(id)),
    [initialClosed, setInitialClosed] = useState(false),
    [actionError, setActionError] = useState(""),
    [edit, setEdit] = useState<Row | null>(null),
    [move, setMove] = useState<Row | null>(null);
  const [products, loading, error, stale] = useListData<Row[]>(
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
  const { sort, toggle, rows: sortedProducts } = useListSort(products, productSortValues);
  const rows = sortedProducts.filter(
    (p) =>
      (!low || p.low_stock) &&
      normalize(p.name + " " + (p.sku || "")).includes(normalize(query)),
  );
  const selectedProduct = edit || (!stale && !initialClosed && id ? products.find(product => product.id === id) : null);
  const closeProduct = () => { setEdit(null); setInitialClosed(true); };
  async function archiveProduct(product: Row) {
    setActionError("");
    try {
      await api("products.archive", { identifier: product.id, archived: !product.archived });
      setTick(value => value + 1);
    } catch (failure: any) {
      setActionError(failure.message);
    }
  }
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
        {id && !initialClosed && !loading && !error && !selectedProduct && (
          <Notice tone="error">No se encuentra el artículo vinculado.</Notice>
        )}
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
          <Notice tone="error">{error || actionError}{error && <Button onClick={() => setTick(value => value + 1)}>Reintentar</Button>}</Notice>
        )}
        {stale && rows.length > 0 && <p className="padded subtle" role="status">{loading ? "Actualizando artículos…" : "Resultados anteriores de artículos."}</p>}
        {loading && !rows.length ? (
          <Loading />
        ) : rows.length ? (
          <div className="table-scroll">
            <table aria-busy={loading}>
              <thead>
                <tr>
                  <SortHeader label="Artículo" field="name" secondary={{ field: "sku", label: "Referencia" }} sort={sort} onSort={toggle} />
                  <SortHeader label="Precio sin IVA" field="unit_price" className="right" sort={sort} onSort={toggle} />
                  <SortHeader label="Existencias" field="stock" className="right" sort={sort} onSort={toggle} />
                  <SortHeader label="Tipo" field="type" sort={sort} onSort={toggle} />
                  <SortHeader label="Proveedor" field="supplier" sort={sort} onSort={toggle} />
                  <th><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <EntityRow key={p.id} disabled={stale} onOpen={() => setEdit(p)}>
                    <td>
                      <button type="button" disabled={stale} className="entity-reference" onClick={() => setEdit(p)}><strong>{p.name}</strong></button>
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
                    <td><EntityReference entity="supplier" id={p.supplier_id} disabled={stale} navigate={navigate}>{p.supplier_name || "—"}</EntityReference></td>
                    <td>
                      <RowActions label={p.name} disabled={stale} items={[
                        { label: "Editar artículo", onSelect: () => setEdit(p) },
                        ...(p.track_stock && !p.archived ? [{ label: "Existencias", onSelect: () => setMove(p) }] : []),
                        { label: p.archived ? "Restaurar" : "Archivar", onSelect: () => void archiveProduct(p) },
                      ]} />
                    </td>
                  </EntityRow>
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
      <Presence>{selectedProduct && (
        <ProductForm
          product={selectedProduct.id ? selectedProduct : null}
          suppliers={suppliers}
          onClose={closeProduct}
          onSaved={() => {
            closeProduct();
            setTick((t) => t + 1);
            notify("Art\u00edculo guardado");
          }}
        />
      )}</Presence>
      <Presence>{move && (
        <StockForm
          product={move}
          navigate={navigate}
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
export function SuppliersPage({ notify, id }: Row) {
  const [tick, setTick] = useState(0),
    [edit, setEdit] = useState<Row | null>(null),
    [query, setQuery] = useState(""),
    [archived, setArchived] = useState(Boolean(id)),
    [initialClosed, setInitialClosed] = useState(false),
    [actionError, setActionError] = useState("");
  const [data, loading, error, stale] = useListData<Row[]>(
    "suppliers.list",
    { include_archived: archived },
    [],
    tick,
  );
  const { sort, toggle, rows: sortedSuppliers } = useListSort(data, supplierSortValues);
  const rows = sortedSuppliers.filter((row) =>
    normalize(row.name + " " + row.tax_id + " " + row.phone).includes(
      normalize(query),
    ),
  );
  const selectedSupplier = edit || (!stale && !initialClosed && id ? data.find(supplier => supplier.id === id) : null);
  const closeSupplier = () => { setEdit(null); setInitialClosed(true); };
  async function archiveSupplier(supplier: Row) {
    setActionError("");
    try {
      await api("suppliers.archive", { identifier: supplier.id, archived: !supplier.archived });
      setTick(value => value + 1);
    } catch (failure: any) {
      setActionError(failure.message);
    }
  }
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
        {id && !initialClosed && !loading && !error && !selectedSupplier && (
          <Notice tone="error">No se encuentra el proveedor vinculado.</Notice>
        )}
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
          <Notice tone="error">{error || actionError}{error && <Button onClick={() => setTick(value => value + 1)}>Reintentar</Button>}</Notice>
        )}
        {stale && rows.length > 0 && <p className="padded subtle" role="status">{loading ? "Actualizando proveedores…" : "Resultados anteriores de proveedores."}</p>}
        {loading && !rows.length ? (
          <Loading />
        ) : rows.length ? (
          <div className="table-scroll">
            <table aria-busy={loading}>
              <thead>
                <tr>
                  <SortHeader label="Proveedor" field="name" secondary={{ field: "tax_id", label: "NIF / CIF" }} sort={sort} onSort={toggle} />
                  <SortHeader label="Teléfono" field="phone" sort={sort} onSort={toggle} />
                  <SortHeader label="Correo" field="email" sort={sort} onSort={toggle} />
                  <th><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <EntityRow key={s.id} disabled={stale} onOpen={() => setEdit(s)}>
                    <td>
                      <button type="button" disabled={stale} className="entity-reference" onClick={() => setEdit(s)}><strong>{s.name}</strong></button>
                      {s.archived ? (
                        <small className="block subtle">Archivado</small>
                      ) : null}
                      <small className="block subtle">{s.tax_id}</small>
                    </td>
                    <td>{s.phone || "\u2014"}</td>
                    <td>{s.email || "\u2014"}</td>
                    <td>
                      <RowActions label={s.name} disabled={stale} items={[
                        { label: "Editar proveedor", onSelect: () => setEdit(s) },
                        { label: s.archived ? "Restaurar" : "Archivar", onSelect: () => void archiveSupplier(s) },
                      ]} />
                    </td>
                  </EntityRow>
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
      <Presence>{selectedSupplier && (
        <SupplierForm
          supplier={selectedSupplier.id ? selectedSupplier : null}
          onClose={closeSupplier}
          onSaved={() => {
            closeSupplier();
            setTick((t) => t + 1);
            notify("Proveedor guardado");
          }}
        />
      )}</Presence>
    </>
  );
}
