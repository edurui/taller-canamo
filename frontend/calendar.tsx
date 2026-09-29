import { Presence } from "./overlays.js";
import { Select, Textarea, TextInput } from "./controls.js";
import * as React from "react";
import {
  Row,
  api,
  useState,
  useEffect,
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
  CustomerSearch,
  saveExport,
} from "./core.js";
const types: Row = {
  appointment: "Cita de taller",
  pickup: "Entrega de veh\u00edculo",
  itv: "ITV",
  maintenance: "Mantenimiento",
  task: "Tarea",
  personal: "Personal",
};
const days = ["Lun", "Mar", "Mi\u00e9", "Jue", "Vie", "S\u00e1b", "Dom"];
const localDate = (value: Date) => value.toISOString().slice(0, 10);
const localDateTime = (value: Date) => value.toISOString().slice(0, 16);
const wallCarrier = (value: string) =>
  new Date((value.length === 10 ? value + "T00:00:00" : value) + "Z");
const addDays = (d: Date, n: number) => {
  const v = new Date(d);
  v.setUTCDate(v.getUTCDate() + n);
  return v;
};
const startDay = (d: Date) =>
  new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
const startWeek = (d: Date) => addDays(startDay(d), -((d.getUTCDay() + 6) % 7));
const formatter = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "Europe/Madrid",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});
const wallText = (instant: string) =>
  formatter.format(new Date(instant)).replace(" ", "T");
export function wallDate(instant: string) {
  return wallCarrier(wallText(instant));
}
export function madridCandidates(wall: string): string[] {
  const normalized =
    wall.length === 10
      ? wall + "T00:00:00"
      : wall.length === 16
        ? wall + ":00"
        : wall;
  const target = wallCarrier(normalized);
  if (
    !Number.isFinite(target.getTime()) ||
    target.toISOString().slice(0, 19) !== normalized
  )
    return [];
  const desired = target.getTime();
  const choices = new Set<string>();
  for (const sample of [desired - 86400000, desired, desired + 86400000]) {
    const offset =
      wallCarrier(wallText(new Date(sample).toISOString())).getTime() - sample;
    const candidate = new Date(desired - offset).toISOString();
    if (wallText(candidate) === normalized) choices.add(candidate);
  }
  return [...choices].sort();
}
export function madridISO(wall: string, fold?: number) {
  const choices = madridCandidates(wall);
  if (!choices.length)
    throw new Error(
      "Esa hora no existe en Madrid por el cambio de horario. Elige otra hora.",
    );
  if (choices.length === 2 && fold !== 0 && fold !== 1)
    throw new Error(
      "Esa hora ocurre dos veces en Madrid. Elige la primera o la segunda.",
    );
  return choices[choices.length === 2 ? fold! : 0];
}
const dayISO = (d: Date) => madridISO(localDate(d));
const time = (d: Date) =>
  d.toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
function instantLabel(instant: string) {
  const wall = wallText(instant),
    choices = madridCandidates(wall);
  const index = choices.findIndex(
    (candidate) =>
      new Date(candidate).getTime() === new Date(instant).getTime(),
  );
  return (
    time(wallDate(instant)) +
    (choices.length === 2 ? (index === 0 ? " (primera)" : " (segunda)") : "")
  );
}
const visualDuration = (event: Row) =>
  Math.max(
    45,
    (wallDate(event.occurrence_end).getTime() -
      wallDate(event.occurrence_start).getTime()) /
      60000,
    (new Date(event.occurrence_end).getTime() -
      new Date(event.occurrence_start).getTime()) /
      60000,
  );
function calendarRange(focus: Date, view: string) {
  if (view === "month") {
    const start = startWeek(
      new Date(Date.UTC(focus.getUTCFullYear(), focus.getUTCMonth(), 1)),
    );
    return { start, end: addDays(start, 42) };
  }
  const start = view === "week" ? startWeek(focus) : startDay(focus);
  return { start, end: addDays(start, view === "week" ? 7 : 1) };
}
function overlaps(event: Row, day: Date) {
  return (
    wallDate(event.occurrence_start) < addDays(day, 1) &&
    wallDate(event.occurrence_end) > day
  );
}
function isMulti(event: Row) {
  const start = wallDate(event.occurrence_start),
    end = wallDate(event.occurrence_end);
  return (
    event.all_day || localDate(start) !== localDate(new Date(end.getTime() - 1))
  );
}
function EventForm({ event, config, onClose, onSaved }: Row) {
  const recurring = !!event.id && event.recurrence?.freq !== "none";
  const start = event.id
    ? wallDate(event.occurrence_start || event.start)
    : event.date || wallDate(new Date().toISOString());
  if (!event.id && start.getUTCHours() === 0) start.setUTCHours(9);
  function formValues(source: Row): Row {
    const first = source.id
      ? wallDate(source.occurrence_start || source.start)
      : start;
    const finish = source.id
      ? wallDate(source.occurrence_end || source.end)
      : new Date(first.getTime() + 3600000);
    const value: Row = {
      title: "",
      kind: "appointment",
      all_day: false,
      location: "",
      notes: "",
      customer_id: "",
      vehicle_id: "",
      completed: false,
      recurrence: { freq: "none", dst_policy: "skip" },
      reminders: [config.agenda.reminder_minutes],
      ...source,
      start: source.proposed_start || localDateTime(first),
      end:
        source.proposed_end ||
        localDateTime(source.all_day ? addDays(finish, -1) : finish),
    };
    for (const name of ["start", "end"]) {
      const instant = source["occurrence_" + name] || source[name];
      const choices = madridCandidates(value[name]);
      value[name + "_fold"] =
        !source["proposed_" + name] && choices.length === 2
          ? choices.findIndex(
              (candidate) =>
                new Date(candidate).getTime() === new Date(instant).getTime(),
            )
          : "";
    }
    return value;
  }
  const [v, setV] = useState<Row>(() => formValues(event));
  const [scope, setScope] = useState(recurring ? "occurrence" : "series"),
    [series, setSeries] = useState<Row | null>(null),
    [resetExceptions, setResetExceptions] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [remove, setRemove] = useState(false),
    [who, setWho] = useState(event.customer_name || ""),
    [custom, setCustom] = useState("");
  useEffect(() => {
    if (!recurring) return;
    let active = true;
    api<Row>("agenda.get", { identifier: event.id })
      .then((row) => {
        if (active) setSeries(row);
      })
      .catch((err: Error) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [event.id, recurring]);
  const set = (key: string, x: any) => setV((old) => ({ ...old, [key]: x }));
  function setWall(key: string, value: string) {
    setV((old) => ({ ...old, [key]: value, [key + "_fold"]: "" }));
  }
  const foldField = (name: string, label: string) =>
    !v.all_day &&
    madridCandidates(v[name]).length === 2 && (
      <Field label={label + ": hora repetida"}>
        <Select
          required
          value={v[name + "_fold"] ?? ""}
          onChange={(e) =>
            set(
              name + "_fold",
              e.target.value === "" ? "" : Number(e.target.value),
            )
          }
        >
          <option value="">Elige qué hora</option>
          <option value="0">Primera vez · horario de verano (UTC+02)</option>
          <option value="1">Segunda vez · horario de invierno (UTC+01)</option>
        </Select>
      </Field>
    );
  function changeAllDay(checked: boolean) {
    setV((old) => {
      const s = wallCarrier(old.start),
        e = wallCarrier(old.end);
      if (checked)
        return {
          ...old,
          all_day: true,
          start: localDate(s) + "T00:00",
          end: localDate(e) + "T00:00",
        };
      s.setUTCHours(9, 0);
      e.setUTCHours(10, 0);
      return {
        ...old,
        all_day: false,
        start: localDateTime(s),
        end: localDateTime(e),
      };
    });
  }
  return (
    <Modal
      title={event.id ? "Editar evento" : "Nuevo evento"}
      subtitle="Hora de Espa&ntilde;a peninsular &middot; Europe/Madrid"
      onClose={() => !busy && onClose()}
      wide
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          setBusy(true);
          try {
            const endWall = v.all_day
              ? localDate(addDays(wallCarrier(v.end), 1))
              : v.end;
            const data = {
              ...v,
              scope,
              occurrence_key: event.occurrence_key,
              reset_exceptions: resetExceptions,
              start_local: v.all_day ? v.start.slice(0, 10) : v.start,
              end_local: endWall,
              start_date: v.all_day ? v.start.slice(0, 10) : "",
              end_date: v.all_day ? endWall.slice(0, 10) : "",
              start_fold: v.start_fold === "" ? null : v.start_fold,
              end_fold: v.end_fold === "" ? null : v.end_fold,
            };
            onSaved(await api("agenda.save", { data }));
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {recurring && (
          <Field label="Aplicar cambios a">
            <Select
              value={scope}
              disabled={!series || busy}
              onChange={(e) => {
                const next = e.target.value;
                setScope(next);
                setV(formValues(next === "series" ? series! : event));
                setResetExceptions(false);
              }}
            >
              <option value="occurrence">Esta repetición</option>
              <option value="series">Toda la serie</option>
            </Select>
          </Field>
        )}
        {event.cancelled && (
          <Notice>
            Esta repetición está cancelada. Puedes restablecerla o guardar
            cambios para recuperarla.
            <Button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  onSaved(
                    await api("agenda.restore_occurrence", {
                      identifier: event.id,
                      occurrence_key: event.occurrence_key,
                      version: event.version,
                    }),
                  );
                } catch (err: any) {
                  setError(err.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Restablecer repetición
            </Button>
          </Notice>
        )}
        {event.proposed_start && (
          <Notice>
            Revisa las fechas propuestas y guarda para confirmar el movimiento.
          </Notice>
        )}
        <Input
          label="T&iacute;tulo"
          value={v.title}
          required
          autoFocus
          maxLength={150}
          placeholder="Por ejemplo, revisi&oacute;n del Seat Le&oacute;n"
          onChange={(e) => set("title", e.target.value)}
        />
        <div className="form-grid">
          <Field label="Tipo de evento">
            <Select
              value={v.kind}
              onChange={(e) => set("kind", e.target.value)}
            >
              {Object.entries(types).map(([k, l]) => (
                <option value={k} key={k}>
                  {String(l)}
                </option>
              ))}
            </Select>
          </Field>
          <div className="align-end">
            <Toggle checked={v.all_day} onChange={changeAllDay}>
              Todo el d&iacute;a
            </Toggle>
          </div>
          <Input
            label={v.all_day ? "Primer día" : "Comienza"}
            type={v.all_day ? "date" : "datetime-local"}
            value={v.all_day ? v.start.slice(0, 10) : v.start}
            required
            onChange={(e) => {
              const x = e.target.value + (v.all_day ? "T00:00" : "");
              setWall("start", x);
              if (x > v.end)
                setWall(
                  "end",
                  v.all_day
                    ? x
                    : localDateTime(
                        new Date(wallCarrier(x).getTime() + 3600000),
                      ),
                );
            }}
          />
          <Input
            label={v.all_day ? "Último día (incluido)" : "Termina"}
            type={v.all_day ? "date" : "datetime-local"}
            value={v.all_day ? v.end.slice(0, 10) : v.end}
            required
            onChange={(e) =>
              setWall("end", e.target.value + (v.all_day ? "T00:00" : ""))
            }
          />
          {foldField("start", "Comienza")}
          {foldField("end", "Termina")}
          <Field label="Repetir">
            <Select
              value={v.recurrence.freq}
              disabled={recurring && scope === "occurrence"}
              onChange={(e) =>
                set("recurrence", {
                  freq: e.target.value,
                  dst_policy: v.recurrence.dst_policy || "skip",
                  until: v.recurrence.until || localDate(addDays(start, 90)),
                })
              }
            >
              <option value="none">No se repite</option>
              <option value="daily">Cada d&iacute;a</option>
              <option value="weekly">Cada semana</option>
              <option value="monthly">Cada mes</option>
            </Select>
          </Field>
          {v.recurrence.freq !== "none" && (
            <Input
              label="Repetir hasta"
              disabled={recurring && scope === "occurrence"}
              type="date"
              value={v.recurrence.until || ""}
              onChange={(e) =>
                set("recurrence", { ...v.recurrence, until: e.target.value })
              }
              required
            />
          )}
        </div>
        {v.recurrence.freq !== "none" && (
          <>
            <Field label="Si una hora se repite en octubre">
              <Select
                value={v.recurrence.dst_policy || "skip"}
                disabled={recurring && scope === "occurrence"}
                onChange={(e) =>
                  set("recurrence", {
                    ...v.recurrence,
                    dst_policy: e.target.value,
                  })
                }
              >
                <option value="skip">Omitir esa repetición</option>
                <option value="earlier">Usar la primera hora (verano)</option>
                <option value="later">Usar la segunda hora (invierno)</option>
              </Select>
            </Field>
            <p className="small subtle">
              Las horas que no existen en marzo se omiten. Se conserva la hora
              de inicio de Madrid y la duración real del evento.
            </p>
          </>
        )}
        {recurring && (
          <Notice>
            {scope === "occurrence"
              ? "Solo cambiará esta repetición; el resto de la serie conserva sus fechas."
              : "Los cambios se aplican a la serie. Las repeticiones modificadas conservan sus datos mientras no reinicies las excepciones."}
          </Notice>
        )}
        {scope === "series" && !!series?.exceptions?.length && (
          <>
            <Toggle checked={resetExceptions} onChange={setResetExceptions}>
              Reiniciar las repeticiones modificadas o eliminadas al cambiar las
              fechas o la repetición
            </Toggle>
            <details className="form-section">
              <summary>
                Repeticiones modificadas o eliminadas (
                {series.exceptions.length})
              </summary>
              {series.exceptions.map((item: Row) => (
                <div className="linked-item" key={item.occurrence_key}>
                  <span>
                    {wallDate(item.occurrence_key).toLocaleString("es-ES", {
                      timeZone: "UTC",
                    })}{" "}
                    · {item.cancelled ? "Eliminada" : "Modificada"}
                  </span>
                  <Button
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      setError("");
                      try {
                        onSaved(
                          await api("agenda.restore_occurrence", {
                            identifier: event.id,
                            occurrence_key: item.occurrence_key,
                            version: series.version,
                          }),
                        );
                      } catch (err: any) {
                        setError(err.message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Restablecer repetición
                  </Button>
                </div>
              ))}
            </details>
          </>
        )}
        {v.recurrence.freq === "monthly" && (
          <p className="small subtle">
            Si el mes no tiene ese d&iacute;a (por ejemplo, el 31), se omite esa
            repetici&oacute;n.
          </p>
        )}
        <div className="form-section">
          <h3>Avisos</h3>
          <p className="small subtle">
            Elige hasta cinco. Los eventos de todo el d&iacute;a avisan a partir
            de las 09:00.
          </p>
          <div className="reminder-choices">
            {[
              [0, "A la hora"],
              [5, "5 min antes"],
              [15, "15 min antes"],
              [30, "30 min antes"],
              [60, "1 hora antes"],
              [1440, "1 d\u00eda antes"],
            ].map(([n, label]) => (
              <label
                key={String(n)}
                className={v.reminders.includes(n) ? "active" : ""}
              >
                <input
                  type="checkbox"
                  checked={v.reminders.includes(n)}
                  onChange={(e) =>
                    set(
                      "reminders",
                      e.target.checked
                        ? [...v.reminders, n]
                        : v.reminders.filter((x: number) => x !== n),
                    )
                  }
                />
                {label}
              </label>
            ))}
          </div>
          <div className="inline-form">
            <TextInput
              aria-label="Minutos de aviso personalizado"
              type="number"
              min="0"
              max="10080"
              placeholder="Otros minutos"
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
            />
            <Button
              onClick={() => {
                const n = Number(custom);
                if (
                  custom &&
                  Number.isInteger(n) &&
                  n >= 0 &&
                  n <= 10080 &&
                  !v.reminders.includes(n)
                ) {
                  set("reminders", [...v.reminders, n]);
                  setCustom("");
                }
              }}
            >
              A&ntilde;adir aviso
            </Button>
          </div>
          {v.reminders
            .filter((n: number) => ![0, 5, 15, 30, 60, 1440].includes(n))
            .map((n: number) => (
              <Button
                key={n}
                tone="ghost"
                icon="x"
                onClick={() =>
                  set(
                    "reminders",
                    v.reminders.filter((x: number) => x !== n),
                  )
                }
              >
                {n} min antes
              </Button>
            ))}
          {!v.reminders.length && (
            <p className="small">Sin alertas para este evento.</p>
          )}
        </div>
        <details className="form-section">
          <summary>Cliente, lugar y notas (opcional)</summary>
          <CustomerSearch
            placeholder="Vincular cliente o matr&iacute;cula"
            onSelect={(c) => {
              set("customer_id", c.customer_id);
              set("vehicle_id", c.vehicle_id || "");
              setWho(c.name + (c.plate ? " \u00b7 " + c.plate : ""));
            }}
          />
          {who && (
            <div className="linked-item">
              <Icon name="users" />
              <span>{who}</span>
              <Button
                tone="ghost icon-only"
                icon="x"
                aria-label="Quitar cliente del evento"
                onClick={() => {
                  set("customer_id", "");
                  set("vehicle_id", "");
                  setWho("");
                }}
              />
            </div>
          )}
          <Input
            label="Lugar"
            value={v.location}
            onChange={(e) => set("location", e.target.value)}
          />
          <Field label="Notas">
            <Textarea
              rows={3}
              value={v.notes}
              onChange={(e) => set("notes", e.target.value)}
            />
          </Field>
        </details>
        {event.id && (
          <Toggle
            checked={v.completed}
            onChange={(x: boolean) => set("completed", x)}
            hint="No generar nuevos avisos de este evento o serie."
          >
            Marcar como terminado
          </Toggle>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <div className="form-actions">
          {event.id && (
            <Button
              icon="trash"
              tone="danger-ghost push-left"
              onClick={() => setRemove(true)}
            >
              Eliminar
            </Button>
          )}
          <Button onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button type="submit" tone="primary" icon="check" busy={busy}>
            Guardar evento
          </Button>
        </div>
      </form>
      <Presence>{remove && (
        <Confirm
          title="Eliminar evento"
          text={
            scope === "occurrence"
              ? "Se eliminará solo esta repetición y sus avisos. Puedes restablecerla desde la serie."
              : v.recurrence.freq !== "none"
                ? "Se eliminará toda la serie, sus excepciones y sus avisos."
                : "Se eliminará el evento y sus avisos pendientes."
          }
          confirm="Eliminar"
          danger
          onClose={() => setRemove(false)}
          onConfirm={async () => {
            await api("agenda.delete", {
              identifier: v.id,
              scope,
              occurrence_key: event.occurrence_key,
              version: v.version,
            });
            onSaved(null);
          }}
        />
      )}</Presence>
    </Modal>
  );
}
function EventPill({ event, onClick, compact = false }: Row) {
  const start = wallDate(event.occurrence_start);
  return (
    <button
      className={
        "event-pill type-" +
        event.kind +
        (event.completed ? " completed" : "") +
        (event.cancelled ? " cancelled" : "")
      }
      onClick={onClick}
      title={event.title + (event.plate ? " \u00b7 " + event.plate : "")}
    >
      <i />
      <span>
        {!event.all_day && !isMulti(event) && (
          <b>{instantLabel(event.occurrence_start)} </b>
        )}
        {event.cancelled ? "Cancelada · " : ""}
        {event.title}
      </span>
      {!compact && event.reminders?.length > 0 && (
        <Icon name="bell" size={12} />
      )}
    </button>
  );
}
type CalendarViewProps = {
  focus: Date;
  events: Row[];
  onEvent: (event: Row) => void;
  onDay: (day: Date) => void;
};
function MonthView({
  focus,
  events,
  onEvent,
  onDay,
  onMore,
}: CalendarViewProps & { onMore: (day: Date) => void }) {
  const range = calendarRange(focus, "month");
  return (
    <div className="month-calendar">
      <div className="weekdays">
        {days.map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
      <div className="month-grid">
        {Array.from({ length: 42 }, (_, i) => {
          const day = addDays(range.start, i),
            dayEvents = events.filter((e: Row) => overlaps(e, day)),
            today =
              localDate(wallDate(new Date().toISOString())) === localDate(day);
          return (
            <div
              key={i}
              className={
                "month-cell " +
                (day.getUTCMonth() !== focus.getUTCMonth() ? "outside " : "") +
                (today ? "today" : "")
              }
            >
              <div className="cell-top">
                <button
                  aria-label={"Ver d\u00eda " + localDate(day)}
                  className="day-number"
                  onClick={() => onMore(day)}
                >
                  {day.getUTCDate()}
                </button>
                <button
                  className="add-day"
                  aria-label={"A\u00f1adir evento el " + localDate(day)}
                  onClick={() => onDay(day)}
                >
                  <Icon name="plus" size={14} />
                </button>
              </div>
              <div className="cell-events">
                {dayEvents.slice(0, 3).map((e: Row) => (
                  <EventPill
                    key={e.occurrence_id}
                    event={e}
                    compact
                    onClick={() => onEvent(e)}
                  />
                ))}
                {dayEvents.length > 3 && (
                  <button className="more-events" onClick={() => onMore(day)}>
                    +{dayEvents.length - 3} m&aacute;s
                  </button>
                )}
              </div>
              <button
                tabIndex={-1}
                aria-label={"Nuevo evento " + localDate(day)}
                className="cell-empty-area"
                onClick={() => onDay(day)}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
function TimeEvent({
  event,
  first,
  dayIndex,
  dayCount,
  onEvent,
}: {
  event: Row;
  first: number;
  dayIndex: number;
  dayCount: number;
  onEvent: (event: Row) => void;
}) {
  const element = React.useRef<HTMLDivElement>(null);
  const drag = React.useRef<{
    x: number;
    y: number;
    width: number;
    mode: "move" | "resize";
    dx: number;
    minutes: number;
    changed: boolean;
    height: string;
  } | null>(null);
  const ignoreClick = React.useRef(false);
  const start = wallDate(event.occurrence_start),
    end = wallDate(event.occurrence_end);
  const minutes = (start.getUTCHours() - first) * 60 + start.getUTCMinutes();
  const duration =
    (new Date(event.occurrence_end).getTime() -
      new Date(event.occurrence_start).getTime()) /
    60000;
  const drawnDuration = visualDuration(event);
  function begin(
    e: React.PointerEvent<HTMLButtonElement>,
    mode: "move" | "resize",
  ) {
    if (e.button !== 0 || !element.current) return;
    const width = element.current.parentElement!.getBoundingClientRect().width;
    drag.current = {
      x: e.clientX,
      y: e.clientY,
      width,
      mode,
      dx: 0,
      minutes: 0,
      changed: false,
      height: element.current.style.height,
    };
    ignoreClick.current = false;
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function move(e: React.PointerEvent<HTMLButtonElement>) {
    const current = drag.current,
      node = element.current;
    if (!current || !node) return;
    const dy = e.clientY - current.y;
    const dx = e.clientX - current.x;
    if (Math.abs(dy) + Math.abs(dx) < 5 && !current.changed) return;
    current.changed = true;
    current.dx =
      current.mode === "move"
        ? Math.max(
            -dayIndex,
            Math.min(dayCount - dayIndex - 1, Math.round(dx / current.width)),
          )
        : 0;
    current.minutes = Math.round(dy / 16) * 15;
    if (current.mode === "resize") {
      current.minutes = Math.max(15 - duration, current.minutes);
      node.style.height =
        Math.max(42, ((duration + current.minutes) / 60) * 64 - 3) + "px";
    } else {
      const startMinute = start.getUTCHours() * 60 + start.getUTCMinutes();
      current.minutes = Math.max(
        -startMinute,
        Math.min(1425 - startMinute, current.minutes),
      );
      node.style.transform = `translate(${current.dx * current.width}px, ${(current.minutes / 60) * 64}px)`;
    }
    node.style.zIndex = "8";
    node.style.opacity = "0.8";
  }
  function finish(e: React.PointerEvent<HTMLButtonElement>, cancelled = false) {
    const current = drag.current,
      node = element.current;
    if (!current || !node) return;
    drag.current = null;
    node.style.transform = "";
    node.style.zIndex = "";
    node.style.opacity = "";
    node.style.height = current.height;
    if (e.currentTarget.hasPointerCapture(e.pointerId))
      e.currentTarget.releasePointerCapture(e.pointerId);
    ignoreClick.current = current.changed;
    if (cancelled || !current.changed || (!current.dx && !current.minutes))
      return;
    const delta = current.dx * 86400000 + current.minutes * 60000;
    const proposedStart = localDateTime(
      new Date(start.getTime() + (current.mode === "move" ? delta : 0)),
    );
    const choices = madridCandidates(proposedStart);
    const proposedEnd =
      current.mode === "move" && choices.length === 1
        ? localDateTime(
            wallDate(
              new Date(
                new Date(choices[0]).getTime() + duration * 60000,
              ).toISOString(),
            ),
          )
        : localDateTime(new Date(end.getTime() + delta));
    onEvent({
      ...event,
      proposed_start: proposedStart,
      proposed_end: proposedEnd,
    });
  }
  const handlers = (mode: "move" | "resize") => ({
    onPointerDown: (e: React.PointerEvent<HTMLButtonElement>) => begin(e, mode),
    onPointerMove: move,
    onPointerUp: (e: React.PointerEvent<HTMLButtonElement>) => finish(e),
    onPointerCancel: (e: React.PointerEvent<HTMLButtonElement>) =>
      finish(e, true),
    onClick: () => {
      if (!ignoreClick.current) onEvent(event);
      ignoreClick.current = false;
    },
  });
  return (
    <div
      ref={element}
      data-event-id={event.id}
      className={
        "time-event type-" +
        event.kind +
        (event.completed ? " completed" : "") +
        (event.cancelled ? " cancelled" : "")
      }
      style={{
        top: (minutes / 60) * 64,
        height: Math.max(45, (drawnDuration / 60) * 64 - 3),
        left: `calc(${(event.lane / event.lanes) * 100}% + 3px)`,
        width: `calc(${100 / event.lanes}% - 6px)`,
      }}
    >
      <button
        type="button"
        className="time-event-main"
        aria-label={"Editar o mover " + event.title}
        aria-describedby="calendar-drag-help"
        {...handlers("move")}
      >
        <strong>
          {event.cancelled ? "Cancelada · " : ""}
          {event.title}
        </strong>
        <span>
          {instantLabel(event.occurrence_start)} –{" "}
          {instantLabel(event.occurrence_end)}
        </span>
        {duration > 55 && event.plate && <small>{event.plate}</small>}
      </button>
      <button
        type="button"
        className="event-resize-handle"
        aria-label={"Cambiar duración de " + event.title}
        aria-describedby="calendar-drag-help"
        {...handlers("resize")}
      >
        <span aria-hidden="true">↕</span>
      </button>
    </div>
  );
}

function TimeView({
  focus,
  view,
  events,
  onEvent,
  onDay,
  config,
}: CalendarViewProps & { view: string; config: Row }) {
  const range = calendarRange(focus, view),
    dates = Array.from({ length: view === "day" ? 1 : 7 }, (_, i) =>
      addDays(range.start, i),
    );
  let first = Math.max(
    0,
    Math.min(8, Number(config.agenda.work_start.slice(0, 2))),
  );
  let last = Math.min(
    24,
    Math.max(20, Number(config.agenda.work_end.slice(0, 2)) + 1),
  );
  events
    .filter((e: Row) => !isMulti(e))
    .forEach((e: Row) => {
      first = Math.min(first, wallDate(e.occurrence_start).getUTCHours());
      last = Math.max(
        last,
        Math.min(24, wallDate(e.occurrence_end).getUTCHours() + 1),
      );
    });
  const hours = Array.from({ length: last - first }, (_, i) => i + first),
    height = hours.length * 64;
  function placed(day: Date) {
    const rows = events
      .filter((e: Row) => !isMulti(e) && overlaps(e, day))
      .sort((a: Row, b: Row) =>
        a.occurrence_start.localeCompare(b.occurrence_start),
      );
    const out: Row[] = [];
    let group: Row[] = [],
      groupEnd = 0;
    function flush() {
      if (!group.length) return;
      const ends: number[] = [];
      for (const item of group) {
        const start = wallDate(item.occurrence_start).getTime();
        let lane = ends.findIndex((x) => x <= start);
        if (lane < 0) lane = ends.length;
        ends[lane] = start + visualDuration(item) * 60000;
        item.lane = lane;
      }
      for (const item of group) {
        item.lanes = ends.length;
        out.push(item);
      }
      group = [];
      groupEnd = 0;
    }
    for (const event of rows) {
      const start = wallDate(event.occurrence_start).getTime(),
        end = start + visualDuration(event) * 60000;
      if (group.length && start >= groupEnd) flush();
      group.push({ ...event });
      groupEnd = Math.max(groupEnd, end);
    }
    flush();
    return out;
  }
  const positions = dates.map((day) => ({ day, items: placed(day) }));
  return (
    <div className={"time-calendar " + view}>
      <div
        className="time-header"
        style={{
          gridTemplateColumns: `52px repeat(${dates.length},minmax(0,1fr))`,
        }}
      >
        <div className="time-zone">Madrid</div>
        {dates.map((d) => (
          <button
            key={localDate(d)}
            className={
              localDate(d) === localDate(wallDate(new Date().toISOString()))
                ? "today"
                : ""
            }
            onClick={() => onDay(d)}
          >
            <span>{days[(d.getUTCDay() + 6) % 7]}</span>
            <strong>{d.getUTCDate()}</strong>
          </button>
        ))}
      </div>
      <div
        className="all-day-row"
        style={{
          gridTemplateColumns: `52px repeat(${dates.length},minmax(0,1fr))`,
        }}
      >
        <span>
          Todo
          <br />
          el d&iacute;a
        </span>
        {dates.map((d) => (
          <div key={localDate(d)}>
            {events
              .filter((e: Row) => isMulti(e) && overlaps(e, d))
              .map((e: Row) => (
                <EventPill
                  key={e.occurrence_id}
                  event={e}
                  compact
                  onClick={() => onEvent(e)}
                />
              ))}
          </div>
        ))}
      </div>
      <div
        className="time-body"
        style={{
          gridTemplateColumns: `52px repeat(${dates.length},minmax(0,1fr))`,
        }}
      >
        <div className="time-labels" style={{ height }}>
          {hours.map((h) => (
            <span key={h} style={{ top: (h - first) * 64 }}>
              {String(h).padStart(2, "0")}:00
            </span>
          ))}
        </div>
        {positions.map(({ day, items }) => (
          <div key={localDate(day)} className="time-column" style={{ height }}>
            {hours
              .filter((hour) => {
                const slot = new Date(day);
                slot.setUTCHours(hour);
                return !items.some((item) => {
                  const start = wallDate(item.occurrence_start).getTime();
                  return (
                    start < slot.getTime() + 3600000 &&
                    start + visualDuration(item) * 60000 > slot.getTime()
                  );
                });
              })
              .map((h) => (
                <button
                  key={h}
                  className="time-slot"
                  style={{ top: (h - first) * 64, height: 64 }}
                  aria-label={
                    "A\u00f1adir evento el " +
                    localDate(day) +
                    " a las " +
                    h +
                    ":00"
                  }
                  onClick={() => {
                    const d = new Date(day);
                    d.setUTCHours(h);
                    onDay(d);
                  }}
                />
              ))}
            {items.map((e) => (
              <TimeEvent
                key={e.occurrence_id}
                event={e}
                first={first}
                dayIndex={dates.findIndex(
                  (date) => localDate(date) === localDate(day),
                )}
                dayCount={dates.length}
                onEvent={onEvent}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
export function CalendarPage({ config, notify }: Row) {
  const [focus, setFocus] = useState(() =>
      startDay(wallDate(new Date().toISOString())),
    ),
    [view, setView] = useState(config.appearance.calendar_start || "month"),
    [tick, setTick] = useState(0),
    [edit, setEdit] = useState<Row | null>(null),
    [filter, setFilter] = useState(""),
    [showCancelled, setShowCancelled] = useState(false),
    [exporting, setExporting] = useState(false),
    [error, setError] = useState("");
  const range = calendarRange(focus, view);
  const [data, loading, loadError] = useLoad<Row[]>(
    "agenda.list",
    {
      start: dayISO(range.start),
      end: dayISO(range.end),
      include_cancelled: showCancelled,
    },
    [],
    tick,
  );
  const events = filter ? data.filter((e) => e.kind === filter) : data;
  const title =
    view === "month"
      ? focus.toLocaleDateString("es-ES", {
          timeZone: "UTC",
          month: "long",
          year: "numeric",
        })
      : view === "day"
        ? focus.toLocaleDateString("es-ES", {
            timeZone: "UTC",
            weekday: "long",
            day: "numeric",
            month: "long",
          })
        : range.start.toLocaleDateString("es-ES", {
            timeZone: "UTC",
            day: "numeric",
            month: "short",
          }) +
          " \u2014 " +
          addDays(range.end, -1).toLocaleDateString("es-ES", {
            timeZone: "UTC",
            day: "numeric",
            month: "short",
            year: "numeric",
          });
  function move(n: number) {
    const d = new Date(focus);
    if (view === "month") {
      d.setUTCDate(1);
      d.setUTCMonth(d.getUTCMonth() + n);
    } else d.setUTCDate(d.getUTCDate() + n * (view === "week" ? 7 : 1));
    setFocus(d);
  }
  const todayEvents = data.filter((e) => overlaps(e, focus));
  return (
    <>
      <PageHead
        title="Agenda"
        subtitle="Un poco de orden. Sin complicarte el d&iacute;a."
        eyebrow="M&Aacute;S HERRAMIENTAS"
      >
        <Button
          icon="download"
          busy={exporting}
          onClick={async () => {
            setExporting(true);
            try {
              await saveExport(await api("agenda.export"));
            } catch (e: any) {
              setError(e.message);
            } finally {
              setExporting(false);
            }
          }}
        >
          Exportar calendario
        </Button>
        <Button
          tone="primary"
          icon="plus"
          onClick={() => setEdit({ date: new Date(focus) })}
        >
          Nuevo evento
        </Button>
      </PageHead>
      <section className="panel calendar-panel">
        <div className="calendar-toolbar">
          <div className="calendar-date-nav">
            <Button
              onClick={() =>
                setFocus(startDay(wallDate(new Date().toISOString())))
              }
            >
              Hoy
            </Button>
            <Button
              icon="left"
              tone="ghost icon-only"
              aria-label="Periodo anterior"
              onClick={() => move(-1)}
            />
            <Button
              icon="right"
              tone="ghost icon-only"
              aria-label="Periodo siguiente"
              onClick={() => move(1)}
            />
            <h2 className="calendar-title">{title}</h2>
            <TextInput
              aria-label="Ir a una fecha"
              className="jump-date"
              type="date"
              value={localDate(focus)}
              onChange={(e) => {
                if (e.target.value) setFocus(wallCarrier(e.target.value));
              }}
            />
          </div>
          <div
            className="segmented"
            role="group"
            aria-label="Vista de la agenda"
          >
            {[
              ["month", "Mes"],
              ["week", "Semana"],
              ["day", "D\u00eda"],
            ].map(([v, label]) => (
              <button
                key={v}
                className={view === v ? "active" : ""}
                aria-pressed={view === v}
                onClick={() => setView(v)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="calendar-subbar">
          <span>
            <i className="live-dot" /> Europe/Madrid &middot; {events.length}{" "}
            eventos en la vista
          </span>
          <label className="calendar-cancelled-toggle">
            <input
              type="checkbox"
              checked={showCancelled}
              onChange={(e) => setShowCancelled(e.target.checked)}
            />{" "}
            Mostrar canceladas
          </label>
          <Select
            aria-label="Filtrar tipo de evento"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="">Todos los tipos</option>
            {Object.entries(types).map(([k, v]) => (
              <option value={k} key={k}>
                {String(v)}
              </option>
            ))}
          </Select>
        </div>
        {(error || loadError) && (
          <Notice tone="error">{error || loadError}</Notice>
        )}
        {loading && (
          <div className="calendar-loading" role="status">
            Actualizando agenda...
          </div>
        )}
        <div className="calendar-content">
          {view === "month" ? (
            <MonthView
              focus={focus}
              events={events}
              onEvent={setEdit}
              onDay={(d) => setEdit({ date: new Date(d) })}
              onMore={(d) => {
                setFocus(d);
                setView("day");
              }}
            />
          ) : (
            <TimeView
              focus={focus}
              view={view}
              events={events}
              onEvent={setEdit}
              onDay={(d) => setEdit({ date: new Date(d) })}
              config={config}
            />
          )}
        </div>
      </section>
      <p className="small subtle" id="calendar-drag-help">
        En semana y día, arrastra una cita para moverla o su borde inferior para
        cambiar la duración, en pasos de 15 minutos. También puedes abrirla y
        editar Comienza y Termina con el teclado. Guarda para confirmar.
      </p>
      <div className="calendar-bottom">
        <div className="legend">
          {Object.entries(types).map(([k, v]) => (
            <span key={k}>
              <i className={"type-" + k} />
              {String(v)}
            </span>
          ))}
        </div>
        <p>
          <Icon name="bell" size={16} /> Los avisos se guardan y los atrasados
          se agrupan al volver a abrir. Para recibirlos a tiempo, mantén la
          aplicación abierta o en la bandeja de Windows.
        </p>
      </div>
      {view === "month" && (
        <div className="mobile-agenda panel padded">
          <h3>
            {focus.toLocaleDateString("es-ES", {
              timeZone: "UTC",
              weekday: "long",
              day: "numeric",
              month: "long",
            })}
          </h3>
          {todayEvents.length ? (
            todayEvents.map((e) => (
              <EventPill
                event={e}
                key={e.occurrence_id}
                onClick={() => setEdit(e)}
              />
            ))
          ) : (
            <p className="subtle">Sin eventos este d&iacute;a.</p>
          )}
        </div>
      )}
      <Presence>{edit && (
        <EventForm
          event={edit}
          config={config}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            setTick((t) => t + 1);
            notify("Agenda actualizada");
          }}
        />
      )}</Presence>
    </>
  );
}
