import { Presence } from "./overlays.js";
import { createRoot } from "react-dom/client";
import * as React from "react";
import {
  Row,
  api,
  useState,
  useEffect,
  useRef,
  useLoad,
  uuid,
  native,
  money,
  dateText,
  Button,
  Icon,
  Modal,
  Confirm,
  Empty,
  PageHead,
  Loading,
  Notice,
  Badge,
  CustomerSearch,
} from "./core.js";
import {
  CustomerForm,
  CustomersPage,
  CustomerPage,
  VehiclesPage,
  VehiclePage,
} from "./people.js";
import { DocumentsPage, DocumentEditor } from "./documents.js";
import { CalendarPage, wallDate } from "./calendar.js";
import { CataloguePage, SuppliersPage } from "./catalogue.js";
import { ReportsPage } from "./reports.js";
import { SettingsPage, BrandLogo } from "./settings.js";

function HomePage({ config, navigate, newCustomer, refresh, notify }: Row) {
  const [tick, setTick] = useState(0),
    [busy, setBusy] = useState(false),
    [demoConfirm, setDemoConfirm] = useState(false);
  const [data, loading, error] = useLoad<Row>(
    "dashboard",
    {},
    {
      customers: 0,
      drafts: 0,
      active_orders: 0,
      recent_invoices: [],
      today_events: [],
      pending_cents: 0,
      low_stock: 0,
    },
    tick,
  );
  const now = wallDate(new Date().toISOString());
  const formatted = now.toLocaleDateString("es-ES", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  return (
    <>
      <PageHead
        title="Tu taller, a punto."
        subtitle="Encuentra a tu cliente. Prepara su factura. Sigue con lo tuyo."
        eyebrow={formatted}
      />
      <section className="hero">
        <div className="hero-copy">
          <span className="hero-kicker">
            <Icon name="tool" size={17} /> LO DE CADA D&Iacute;A
          </span>
          <h2>
            Menos papeleo.
            <br />
            M&aacute;s tiempo en el taller.
          </h2>
          <p>
            Una matr&iacute;cula o un nombre es todo lo que necesitas para
            empezar.
          </p>
          <Button
            tone="dark"
            icon="plus"
            onClick={() => navigate("editor", { kind: "invoice" })}
          >
            Nueva factura <kbd>F2</kbd>
          </Button>
        </div>
        <div className="hero-graphic" aria-hidden="true">
          <div className="graphic-orbit" />
          <div className="graphic-card">
            <span className="graphic-logo">EC</span>
            <div className="graphic-lines">
              <i />
              <i />
              <i />
            </div>
            <div className="graphic-stamp">
              <Icon name="check" size={22} />
            </div>
            <div className="graphic-total">
              <span />
              <strong>Todo en orden.</strong>
            </div>
          </div>
          <span className="graphic-car">
            <Icon name="car" size={45} />
          </span>
        </div>
      </section>
      {error && <Notice tone="error">{error}</Notice>}
      {!loading && !data.customers && (
        <section className="welcome-panel panel padded">
          <div>
            <h2>Bienvenido a tu nuevo programa</h2>
            <p>
              La base est&aacute; vac&iacute;a. Puedes configurar el taller y
              empezar, o probar todo con clientes ficticios sin tocar Access.
            </p>
          </div>
          <div className="actions">
            <Button
              tone="primary"
              icon="settings"
              onClick={() => navigate("settings", { initialTab: "company" })}
            >
              Configurar taller
            </Button>
            <Button busy={busy} onClick={() => setDemoConfirm(true)}>
              Cargar demostraci&oacute;n
            </Button>
          </div>
        </section>
      )}
      <div className="quick-grid">
        <button className="quick-card" onClick={newCustomer}>
          <span className="quick-icon">
            <Icon name="users" />
          </span>
          <span>
            <strong>Nuevo cliente</strong>
            <small>Su ficha, en un momento</small>
          </span>
          <Icon name="plus" />
        </button>
        <button
          className="quick-card"
          onClick={() => navigate("documents", { kind: "invoice" })}
        >
          <span className="quick-icon">
            <Icon name="invoice" />
          </span>
          <span>
            <strong>Buscar una factura</strong>
            <small>Consultar, guardar o imprimir</small>
          </span>
          <Icon name="arrow" />
        </button>
        {config.appearance.extras && (
          <button className="quick-card" onClick={() => navigate("calendar")}>
            <span className="quick-icon">
              <Icon name="calendar" />
            </span>
            <span>
              <strong>Ver mi agenda</strong>
              <small>Las citas y los avisos de hoy</small>
            </span>
            <Icon name="arrow" />
          </button>
        )}
      </div>
      <div className="home-columns">
        <section className="panel recent-panel">
          <div className="section-head">
            <h2>&Uacute;ltimas facturas</h2>
            <Button
              tone="ghost"
              icon="arrow"
              onClick={() => navigate("documents", { kind: "invoice" })}
            >
              Ver todas
            </Button>
          </div>
          {loading ? (
            <Loading />
          ) : data.recent_invoices.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Cliente / matr&iacute;cula</th>
                    <th>Documento</th>
                    <th>Estado</th>
                    <th className="right">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_invoices.map((d: Row) => (
                    <tr
                      key={d.id}
                      className="clickable"
                      onClick={() =>
                        navigate("editor", { kind: "invoice", id: d.id })
                      }
                    >
                      <td>
                        <button
                          className="text-button"
                          onClick={() =>
                            navigate("editor", { kind: "invoice", id: d.id })
                          }
                        >
                          <strong>{d.customer_name}</strong>
                        </button>
                        <small className="block plate-text">
                          {d.plate || "Sin veh\u00edculo"}
                        </small>
                      </td>
                      <td>
                        <span className="small">
                          {d.full_number || "Borrador"}
                        </span>
                        <small className="block subtle">
                          {dateText(d.issue_date)}
                        </small>
                      </td>
                      <td>
                        <Badge value={d.status} />
                      </td>
                      <td className="right amount">{money(d.total_cents)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="Aqu&iacute; tendr&aacute;s las &uacute;ltimas facturas"
              text="Cada documento queda guardado con su cliente."
            />
          )}
          <div className="panel-footer">
            <span>
              <Icon name="invoice" size={16} />
              {data.drafts} borradores
            </span>
            <span>
              <Icon name="users" size={16} />
              {data.customers} clientes
            </span>
          </div>
        </section>
        {config.appearance.extras ? (
          <section className="panel today-panel">
            <div className="section-head">
              <h2>Hoy en el taller</h2>
              <span className="count">{data.today_events.length}</span>
            </div>
            {data.today_events.length ? (
              <div className="today-list">
                {data.today_events.slice(0, 4).map((e: Row) => (
                  <button
                    key={e.id + e.occurrence_start}
                    onClick={() => navigate("calendar")}
                  >
                    <span className="today-time">
                      {e.all_day
                        ? "D\u00eda"
                        : wallDate(e.occurrence_start).toLocaleTimeString(
                            "es-ES",
                            { hour: "2-digit", minute: "2-digit" },
                          )}
                    </span>
                    <span className={"event-dot type-" + e.kind} />
                    <span>
                      <strong>{e.title}</strong>
                      <small>
                        {e.plate || e.customer_name || "Evento del taller"}
                      </small>
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <Empty
                icon="calendar"
                title="El d&iacute;a est&aacute; despejado"
                text="Sin citas en la agenda de hoy."
              />
            )}
            <div className="padded">
              <Button
                tone="full"
                icon="calendar"
                onClick={() => navigate("calendar")}
              >
                Abrir agenda
              </Button>
            </div>
          </section>
        ) : (
          <section className="panel padded calm-card">
            <Icon name="shield" size={30} />
            <h2>Lo sencillo funciona.</h2>
            <p>Clientes y facturas. Todo lo necesario, sin distracciones.</p>
            <p className="small subtle">
              Las funciones adicionales se pueden mostrar desde
              Configuraci&oacute;n &rarr; Aspecto y comodidad.
            </p>
          </section>
        )}
      </div>
      {data.low_stock > 0 && config.appearance.extras && (
        <button
          className="low-stock-note"
          onClick={() => navigate("catalogue")}
        >
          <Icon name="box" size={18} />
          {data.low_stock} art&iacute;culos est&aacute;n por debajo del
          m&iacute;nimo. <strong>Revisar almac&eacute;n</strong>
          <Icon name="arrow" size={16} />
        </button>
      )}
      <Presence>{demoConfirm && (
        <Confirm
          title="Cargar datos de demostraci&oacute;n"
          text="Se a&ntilde;aden clientes, veh&iacute;culos, facturas y eventos ficticios. Tambi&eacute;n se configura un emisor de prueba. Solo puede hacerse con la base vac&iacute;a. No se env&iacute;a nada a Hacienda."
          confirm="Cargar demostraci&oacute;n"
          onClose={() => setDemoConfirm(false)}
          onConfirm={async () => {
            setBusy(true);
            try {
              await api("demo.load");
              await refresh();
              setTick((t) => t + 1);
              notify(
                "Demostraci\u00f3n preparada. Todos los datos son ficticios.",
              );
            } finally {
              setBusy(false);
            }
          }}
        />
      )}</Presence>
    </>
  );
}
function Notifications({ items, onClose, refresh, navigate }: Row) {
  return (
    <Modal
      title="Tus avisos"
      subtitle="Los avisos pendientes se conservan al cerrar y volver a abrir."
      onClose={onClose}
    >
      {items.length ? (
        <>
          <div className="actions">
            <Button
              tone="ghost"
              icon="check"
              onClick={async () => {
                await api("notifications.mark", {
                  identifiers: items.map((n: Row) => n.id),
                  action: "read",
                });
                refresh();
              }}
            >
              Marcar todos como le&iacute;dos
            </Button>
          </div>
          <div className="notification-list">
            {items.map((n: Row) => (
              <article key={n.id}>
                <span className="quick-icon">
                  <Icon name="bell" />
                </span>
                <div>
                  <h3>{n.title}</h3>
                  <p>{n.message}</p>
                  <small>{dateText(n.due_at)}</small>
                  <div className="actions">
                    <Button
                      tone="ghost"
                      onClick={async () => {
                        await api("notifications.mark", {
                          identifiers: [n.id],
                          action: "read",
                        });
                        refresh();
                      }}
                    >
                      Le&iacute;do
                    </Button>
                    <Button
                      tone="ghost"
                      icon="clock"
                      onClick={async () => {
                        await api("notifications.mark", {
                          identifiers: [n.id],
                          action: "snooze",
                          minutes: 15,
                        });
                        refresh();
                      }}
                    >
                      Posponer 15 min
                    </Button>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <Button
            tone="full"
            onClick={() => {
              onClose();
              navigate("calendar");
            }}
          >
            Abrir agenda
          </Button>
        </>
      ) : (
        <Empty
          icon="bell"
          title="Todo al d&iacute;a"
          text="No tienes avisos pendientes."
        />
      )}
    </Modal>
  );
}
function App() {
  const [boot, setBoot] = useState<Row | null>(null),
    [fatal, setFatal] = useState(""),
    [route, setRoute] = useState<Row>({ page: "home", key: uuid() }),
    [unsaved, setUnsaved] = useState(false),
    [pendingRoute, setPendingRoute] = useState<Row | null>(null),
    [extra, setExtra] = useState(false),
    [mobile, setMobile] = useState(false),
    [customerModal, setCustomerModal] = useState(false),
    [toast, setToast] = useState(""),
    [alerts, setAlerts] = useState<Row[]>([]),
    [showAlerts, setShowAlerts] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null),
    seen = useRef(new Set<string>());
  function notify(message: string) {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 5500);
  }
  async function refresh() {
    const result = await api("bootstrap");
    setBoot(result);
    return result;
  }
  useEffect(() => {
    refresh().catch((e) => setFatal(e.message));
  }, []);
  function navigate(page: string, params: Row = {}) {
    const next = { page, ...params, key: uuid() };
    if (unsaved && !params.force) {
      setPendingRoute(next);
      return;
    }
    setUnsaved(false);
    setRoute(next);
    setMobile(false);
    window.scrollTo({ top: 0 });
  }
  const cfg = boot?.settings;
  useEffect(() => {
    if (window.__TAURI__) {
      window.__TAURI__.core
        .invoke("set_document_dirty", { dirty: unsaved })
        .catch(() =>
          notify(
            "No se ha podido comunicar el estado del borrador. Guarda los cambios antes de salir.",
          ),
        );
    }
  }, [unsaved]);
  useEffect(() => {
    if (!cfg) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        cfg.appearance.theme === "system"
          ? media.matches
            ? "dark"
            : "light"
          : cfg.appearance.theme;
      document.documentElement.dataset.font = cfg.appearance.font_size;
      document.documentElement.dataset.contrast = cfg.appearance.high_contrast
        ? "high"
        : "normal";
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [
    cfg?.appearance.theme,
    cfg?.appearance.font_size,
    cfg?.appearance.high_contrast,
  ]);
  useEffect(() => {
    const keys = (e: KeyboardEvent) => {
      if (e.key === "F2") {
        e.preventDefault();
        navigate("editor", { kind: "invoice" });
      }
      if (e.key === "F3") {
        e.preventDefault();
        setCustomerModal(true);
      }
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [unsaved]);
  async function loadAlerts() {
    try {
      const list = await api<Row[]>("notifications.list");
      setAlerts(list);
      if (
        !native() &&
        cfg?.agenda.desktop_notifications &&
        "Notification" in window &&
        Notification.permission === "granted"
      ) {
        const pending = list.filter(
          (n) => !n.delivered_at && !seen.current.has(n.id + ":" + n.due_at),
        );
        if (pending.length) {
          // One summary prevents an avalanche after returning to a closed app.
          // due_at changes when snoozing, so that reminder can be delivered again.
          new Notification("Talleres El Cáñamo", {
            body:
              pending.length > 3
                ? `${pending.length} avisos pendientes. Abre Tus avisos para revisarlos.`
                : pending.map((n) => n.message).join("\n"),
            silent: !cfg.agenda.sound,
            tag: "canamo-reminders",
          });
          await api("notifications.mark", {
            identifiers: pending.map((n) => n.id),
            action: "delivered",
          });
          pending.forEach((n) => seen.current.add(n.id + ":" + n.due_at));
        }
      }
    } catch {
      /* The local service might be restarting; retry at the next poll. */
    }
  }
  useEffect(() => {
    if (!cfg) return;
    void loadAlerts();
    const interval = setInterval(loadAlerts, 20000);
    return () => clearInterval(interval);
  }, [cfg?.agenda.desktop_notifications, cfg?.agenda.sound]);
  if (fatal)
    return (
      <div className="fatal">
        <BrandLogo />
        <h1>No se puede abrir el servicio local</h1>
        <p>{fatal}</p>
        <p>
          Inicia ABRIR-PREVISUALIZACION.cmd o revisa que el servicio de
          escritorio est&eacute; activo.
        </p>
        <Button onClick={() => location.reload()}>Volver a intentar</Button>
      </div>
    );
  if (!boot || !cfg)
    return (
      <div className="splash">
        <BrandLogo />
        <h1>Talleres El Ca&ntilde;amo</h1>
        <Loading />
      </div>
    );
  const shared = {
    config: cfg,
    productionReleased: boot.production_released === true,
    series: boot.series,
    navigate,
    refresh,
    notify,
  };
  const nav = (page: string, label: string, icon: string, params: Row = {}) => {
    const active =
      (route.page === page &&
        (params.kind ? route.kind === params.kind : true)) ||
      (page === "customers" && route.page === "customer") ||
      (page === "documents" &&
        route.page === "editor" &&
        route.kind === params.kind);
    return (
      <button
        key={label}
        className={"nav-item " + (active ? "active" : "")}
        aria-current={active ? "page" : undefined}
        onClick={() => navigate(page, params)}
      >
        <Icon name={icon} />
        <span>{label}</span>
        {active && <i />}
      </button>
    );
  };
  let content: any;
  if (route.page === "home")
    content = (
      <HomePage {...shared} newCustomer={() => setCustomerModal(true)} />
    );
  else if (route.page === "customers") content = <CustomersPage {...shared} />;
  else if (route.page === "customer")
    content = <CustomerPage {...shared} {...route} />;
  else if (route.page === "documents")
    content = <DocumentsPage {...shared} kind={route.kind} />;
  else if (route.page === "editor")
    content = <DocumentEditor {...shared} {...route} onDirty={setUnsaved} />;
  else if (route.page === "calendar") content = <CalendarPage {...shared} />;
  else if (route.page === "vehicles") content = <VehiclesPage {...shared} />;
  else if (route.page === "vehicle")
    content = <VehiclePage {...shared} {...route} />;
  else if (route.page === "catalogue") content = <CataloguePage {...shared} />;
  else if (route.page === "suppliers") content = <SuppliersPage {...shared} />;
  else if (route.page === "reports") content = <ReportsPage />;
  else if (route.page === "settings")
    content = <SettingsPage {...shared} initialTab={route.initialTab} />;
  else content = <Empty title="Pantalla no disponible" />;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>
      {mobile && (
        <div className="sidebar-scrim" onClick={() => setMobile(false)} />
      )}
      <aside className={"sidebar " + (mobile ? "mobile-open" : "")}>
        <button
          className="brand"
          aria-label="Ir a inicio"
          onClick={() => navigate("home")}
        >
          <BrandLogo identifier={cfg.billing.logo_id} />
          <span>
            <small>AUTOMEC&Aacute;NICA</small>
            <strong>
              El Ca&ntilde;amo<span className="brand-dot">.</span>
            </strong>
          </span>
        </button>
        <div className="nav-heading">TU D&Iacute;A A D&Iacute;A</div>
        <nav aria-label="Men&uacute; principal">
          {nav("home", "Inicio", "home")}
          {nav("customers", "Clientes", "users")}
          {nav("documents", "Facturas", "invoice", { kind: "invoice" })}
        </nav>
        {cfg.appearance.extras && (
          <>
            <div className="nav-divider" />
            <button
              className={"extras-toggle " + (extra ? "expanded" : "")}
              onClick={() => setExtra(!extra)}
              aria-expanded={extra}
            >
              <Icon name="dots" />
              <span>M&aacute;s herramientas</span>
              <Icon name="down" size={16} />
            </button>
            {extra && (
              <nav className="extras-nav" aria-label="Herramientas adicionales">
                {nav("calendar", "Agenda", "calendar")}
                {nav("vehicles", "Veh\u00edculos", "car")}
                {nav("documents", "Presupuestos", "invoice", { kind: "quote" })}
                {nav("documents", "\u00d3rdenes de trabajo", "tool", {
                  kind: "order",
                })}
                {nav("catalogue", "Art\u00edculos y stock", "box")}
                {nav("suppliers", "Proveedores", "users")}
                {nav("reports", "Resumen", "chart")}
              </nav>
            )}
          </>
        )}
        <div className="sidebar-bottom">
          {nav("settings", "Configuraci\u00f3n", "settings")}
          <div className="local-card">
            <span className="live-dot" />
            <div>
              <strong>Todo en este equipo</strong>
              <small>Sin servidores ni suscripci&oacute;n</small>
            </div>
            <Icon name="shield" size={17} />
          </div>
          <small className="sidebar-version">
            El Ca&ntilde;amo &middot; {boot.version}
            {boot.production_released ? "" : " / desarrollo"}
          </small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <Button
            tone="ghost icon-only mobile-menu"
            icon="menu"
            aria-label="Abrir men&uacute;"
            onClick={() => setMobile(true)}
          />
          <CustomerSearch
            global
            onSelect={(c) =>
              navigate("customer", {
                id: c.customer_id,
                vehicleId: c.vehicle_id,
              })
            }
          />
          <div className="topbar-actions">
            <button
              className="theme-toggle"
              aria-label="Cambiar modo claro u oscuro"
              onClick={async () => {
                try {
                  const current = document.documentElement.dataset.theme;
                  await api("settings.save", {
                    section: "appearance",
                    values: { theme: current === "dark" ? "light" : "dark" },
                  });
                  await refresh();
                } catch (e: any) {
                  notify(e.message);
                }
              }}
            >
              <Icon
                name={
                  document.documentElement.dataset.theme === "dark"
                    ? "sun"
                    : "moon"
                }
              />
            </button>
            <button
              className="notification-button"
              aria-label={"Avisos: " + alerts.length + " pendientes"}
              onClick={() => {
                void loadAlerts();
                setShowAlerts(true);
              }}
            >
              <Icon name="bell" />
              {alerts.length > 0 && (
                <span>{alerts.length > 9 ? "9+" : alerts.length}</span>
              )}
            </button>
            <div className="profile-icon" title="Espacio del taller">
              EC
            </div>
          </div>
        </header>
        {!boot.production_released && (
          <div className="test-strip">
            <span>
              <i /> EDICI&Oacute;N DE PRUEBAS
            </span>
            <p>La emisi&oacute;n fiscal real no est&aacute; habilitada.</p>
            <button
              onClick={() => navigate("settings", { initialTab: "fiscal" })}
            >
              Ver estado <Icon name="arrow" size={14} />
            </button>
          </div>
        )}
        <main
          id="main-content"
          tabIndex={-1}
          key={route.key}
          className={"main-content page-" + route.page}
        >
          {boot.recovery?.blocked && (
            <Notice tone="warning">
              <strong>Emisión detenida para proteger el historial.</strong>{" "}
              {boot.recovery.message}
              <Button
                tone="ghost"
                onClick={() => navigate("settings", { initialTab: "backup" })}
              >
                Revisar recuperación o traslado
              </Button>
            </Notice>
          )}
          {content}
        </main>
        <footer className="app-footer">
          <span>
            <Icon name="shield" size={14} />
            {unsaved ? "Cambios sin guardar" : "Almacenamiento local"} &middot;
            Europe/Madrid
          </span>
          <span>
            {cfg.backup.last_success
              ? "\u00daltima copia: " + dateText(cfg.backup.last_success)
              : "Conserva tus copias fuera de este equipo"}
          </span>
        </footer>
      </div>
      {toast && (
        <div className="toast" role="status">
          <span className="toast-check">
            <Icon name="check" size={17} />
          </span>
          {toast}
          <button aria-label="Cerrar aviso" onClick={() => setToast("")}>
            <Icon name="x" size={16} />
          </button>
        </div>
      )}
      <Presence>{customerModal && (
        <CustomerForm
          onClose={() => setCustomerModal(false)}
          onSaved={(c) => {
            setCustomerModal(false);
            notify("Cliente guardado");
            navigate("customer", { id: c.id });
          }}
        />
      )}</Presence>
      <Presence>{showAlerts && (
        <Notifications
          items={alerts}
          onClose={() => setShowAlerts(false)}
          refresh={loadAlerts}
          navigate={navigate}
        />
      )}</Presence>
      <Presence>{pendingRoute && (
        <Confirm
          title="Hay cambios sin guardar"
          text="Vuelve al documento y guarda el borrador antes de salir. Si contin&uacute;as, se descartan los cambios que a&uacute;n no has guardado."
          confirm="Salir sin guardar"
          danger
          onClose={() => setPendingRoute(null)}
          onConfirm={() => {
            setUnsaved(false);
            setRoute(pendingRoute);
            setMobile(false);
            setPendingRoute(null);
          }}
        />
      )}</Presence>
    </div>
  );
}
class ErrorBoundary extends React.Component<
  { children?: React.ReactNode },
  { error: string }
> {
  state = { error: "" };
  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }
  render() {
    return this.state.error ? (
      <div className="fatal">
        <h1>La pantalla no se ha podido cargar</h1>
        <p>
          Los datos guardados permanecen en el equipo. No vuelvas a emitir sin
          consultar el historial.
        </p>
        <Button onClick={() => location.reload()}>Volver a abrir</Button>
        <details>
          <summary>Detalle t&eacute;cnico</summary>
          <code>{this.state.error}</code>
        </details>
      </div>
    ) : (
      this.props.children
    );
  }
}
createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
