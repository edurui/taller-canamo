import { Presence } from "./overlays.js";
import { Textarea, TextInput } from "./controls.js";
import * as React from "react";
import { HistoricalTotal } from "./historical-review.js";
import { EntityRow, RowActions, SortHeader, useListSort, useListData, nextSort, type ListSort } from "./list-controls.js";
import {
  Row,
  api,
  useState,
  useLoad,
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
  Avatar,
  Pager,
  dateText,
  CustomerSearch,
} from "./core.js";
import { TextAssistance, ReadImageButton, HistorySearch } from "./assistant.js";
import { EntityReference } from "./entity-navigation.js";
import { AddressAutocomplete } from "./address-autocomplete.js";

export function CustomerForm({
  customer,
  onClose,
  onSaved,
}: {
  customer?: Row;
  onClose: () => void;
  onSaved: (customer: Row) => void;
}) {
  const [assistance] = useLoad<Row>("assistant.status", {}, { enabled: false });
  const [value, setValue] = useState<Row>({
    ...{
      name: "",
      tax_id: "",
      address: "",
      postal_code: "41300",
      city: "San Jos\u00e9 de la Rinconada",
      province: "Sevilla",
      country: "ES",
      phone: "",
      phone2: "",
      email: "",
      notes: "",
      legacy_code: "",
    },
    ...(customer || {}),
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const input = (key: string, label: string, extra: Row = {}) => (
    <Input
      label={label}
      value={value[key] || ""}
      onChange={(e) => setValue((v) => ({ ...v, [key]: e.target.value }))}
      {...extra}
    />
  );
  return (
    <Modal
      title={customer ? "Editar cliente" : "Nuevo cliente"}
      subtitle="Empieza con su nombre y tel&eacute;fono. Los datos fiscales se pueden completar despu&eacute;s."
      onClose={() => !busy && onClose()}
      wide
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const r = await api("customers.save", { data: value });
            onSaved(r);
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <ReadImageButton
          enabled={assistance.enabled}
          fields={[
            { key: "name", label: "Nombre" },
            { key: "tax_id", label: "NIF / CIF" },
            { key: "email", label: "Correo electrónico" },
            { key: "notes", label: "Notas" },
          ]}
          onApply={(fields) => setValue((old) => ({ ...old, ...fields }))}
        />
        <div className="form-grid">
          <div className="span-2">
            {input("name", "Nombre o raz\u00f3n social", {
              required: true,
              autoFocus: true,
              maxLength: 250,
              hint: "Nombre completo que debe figurar como destinatario en sus facturas.",
            })}
          </div>
          {input("phone", "Tel\u00e9fono principal", {
            type: "tel",
            inputMode: "tel",
          })}
          {input("phone2", "Otro tel\u00e9fono", { type: "tel" })}
          {input("tax_id", "NIF / CIF", {
            autoCapitalize: "characters",
            hint: "Necesario para emitir una factura completa.",
          })}
          {input("email", "Correo electr\u00f3nico", { type: "email" })}
          <div className="span-2">
            <AddressAutocomplete
              value={{
                address: value.address || "",
                postal_code: value.postal_code || "",
                city: value.city || "",
                province: value.province || "",
                country: value.country || "",
              }}
              onChange={patch => setValue(old => ({ ...old, ...patch }))}
              disabled={busy}
            />
          </div>
          {input("postal_code", "C\u00f3digo postal", {
            maxLength: String(value.country).toUpperCase() === "ES" ? 5 : 20,
            inputMode:
              String(value.country).toUpperCase() === "ES" ? "numeric" : "text",
          })}
          {input("city", "Poblaci\u00f3n")}
          {input("province", "Provincia")}
          {input("country", "País (dos letras)", {
            maxLength: 2,
            autoCapitalize: "characters",
            hint: "Por ejemplo ES, PT o FR. La facturación internacional está deshabilitada.",
          })}
          {input("legacy_code", "C\u00f3digo antiguo (opcional)", {
            hint: "Sirve para encontrarlo igual que en Access.",
          })}
          <Field label="Notas del cliente" className="span-2">
            <Textarea
              rows={3}
              value={value.notes}
              onChange={(e) =>
                setValue((v) => ({ ...v, notes: e.target.value }))
              }
              placeholder="Preferencias de contacto, indicaciones..."
            />
          </Field>
        </div>
        <TextAssistance
          enabled={assistance.enabled}
          value={value.notes}
          onApply={(notes) => setValue((old) => ({ ...old, notes }))}
        />
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button type="submit" icon="check" tone="primary" busy={busy}>
            Guardar cliente
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function vehicleDescription(vehicle: {
  make?: string | null;
  model?: string | null;
  kind?: string | null;
}) {
  return (
    [vehicle.make?.trim(), vehicle.model?.trim()].filter(Boolean).join(" ") ||
    vehicle.kind?.trim() ||
    "Vehículo sin descripción"
  );
}
export function VehicleForm({
  vehicle,
  customerId,
  onClose,
  onSaved,
}: {
  vehicle?: Row | null;
  customerId: string;
  onClose: () => void;
  onSaved: (vehicle: Row) => void;
}) {
  const [assistance] = useLoad<Row>("assistant.status", {}, { enabled: false });
  const [value, setValue] = useState<Row>({
    customer_id: customerId,
    plate: "",
    make: "",
    model: "",
    vin: "",
    kind: "Turismo",
    km: 0,
    itv_date: "",
    next_service: "",
    notes: "",
    ...vehicle,
  });
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const input = (key: string, label: string, extra: Row = {}) => (
    <Input
      label={label}
      value={value[key] ?? ""}
      onChange={(e) =>
        setValue((v) => ({
          ...v,
          [key]: key === "km" ? Number(e.target.value) : e.target.value,
        }))
      }
      {...extra}
    />
  );
  return (
    <Modal
      title={vehicle ? "Editar veh\u00edculo" : "A\u00f1adir veh\u00edculo"}
      subtitle="Se vincular&aacute; a este cliente. Podr&aacute;s encontrarlo por su matr&iacute;cula."
      onClose={() => !busy && onClose()}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            onSaved(await api("vehicles.save", { data: value }));
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <ReadImageButton
          enabled={assistance.enabled}
          fields={[
            { key: "plate", label: "Matrícula" },
            { key: "vin", label: "Número de chasis" },
            { key: "km", label: "Kilómetros" },
            { key: "notes", label: "Notas" },
          ]}
          onApply={(fields) =>
            setValue((old) => ({
              ...old,
              ...fields,
              ...(fields.km !== undefined ? { km: Number(fields.km) } : {}),
            }))
          }
        />
        <div className="form-grid">
          {input("plate", "Matr\u00edcula", {
            required: true,
            autoFocus: true,
            className: "plate-input",
            maxLength: 20,
          })}
          {input("kind", "Tipo de veh\u00edculo")}
          {input("make", "Marca")}
          {input("model", "Modelo")}
          {input("km", "Kil\u00f3metros actuales", {
            type: "number",
            min: 0,
            max: 10000000,
          })}
          {input("vin", "N\u00famero de chasis / VIN", { maxLength: 40 })}
          {input("itv_date", "Pr\u00f3xima ITV", { type: "date" })}
          {input("next_service", "Pr\u00f3xima revisi\u00f3n", {
            type: "date",
          })}
          <Field label="Notas" className="span-2">
            <Textarea
              rows={3}
              value={value.notes}
              onChange={(e) =>
                setValue((v) => ({ ...v, notes: e.target.value }))
              }
            />
          </Field>
        </div>
        {vehicle && value.km < vehicle.km && (
          <label className="check-row">
            <input
              type="checkbox"
              checked={!!value.confirm_km_correction}
              onChange={(e) =>
                setValue((v) => ({
                  ...v,
                  confirm_km_correction: e.target.checked,
                }))
              }
            />{" "}
            Confirmo que el kilometraje es inferior al anterior.
          </label>
        )}
        <TextAssistance
          enabled={assistance.enabled}
          value={value.notes}
          onApply={(notes) => setValue((old) => ({ ...old, notes }))}
        />
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button type="submit" tone="primary" busy={busy}>
            Guardar veh&iacute;culo
          </Button>
        </div>
      </form>
    </Modal>
  );
}
type CustomerListItem = {
  id: string;
  name: string;
  city: string;
  phone: string;
  tax_id: string;
  legacy_code: string | null;
  plates: string | null;
  vehicles: { id: string; plate: string }[];
};

export function CustomersPage({ navigate, notify }: Row) {
  const [request, setRequest] = useState({
    query: "",
    page: 0,
    archived: false,
    revision: 0,
    sort: null as ListSort,
  });
  const [form, setForm] = useState(false);
  const [editCustomer, setEditCustomer] = useState<Row | undefined>(undefined);
  const [archiveCustomer, setArchiveCustomer] = useState<CustomerListItem | null>(null);
  const [actionError, setActionError] = useState("");
  const [openingEdit, setOpeningEdit] = useState(false);
  const [result, setResult] = useState<{
    revision: number;
    data: { items: CustomerListItem[]; total: number } | null;
    page: number;
    error: string;
  }>({ revision: -1, data: null, page: 0, error: "" });
  const { query, page, archived, revision, sort } = request;
  const updateRequest = (change: Partial<Omit<typeof request, "revision">>) =>
    setRequest((previous) => ({
      ...previous,
      ...change,
      revision: previous.revision + 1,
    }));
  React.useEffect(() => {
    let current = true;
    api<{ items: CustomerListItem[]; total: number }>("customers.list", {
      query,
      page,
      archived,
      sort_by: sort?.key || "",
      sort_direction: sort?.direction || "asc",
    })
      .then((data) => {
        if (current) setResult({ revision, data, page, error: "" });
      })
      .catch((error: Error) => {
        if (current)
          setResult((previous) => ({
            ...previous,
            revision,
            error: error.message,
          }));
      });
    return () => {
      current = false;
    };
  }, [query, page, archived, revision, sort?.key, sort?.direction]);
  // Invalidate in the filter's render, including A → B → A before B completes.
  // The last successful table stays mounted, but cannot open obsolete matches.
  const loading = result.revision !== revision;
  const error = loading ? "" : result.error;
  const stale = loading || Boolean(error);
  const data = result.data;
  function sortBy(key: string) {
    updateRequest({ page: 0, sort: nextSort(sort, key) });
  }
  async function openEdit(customer: CustomerListItem) {
    setOpeningEdit(true);
    setActionError("");
    try {
      setEditCustomer(await api<Row>("customers.get", { identifier: customer.id }));
      setForm(true);
    } catch (failure: any) {
      setActionError(failure.message);
    } finally {
      setOpeningEdit(false);
    }
  }
  function newCustomer() {
    setEditCustomer(undefined);
    setForm(true);
  }
  const count = `${data?.total ?? 0} ${data?.total === 1 ? "cliente" : "clientes"}`;
  const status = loading ? (
    data ? (
      <>
        <span>Actualizando…</span>
        <span>Anteriores: {data.total}</span>
      </>
    ) : (
      "Buscando clientes…"
    )
  ) : error ? (
    data ? (
      `Anteriores: ${data.total}`
    ) : (
      "Lista no disponible"
    )
  ) : (
    count
  );
  return (
    <>
      <PageHead
        title="Clientes"
        subtitle="Las personas que conf&iacute;an en tu taller."
      >
        <Button tone="primary" icon="plus" onClick={newCustomer} disabled={openingEdit}>
          Nuevo cliente
        </Button>
      </PageHead>
      <section className="panel">
        <div className="list-toolbar">
          <div className="filter-input">
            <Icon name="search" />
            <TextInput
              aria-label="Filtrar clientes"
              placeholder="Buscar nombre, matr&iacute;cula, tel&eacute;fono..."
              value={query}
              onChange={(e) =>
                updateRequest({ query: e.target.value, page: 0 })
              }
            />
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) =>
                updateRequest({ archived: e.target.checked, page: 0 })
              }
            />{" "}
            Archivados
          </label>
          <span
            className="subtle"
            role="status"
            aria-live="polite"
            style={{
              flex: "0 0 10em",
              minHeight: "2.6em",
              lineHeight: 1.3,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              textAlign: "right",
              whiteSpace: "normal",
            }}
          >
            {status}
          </span>
        </div>
        {actionError && <Notice tone="error">{actionError}</Notice>}
        {error && (
          <Notice tone="error">
            No se pudo cargar la lista. {error}{" "}
            <Button onClick={() => updateRequest({})}>Reintentar</Button>
          </Notice>
        )}
        <div aria-busy={loading} aria-label="Listado de clientes" role="region">
          {!data && loading ? (
            <Loading />
          ) : data?.items.length ? (
            <div className="table-scroll" tabIndex={0}>
              <table
                aria-label={
                  stale ? "Resultados anteriores de clientes" : "Clientes"
                }
              >
                <thead>
                  <tr>
                    <SortHeader label="Cliente" field="name" sort={sort} onSort={sortBy} secondary={{ field: "city", label: "Población" }} />
                    <SortHeader label="Teléfono" field="phone" sort={sort} onSort={sortBy} />
                    <SortHeader label="Vehículos" field="plates" sort={sort} onSort={sortBy} />
                    <SortHeader label="NIF / CIF" field="tax_id" sort={sort} onSort={sortBy} />
                    <th><span className="sr-only">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((c) => (
                    <EntityRow key={c.id} disabled={stale} onOpen={() => navigate("customer", { id: c.id })}>
                      <td>
                        <button
                          className="row-link"
                          disabled={stale}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (!stale) navigate("customer", { id: c.id });
                          }}
                        >
                          <Avatar name={c.name} />
                          <span>
                            <strong>{c.name}</strong>
                            <small>{c.city || "Sin direcci\u00f3n"}</small>
                          </span>
                        </button>
                      </td>
                      <td className="nowrap">{c.phone || "\u2014"}</td>
                      <td>
                        {c.vehicles.length
                          ? c.vehicles.map((vehicle, index) => (
                              <React.Fragment key={vehicle.id}>
                                {index > 0 && ", "}
                                <EntityReference
                                  entity="vehicle"
                                  id={vehicle.id}
                                  navigate={navigate}
                                  disabled={stale}
                                >
                                  {vehicle.plate}
                                </EntityReference>
                              </React.Fragment>
                            ))
                          : "Sin vehículo"}
                      </td>
                      <td className="subtle">{c.tax_id || "Pendiente"}</td>
                      <td>
                        <RowActions label={c.name} disabled={stale || openingEdit} items={[
                          { label: "Ver ficha", onSelect: () => navigate("customer", { id: c.id }), disabled: stale },
                          { label: "Editar cliente", onSelect: () => void openEdit(c), disabled: stale || openingEdit },
                          { label: archived ? "Recuperar cliente" : "Archivar cliente", onSelect: () => setArchiveCustomer(c), disabled: stale },
                        ]} />
                      </td>
                    </EntityRow>
                  ))}
                </tbody>
              </table>
            </div>
          ) : data && !stale ? (
            <Empty
              icon="users"
              title={
                query
                  ? "No encontramos ese cliente"
                  : "Tu agenda de clientes, a mano"
              }
              text={
                query
                  ? "Prueba con una parte del nombre o de la matr\u00edcula."
                  : "A\u00f1ade tu primer cliente. Despu\u00e9s podr\u00e1s importar los de Access."
              }
            >
              <Button tone="primary" icon="plus" onClick={newCustomer} disabled={openingEdit}>
                A&ntilde;adir cliente
              </Button>
            </Empty>
          ) : null}
          {data && data.total > 50 && (
            <div className="pager">
              <span>
                {stale && "Consulta anterior: "}
                {result.page * 50 + 1}–
                {Math.min((result.page + 1) * 50, data.total)} de {data.total}
              </span>
              <Button
                icon="left"
                disabled={stale || !result.page}
                onClick={() => updateRequest({ page: result.page - 1 })}
              >
                Anterior
              </Button>
              <Button
                icon="right"
                disabled={stale || (result.page + 1) * 50 >= data.total}
                onClick={() => updateRequest({ page: result.page + 1 })}
              >
                Siguiente
              </Button>
            </div>
          )}
        </div>
      </section>
      <Presence>
        {form && (
          <CustomerForm
            customer={editCustomer}
            onClose={() => setForm(false)}
            onSaved={(c) => {
              setForm(false);
              updateRequest({});
              notify("Cliente guardado");
              navigate("customer", { id: c.id });
            }}
          />
        )}
      </Presence>
      <Presence>{archiveCustomer && (
        <Confirm
          title={archived ? "Recuperar cliente" : "Archivar cliente"}
          text={`El historial de ${archiveCustomer.name} se conserva. Un cliente archivado deja de aparecer en el buscador diario.`}
          confirm={archived ? "Recuperar" : "Archivar"}
          onClose={() => setArchiveCustomer(null)}
          onConfirm={async () => {
            await api("customers.archive", { identifier: archiveCustomer.id, archived: !archived });
            updateRequest({ page: 0 });
          }}
        />
      )}</Presence>
    </>
  );
}
export function CustomerPage({ id, vehicleId, navigate, notify }: Row) {
  const [tick, setTick] = useState(0),
    [historyPage, setHistoryPage] = useState(0),
    [edit, setEdit] = useState(false),
    [vehicle, setVehicle] = useState<Row | null>(null),
    [archive, setArchive] = useState(false),
    [selected, setSelected] = useState(vehicleId || "");
  const { sort, toggle } = useListSort();
  const sortBy = (key: string) => { toggle(key); setHistoryPage(0); };
  const [customer, loading, error] = useLoad<Row | null>(
    "customers.get",
    { identifier: id },
    null,
    tick,
  );
  const [docs, historyLoading, historyError, historyStale] = useListData<Row>(
    "documents.list",
    { customer_id: id, vehicle_id: selected || null, page: historyPage, sort_by: sort?.key || "", sort_direction: sort?.direction || "asc" },
    { items: [], total: 0 },
    tick,
  );
  function selectVehicle(identifier: string) {
    setSelected(identifier);
    setHistoryPage(0);
  }
  if (loading) return <Loading />;
  if (!customer)
    return (
      <Notice tone="error">{error || "No se encuentra el cliente."}</Notice>
    );
  return (
    <>
      <button className="back-link" onClick={() => navigate("customers")}>
        <Icon name="back" size={17} /> Todos los clientes
      </button>
      <PageHead
        title={customer.name}
        subtitle={
          customer.legacy_code
            ? "Cliente " + customer.legacy_code
            : "Ficha de cliente"
        }
      >
        <Button icon="edit" onClick={() => setEdit(true)}>
          Editar ficha
        </Button>
        <Button
          tone="primary"
          icon="plus"
          onClick={() =>
            navigate("editor", {
              kind: "invoice",
              customerId: id,
              vehicleId: selected,
              vehicleKilometres:
                customer.vehicles.find((item: Row) => item.id === selected)
                  ?.km ?? 0,
            })
          }
        >
          Nueva factura
        </Button>
      </PageHead>
      <HistorySearch
        customerId={id}
        vehicleId={selected || undefined}
        navigate={navigate}
      />
      <div className="customer-layout">
        <aside className="panel customer-card">
          <Avatar name={customer.name} large />
          <h3>{customer.name}</h3>
          <p>{customer.tax_id || "NIF pendiente"}</p>
          <div className="contact-line">
            <Icon name="phone" />
            <div>
              <small>Tel&eacute;fono principal</small>
              <strong className="big-phone">
                {customer.phone || "Sin tel\u00e9fono"}
              </strong>
              {customer.phone2 && <span>{customer.phone2}</span>}
            </div>
          </div>
          <div className="contact-line">
            <Icon name="mail" />
            <div>
              <small>Correo electr&oacute;nico</small>
              <span>{customer.email || "No indicado"}</span>
            </div>
          </div>
          <div className="contact-address">
            {customer.address || "Direcci\u00f3n pendiente"}
            <br />
            {customer.postal_code} {customer.city}
            <br />
            {customer.province}
          </div>
          {!customer.tax_id_valid && (
            <Notice>Completa o revisa el NIF antes de facturar.</Notice>
          )}
          {customer.notes && (
            <div className="note-paper">
              <strong>Notas</strong>
              <p>{customer.notes}</p>
            </div>
          )}
          <Button tone="ghost" onClick={() => setArchive(true)}>
            {customer.archived ? "Recuperar cliente" : "Archivar cliente"}
          </Button>
        </aside>
        <div className="customer-main">
          <section className="panel">
            <div className="section-head">
              <h2>
                Sus veh&iacute;culos{" "}
                <span className="count">{customer.vehicles.length}</span>
              </h2>
              <Button icon="plus" tone="ghost" onClick={() => setVehicle({})}>
                A&ntilde;adir
              </Button>
            </div>
            {!customer.vehicles.length ? (
              <Empty
                title="A&uacute;n sin veh&iacute;culos"
                text="Puedes facturar sin matr&iacute;cula, o a&ntilde;adirla para consultar su historial."
                icon="car"
              />
            ) : (
              <div className="vehicle-grid">
                {customer.vehicles.map((v: Row) => (
                  <div
                    key={v.id}
                    className={
                      "vehicle-card " + (selected === v.id ? "selected" : "")
                    }
                  >
                    <button
                      className="vehicle-select"
                      onClick={() =>
                        selectVehicle(selected === v.id ? "" : v.id)
                      }
                    >
                      <span className="plate">{v.plate}</span>
                      <strong>{vehicleDescription(v)}</strong>
                      <small>
                        {Number(v.km).toLocaleString("es-ES")} km{" "}
                        {v.itv_date && "\u00b7 ITV " + dateText(v.itv_date)}
                      </small>
                    </button>
                    <Button
                      icon="edit"
                      tone="ghost icon-only"
                      aria-label={"Editar " + v.plate}
                      onClick={() => setVehicle(v)}
                    />
                    <Button
                      tone="ghost"
                      onClick={() => navigate("vehicle", { id: v.id })}
                    >
                      Historial y titular
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </section>
          <section className="panel">
            <div className="section-head">
              <h2>Historial de facturas</h2>
              {selected && (
                <Button tone="ghost" onClick={() => selectVehicle("")}>
                  Ver todos los veh&iacute;culos
                </Button>
              )}
            </div>
            {historyError && <Notice tone="error">{historyError}</Notice>}
            {historyStale && docs.items.length > 0 && <p className="padded subtle" role="status">{historyLoading ? "Actualizando historial…" : "Resultados anteriores del historial."}</p>}
            {historyLoading && !docs.items.length ? (
              <Loading />
            ) : docs.items.length ? (
              <div className="table-scroll">
                <table aria-busy={historyLoading}>
                  <thead>
                    <tr>
                      <SortHeader label="Factura" field="full_number" sort={sort} onSort={sortBy} />
                      <SortHeader label="Fecha" field="issue_date" sort={sort} onSort={sortBy} />
                      <SortHeader label="Matrícula" field="plate" sort={sort} onSort={sortBy} />
                      <SortHeader label="Importe" field="total_cents" className="right" sort={sort} onSort={sortBy} />
                      <th><span className="sr-only">Acciones</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {docs.items.map((d: Row) => (
                      <EntityRow key={d.id} disabled={historyStale} onOpen={() => navigate("editor", { id: d.id, kind: "invoice" })}>
                        <td>
                          <EntityReference entity="document" id={d.id} navigate={navigate} disabled={historyStale}>
                            {d.full_number || "Borrador"}
                          </EntityReference>
                        </td>
                        <td>{dateText(d.issue_date)}</td>
                        <td>
                          <EntityReference entity="vehicle" id={d.vehicle_id} navigate={navigate} disabled={historyStale}>
                            {d.plate || (d.vehicle_id ? "Vehículo sin matrícula conservada" : "—")}
                          </EntityReference>
                        </td>
                        <td className="right amount"><HistoricalTotal total={d.total_cents} review={d.historical_review} /></td>
                        <td><RowActions disabled={historyStale} label={d.full_number || "borrador"} items={[
                          { label: "Abrir factura", onSelect: () => navigate("editor", { id: d.id, kind: "invoice" }) },
                        ]} /></td>
                      </EntityRow>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="El historial empieza aqu&iacute;"
                text="Las facturas que emitas quedar&aacute;n guardadas en esta ficha."
              />
            )}
            <Pager
              total={docs.total}
              page={historyPage}
              onChange={setHistoryPage}
            />
          </section>
        </div>
      </div>
      <Presence>{edit && (
        <CustomerForm
          customer={customer}
          onClose={() => setEdit(false)}
          onSaved={() => {
            setEdit(false);
            setTick((t) => t + 1);
            notify("Ficha actualizada. Las facturas antiguas no cambian.");
          }}
        />
      )}</Presence>
      <Presence>{vehicle && (
        <VehicleForm
          customerId={id}
          vehicle={vehicle.id ? vehicle : null}
          onClose={() => setVehicle(null)}
          onSaved={() => {
            setVehicle(null);
            setTick((t) => t + 1);
            notify("Veh\u00edculo guardado");
          }}
        />
      )}</Presence>
      <Presence>{archive && (
        <Confirm
          title={customer.archived ? "Recuperar cliente" : "Archivar cliente"}
          text="El historial se conserva. Un cliente archivado deja de aparecer en el buscador diario."
          confirm={customer.archived ? "Recuperar" : "Archivar"}
          onClose={() => setArchive(false)}
          onConfirm={async () => {
            await api("customers.archive", {
              identifier: id,
              archived: !customer.archived,
            });
            setTick((t) => t + 1);
          }}
        />
      )}</Presence>
    </>
  );
}
export function VehiclesPage({ navigate, notify }: Row) {
  const [editVehicle, setEditVehicle] = useState<Row | null>(null);
  const [tick, setTick] = useState(0);
  const { sort, toggle } = useListSort();
  const sortBy = (key: string) => { toggle(key); setPage(0); };
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [data, loading, error, stale] = useListData<Row>(
    "vehicles.page",
    { query, page, sort_by: sort?.key || "", sort_direction: sort?.direction || "asc" },
    { items: [], total: 0 },
    tick,
  );
  const rows = data.items as Row[];
  return (
    <>
      <PageHead
        title="Veh&iacute;culos"
        subtitle="Una matr&iacute;cula, todo su historial."
      />
      <section className="panel">
        <div className="list-toolbar">
          <div className="filter-input">
            <Icon name="search" />
            <TextInput
              aria-label="Buscar veh&iacute;culos"
              placeholder="Matr&iacute;cula, marca, modelo o cliente"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </div>
          <span className="subtle">
            {data.total} {data.total === 1 ? "vehículo" : "vehículos"}
          </span>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        {stale && rows.length > 0 && <p className="padded subtle" role="status">{loading ? "Actualizando vehículos…" : "Resultados anteriores de vehículos."}</p>}
        {loading && !rows.length ? (
          <Loading />
        ) : !rows.length ? (
          <Empty
            icon="car"
            title="No hay veh&iacute;culos"
            text="A&ntilde;ade un veh&iacute;culo desde la ficha de su cliente."
          />
        ) : (
          <div className="table-scroll">
            <table aria-busy={loading}>
              <thead>
                <tr>
                  <SortHeader label="Matrícula" field="plate" sort={sort} onSort={sortBy} />
                  <SortHeader label="Vehículo" field="description" sort={sort} onSort={sortBy} />
                  <SortHeader label="Cliente" field="customer_name" sort={sort} onSort={sortBy} />
                  <SortHeader label="Teléfono" field="phone" sort={sort} onSort={sortBy} />
                  <SortHeader label="Kilómetros" field="km" sort={sort} onSort={sortBy} />
                  <th><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((v) => (
                  <EntityRow key={v.id} disabled={stale} onOpen={() => navigate("vehicle", { id: v.id })}>
                    <td>
                      <EntityReference entity="vehicle" id={v.id} navigate={navigate} disabled={stale} className="plate">
                        {v.plate}
                      </EntityReference>
                    </td>
                    <td className="vehicle-description">
                      {vehicleDescription(v)}
                    </td>
                    <td>
                      <EntityReference entity="customer" id={v.customer_id} navigate={navigate} disabled={stale}>
                        {v.customer_name}
                      </EntityReference>
                    </td>
                    <td>{v.phone || "\u2014"}</td>
                    <td>{Number(v.km).toLocaleString("es-ES")}</td>
                    <td><RowActions disabled={stale} label={v.plate} items={[
                      { label: "Ver ficha", onSelect: () => navigate("vehicle", { id: v.id }) },
                      { label: "Editar vehículo", onSelect: () => setEditVehicle(v) },
                      { label: "Ver titular", onSelect: () => navigate("customer", { id: v.customer_id }) },
                    ]} /></td>
                  </EntityRow>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager page={page} total={data.total} onChange={setPage} />
      </section>
      <Presence>{editVehicle && (
        <VehicleForm
          customerId={editVehicle.customer_id}
          vehicle={editVehicle}
          onClose={() => setEditVehicle(null)}
          onSaved={() => { setEditVehicle(null); setTick(value => value + 1); notify("Vehículo guardado"); }}
        />
      )}</Presence>
    </>
  );
}

function ownershipReason(reason: string) {
  return /^Importación: [0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(
    reason,
  )
    ? "Alta desde importación"
    : reason;
}

export function VehiclePage({ id, navigate, notify }: Row) {
  const [tick, setTick] = useState(0);
  const [page, setPage] = useState(0);
  const { sort, toggle } = useListSort();
  const sortBy = (key: string) => { toggle(key); setPage(0); };
  const [transfer, setTransfer] = useState(false);
  const [owner, setOwner] = useState<Row | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [vehicle, loading, loadError] = useLoad<Row | null>(
    "vehicles.get",
    { identifier: id },
    null,
    tick,
  );
  const [history, historyLoading, historyError, historyStale] = useListData<Row>(
    "documents.list",
    { vehicle_id: id, page, sort_by: sort?.key || "", sort_direction: sort?.direction || "asc" },
    { items: [], total: 0 },
    tick,
  );
  if (loading) return <Loading />;
  if (!vehicle)
    return (
      <Notice tone="error">{loadError || "Vehículo no encontrado"}</Notice>
    );
  return (
    <>
      <button className="back-link" onClick={() => navigate("vehicles")}>
        <Icon name="back" size={17} /> Vehículos
      </button>
      <PageHead
        title={vehicle.plate}
        subtitle={
          <span className="vehicle-description">
            {vehicleDescription(vehicle)}
          </span>
        }
      >
        <Button
          onClick={() =>
            navigate("customer", { id: vehicle.customer_id, vehicleId: id })
          }
        >
          Ficha del titular actual
        </Button>
      </PageHead>
      <HistorySearch vehicleId={id} navigate={navigate} />
      <div className="vehicle-detail">
        <section className="panel padded vehicle-owner-card">
          <h2>Titular actual</h2>
          <p>
            <EntityReference entity="customer" id={vehicle.customer_id} navigate={navigate}>
              {vehicle.customer_name}
            </EntityReference> ·{" "}
            <strong>{vehicle.phone || "Sin teléfono"}</strong>
          </p>
          <p>{Number(vehicle.km).toLocaleString("es-ES")} km</p>
          <Button
            onClick={() => {
              setOwner(null);
              setReason("");
              setError("");
              setTransfer(true);
            }}
          >
            Cambiar propietario
          </Button>
        </section>
        <section className="panel padded vehicle-owner-card">
          <h2>Historial de titularidad</h2>
          <ul className="vehicle-owners">
            {vehicle.owners.map((entry: Row) => (
              <li key={entry.id}>
                <EntityReference entity="customer" id={entry.customer_id} navigate={navigate}>
                  {entry.customer_name}
                </EntityReference> · {dateText(entry.from_date)} —{" "}
                {entry.until_date ? dateText(entry.until_date) : "Actual"}
                {entry.reason && (
                  <span className="vehicle-owner-reason">
                    {" "}
                    · {ownershipReason(entry.reason)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
        <section className="panel">
          <div className="section-head">
            <h2>Facturas del vehículo</h2>
          </div>
          <p className="padded">
            Cada documento conserva el cliente y la matrícula de su emisión,
            aunque cambie el propietario.
          </p>
          {historyError && <Notice tone="error">{historyError}</Notice>}
          {historyStale && history.items.length > 0 && <p className="padded subtle" role="status">{historyLoading ? "Actualizando historial…" : "Resultados anteriores del historial."}</p>}
          {historyLoading && !history.items.length ? <Loading /> : history.items.length ? (
            <div className="table-scroll">
              <table aria-busy={historyLoading}>
                <thead>
                  <tr>
                    <SortHeader label="Documento" field="full_number" sort={sort} onSort={sortBy} />
                    <SortHeader label="Fecha" field="issue_date" sort={sort} onSort={sortBy} />
                    <SortHeader label="Cliente al emitir" field="customer_name" sort={sort} onSort={sortBy} />
                    <SortHeader label="Matrícula al emitir" field="plate" sort={sort} onSort={sortBy} />
                    <SortHeader label="Total" field="total_cents" className="right" sort={sort} onSort={sortBy} />
                    <th><span className="sr-only">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {history.items.map((document: Row) => (
                    <EntityRow key={document.id} disabled={historyStale} onOpen={() => navigate("editor", { id: document.id, kind: "invoice" })}>
                      <td>
                        <EntityReference entity="document" id={document.id} navigate={navigate} disabled={historyStale}>
                          {document.full_number || "Borrador"}
                        </EntityReference>
                      </td>
                      <td>{dateText(document.issue_date)}</td>
                      <td>
                        <EntityReference entity="customer" id={document.customer_id} navigate={navigate} disabled={historyStale}>
                          {document.customer_name?.trim() || document.current_customer_name || "Cliente no disponible"}
                        </EntityReference>
                        {!document.customer_name?.trim() && document.current_customer_name && (
                          <small className="block subtle">Ficha actual</small>
                        )}
                      </td>
                      <td>
                        <EntityReference entity="vehicle" id={document.vehicle_id} navigate={navigate} disabled={historyStale}>
                          {document.plate || (document.vehicle_id ? "Vehículo sin matrícula conservada" : "—")}
                        </EntityReference>
                      </td>
                      <td className="right"><HistoricalTotal total={document.total_cents} review={document.historical_review} /></td>
                      <td><RowActions disabled={historyStale} label={document.full_number || "borrador"} items={[
                        { label: "Abrir factura", onSelect: () => navigate("editor", { id: document.id, kind: "invoice" }) },
                      ]} /></td>
                    </EntityRow>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="Este vehículo aún no tiene facturas" />
          )}
          <Pager page={page} total={history.total} onChange={setPage} />
        </section>
      </div>
      <Presence>
        {transfer && (
          <Modal
            title="Cambiar propietario"
            onClose={() => !busy && setTransfer(false)}
          >
            <Notice>
              Las facturas anteriores permanecen con su cliente original. El
              nuevo titular se utilizará para trabajos nuevos.
            </Notice>
            <CustomerSearch
              placeholder="Buscar nuevo propietario"
              onSelect={(value) => setOwner(value)}
            />
            {owner && (
              <p>
                Nuevo titular: <strong>{owner.name}</strong>
              </p>
            )}
            <Input
              label="Motivo del cambio de propietario"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
            />
            {error && <Notice tone="error">{error}</Notice>}
            <div className="form-actions">
              <Button onClick={() => setTransfer(false)} disabled={busy}>
                Cancelar
              </Button>
              <Button
                tone="primary"
                busy={busy}
                disabled={
                  !owner ||
                  owner.customer_id === vehicle.customer_id ||
                  !reason.trim()
                }
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    await api("vehicles.transfer", {
                      identifier: id,
                      customer_id: owner!.customer_id,
                      reason,
                      expected_version: vehicle.version,
                    });
                    setTransfer(false);
                    setTick((t) => t + 1);
                    notify(
                      "Titular actualizado. El historial anterior se conserva.",
                    );
                  } catch (e: unknown) {
                    setError(e instanceof Error ? e.message : String(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Confirmar cambio de titular
              </Button>
            </div>
          </Modal>
        )}
      </Presence>
    </>
  );
}
