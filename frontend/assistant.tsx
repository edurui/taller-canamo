import { Presence, useClosing } from "./overlays.js";
import { Textarea } from "./controls.js";
import * as React from "react";
import {
  api,
  Row,
  useState,
  useEffect,
  useRef,
  useLoad,
  Button,
  Field,
  Input,
  Modal,
  Notice,
  Loading,
  Empty,
  Pager,
  fileBase64,
  dateText,
  money,
} from "./core.js";

type Suggestion = {
  text: string;
  provider: string;
  warning?: string;
  source?: Row;
};
type Candidate = {
  field: string;
  value: string;
  confidence?: number;
  valid_format?: boolean;
  source_text: string;
};
type Extraction = Suggestion & { candidates: Candidate[]; lines: Row[] };
type TargetField = { key: string; label: string };

async function assistanceTask<T>(
  operation: string,
  params: Row,
  signal: AbortSignal,
): Promise<T> {
  signal.throwIfAborted();
  const job = await api("assistant.start", {
    operation,
    params,
    idempotency_key: crypto.randomUUID(),
  });
  const cancel = () => {
    void api("assistant.cancel", { identifier: job.id }).catch(() => {});
  };
  signal.addEventListener("abort", cancel, { once: true });
  if (signal.aborted) {
    cancel();
    signal.throwIfAborted();
  }
  try {
    for (;;) {
      signal.throwIfAborted();
      const state = await api("assistant.job_status", { identifier: job.id });
      signal.throwIfAborted();
      if (state.status === "completed") return state.result as T;
      if (state.status === "failed")
        throw new Error(
          state.error?.message || "No se pudo preparar la propuesta.",
        );
      if (state.status === "cancelled")
        throw new DOMException("Propuesta descartada", "AbortError");
      await new Promise<void>((resolve, reject) => {
        const aborted = () => {
          clearTimeout(timer);
          reject(new DOMException("Propuesta descartada", "AbortError"));
        };
        const timer = setTimeout(() => {
          signal.removeEventListener("abort", aborted);
          resolve();
        }, 250);
        signal.addEventListener("abort", aborted, { once: true });
        if (signal.aborted) aborted();
      });
    }
  } finally {
    signal.removeEventListener("abort", cancel);
  }
}

function useAssistanceTask() {
  const active = useRef<AbortController | null>(null);
  const cancel = () => active.current?.abort();
  const closing = useClosing();
  React.useLayoutEffect(() => { if (closing) cancel(); return cancel; }, [closing]);
  return {
    cancel,
    run: async <T,>(operation: string, params: Row): Promise<T> => {
      cancel();
      const controller = new AbortController();
      active.current = controller;
      try {
        return await assistanceTask<T>(operation, params, controller.signal);
      } finally {
        if (active.current === controller) active.current = null;
      }
    },
  };
}

function waveFile(chunks: Int16Array[], rate: number) {
  const count = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const bytes = new ArrayBuffer(44 + count * 2),
    view = new DataView(bytes);
  const word = (offset: number, text: string) =>
    [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  word(0, "RIFF");
  view.setUint32(4, 36 + count * 2, true);
  word(8, "WAVE");
  word(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  word(36, "data");
  view.setUint32(40, count * 2, true);
  let offset = 44;
  for (const chunk of chunks)
    for (const sample of chunk) {
      view.setInt16(offset, sample, true);
      offset += 2;
    }
  return new File([bytes], "dictado.wav", { type: "audio/wav" });
}

function Dictation({
  onApply,
  onClose,
}: {
  onApply: (text: string) => void;
  onClose: () => void;
}) {
  const [recording, setRecording] = useState(false),
    [busy, setBusy] = useState(false),
    [seconds, setSeconds] = useState(0);
  const [error, setError] = useState(""),
    [result, setResult] = useState<Suggestion | null>(null),
    [text, setText] = useState("");
  const session = useRef<{
    stream: MediaStream;
    context: AudioContext;
    source: MediaStreamAudioSourceNode;
    node: AudioWorkletNode;
    chunks: Int16Array[];
  } | null>(null);
  const alive = useRef(true),
    generation = useRef(0);
  const task = useAssistanceTask();
  const closing = useClosing();
  function release() {
    const current = session.current;
    session.current = null;
    if (current) {
      current.stream.getTracks().forEach((track) => track.stop());
      current.node.port.onmessage = null;
      current.node.disconnect();
      current.source.disconnect();
      void current.context.close().catch(() => {});
    }
    return current;
  }
  React.useLayoutEffect(() => {
    alive.current = !closing;
    return () => {
      alive.current = false;
      generation.current++;
      release();
    };
  }, [closing]);
  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(
      () => setSeconds((value) => value + 1),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [recording]);
  useEffect(() => {
    if (recording && seconds >= 120) void stop();
  }, [seconds, recording]);
  async function transcribe(file: File) {
    setError("");
    setBusy(true);
    setResult(null);
    setText("");
    try {
      if (file.size > 16_000_000) throw new Error("El audio supera 16 MB.");
      const answer = await task.run<Suggestion>("transcribe", {
        content: await fileBase64(file),
        name: file.name,
      });
      if (alive.current) {
        setResult(answer);
        setText(answer.text);
      }
    } catch (e) {
      if (alive.current && (e as Error).name !== "AbortError")
        setError((e as Error).message);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function start() {
    const request = ++generation.current;
    setBusy(true);
    setError("");
    setText("");
    setResult(null);
    setSeconds(0);
    let stream: MediaStream | null = null,
      context: AudioContext | null = null;
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode)
        throw new Error(
          "Este equipo no permite capturar el micrófono. Puedes seleccionar un WAV mono PCM de 16 bits.",
        );
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true },
        video: false,
      });
      if (!alive.current || request !== generation.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      context = new AudioContext({ sampleRate: 16000 });
      await context.audioWorklet.addModule(
        new URL("./audio-worklet.js", window.location.href).href,
      );
      if (!alive.current || request !== generation.current) {
        stream.getTracks().forEach((track) => track.stop());
        await context.close();
        return;
      }
      const source = context.createMediaStreamSource(stream),
        node = new AudioWorkletNode(context, "canamo-recorder");
      const current = {
        stream,
        context,
        source,
        node,
        chunks: [] as Int16Array[],
      };
      node.port.onmessage = (event: MessageEvent<Int16Array>) => {
        if (session.current === current) current.chunks.push(event.data);
      };
      session.current = current;
      source.connect(node);
      node.connect(context.destination);
      await context.resume();
      setRecording(true);
    } catch (e) {
      stream?.getTracks().forEach((track) => track.stop());
      if (context && context.state !== "closed")
        await context.close().catch(() => {});
      session.current = null;
      if (alive.current)
        setError(
          (e as Error).name === "NotAllowedError"
            ? "No se ha autorizado el micrófono. Activa su permiso o selecciona un WAV."
            : (e as Error).message,
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function stop() {
    const current = release();
    setRecording(false);
    if (current)
      await transcribe(waveFile(current.chunks, current.context.sampleRate));
  }
  return (
    <Modal title="Dictado local" onClose={onClose}>
      <p>
        Habla en castellano durante un máximo de dos minutos. El audio se
        procesa en este ordenador y no se conserva.
      </p>
      <div className="form-actions">
        {recording ? (
          <Button tone="primary" onClick={() => void stop()}>
            Terminar dictado ({seconds} s)
          </Button>
        ) : (
          <Button onClick={() => void start()} busy={busy}>
            Iniciar micrófono
          </Button>
        )}
        <Field label="O seleccionar audio WAV">
          <input
            type="file"
            accept=".wav,audio/wav"
            disabled={busy || recording}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void transcribe(file);
              event.target.value = "";
            }}
          />
        </Field>
      </div>
      {busy && <p role="status">Procesando el audio localmente…</p>}
      {error && <Notice tone="error">{error}</Notice>}
      {result && (
        <>
          <Notice>
            {result.warning ||
              "Revisa nombres, cifras y términos antes de insertar el dictado."}
          </Notice>
          <Field label="Dictado para revisar">
            <Textarea
              rows={6}
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </Field>
          <small>
            {result.provider} · {result.source?.name}
          </small>
          <div className="form-actions">
            <Button onClick={onClose}>Descartar</Button>
            <Button
              tone="primary"
              disabled={!text.trim()}
              onClick={() => {
                onApply(text);
                onClose();
              }}
            >
              Insertar dictado revisado
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}

export function TextAssistance({
  enabled,
  value,
  onApply,
}: {
  enabled: boolean;
  value: string;
  onApply: (value: string) => void;
}) {
  const [dictation, setDictation] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [proposal, setProposal] = useState<Suggestion | null>(null),
    [text, setText] = useState("");
  const original = useRef(value);
  const task = useAssistanceTask();
  if (!enabled) return null;
  return (
    <>
      <div className="row-actions">
        <Button disabled={busy} onClick={() => setDictation(true)}>
          Dictar notas
        </Button>
        <Button
          icon="sparkles"
          busy={busy}
          disabled={!value.trim()}
          onClick={async () => {
            original.current = value;
            setBusy(true);
            setError("");
            try {
              const answer = await task.run<Suggestion>("rewrite", {
                text: value,
              });
              setProposal(answer);
              setText(answer.text);
            } catch (e) {
              if ((e as Error).name !== "AbortError")
                setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Revisar redacción
        </Button>
        {busy && <Button onClick={task.cancel}>Cancelar propuesta</Button>}
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      <Presence>{dictation && (
        <Dictation
          onClose={() => setDictation(false)}
          onApply={(dictated) =>
            onApply(value + (value ? "\n" : "") + dictated)
          }
        />
      )}</Presence>
      <Presence>{proposal && (
        <Modal title="Propuesta para revisar" onClose={() => setProposal(null)}>
          <Notice>{proposal.warning}</Notice>
          <small>{proposal.provider}</small>
          <Field label="Propuesta editable">
            <Textarea
              rows={7}
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </Field>
          {value !== original.current && (
            <Notice>
              Las notas han cambiado mientras se preparaba la propuesta.
              Descártala y solicita otra para conservar los cambios.
            </Notice>
          )}
          <div className="form-actions">
            <Button onClick={() => setProposal(null)}>Descartar</Button>
            <Button
              tone="primary"
              disabled={value !== original.current || !text.trim()}
              onClick={() => {
                onApply(text);
                setProposal(null);
              }}
            >
              Usar texto revisado
            </Button>
          </div>
        </Modal>
      )}</Presence>
    </>
  );
}

export function ReadImageButton({
  enabled,
  fields,
  onApply,
}: {
  enabled: boolean;
  fields: TargetField[];
  onApply: (values: Record<string, string>) => void;
}) {
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [result, setResult] = useState<Extraction | null>(null),
    [values, setValues] = useState<Record<string, string>>({}),
    [selected, setSelected] = useState<Record<string, boolean>>({}),
    [preview, setPreview] = useState("");
  const task = useAssistanceTask();
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  if (!enabled) return null;
  return (
    <>
      <Button icon="upload" onClick={() => setOpen(true)}>
        Leer documentación
      </Button>
      <Presence>{open && (
        <Modal
          title="Leer imagen y revisar datos"
          wide
          onClose={() => {
            task.cancel();
            setOpen(false);
            setResult(null);
            setPreview("");
            setBusy(false);
          }}
        >
          <p>
            Procesamiento local de una página. Nada se guarda hasta que revises
            los campos y guardes la ficha.
          </p>
          <Field label="Imagen del documento">
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/tiff,.tif,.tiff"
              disabled={busy}
              onChange={async (event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (!file) return;
                setError("");
                setResult(null);
                setSelected({});
                setValues({});
                setBusy(true);
                setPreview("");
                try {
                  if (file.size > 16_000_000)
                    throw new Error("La imagen supera 16 MB.");
                  setPreview(URL.createObjectURL(file));
                  const answer = await task.run<Extraction>("extract", {
                    content: await fileBase64(file),
                    name: file.name,
                  });
                  setResult(answer);
                  setValues(
                    Object.fromEntries(
                      fields.map((field) => [
                        field.key,
                        field.key === "notes"
                          ? answer.text
                          : answer.candidates.find(
                              (candidate) => candidate.field === field.key,
                            )?.value || "",
                      ]),
                    ),
                  );
                } catch (e) {
                  if ((e as Error).name !== "AbortError")
                    setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            />
          </Field>
          {busy && <p role="status">Leyendo la imagen en este ordenador…</p>}
          {error && <Notice tone="error">{error}</Notice>}
          {preview && (
            <img
              src={preview}
              alt="Documento original para cotejar"
              style={{ width: "100%", maxHeight: 340, objectFit: "contain" }}
            />
          )}
          {result && (
            <>
              <Notice>{result.warning}</Notice>
              <details>
                <summary>Texto y procedencia</summary>
                <pre className="fiscal-response">
                  {result.text || "No se ha reconocido texto."}
                </pre>
                <small>
                  {result.source?.name} · SHA-256 {result.source?.sha256}
                </small>
              </details>
              <div className="form-grid">
                {fields.map((field) => {
                  const candidate = result.candidates.find(
                    (item) => item.field === field.key,
                  );
                  return (
                    <div key={field.key}>
                      <label className="check-row">
                        <input
                          type="checkbox"
                          checked={selected[field.key] || false}
                          onChange={(event) =>
                            setSelected((old) => ({
                              ...old,
                              [field.key]: event.target.checked,
                            }))
                          }
                        />
                        Incorporar {field.label.toLocaleLowerCase("es")}
                      </label>
                      <Input
                        label={field.label + " leído"}
                        value={values[field.key] || ""}
                        onChange={(event) =>
                          setValues((old) => ({
                            ...old,
                            [field.key]: event.target.value,
                          }))
                        }
                      />
                      {candidate && (
                        <small>
                          Fuente: {candidate.source_text}. Confianza del motor:{" "}
                          {Math.round((candidate.confidence || 0) * 100)} %.
                          {candidate.valid_format === false
                            ? " Formato o control no válido: corrígelo."
                            : ""}
                        </small>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="form-actions">
                <Button
                  onClick={() => {
                    setOpen(false);
                    setResult(null);
                    setPreview("");
                  }}
                >
                  Descartar
                </Button>
                <Button
                  tone="primary"
                  disabled={!Object.values(selected).some(Boolean)}
                  onClick={() => {
                    onApply(
                      Object.fromEntries(
                        Object.entries(values).filter(([key]) => selected[key]),
                      ),
                    );
                    setOpen(false);
                    setResult(null);
                    setPreview("");
                  }}
                >
                  Incorporar campos revisados
                </Button>
              </div>
            </>
          )}
        </Modal>
      )}</Presence>
    </>
  );
}

export function HistorySearch({
  customerId,
  vehicleId,
  navigate,
}: {
  customerId?: string;
  vehicleId?: string;
  navigate: (page: string, params: Row) => void;
}) {
  const [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [open, setOpen] = useState(false);
  return (
    <section className="panel padded history-search">
      <Button icon="search" onClick={() => setOpen(!open)} aria-expanded={open}>
        Consultar trabajos del historial
      </Button>
      {open && (
        <HistoryResults
          {...{ query, page, navigate, customerId, vehicleId }}
          setQuery={(value) => {
            setQuery(value);
            setPage(0);
          }}
          setPage={setPage}
        />
      )}
    </section>
  );
}
function HistoryResults({
  query,
  page,
  customerId,
  vehicleId,
  setQuery,
  setPage,
  navigate,
}: {
  query: string;
  page: number;
  customerId?: string;
  vehicleId?: string;
  setQuery: (v: string) => void;
  setPage: (v: number) => void;
  navigate: (page: string, params: Row) => void;
}) {
  const [result, loading, error] = useLoad<{
    items: Row[];
    total: number;
    notice: string;
  }>(
    "assistant.history",
    { customer_id: customerId, vehicle_id: vehicleId, query, page },
    { items: [], total: 0, notice: "" },
  );
  return (
    <>
      <Input
        label="Palabras que constan en el historial"
        value={query}
        maxLength={150}
        placeholder="Por ejemplo: aceite"
        onChange={(event) => setQuery(event.target.value)}
      />
      <p className="subtle">
        Consulta directa de las facturas conservadas. Funciona sin IA ni
        Internet y no deduce diagnósticos.
      </p>
      {error && <Notice tone="error">{error}</Notice>}
      {loading ? (
        <Loading />
      ) : !result.items.length ? (
        <Empty
          title="Sin coincidencias documentadas"
          text="Prueba con otra palabra o deja la búsqueda vacía."
        />
      ) : (
        <div className="pick-list">
          {result.items.map((item) => (
            <button
              key={item.id}
              onClick={() =>
                navigate("editor", { id: item.id, kind: "invoice" })
              }
            >
              <span>
                <strong>
                  {item.full_number} · {dateText(item.issue_date)}
                </strong>
                <small>
                  {item.payload.lines
                    .map((line: Row) => line.description)
                    .join(" · ")}
                </small>
              </span>
              <span>{money(item.total_cents)}</span>
            </button>
          ))}
        </div>
      )}
      <Pager page={page} total={result.total} size={30} onChange={setPage} />
    </>
  );
}

export function MessageButton({
  identifier,
  purpose,
}: {
  identifier: string;
  purpose: "invoice" | "quote" | "vehicle_ready";
}) {
  const [draft, setDraft] = useState<Row | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [copied, setCopied] = useState(false);
  return (
    <>
      <Button
        busy={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          setCopied(false);
          try {
            setDraft(await api("messages.prepare", { identifier, purpose }));
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Preparar mensaje
      </Button>
      {error && !draft && <Notice tone="error">{error}</Notice>}
      <Presence>{draft && (
        <Modal title="Mensaje para revisar" onClose={() => setDraft(null)}>
          <Notice>
            El mensaje no se ha enviado. Revisa el destinatario y el texto antes
            de compartirlo.
          </Notice>
          <Input
            label="Teléfono del destinatario"
            value={draft.phone}
            onChange={(event) =>
              setDraft((old) => ({ ...old, phone: event.target.value }))
            }
          />
          <Field label="Texto del mensaje">
            <Textarea
              rows={6}
              value={draft.text}
              onChange={(event) => {
                setDraft((old) => ({ ...old, text: event.target.value }));
                setCopied(false);
              }}
            />
          </Field>
          {error && <Notice tone="error">{error}</Notice>}
          {copied && <p role="status">Texto copiado. Aún no se ha enviado.</p>}
          <div className="form-actions">
            <Button
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(draft.text);
                  setCopied(true);
                } catch {
                  setError(
                    "No se pudo acceder al portapapeles. Selecciona y copia el texto manualmente.",
                  );
                }
              }}
            >
              Copiar texto
            </Button>
            <Button
              onClick={async () => {
                let phone = String(draft.phone).replace(/\D/g, "");
                if (phone.length === 9) phone = "34" + phone;
                if (!/^\d{9,15}$/.test(phone)) {
                  setError(
                    "Revisa el teléfono, incluido el prefijo internacional.",
                  );
                  return;
                }
                const url =
                  "https://wa.me/" +
                  phone +
                  "?text=" +
                  encodeURIComponent(draft.text);
                try {
                  if (window.__TAURI__)
                    await window.__TAURI__.core.invoke("open_external", {
                      url,
                    });
                  else window.open(url, "_blank", "noopener,noreferrer");
                } catch (e) {
                  setError(
                    typeof e === "string"
                      ? e
                      : "No se ha podido abrir WhatsApp. Puedes copiar el texto.",
                  );
                }
              }}
            >
              Abrir WhatsApp con el borrador
            </Button>
          </div>
        </Modal>
      )}</Presence>
    </>
  );
}

export function AssistanceStatus() {
  const [tick, setTick] = useState(0),
    [value, loading, error] = useLoad<Row>(
      "assistant.status",
      { check_model: tick > 0 },
      {},
      tick,
    );
  return (
    <>
      <h3>Motores locales</h3>
      {loading ? (
        <Loading />
      ) : (
        <p>
          Dictado español:{" "}
          {value.voice_available ? "modelo incluido" : "falta el paquete"}.
          Lectura de imágenes:{" "}
          {value.ocr_available ? "modelos incluidos" : "faltan modelos"}.
        </p>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      <p>
        Sin coste por uso. Voz y OCR funcionan sin conexión y no descargan
        modelos al utilizarse.
      </p>
      <Button onClick={() => setTick((v) => v + 1)}>
        Comprobar asistencia
      </Button>
      {value.model && value.model_available !== null && (
        <Notice tone={value.model_available ? "success" : "warning"}>
          {value.model_available
            ? "Ollama local reconoce el modelo configurado."
            : value.model_error ||
              "El modelo no está instalado en Ollama local."}
        </Notice>
      )}
    </>
  );
}
