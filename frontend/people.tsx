import { Presence } from "./overlays.js";
import { Textarea, TextInput } from "./controls.js";
import * as React from "react";
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
  money,
  dateText,
  CustomerSearch,
} from "./core.js";
import { TextAssistance, ReadImageButton, HistorySearch } from "./assistant.js";

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
          <div className="span-2">{input("address", "Direcci\u00f3n")}</div>
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
export function CustomersPage({ navigate, notify }: Row) {
  const [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [archived, setArchived] = useState(false),
    [form, setForm] = useState(false),
    [tick, setTick] = useState(0);
  const [data, loading, error] = useLoad<Row>(
    "customers.list",
    { query, page, archived },
    { items: [], total: 0 },
    tick,
  );
  return (
    <>
      <PageHead
        title="Clientes"
        subtitle="Las personas que conf&iacute;an en tu taller."
      >
        <Button tone="primary" icon="plus" onClick={() => setForm(true)}>
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
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => {
                setArchived(e.target.checked);
                setPage(0);
              }}
            />{" "}
            Archivados
          </label>
          <span className="subtle">{data.total} clientes</span>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        {loading ? (
          <Loading />
        ) : data.items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Tel&eacute;fono</th>
                  <th>Veh&iacute;culos</th>
                  <th>NIF / CIF</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((c: Row) => (
                  <tr
                    key={c.id}
                    className="clickable"
                    onClick={() => navigate("customer", { id: c.id })}
                  >
                    <td>
                      <button
                        className="row-link"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate("customer", { id: c.id });
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
                    <td>{c.plates || "Sin veh\u00edculo"}</td>
                    <td className="subtle">{c.tax_id || "Pendiente"}</td>
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
            <Button tone="primary" icon="plus" onClick={() => setForm(true)}>
              A&ntilde;adir cliente
            </Button>
          </Empty>
        )}
        <Pager total={data.total} page={page} onChange={setPage} />
      </section>
      <Presence>{form && (
        <CustomerForm
          onClose={() => setForm(false)}
          onSaved={(c) => {
            setForm(false);
            setTick((t) => t + 1);
            notify("Cliente guardado");
            navigate("customer", { id: c.id });
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
  const [customer, loading, error] = useLoad<Row | null>(
    "customers.get",
    { identifier: id },
    null,
    tick,
  );
  const [docs, historyLoading, historyError] = useLoad<Row>(
    "documents.list",
    { customer_id: id, vehicle_id: selected || null, page: historyPage },
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
                      <strong>
                        {v.make} {v.model}
                      </strong>
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
            {historyLoading ? (
              <Loading />
            ) : docs.items.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Factura</th>
                      <th>Fecha</th>
                      <th>Matr&iacute;cula</th>
                      <th className="right">Importe</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {docs.items.map((d: Row) => (
                      <tr
                        key={d.id}
                        className="clickable"
                        onClick={() =>
                          navigate("editor", { id: d.id, kind: "invoice" })
                        }
                      >
                        <td>
                          <button
                            className="text-button"
                            onClick={() =>
                              navigate("editor", { id: d.id, kind: "invoice" })
                            }
                          >
                            {d.full_number || "Borrador"}
                          </button>
                        </td>
                        <td>{dateText(d.issue_date)}</td>
                        <td>{d.plate || "\u2014"}</td>
                        <td className="right amount">{money(d.total_cents)}</td>
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
export function VehiclesPage({ navigate }: Row) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [data, loading, error] = useLoad<Row>(
    "vehicles.page",
    { query, page },
    { items: [], total: 0 },
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
          <span className="subtle">Hasta 300 coincidencias</span>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        {loading ? (
          <Loading />
        ) : !rows.length ? (
          <Empty
            icon="car"
            title="No hay veh&iacute;culos"
            text="A&ntilde;ade un veh&iacute;culo desde la ficha de su cliente."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Matr&iacute;cula</th>
                  <th>Veh&iacute;culo</th>
                  <th>Cliente</th>
                  <th>Tel&eacute;fono</th>
                  <th>Kil&oacute;metros</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((v) => (
                  <tr key={v.id}>
                    <td>
                      <button
                        className="plate text-button"
                        onClick={() => navigate("vehicle", { id: v.id })}
                      >
                        {v.plate}
                      </button>
                    </td>
                    <td>
                      {v.make} {v.model}
                    </td>
                    <td>{v.customer_name}</td>
                    <td>{v.phone || "\u2014"}</td>
                    <td>{Number(v.km).toLocaleString("es-ES")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pager page={page} total={data.total} onChange={setPage} />
      </section>
    </>
  );
}

export function VehiclePage({ id, navigate, notify }: Row) {
  const [tick, setTick] = useState(0);
  const [page, setPage] = useState(0);
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
  const [history] = useLoad<Row>(
    "documents.list",
    { vehicle_id: id, page },
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
        subtitle={`${vehicle.make} ${vehicle.model}`}
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
      <section className="panel padded">
        <h2>Titular actual</h2>
        <p>
          {vehicle.customer_name} ·{" "}
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
      <section className="panel padded">
        <h2>Historial de titularidad</h2>
        <ul>
          {vehicle.owners.map((entry: Row) => (
            <li key={entry.id}>
              {entry.customer_name} · {dateText(entry.from_date)} —{" "}
              {entry.until_date ? dateText(entry.until_date) : "Actual"}
              {entry.reason && ` · ${entry.reason}`}
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
        {history.items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Documento</th>
                  <th>Fecha</th>
                  <th>Cliente al emitir</th>
                  <th>Matrícula al emitir</th>
                  <th className="right">Total</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((document: Row) => (
                  <tr key={document.id}>
                    <td>
                      <button
                        className="text-button"
                        onClick={() =>
                          navigate("editor", {
                            id: document.id,
                            kind: "invoice",
                          })
                        }
                      >
                        {document.full_number || "Borrador"}
                      </button>
                    </td>
                    <td>{dateText(document.issue_date)}</td>
                    <td>{document.customer_name}</td>
                    <td>{document.plate}</td>
                    <td className="right">{money(document.total_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="Este vehículo aún no tiene facturas" />
        )}
        <Pager page={page} total={history.total} onChange={setPage} />
      </section>
      <Presence>{transfer && (
        <Modal
          title="Cambiar propietario"
          onClose={() => !busy && setTransfer(false)}
        >
          <Notice>
            Las facturas anteriores permanecen con su cliente original. El nuevo
            titular se utilizará para trabajos nuevos.
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
      )}</Presence>
    </>
  );
}
