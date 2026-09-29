import { Presence } from "./overlays.js";
import { Select, Textarea } from "./controls.js";
import * as React from "react";
import {
  Row,
  api,
  useState,
  useEffect,
  useRef,
  useLoad,
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
  Badge,
  dateText,
  localDate,
  fileBase64,
  saveExport,
  native,
} from "./core.js";
import { methods } from "./documents.js";
import { FiscalPanel } from "./fiscal.js";
import { B2BPanel } from "./b2b.js";
import { ImportPanel } from "./imports.js";
import { AssistanceStatus } from "./assistant.js";
const tabs = [
  ["company", "Taller y logo", "home"],
  ["billing", "Facturaci\u00f3n", "invoice"],
  ["appearance", "Aspecto y comodidad", "sun"],
  ["agenda", "Agenda y avisos", "calendar"],
  ["backup", "Copias y traslado", "shield"],
  ["import", "Importar Access", "upload"],
  ["fiscal", "VERI*FACTU (pruebas)", "lock"],
  ["b2b", "Factura electrónica B2B", "invoice"],
  ["assistant", "Asistencia opcional", "sparkles"],
  ["about", "Acerca del programa", "dots"],
];
export function BrandLogo({ identifier, className = "" }: Row) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let live = true;
    setSrc("");
    if (identifier)
      api("asset.read", { identifier })
        .then((r) => {
          if (live) setSrc("data:" + r.mime + ";base64," + r.content);
        })
        .catch(() => {});
    return () => {
      live = false;
    };
  }, [identifier]);
  return src ? (
    <img
      src={src}
      className={"brand-logo " + className}
      alt="Logo del taller"
    />
  ) : (
    <span
      className={"brand-placeholder " + className}
      role="img"
      aria-label="El Ca&ntilde;amo"
    >
      EC
    </span>
  );
}
function SeriesForm({ series, onClose, onSaved }: Row) {
  const [v, setV] = useState<Row>({
      kind: "invoice",
      label: "Facturas",
      prefix: "FAC-{YYYY}-",
      year: new Date().getFullYear(),
      padding: 5,
      next_number: 1,
      archived: false,
      ...series,
    }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const set = (k: string, x: any) => setV((o) => ({ ...o, [k]: x }));
  const preview =
    v.prefix
      .replaceAll("{YYYY}", String(v.year))
      .replaceAll("{YY}", String(v.year).slice(-2)) +
    String(v.next_number).padStart(v.padding, "0");
  return (
    <Modal
      title={series ? "Editar serie" : "Nueva serie"}
      onClose={() => !busy && onClose()}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("series.save", { data: v });
            onSaved();
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {series?.used ? (
          <Notice>
            Esta serie ya se ha utilizado. Su numeraci&oacute;n est&aacute;
            protegida: crea otra para empezar una numeraci&oacute;n diferente.
          </Notice>
        ) : (
          <Notice>
            El n&uacute;mero inicial no depende de la migraci&oacute;n. Confirma
            la continuidad con el &uacute;ltimo n&uacute;mero emitido en el
            programa anterior.
          </Notice>
        )}
        <div className="form-grid">
          <Input
            label="Nombre de la serie"
            value={v.label}
            onChange={(e) => set("label", e.target.value)}
            required
          />
          <Field label="Tipo">
            <Select
              disabled={!!series?.used}
              value={v.kind}
              onChange={(e) => set("kind", e.target.value)}
            >
              <option value="invoice">Facturas</option>
              <option value="rectification">Rectificativas</option>
              <option value="quote">Presupuestos</option>
              <option value="order">&Oacute;rdenes</option>
            </Select>
          </Field>
          <Input
            label="Prefijo"
            value={v.prefix}
            disabled={!!series?.used}
            onChange={(e) => set("prefix", e.target.value)}
            hint="{YYYY} = a&ntilde;o completo. {YY} = dos cifras."
          />
          <Field label="Continuidad">
            <Select
              disabled={!!series?.used}
              value={v.year === 0 ? "continuous" : "annual"}
              onChange={(e) => {
                if (e.target.value === "continuous")
                  setV((o) => ({
                    ...o,
                    year: 0,
                    prefix: o.prefix
                      .replaceAll("{YYYY}", "")
                      .replaceAll("{YY}", ""),
                  }));
                else set("year", new Date().getFullYear());
              }}
            >
              <option value="annual">Serie de un ejercicio</option>
              <option value="continuous">Continúa entre ejercicios</option>
            </Select>
          </Field>
          <Input
            label="A&ntilde;o"
            type="number"
            min={2000}
            max={2200}
            disabled={!!series?.used || v.year === 0}
            value={v.year}
            onChange={(e) => set("year", Number(e.target.value))}
          />
          <Input
            label="Siguiente n&uacute;mero"
            type="number"
            min={1}
            disabled={!!series?.used}
            value={v.next_number}
            onChange={(e) => set("next_number", Number(e.target.value))}
          />
          <Input
            label="N&uacute;mero m&iacute;nimo de cifras"
            type="number"
            min={1}
            max={8}
            disabled={!!series?.used}
            value={v.padding}
            onChange={(e) => set("padding", Number(e.target.value))}
          />
        </div>
        <div className="number-preview">
          <span>La siguiente ser&aacute;</span>
          <strong>{preview}</strong>
        </div>
        {series && (
          <Toggle checked={v.archived} onChange={(x) => set("archived", x)}>
            Archivar esta serie
          </Toggle>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" tone="primary" busy={busy}>
            Guardar serie
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function BackupsPanel({ config, refresh, notify }: Row) {
  const [v, setV] = useState<Row>({ ...config.backup }),
    [tick, setTick] = useState(0),
    [password, setPassword] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState<Row | null>(null),
    [word, setWord] = useState(""),
    [transferWord, setTransferWord] = useState(""),
    [prepareTransfer, setPrepareTransfer] = useState(false),
    [retention, setRetention] = useState<Row>(
      config.backup.retention || { daily: 7, weekly: 4, monthly: 12 },
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [backups] = useLoad<Row[]>("backup.list", {}, [], tick);
  const [recovery] = useLoad<Row>("backup.recovery_status", {}, {}, tick);
  const [pendingUploads] = useLoad<Row[]>("backup.upload_list", {}, [], tick);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [validating, setValidating] = useState(false);
  const upload = useRef<{ id: string; file: File } | null>(null);
  const pauseUpload = useRef(false);
  useEffect(
    () => () => {
      pauseUpload.current = true;
    },
    [],
  );
  async function checkBackup() {
    if (!file) return;
    pauseUpload.current = false;
    setPreview(null);
    setWord("");
    if (upload.current && upload.current.file !== file) {
      await api("backup.upload_cancel", { upload_id: upload.current.id });
      upload.current = null;
    }
    let progress: Row;
    if (upload.current)
      progress = await api("backup.upload_status", {
        upload_id: upload.current.id,
      });
    else {
      progress = await api("backup.upload_start", {
        name: file.name,
        total_bytes: file.size,
      });
      upload.current = { id: progress.upload_id, file };
    }
    let offset: number = progress.offset;
    setUploadProgress(Math.floor((offset / file.size) * 100));
    while (offset < file.size) {
      if (pauseUpload.current) return;
      const end = Math.min(offset + progress.chunk_bytes, file.size);
      const block = new File([file.slice(offset, end)], "bloque.canamo");
      const result = await api("backup.upload_chunk", {
        upload_id: progress.upload_id,
        offset,
        content: await fileBase64(block),
      });
      if (result.offset !== end)
        throw new Error(
          "La carga no confirmó el bloque. Pulsa continuar para consultar su progreso.",
        );
      offset = result.offset;
      setUploadProgress(Math.floor((offset / file.size) * 100));
    }
    if (pauseUpload.current) return;
    setValidating(true);
    try {
      setPreview(
        await api("backup.upload_finish", {
          upload_id: progress.upload_id,
          password,
        }),
      );
      upload.current = null;
      setUploadProgress(null);
    } finally {
      setValidating(false);
    }
  }
  async function run(task: () => Promise<any>) {
    setBusy(true);
    setError("");
    try {
      await task();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setTick((t) => t + 1);
      await refresh().catch((e: Error) => setError(e.message));
      setBusy(false);
    }
  }
  return (
    <>
      <div className="settings-title">
        <h2>Copias de seguridad y cambio de ordenador</h2>
        <p>
          Tu taller no depende de una nube. Pero la copia externa es
          imprescindible.
        </p>
      </div>
      <section className="panel padded">
        <Toggle
          checked={v.daily}
          onChange={(x) => setV((o) => ({ ...o, daily: x }))}
        >
          Copia autom&aacute;tica diaria
        </Toggle>
        <Toggle
          checked={v.on_close}
          onChange={(x) => setV((o) => ({ ...o, on_close: x }))}
        >
          Copia al salir de la aplicaci&oacute;n
        </Toggle>
        <Input
          label="Segunda carpeta de copias (opcional)"
          value={v.external_directory}
          onChange={(e) =>
            setV((o) => ({ ...o, external_directory: e.target.value }))
          }
          placeholder="D:\CopiasTaller"
          hint="Puede ser un disco externo o una carpeta sincronizada. Nunca sincronices la base SQLite abierta."
        />
        <div className="form-grid">
          {[
            ["daily", "Copias diarias"],
            ["weekly", "Copias semanales"],
            ["monthly", "Copias mensuales"],
          ].map(([key, label]) => (
            <Input
              key={key}
              label={label}
              type="number"
              min={1}
              max={365}
              value={retention[key]}
              onChange={(e) =>
                setRetention((o) => ({ ...o, [key]: Number(e.target.value) }))
              }
            />
          ))}
        </div>
        <p className="small subtle">
          Esta retención solo elimina copias automáticas antiguas. Los
          documentos y copias manuales, previas y de traslado se conservan.
        </p>
        <Button
          tone="primary"
          busy={busy}
          onClick={() =>
            run(async () => {
              const {
                last_success,
                retention: ignoredRetention,
                ...values
              } = v;
              await api("settings.save", { section: "backup", values });
              await api("backup.retention", retention);
              await refresh();
              notify("Copias configuradas");
            })
          }
        >
          Guardar configuraci&oacute;n
        </Button>
      </section>
      <section className="panel padded">
        <h3>Crear una copia para guardar fuera del ordenador</h3>
        <Input
          label="Contrase&ntilde;a de cifrado (opcional, m&iacute;nimo 10 caracteres)"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          hint="Sin contrase&ntilde;a, la copia contiene datos legibles. No pierdas la contrase&ntilde;a: no se puede recuperar."
        />
        <div className="actions">
          <Button
            tone="primary"
            icon="download"
            busy={busy}
            onClick={() =>
              run(async () => {
                const r = await api("backup.create", { password });
                const saved = await saveExport(r);
                setTick((t) => t + 1);
                await refresh();
                notify(
                  r.warning ||
                    (saved.saved === false
                      ? "Copia local creada. Has cancelado guardar otra copia fuera del programa."
                      : saved.saved
                        ? "Copia guardada"
                        : "Copia creada; descarga iniciada en el navegador"),
                );
              })
            }
          >
            Crear y guardar copia
          </Button>
          {native() && (
            <Button
              onClick={() =>
                run(async () => {
                  await api("backup.password", { value: password });
                  notify(
                    "Contrase\u00f1a de copias autom\u00e1ticas protegida en Windows",
                  );
                })
              }
            >
              Usar para copias autom&aacute;ticas
            </Button>
          )}
        </div>
      </section>
      <section className="panel padded">
        <h3>Preparar el traslado a otro ordenador</h3>
        <p>
          Cuando vayas a cambiar de equipo, prepara un paquete de traslado. Este
          equipo dejará de emitir y enviar registros fiscales. Conserva el
          paquete y actívalo solo en el ordenador de destino.
        </p>
        <Button
          busy={busy}
          disabled={recovery.blocked && recovery.reason !== "transfer_source"}
          onClick={() => setPrepareTransfer(true)}
        >
          {recovery.reason === "transfer_source"
            ? "Volver a guardar el paquete preparado"
            : "Preparar traslado"}
        </Button>
        {recovery.blocked && <Notice tone="warning">{recovery.message}</Notice>}
        {recovery.transfer_ready && (
          <>
            <Input
              label="Escribe ACTIVAR SOLO ESTE EQUIPO tras retirar el anterior"
              value={transferWord}
              onChange={(e) => setTransferWord(e.target.value)}
            />
            <Button
              tone="primary"
              busy={busy}
              disabled={transferWord !== "ACTIVAR SOLO ESTE EQUIPO"}
              onClick={() =>
                run(async () => {
                  await api("backup.activate_transfer", {
                    confirmation: transferWord,
                  });
                  setTransferWord("");
                  notify(
                    "Traslado activado en este equipo. Conserva el anterior inactivo.",
                  );
                })
              }
            >
              Activar equipo de destino
            </Button>
          </>
        )}
      </section>
      <section className="panel padded">
        <h3>Restaurar una copia o recibir un traslado</h3>
        <p>
          Instala la misma versi&oacute;n en el nuevo equipo, selecciona tu
          archivo <code>.canamo</code> y comprueba la vista previa. Utiliza un
          solo ordenador para emitir. Una copia antigua con historial incompleto
          no permite volver a emitir: recupera una copia completa.
        </p>
        <input
          type="file"
          accept=".canamo"
          disabled={busy}
          aria-label="Seleccionar copia para restaurar"
          onChange={(e) => {
            setFile(e.target.files?.[0] || null);
            setPreview(null);
            setWord("");
          }}
        />
        <p className="small subtle">
          La contrase&ntilde;a indicada arriba se utilizar&aacute;
          tambi&eacute;n para abrir la copia. El certificado digital nunca se
          incluye y debe configurarse de nuevo.
        </p>
        <Button
          icon="search"
          busy={busy}
          disabled={!file}
          onClick={() => run(checkBackup)}
        >
          {upload.current ? "Continuar comprobación" : "Comprobar copia"}
        </Button>
        {uploadProgress !== null && (
          <div>
            <p role="status">
              {validating
                ? "Comprobando integridad y contenido de la copia…"
                : `Copia cargada: ${uploadProgress} %`}
            </p>
            <progress
              max={100}
              value={uploadProgress}
              aria-label="Progreso de carga de la copia"
            />
            {busy && !validating && (
              <Button
                onClick={() => {
                  pauseUpload.current = true;
                }}
              >
                Pausar carga
              </Button>
            )}
            {!busy && upload.current && (
              <Button
                onClick={() =>
                  run(async () => {
                    await api("backup.upload_cancel", {
                      upload_id: upload.current!.id,
                    });
                    upload.current = null;
                    setUploadProgress(null);
                  })
                }
              >
                Descartar carga
              </Button>
            )}
          </div>
        )}
        {pendingUploads.filter((item) => item.upload_id !== upload.current?.id)
          .length > 0 && (
          <div className="restore-preview">
            <h4>Cargas anteriores pendientes</h4>
            <p className="small subtle">
              Puedes descartarlas y seleccionar de nuevo la copia. Descartar una
              carga no borra el archivo original.
            </p>
            {pendingUploads
              .filter((item) => item.upload_id !== upload.current?.id)
              .map((item) => (
                <div className="actions" key={item.upload_id}>
                  <span>
                    {item.name || "Carga sin terminar"} ·{" "}
                    {Math.floor((item.offset || 0) / 1024)} KB recibidos
                  </span>
                  <Button
                    busy={busy}
                    onClick={() =>
                      run(async () => {
                        await api("backup.upload_cancel", {
                          upload_id: item.upload_id,
                        });
                      })
                    }
                  >
                    Descartar carga {item.name || "incompleta"}
                  </Button>
                </div>
              ))}
          </div>
        )}
        {preview && (
          <div className="restore-preview">
            <Notice tone="warning">{preview.warning}</Notice>
            <div className="mini-stats">
              {Object.entries(preview.counts).map(([k, n]) => (
                <span key={k}>
                  <strong>{String(n)}</strong>
                  {{
                    customers: "clientes",
                    vehicles: "veh\u00edculos",
                    documents: "documentos",
                    fiscal_records: "registros fiscales",
                    events: "eventos",
                  }[k] || k}
                </span>
              ))}
            </div>
            <Input
              label="Escribe RESTAURAR para reemplazar los datos de este equipo"
              value={word}
              onChange={(e) => setWord(e.target.value)}
            />
            <Button
              tone="danger"
              busy={busy}
              disabled={word !== "RESTAURAR"}
              onClick={() =>
                run(async () => {
                  const r = await api("backup.restore", {
                    token: preview.token,
                    confirmation: word,
                  });
                  await refresh();
                  setPreview(null);
                  setTick((t) => t + 1);
                  notify(
                    "Copia restaurada. Se guard\u00f3 una copia previa: " +
                      r.safety_copy,
                  );
                })
              }
            >
              Restaurar datos
            </Button>
          </div>
        )}
      </section>
      {error && <Notice tone="error">{error}</Notice>}
      <Presence>
        {prepareTransfer && (
          <Confirm
            title="Preparar cambio de ordenador"
            text="Se conserva una copia del conjunto y se detiene la emisión en este equipo. Si cancelas el guardado del archivo, podrás volver a guardar el mismo paquete desde aquí."
            confirm="Preparar y guardar traslado"
            onClose={() => setPrepareTransfer(false)}
            onConfirm={async () => {
              setPrepareTransfer(false);
              await run(async () => {
                const result = await api("backup.prepare_transfer", {
                  password,
                });
                const saved = await saveExport(result);
                notify(
                  saved.saved === false
                    ? "Traslado preparado y conservado en copias locales. Vuelve a guardar el paquete para llevarlo al otro equipo."
                    : "Paquete de traslado preparado. Este equipo ha quedado inactivo para emitir.",
                );
              });
            }}
          />
        )}
      </Presence>
      <section className="panel">
        <div className="section-head">
          <h3>&Uacute;ltimas copias locales</h3>
          <span className="subtle">{backups.length}</span>
        </div>
        {backups.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Archivo</th>
                  <th>Fecha</th>
                  <th className="right">Tama&ntilde;o</th>
                </tr>
              </thead>
              <tbody>
                {backups.slice(0, 8).map((b) => (
                  <tr key={b.name}>
                    <td>
                      <code>{b.name}</code>
                    </td>
                    <td>{dateText(b.created_at)}</td>
                    <td className="right">{Math.ceil(b.bytes / 1024)} KB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon="shield"
            title="Todav&iacute;a no hay copias"
            text="Crea la primera antes de empezar a trabajar."
          />
        )}
      </section>
    </>
  );
}
export function SettingsPage({
  config,
  productionReleased = false,
  series,
  refresh,
  notify,
  initialTab = "company",
}: Row) {
  const [tab, setTab] = useState(initialTab);
  const content = useRef<HTMLDivElement | null>(null);
  function selectTab(next: string) {
    setTab(next);
    const section = content.current;
    if (section && section.getBoundingClientRect().top < 0)
      section.scrollIntoView({ block: "start", behavior: "instant" });
  }
  return (
    <>
      <PageHead
        title="Configuraci&oacute;n"
        subtitle="Hazlo tuyo. Sin complicar el trabajo de cada d&iacute;a."
      >
        <Button icon="settings" onClick={() => selectTab("appearance")}>
          Tamaño de letra y aspecto
        </Button>
      </PageHead>
      <div className="settings-layout">
        <nav
          className="settings-nav"
          aria-label="Secciones de configuraci&oacute;n"
        >
          {tabs.map(([key, label, icon]) => (
            <button
              key={key}
              className={tab === key ? "active" : ""}
              aria-current={tab === key ? "page" : undefined}
              onClick={() => selectTab(key)}
            >
              <Icon name={icon} size={18} />
              {label}
            </button>
          ))}
        </nav>
        <div className="settings-content" ref={content}>
          {tab === "backup" ? (
            <BackupsPanel config={config} refresh={refresh} notify={notify} />
          ) : tab === "import" ? (
            <ImportPanel refresh={refresh} notify={notify} />
          ) : tab === "fiscal" ? (
            <FiscalPanel config={config} refresh={refresh} notify={notify} />
          ) : tab === "b2b" ? (
            <B2BPanel />
          ) : (
            <GeneralSettings
              key={tab}
              tab={tab}
              config={config}
              productionReleased={productionReleased}
              series={series}
              refresh={refresh}
              notify={notify}
            />
          )}
        </div>
      </div>
    </>
  );
}
function GeneralSettings({
  tab,
  config,
  series,
  refresh,
  notify,
  productionReleased = false,
}: Row) {
  const [v, setV] = useState<Row>({ ...config[tab] }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [editSeries, setEditSeries] = useState<Row | null>(null);
  const [startup, setStartup] = useState<boolean | null>(null);
  const [startupBusy, setStartupBusy] = useState(false);
  const [licenses, setLicenses] = useState<Row | null>(null);
  const savedFont = useRef(config.appearance.font_size);
  savedFont.current = config.appearance.font_size;
  useEffect(() => {
    if (tab !== "appearance") return;
    document.documentElement.dataset.font = v.font_size;
    return () => {
      document.documentElement.dataset.font = savedFont.current;
    };
  }, [tab, v.font_size]);
  useEffect(() => {
    if (tab !== "about") return;
    let active = true;
    api("licenses.status")
      .then((result) => {
        if (active) setLicenses(result);
      })
      .catch((error: Error) => {
        if (active) setError(error.message);
      });
    return () => {
      active = false;
    };
  }, [tab]);
  useEffect(() => {
    if (tab !== "agenda" || !window.__TAURI__) return;
    let active = true;
    window.__TAURI__.core
      .invoke<boolean>("startup_status")
      .then((enabled) => {
        if (active) setStartup(enabled);
      })
      .catch((error: unknown) => {
        if (active) setError(String(error));
      });
    return () => {
      active = false;
    };
  }, [tab]);
  const set = (k: string, x: any) => setV((old) => ({ ...old, [k]: x }));
  const input = (key: string, label: string, props: Row = {}) => (
    <Input
      label={label}
      value={v[key] ?? ""}
      onChange={(e) =>
        set(
          key,
          props.type === "number" ? Number(e.target.value) : e.target.value,
        )
      }
      {...props}
    />
  );
  async function run(fn: () => Promise<any>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    await run(async () => {
      const values = { ...v };
      delete values.logo_id;
      await api("settings.save", { section: tab, values });
      notify("Configuraci\u00f3n guardada");
    });
  }
  const title = tabs.find((x) => x[0] === tab)?.[1] || tab;
  return (
    <>
      <div className="settings-title">
        <h2>{title}</h2>
        <p>
          {tab === "company"
            ? "Estos datos aparecen en los documentos nuevos. Las facturas emitidas conservan su versi\u00f3n original."
            : tab === "billing"
              ? "Series, impuestos, vencimientos y aspecto de los documentos."
              : tab === "appearance"
                ? "Un espacio c\u00f3modo para trabajar, a tu manera."
                : tab === "agenda"
                  ? "Tus citas, tus horarios y solo los avisos que necesites."
                  : tab === "assistant"
                    ? "La automatizaci\u00f3n normal no necesita IA ni suscripciones."
                    : ""}
        </p>
      </div>
      {tab === "company" && (
        <>
          <section className="panel padded">
            <div className="logo-settings">
              <BrandLogo identifier={config.billing.logo_id} />
              <div>
                <h3>Logo del taller</h3>
                <p>
                  PNG, JPG o WebP. M&aacute;ximo 4 MB. Se utiliza tambi&eacute;n
                  como marca de agua.
                </p>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  aria-label="Subir logo"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file)
                      run(async () => {
                        await api("settings.logo", {
                          content: await fileBase64(file),
                        });
                        notify("Logo actualizado");
                      });
                  }}
                />
                {config.billing.logo_id && (
                  <Button
                    tone="ghost"
                    onClick={() =>
                      run(async () => {
                        await api("settings.logo", { content: null });
                        notify("Logo retirado");
                      })
                    }
                  >
                    Quitar logo
                  </Button>
                )}
              </div>
            </div>
          </section>
          <section className="panel padded">
            <div className="form-grid">
              <div className="span-2">
                {input("trading_name", "Nombre comercial", { required: true })}
              </div>
              {input("legal_name", "Nombre fiscal / titular", {
                hint: "No sustituye al nombre comercial.",
              })}
              {input("tax_id", "NIF del titular")}
              {input("phone", "Tel\u00e9fono", { type: "tel" })}
              {input("email", "Correo electr\u00f3nico", { type: "email" })}
              <div className="span-2">{input("address", "Direcci\u00f3n")}</div>
              {input("postal_code", "C\u00f3digo postal", { maxLength: 5 })}
              {input("city", "Poblaci\u00f3n")}
              {input("province", "Provincia")}
              {input("iban", "IBAN (opcional)", {
                placeholder: "ES00 0000 0000 0000 0000 0000",
              })}
            </div>
          </section>
        </>
      )}
      {tab === "billing" && (
        <>
          <section className="panel">
            <div className="section-head">
              <h3>Series y numeraci&oacute;n</h3>
              <Button
                tone="primary"
                icon="plus"
                onClick={() => setEditSeries({})}
              >
                Nueva serie
              </Button>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Serie</th>
                    <th>A&ntilde;o</th>
                    <th>Pr&oacute;ximo n&uacute;mero</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {series.map((s: Row) => (
                    <tr key={s.id}>
                      <td>
                        <strong>{s.label}</strong>
                        <small className="block subtle">
                          {s.kind === "rectification"
                            ? "Rectificativa"
                            : s.kind === "invoice"
                              ? "Factura"
                              : s.kind === "quote"
                                ? "Presupuesto"
                                : "Orden"}{" "}
                          {s.archived ? "\u00b7 Archivada" : ""}
                        </small>
                      </td>
                      <td>{s.year || "Continua"}</td>
                      <td>
                        <code>
                          {s.prefix
                            .replaceAll("{YYYY}", String(s.year))
                            .replaceAll("{YY}", String(s.year).slice(-2)) +
                            String(s.next_number).padStart(s.padding, "0")}
                        </code>
                      </td>
                      <td>
                        <Button
                          tone="ghost"
                          icon="edit"
                          onClick={() => setEditSeries(s)}
                        >
                          Editar
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel padded">
            <h3>Valores habituales</h3>
            <div className="form-grid">
              <Field label="IVA por defecto">
                <Select
                  value={v.vat}
                  onChange={(e) => set("vat", e.target.value)}
                >
                  {["21", "10", "4", "0"].map((x) => (
                    <option value={x} key={x}>
                      {x}%
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Forma de pago por defecto">
                <Select
                  value={v.payment_method}
                  onChange={(e) => set("payment_method", e.target.value)}
                >
                  {Object.entries(methods).map(([k, l]) => (
                    <option value={k} key={k}>
                      {String(l)}
                    </option>
                  ))}
                </Select>
              </Field>
              {input("due_days", "D\u00edas hasta el vencimiento", {
                type: "number",
                min: 0,
                max: 365,
              })}
              {input("quote_days", "Validez del presupuesto (d\u00edas)", {
                type: "number",
                min: 1,
                max: 365,
              })}
              {input("labor_rate", "Tarifa de mano de obra por hora (EUR)", {
                inputMode: "decimal",
                hint: "Se aplica al pulsar Mano de obra en un documento. Revísala antes de emitir.",
              })}
            </div>
            <Field label="Pie del documento">
              <Textarea
                value={v.footer}
                rows={3}
                maxLength={800}
                onChange={(e) => set("footer", e.target.value)}
              />
            </Field>
            <Field
              label={
                "Intensidad de la marca de agua: " +
                Math.round(v.watermark_opacity * 100) +
                "%"
              }
            >
              <input
                type="range"
                min="0"
                max="0.15"
                step="0.01"
                value={v.watermark_opacity}
                onChange={(e) =>
                  set("watermark_opacity", Number(e.target.value))
                }
              />
            </Field>
            <Toggle checked={v.show_bank} onChange={(x) => set("show_bank", x)}>
              Mostrar IBAN en el pie (si est&aacute; configurado)
            </Toggle>
            <Toggle
              checked={v.allow_negative_stock}
              onChange={(x) => set("allow_negative_stock", x)}
              hint="Desaconsejado: puede ocultar errores de inventario."
            >
              Permitir existencias negativas
            </Toggle>
          </section>
        </>
      )}
      {tab === "appearance" && (
        <>
          <section
            className="panel padded"
            aria-labelledby="font-settings-title"
          >
            <h3 id="font-settings-title">Tamaño de letra</h3>
            <p>
              Elige el tamaño que te resulte más cómodo. Puedes probarlo aquí y
              guardar cuando lo veas bien.
            </p>
            <div
              className="font-size-choices"
              role="group"
              aria-label="Tamaño de letra"
            >
              {[
                ["normal", "Normal", "100 %"],
                ["large", "Grande", "112,5 %"],
                ["extra", "Muy grande", "125 %"],
              ].map(([key, label, scale]) => (
                <button
                  type="button"
                  key={key}
                  className="font-size-choice"
                  aria-pressed={v.font_size === key}
                  onClick={() => set("font_size", key)}
                >
                  <span
                    aria-hidden="true"
                    style={{
                      fontSize:
                        key === "extra"
                          ? "1.75em"
                          : key === "large"
                            ? "1.5em"
                            : "1.25em",
                    }}
                  >
                    Aa
                  </span>
                  <strong>{label}</strong>
                  <small>{scale}</small>
                </button>
              ))}
            </div>
            <div className="font-example">
              <strong>Así se verá tu taller</strong>
              <p>
                Buscar un cliente, preparar una factura y revisar los trabajos,
                con una letra cómoda de leer.
              </p>
            </div>
            <p className="small subtle">
              Se ajusta el texto de la aplicación. El PDF conserva su tamaño de
              impresión A4.
            </p>
          </section>
          <section className="panel padded">
            <h3>Tema de la aplicaci&oacute;n</h3>
            <div className="theme-choices">
              {[
                ["light", "Claro", "sun"],
                ["dark", "Oscuro", "moon"],
                ["system", "Como Windows", "settings"],
              ].map(([key, label, icon]) => (
                <button
                  key={key}
                  className={v.theme === key ? "selected" : ""}
                  aria-pressed={v.theme === key}
                  onClick={() => set("theme", key)}
                >
                  <div className={"theme-sample " + key}>
                    <span />
                    <i />
                    <i />
                    <b />
                  </div>
                  <span>
                    <Icon name={icon} size={17} />
                    {label}
                  </span>
                  {v.theme === key && <Icon name="check" size={17} />}
                </button>
              ))}
            </div>
            <Toggle
              checked={v.high_contrast}
              onChange={(x) => set("high_contrast", x)}
            >
              M&aacute;s contraste en bordes y texto
            </Toggle>
            <Toggle
              checked={v.extras}
              onChange={(x) => set("extras", x)}
              hint="Al desactivarlo solo quedan Inicio, Clientes, Facturas y Configuraci&oacute;n. Los datos de los extras no se borran."
            >
              Mostrar &laquo;M&aacute;s herramientas&raquo;
            </Toggle>
            <Field label="Vista inicial de la agenda">
              <Select
                value={v.calendar_start}
                onChange={(e) => set("calendar_start", e.target.value)}
              >
                <option value="month">Mes</option>
                <option value="week">Semana</option>
                <option value="day">D&iacute;a</option>
              </Select>
            </Field>
          </section>
        </>
      )}
      {tab === "agenda" && (
        <section className="panel padded">
          <div className="form-grid">
            {input("work_start", "Inicio de la jornada", { type: "time" })}
            {input("work_end", "Fin de la jornada", { type: "time" })}
            <Field label="Aviso por defecto para citas nuevas">
              <Select
                value={v.reminder_minutes}
                onChange={(e) =>
                  set("reminder_minutes", Number(e.target.value))
                }
              >
                {[
                  [0, "En el momento"],
                  [5, "5 minutos antes"],
                  [10, "10 minutos antes"],
                  [15, "15 minutos antes"],
                  [30, "30 minutos antes"],
                  [60, "1 hora antes"],
                  [120, "2 horas antes"],
                  [1440, "1 d\u00eda antes"],
                  [2880, "2 d\u00edas antes"],
                  [10080, "1 semana antes"],
                ].map(([n, l]) => (
                  <option key={String(n)} value={n}>
                    {l}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Toggle checked={v.sound} onChange={(x) => set("sound", x)}>
            Sonido de aviso
          </Toggle>
          <Toggle
            checked={v.desktop_notifications}
            onChange={(x) => set("desktop_notifications", x)}
            hint="Windows o el navegador pueden pedir permiso para mostrarlas."
          >
            Notificaciones del sistema
          </Toggle>
          <Button
            icon="bell"
            onClick={async () => {
              try {
                if (window.__TAURI__) {
                  await window.__TAURI__.core.invoke("test_notification");
                  notify("Aviso de prueba solicitado a Windows");
                } else if ("Notification" in window) {
                  const permission = await Notification.requestPermission();
                  if (permission === "granted")
                    new Notification("Talleres El Ca\u00f1amo", {
                      body: "Tus avisos est\u00e1n preparados.",
                    });
                  else
                    notify(
                      "El navegador no ha concedido permiso. Los avisos siguen dentro de la app.",
                    );
                }
              } catch (e: unknown) {
                setError(e instanceof Error ? e.message : String(e));
              }
            }}
          >
            Probar aviso
          </Button>
          <Notice>
            Con el ordenador apagado o la aplicaci&oacute;n completamente
            cerrada no hay alertas. En el programa de Windows, cerrar la ventana
            la oculta en la bandeja; &laquo;Salir&raquo; detiene el programa.
            Los avisos pendientes reaparecen al volver a abrir.
          </Notice>
          {native() && startup !== null && (
            <Toggle
              checked={startup}
              disabled={startupBusy}
              hint="Se inicia en la bandeja al entrar en Windows para mantener los avisos activos."
              onChange={async (enabled) => {
                if (!window.__TAURI__ || startupBusy) return;
                setStartupBusy(true);
                try {
                  setStartup(
                    await window.__TAURI__.core.invoke<boolean>("set_startup", {
                      enabled,
                    }),
                  );
                  notify(
                    enabled
                      ? "Inicio de sesión activado"
                      : "Inicio de sesión desactivado",
                  );
                } catch (error: unknown) {
                  setError(String(error));
                } finally {
                  setStartupBusy(false);
                }
              }}
            >
              Abrir el programa al iniciar sesión
            </Toggle>
          )}
        </section>
      )}
      {tab === "assistant" && (
        <section className="panel padded">
          <Toggle
            checked={v.enabled}
            onChange={(x) => set("enabled", x)}
            hint="Dictado, lectura de documentación y propuestas de texto. Revisa cada resultado antes de incorporarlo."
          >
            Activar asistencia local opcional
          </Toggle>
          {input("model", "Modelo de Ollama para redacción (opcional)", {
            placeholder: "Vacío: reglas de presentación locales",
            hint: "Solo si ya tienes Ollama en este ordenador (127.0.0.1:11434). El programa no instala modelos generativos ni usa proveedores externos.",
          })}
          <AssistanceStatus />
          <Notice>
            La asistencia no emite facturas ni decide reparaciones. Los textos e
            imágenes se procesan localmente; los resultados siempre se revisan
            antes de guardar.
          </Notice>
          <h3>Automatizaciones disponibles sin IA</h3>
          <p>
            Consulta del historial, conceptos frecuentes, conversiones, avisos
            de agenda, mensajes preparados, existencias y copias de seguridad.
            Abrir un borrador de WhatsApp no lo envía.
          </p>
        </section>
      )}
      {tab === "about" && (
        <section className="panel padded">
          <BrandLogo identifier={config.billing.logo_id} />
          <h2>Talleres El C&aacute;&ntilde;amo</h2>
          <p>
            Versi&oacute;n {licenses?.version || "—"} &middot;{" "}
            {productionReleased
              ? "Expediente de liberación verificado"
              : "Edición de desarrollo y validación"}
          </p>
          <div className="divider" />
          <h3>Tus datos, en tu equipo</h3>
          <p>
            Clientes, facturas y documentos se guardan en este ordenador. Haz
            copias periódicas en una unidad externa y comprueba su restauración.
          </p>
          <h3>Licencias y componentes</h3>
          <p>
            Consulta los avisos, las versiones y las fuentes de los componentes
            del programa.
          </p>
          <Button
            icon="download"
            busy={busy}
            disabled={!licenses?.available}
            onClick={() =>
              run(async () => {
                await saveExport(await api("licenses.export"));
              })
            }
          >
            Descargar licencias
          </Button>
          {licenses && !licenses.available && (
            <Notice tone="error">
              Falta el inventario de licencias. Repara la instalación.
            </Notice>
          )}
          <h3>Atajos</h3>
          <dl className="shortcuts">
            <dt>
              <kbd>Ctrl K</kbd>
            </dt>
            <dd>Buscar cliente o matr&iacute;cula</dd>
            <dt>
              <kbd>F2</kbd>
            </dt>
            <dd>Nueva factura</dd>
            <dt>
              <kbd>F3</kbd>
            </dt>
            <dd>Nuevo cliente</dd>
            <dt>
              <kbd>Ctrl S</kbd>
            </dt>
            <dd>Guardar borrador</dd>
            <dt>
              <kbd>Ctrl P</kbd>
            </dt>
            <dd>Vista previa del documento</dd>
            <dt>
              <kbd>Esc</kbd>
            </dt>
            <dd>Cerrar ventana emergente</dd>
          </dl>
          <div className="actions">
            <Button
              icon="shield"
              onClick={() =>
                run(async () => {
                  const r = await api("audit.check");
                  notify(
                    r.ok
                      ? "Historial de auditor\u00eda comprobado: " +
                          r.checked +
                          " entradas"
                      : "La auditor\u00eda contiene incidencias",
                  );
                })
              }
            >
              Comprobar auditor&iacute;a local
            </Button>
            {[
              ["customers", "clientes"],
              ["vehicles", "veh\u00edculos"],
              ["invoices", "facturas"],
              ["stock", "cat\u00e1logo"],
            ].map(([kind, name]) => (
              <Button
                key={kind}
                icon="download"
                onClick={() =>
                  run(async () =>
                    saveExport(await api("data.export", { kind })),
                  )
                }
              >
                Exportar {name}
              </Button>
            ))}
          </div>
          <p className="small subtle">
            Consulta LEEME.md y docs/ESTADO-VERIFICADO.md para requisitos,
            pruebas y l&iacute;mites. No es una certificaci&oacute;n oficial de
            la AEAT.
          </p>
        </section>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      {tab !== "about" && (
        <div className="settings-save">
          <Button tone="primary" icon="check" busy={busy} onClick={save}>
            Guardar cambios
          </Button>
          <span className="small subtle">
            Solo afecta a los nuevos documentos o a la apariencia.
          </span>
        </div>
      )}
      <Presence>
        {editSeries && (
          <SeriesForm
            series={editSeries.id ? editSeries : null}
            onClose={() => setEditSeries(null)}
            onSaved={async () => {
              setEditSeries(null);
              await refresh();
              notify("Serie guardada");
            }}
          />
        )}
      </Presence>
    </>
  );
}
