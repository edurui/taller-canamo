import { Presence } from "./overlays.js";
import { Select, Textarea } from "./controls.js";
import * as React from "react";
import {
  Row,
  api,
  useState,
  useRef,
  useLoad,
  uuid,
  Button,
  Input,
  Field,
  Notice,
  Modal,
  Empty,
  Badge,
  dateText,
  fileBase64,
  saveExport,
} from "./core.js";

function CorrectionForm({
  record,
  onClose,
  onSaved,
}: {
  record: Row;
  onClose: () => void;
  onSaved: (record: Row) => void;
}) {
  const keys = [
    ["issuer_name", "Nombre fiscal del emisor"],
    ["customer_name", "Nombre fiscal del destinatario"],
    ["customer_nif", "NIF del destinatario"],
    ["description", "Descripción del registro"],
  ];
  const [values, setValues] = useState<Row>(() =>
    Object.fromEntries(keys.map(([key]) => [key, record.payload[key] || ""])),
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef(uuid());
  return (
    <Modal title="Subsanar registro fiscal" onClose={() => !busy && onClose()}>
      <Notice>
        Esta acción conserva el registro anterior y añade su corrección a la
        cadena. Para cambiar importes, fecha, número o impuestos utiliza una
        factura rectificativa.
      </Notice>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const changes =
              record.kind === "anulacion"
                ? {}
                : Object.fromEntries(
                    keys
                      .filter(
                        ([name]) =>
                          values[name] !== (record.payload[name] || ""),
                      )
                      .map(([name]) => [name, values[name]]),
                  );
            onSaved(
              await api("fiscal.correct", {
                record_id: record.id,
                changes,
                reason,
                idempotency_key: key.current,
              }),
            );
          } catch (e: unknown) {
            setError(e instanceof Error ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        {record.kind !== "anulacion" &&
          keys.map(([name, label]) => (
            <Input
              key={name}
              label={label}
              value={values[name]}
              onChange={(e) =>
                setValues((v) => ({ ...v, [name]: e.target.value }))
              }
              required
              maxLength={
                name === "description" ? 500 : name === "customer_nif" ? 9 : 120
              }
            />
          ))}
        <Input
          label="Motivo de la subsanación"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          required
          minLength={3}
          maxLength={1500}
        />
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          <Button onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button type="submit" tone="primary" busy={busy}>
            Conservar subsanación
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function FiscalPanel({ config, refresh, notify }: Row) {
  const [v, setV] = useState<Row>({ ...config.fiscal }),
    [file, setFile] = useState<File | null>(null),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [tick, setTick] = useState(0),
    [detail, setDetail] = useState<Row | null>(null);
  const [correcting, setCorrecting] = useState(false);
  const [records] = useLoad<Row[]>("fiscal.list", {}, [], tick);
  const [readiness, readinessLoading, readinessError] = useLoad<Row | null>(
    "fiscal.readiness",
    {},
    null,
    tick,
  );
  async function run(fn: () => Promise<any>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      setTick((t) => t + 1);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const input = (key: string, label: string, props: Row = {}) => (
    <Input
      label={label}
      value={v[key] || ""}
      onChange={(e) => setV((o) => ({ ...o, [key]: e.target.value }))}
      {...props}
    />
  );
  return (
    <>
      <div className="settings-title">
        <h2>VERI*FACTU</h2>
        <p>
          Registros trazables, cola de env&iacute;o y respuestas verificables.
        </p>
      </div>
      {!readiness?.production_ready ? (
        <Notice tone="warning">
          <strong>Emisi&oacute;n real bloqueada en esta edici&oacute;n.</strong>{" "}
          El c&oacute;digo integra el entorno externo de pruebas de la AEAT.
          Faltan la validaci&oacute;n externa, las pruebas con certificado y la
          declaraci&oacute;n responsable del productor. VERI*FACTU no sustituye
          el intercambio de factura electr&oacute;nica B2B.
        </Notice>
      ) : (
        <Notice>
          El expediente y la configuración de esta versión están verificados.
          Modo guardado:{" "}
          {config.fiscal.mode === "production"
            ? "producción"
            : config.fiscal.mode === "aeat_test"
              ? "pruebas externas de AEAT"
              : "pruebas locales"}
          . VERI*FACTU y factura electrónica B2B mantienen estados separados.
        </Notice>
      )}
      <section className="panel padded">
        <h3>Diagnóstico de puesta en marcha</h3>
        <p>
          Comprueba identidad, certificado, esquemas, cadena y evidencias de
          esta versión. Este diagnóstico local no realiza envíos.
        </p>
        {readinessError && <Notice tone="error">{readinessError}</Notice>}
        {readiness && (
          <>
            <p>
              Integridad local:{" "}
              {readiness.chain.ok
                ? `${readiness.chain.checked} registros comprobados`
                : "Se ha detectado una incidencia"}
              .
            </p>
            {readiness.problems.length ? (
              <ul>
                {readiness.problems.map((problem: Row) => (
                  <li key={problem.code}>{problem.message}</li>
                ))}
              </ul>
            ) : (
              <Notice>
                Configuración y evidencias de liberación comprobadas.
              </Notice>
            )}
          </>
        )}
        <Button busy={readinessLoading} onClick={() => setTick((t) => t + 1)}>
          Comprobar configuración
        </Button>
      </section>
      <section className="panel padded">
        <h3>Entorno y productor del sistema</h3>
        <Field label="Modo de trabajo">
          <Select
            value={v.mode}
            onChange={(e) => setV((o) => ({ ...o, mode: e.target.value }))}
          >
            <option value="local_test">
              Pruebas locales &middot; Sin env&iacute;os a la AEAT
            </option>
            <option value="aeat_test">
              Entorno externo de pruebas de la AEAT
            </option>
            {(readiness?.build_policy?.candidate_build ||
              v.mode === "production") && (
              <option
                value="production"
                disabled={!readiness?.production_ready}
              >
                Producción · requiere expediente verificado
              </option>
            )}
          </Select>
        </Field>
        <div className="form-grid">
          {input("producer_name", "Nombre fiscal del productor")}
          {input("producer_tax_id", "NIF del productor")}
          {input("system_id", "Identificador del SIF (2 caracteres)", {
            maxLength: 2,
          })}
          <Input
            label="Identificador de instalaci&oacute;n"
            value={v.installation_id}
            readOnly
          />
        </div>
        <Field label="Declaraci&oacute;n responsable de esta versi&oacute;n">
          <Textarea
            rows={5}
            placeholder="Debe elaborarla y suscribirla el productor. No se genera ni firma autom&aacute;ticamente."
            value={v.declaration_text}
            onChange={(e) =>
              setV((o) => ({ ...o, declaration_text: e.target.value }))
            }
          />
        </Field>
        <Button
          tone="primary"
          busy={busy}
          onClick={() =>
            run(async () => {
              const { certificate_info, installation_id, ...values } = v;
              await api("settings.save", { section: "fiscal", values });
              notify("Configuraci\u00f3n fiscal guardada");
            })
          }
        >
          Guardar configuraci&oacute;n fiscal
        </Button>
      </section>
      <section className="panel padded">
        <h3>Certificado digital en este equipo</h3>
        {config.fiscal.certificate_info ? (
          <Notice>
            <strong>{config.fiscal.certificate_info.subject}</strong>
            <br />
            Caduca: {dateText(config.fiscal.certificate_info.expires)}. La clave
            privada est&aacute; protegida con DPAPI del usuario de Windows.
          </Notice>
        ) : (
          <p>
            No hay certificado configurado. Esto no impide probar la
            gesti&oacute;n local.
          </p>
        )}
        <input
          type="file"
          accept=".pfx,.p12"
          aria-label="Certificado PFX o P12"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />
        <Input
          label="Contrase&ntilde;a del certificado"
          type="password"
          autoComplete="off"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <div className="actions">
          <Button
            icon="lock"
            busy={busy}
            disabled={!file}
            onClick={() =>
              run(async () => {
                await api("certificate.save", {
                  content: await fileBase64(file!),
                  password,
                });
                setPassword("");
                setFile(null);
                notify("Certificado protegido en este equipo");
              })
            }
          >
            Guardar de forma segura
          </Button>
          {config.fiscal.certificate_info && (
            <Button
              onClick={() =>
                run(async () => {
                  await api("certificate.delete");
                  notify("Certificado retirado");
                })
              }
            >
              Retirar certificado
            </Button>
          )}
        </div>
        <p className="small subtle">
          Solo se guarda persistentemente en Windows. No env&iacute;es este
          archivo ni su contrase&ntilde;a por chat. No se incluye en las copias
          de seguridad.
        </p>
      </section>
      <section className="panel padded">
        <h3>
          {config.fiscal.mode === "production"
            ? "Comprobaciones y envío fiscal"
            : "Comprobaciones y envío de prueba"}
        </h3>
        <p>
          Los esquemas oficiales revisados están incluidos y se validan sin
          Internet. Puedes contrastar sus hashes con los publicados por AEAT; un
          cambio exige revisar y actualizar el programa.
        </p>
        <div className="actions">
          <Button
            busy={busy}
            icon="download"
            onClick={() =>
              run(async () => {
                const r = await api("fiscal.specs");
                notify("Esquemas descargados: " + r.downloaded.length);
              })
            }
          >
            Obtener esquemas AEAT
          </Button>
          <Button
            busy={busy}
            icon="shield"
            onClick={() =>
              run(async () => {
                const r = await api("fiscal.check");
                if (!r.ok)
                  throw new Error("La comprobaci\u00f3n detecta incidencias.");
                notify("Cadena local comprobada: " + r.checked + " registros");
              })
            }
          >
            Comprobar cadena
          </Button>
          <Button
            busy={busy}
            tone="primary"
            onClick={() =>
              run(async () => {
                const r = await api("fiscal.send");
                notify(
                  r.reason === "waiting"
                    ? "AEAT exige esperar hasta " +
                        new Date(r.next_attempt).toLocaleString("es-ES", {
                          timeZone: "Europe/Madrid",
                        })
                    : r.status === "idle"
                      ? "No hay registros externos pendientes"
                      : "Resultado del procesamiento: " +
                        r.status +
                        (r.last_error ? ". " + r.last_error : ""),
                );
              })
            }
          >
            {config.fiscal.mode === "production"
              ? "Procesar envío fiscal"
              : "Procesar envío de prueba"}
          </Button>
        </div>
      </section>
      {error && <Notice tone="error">{error}</Notice>}
      <section className="panel">
        <div className="section-head">
          <h3>Registros y respuestas</h3>
          <Button
            icon="dots"
            tone="ghost"
            onClick={() => setTick((t) => t + 1)}
          >
            Actualizar
          </Button>
        </div>
        {records.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Documento</th>
                  <th>Tipo</th>
                  <th>Entorno</th>
                  <th>Resultado</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id}>
                    <td>{r.full_number || r.document_id?.slice(0, 8)}</td>
                    <td>{r.kind}</td>
                    <td>
                      {r.environment === "local_test"
                        ? "Local"
                        : r.environment === "production"
                          ? "AEAT producción"
                          : "AEAT pruebas"}
                    </td>
                    <td>
                      <Badge value={r.status} />
                    </td>
                    <td>
                      <Button
                        tone="ghost"
                        busy={busy}
                        onClick={() =>
                          run(async () =>
                            setDetail({
                              ...r,
                              ...(await api("fiscal.details", {
                                record_id: r.id,
                              })),
                            }),
                          )
                        }
                      >
                        Detalle
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon="shield"
            title="Todav&iacute;a no hay registros"
            text="Se generan al emitir facturas. Guardar un borrador no genera un registro."
          />
        )}
      </section>
      <Presence>{detail && (
        <Modal
          title="Detalle del registro"
          onClose={() => !busy && setDetail(null)}
          wide
        >
          <dl className="details-list">
            <dt>Estado</dt>
            <dd>
              <Badge value={detail.status} />
            </dd>
            <dt>CSV de la AEAT</dt>
            <dd>{detail.csv || "No recibido"}</dd>
            <dt>&Uacute;ltimo error</dt>
            <dd>{detail.last_error || "Ninguno registrado"}</dd>
            <dt>Huella</dt>
            <dd>
              <code>{detail.hash}</code>
            </dd>
            <dt>Entorno</dt>
            <dd>{detail.environment}</dd>
            <dt>Próximo intento permitido</dt>
            <dd>{dateText(detail.next_attempt)}</dd>
            {detail.reason && (
              <>
                <dt>Motivo de corrección</dt>
                <dd>{detail.reason}</dd>
              </>
            )}
          </dl>
          {error && <Notice tone="error">{error}</Notice>}
          <div className="actions">
            {detail.environment !== "local_test" &&
              !["pending", "sending"].includes(detail.status) && (
                <Button
                  busy={busy}
                  onClick={() =>
                    run(async () => {
                      const result = await api("fiscal.reconcile", {
                        record_id: detail.id,
                      });
                      setDetail({
                        ...detail,
                        ...(await api("fiscal.details", {
                          record_id: detail.id,
                        })),
                      });
                      notify("Resultado de consulta: " + result.status);
                    })
                  }
                >
                  Consultar resultado en AEAT
                </Button>
              )}
            {[
              "local_only",
              "accepted",
              "accepted_with_errors",
              "rejected",
              "invalid_local",
            ].includes(detail.status) && (
              <Button busy={busy} onClick={() => setCorrecting(true)}>
                Subsanar registro
              </Button>
            )}
          </div>
          {(detail.attempt_history?.length > 0 ||
            detail.reconciliations?.length > 0) && (
            <section>
              <h3>Intentos y consultas conservados</h3>
              {[
                ...(detail.attempt_history || []),
                ...(detail.reconciliations || []),
              ].map((attempt: Row) => (
                <details key={attempt.id}>
                  <summary>
                    {dateText(attempt.created_at)} ·{" "}
                    {attempt.status || attempt.result || "Consulta"}
                  </summary>
                  <pre className="fiscal-response">
                    {attempt.response || JSON.stringify(attempt, null, 2)}
                  </pre>
                </details>
              ))}
            </section>
          )}
          {detail.corrections?.length > 0 && (
            <section>
              <h3>Correcciones posteriores</h3>
              {detail.corrections.map((correction: Row) => (
                <p key={correction.id}>
                  <Button
                    tone="ghost"
                    onClick={() =>
                      run(async () =>
                        setDetail(
                          await api("fiscal.details", {
                            record_id: correction.id,
                          }),
                        ),
                      )
                    }
                  >
                    {dateText(correction.created_at)} · {correction.reason}
                  </Button>
                </p>
              ))}
            </section>
          )}
          <Button
            icon="download"
            onClick={() =>
              run(async () =>
                saveExport(
                  await api("fiscal.export", { record_id: detail.id }),
                ),
              )
            }
          >
            Guardar XML conservado
          </Button>
        </Modal>
      )}</Presence>
      <Presence>{correcting && detail && (
        <CorrectionForm
          record={detail}
          onClose={() => setCorrecting(false)}
          onSaved={(record) => {
            setCorrecting(false);
            setDetail(record);
            setTick((t) => t + 1);
            notify("Subsanación conservada; consulta su estado en el registro");
          }}
        />
      )}</Presence>
    </>
  );
}
