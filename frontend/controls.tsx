import * as React from "react";
import { Popup, Presence, useCompact } from "./overlays.js";

type InputProps = React.InputHTMLAttributes<HTMLInputElement>;
const classes = (name: string, extra?: string) =>
  name + (extra ? " " + extra : "");
const Chevron = () => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.7"
    aria-hidden="true"
  >
    <path d="m6 9 6 6 6-6" />
  </svg>
);
const clean = (text: string) =>
  text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();

export const NumberInput = React.forwardRef<HTMLInputElement, InputProps>(
  function NumberInput(props, ref) {
    return (
      <input
        {...props}
        ref={ref}
        className={classes("text-control number-control", props.className)}
        type="number"
      />
    );
  },
);
export const TextInput = React.forwardRef<HTMLInputElement, InputProps>(
  function TextInput(props, ref) {
    if (props.type === "date" || props.type === "datetime-local")
      return <DateInput {...props} ref={ref} />;
    if (props.type === "number") return <NumberInput {...props} ref={ref} />;
    return (
      <input
        {...props}
        ref={ref}
        className={classes("text-control", props.className)}
      />
    );
  },
);
export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea(props, ref) {
  return (
    <textarea
      {...props}
      ref={ref}
      className={classes("text-control textarea-control", props.className)}
    />
  );
});

/** Optional local suggestions; free text remains valid. */
export function Autocomplete({
  suggestions,
  onSuggestion,
  ...props
}: InputProps & {
  suggestions: string[];
  onSuggestion?: (value: string) => void;
}) {
  const input = React.useRef<HTMLInputElement>(null);
  const id = React.useId();
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const suppressFocus = React.useRef(false);
  const compact = useCompact();
  const query = String(props.value ?? "");
  const options = suggestions
    .filter((value) => clean(value).includes(clean(query)))
    .slice(0, 20);
  const visible =
    open &&
    !props.disabled &&
    suggestions.length > 0 &&
    (compact || options.length > 0);
  const label = props["aria-label"] || "Concepto";
  function close() {
    suppressFocus.current = compact;
    setOpen(false);
  }
  function choose(value: string) {
    if (!input.current) return;
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!.call(input.current, value);
    input.current.dispatchEvent(new Event("input", { bubbles: true }));
    onSuggestion?.(value);
    close();
  }
  function keys(event: React.KeyboardEvent<HTMLInputElement>) {
    props.onKeyDown?.(event);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActive((index) =>
        Math.max(
          0,
          Math.min(
            options.length - 1,
            index + (event.key === "ArrowDown" ? 1 : -1),
          ),
        ),
      );
    }
    if (event.key === "Enter" && visible && options[active]) {
      event.preventDefault();
      choose(options[active]);
    }
    if (event.key === "Tab") close();
    if (event.key === "Escape" && visible) {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  }
  React.useEffect(() => {
    if (visible)
      document
        .getElementById(id + "-" + active)
        ?.scrollIntoView({ block: "nearest" });
  }, [active, visible, id]);
  const attributes = {
    ...props,
    role: "combobox",
    "aria-autocomplete": "list" as const,
    "aria-expanded": visible,
    "aria-controls": visible ? id : undefined,
    "aria-activedescendant":
      visible && options[active] ? id + "-" + active : undefined,
    autoComplete: "off",
    onKeyDown: keys,
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => {
      setActive(0);
      setOpen(true);
      props.onChange?.(event);
    },
  };
  return (
    <>
      <TextInput
        {...attributes}
        ref={input}
        onFocus={(event) => {
          if (!suppressFocus.current) setOpen(true);
          suppressFocus.current = false;
          props.onFocus?.(event);
        }}
      />
      <Presence>
        {visible && (
          <Popup
            anchor={input}
            title={label}
            onClose={close}
            focusOnOpen={false}
          >
            {compact && (
              <div className="picker-filter">
                <TextInput
                  {...attributes}
                  id={undefined}
                  aria-label={label}
                  aria-labelledby={undefined}
                  data-autofocus
                />
              </div>
            )}
            <div
              role="listbox"
              id={id}
              aria-label="Conceptos frecuentes"
              className="picker-options"
            >
              {options.map((option, index) => (
                <button
                  key={option}
                  id={id + "-" + index}
                  type="button"
                  tabIndex={-1}
                  role="option"
                  aria-selected={index === active}
                  className={classes(
                    "picker-option",
                    index === active ? "active" : "",
                  )}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(option)}
                  onMouseEnter={() => setActive(index)}
                >
                  {option}
                </button>
              ))}
              {!options.length && (
                <p className="picker-empty">
                  Puedes escribir un concepto nuevo.
                </p>
              )}
            </div>
          </Popup>
        )}
      </Presence>
    </>
  );
}

type Option = {
  value: string;
  label: string;
  disabled: boolean;
  group?: string;
};
function textContent(node: React.ReactNode): string {
  return React.Children.toArray(node)
    .map((child) =>
      React.isValidElement<{ children?: React.ReactNode }>(child)
        ? textContent(child.props.children)
        : String(child),
    )
    .join("");
}
function readOptions(
  children: React.ReactNode,
  group?: string,
  disabled = false,
): Option[] {
  return React.Children.toArray(children).flatMap((child) => {
    if (
      !React.isValidElement<{
        children?: React.ReactNode;
        value?: string | number;
        disabled?: boolean;
        label?: string;
      }>(child)
    )
      return [];
    if (child.type === "option")
      return [
        {
          value: String(child.props.value ?? textContent(child.props.children)),
          label: textContent(child.props.children),
          disabled: disabled || !!child.props.disabled,
          group,
        },
      ];
    return readOptions(
      child.props.children,
      child.type === "optgroup" ? child.props.label : group,
      disabled || !!child.props.disabled,
    );
  });
}

/** Native form value/validation, with a consistent keyboard and touch picker. */
export function Select({
  children,
  className,
  id,
  onChange,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const generated = React.useId();
  const controlId = id || generated;
  const listId = generated + "-options";
  const native = React.useRef<HTMLSelectElement>(null);
  const trigger = React.useRef<HTMLButtonElement>(null);
  const list = React.useRef<HTMLDivElement>(null);
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [active, setActive] = React.useState(0);
  const [invalid, setInvalid] = React.useState(false);
  const [uncontrolled, setUncontrolled] = React.useState(props.defaultValue);
  const options = readOptions(children);
  const selected = options.find(
    (option) =>
      option.value ===
      String(props.value ?? uncontrolled ?? options[0]?.value ?? ""),
  );
  const visible = options.filter((option) =>
    clean(option.label).includes(clean(query)),
  );
  const label =
    props["aria-label"] ||
    (props["aria-labelledby"]
      ? document.getElementById(props["aria-labelledby"])?.textContent
      : "") ||
    "Seleccionar opción";
  React.useEffect(() => {
    list.current
      ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);
  function show() {
    if (props.disabled) return;
    setQuery("");
    setActive(
      Math.max(
        0,
        options.findIndex((option) => option === selected),
      ),
    );
    setOpen(true);
  }
  function choose(option: Option) {
    if (option.disabled || !native.current) return;
    native.current.value = option.value;
    native.current.dispatchEvent(new Event("change", { bubbles: true }));
    setOpen(false);
  }
  function keys(event: React.KeyboardEvent) {
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const step = event.key === "ArrowUp" ? -1 : 1;
      let next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? visible.length - 1
            : active + step;
      while (next >= 0 && next < visible.length && visible[next].disabled)
        next += step;
      if (next >= 0 && next < visible.length) setActive(next);
    }
    if (
      event.key === "Enter" ||
      (event.key === " " && event.target === list.current)
    ) {
      event.preventDefault();
      if (visible[active]) choose(visible[active]);
    }
    if (
      event.target === list.current &&
      event.key.length === 1 &&
      event.key !== " "
    ) {
      event.preventDefault();
      const next = visible.findIndex(
        (option, index) =>
          index > active &&
          !option.disabled &&
          clean(option.label).startsWith(clean(event.key)),
      );
      const fallback = visible.findIndex(
        (option) =>
          !option.disabled && clean(option.label).startsWith(clean(event.key)),
      );
      if (next >= 0 || fallback >= 0) setActive(next >= 0 ? next : fallback);
    }
  }
  return (
    <div className={classes("select-control", className)}>
      <select
        {...props}
        id={undefined}
        ref={native}
        className="native-select-value"
        tabIndex={-1}
        aria-hidden="true"
        aria-label={undefined}
        aria-labelledby={undefined}
        onChange={(event) => {
          setUncontrolled(event.target.value);
          setInvalid(false);
          onChange?.(event);
        }}
        onInvalid={(event) => {
          event.preventDefault();
          setInvalid(true);
          if (
            native.current?.form?.querySelector(":invalid") === native.current
          ) {
            trigger.current?.focus();
            show();
          }
        }}
      >
        {children}
      </select>
      <button
        type="button"
        id={controlId}
        ref={trigger}
        className="select-trigger"
        role="combobox"
        disabled={props.disabled}
        aria-label={props["aria-label"]}
        aria-labelledby={props["aria-labelledby"]}
        aria-describedby={
          [props["aria-describedby"], invalid ? generated + "-error" : ""]
            .filter(Boolean)
            .join(" ") || undefined
        }
        aria-required={props.required}
        aria-invalid={props["aria-invalid"] || invalid || undefined}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? listId : undefined}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
            event.preventDefault();
            show();
          }
        }}
      >
        <span>{selected?.label || "Seleccionar…"}</span>
        <Chevron />
      </button>
      {invalid && (
        <small id={generated + "-error"} className="control-error">
          Selecciona una opción.
        </small>
      )}
      <Presence>
        {open && (
          <Popup
            anchor={trigger}
            title={label}
            onClose={() => setOpen(false)}
            className="select-popup"
          >
            {options.length > 8 && (
              <div className="picker-filter">
                <TextInput
                  aria-label="Filtrar opciones"
                  placeholder="Buscar una opción…"
                  value={query}
                  autoComplete="off"
                  data-autofocus
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setActive(0);
                  }}
                  onKeyDown={keys}
                  aria-controls={listId}
                  aria-activedescendant={
                    visible[active] ? listId + "-" + active : undefined
                  }
                  role="combobox"
                  aria-expanded="true"
                  aria-autocomplete="list"
                />
              </div>
            )}
            <div
              id={listId}
              ref={list}
              className="picker-options"
              role="listbox"
              aria-label={label}
              tabIndex={0}
              data-autofocus={options.length <= 8 ? true : undefined}
              aria-activedescendant={
                visible[active] ? listId + "-" + active : undefined
              }
              onKeyDown={keys}
            >
              {visible.map((option, index) => (
                <button
                  type="button"
                  key={option.value}
                  id={listId + "-" + index}
                  data-index={index}
                  data-value={option.value}
                  tabIndex={-1}
                  role="option"
                  aria-selected={selected?.value === option.value}
                  aria-disabled={option.disabled}
                  disabled={option.disabled}
                  className={classes(
                    "picker-option",
                    active === index ? "active" : "",
                  )}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => choose(option)}
                >
                  <span>
                    {option.group && <small>{option.group}</small>}
                    {option.label}
                  </span>
                  <span aria-hidden="true">
                    {selected?.value === option.value ? "✓" : ""}
                  </span>
                </button>
              ))}
              {!visible.length && (
                <p className="picker-empty" role="status">
                  No hay coincidencias.
                </p>
              )}
            </div>
          </Popup>
        )}
      </Presence>
    </div>
  );
}

const iso = (date: Date) =>
  `${String(date.getFullYear()).padStart(4, "0")}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const parseDate = (value: string) =>
  /^\d{4}-\d{2}-\d{2}/.test(value)
    ? new Date(value.slice(0, 10) + "T12:00:00")
    : new Date();
const monthNames = Array.from({ length: 12 }, (_, month) =>
  new Intl.DateTimeFormat("es-ES", { month: "long" }).format(
    new Date(2024, month, 1),
  ),
);
const dayLabel = (date: Date) =>
  new Intl.DateTimeFormat("es-ES", { dateStyle: "full" }).format(date);

export const DateInput = React.forwardRef<HTMLInputElement, InputProps>(
  function DateInput({ className, ...props }, forwardedRef) {
    const input = React.useRef<HTMLInputElement | null>(null);
    const trigger = React.useRef<HTMLButtonElement>(null);
    const [open, setOpen] = React.useState(false);
    const title =
      props["aria-label"] ||
      (props["aria-labelledby"]
        ? document.getElementById(props["aria-labelledby"])?.textContent
        : "") ||
      "Elegir fecha";
    function commit(value: string) {
      if (!input.current) return;
      // Use the native setter so React receives the same input event as direct typing.
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )!.set!;
      setter.call(input.current, value);
      input.current.dispatchEvent(new Event("input", { bubbles: true }));
    }
    return (
      <div className={classes("date-control", className)}>
        <input
          {...props}
          ref={(node) => {
            input.current = node;
            if (typeof forwardedRef === "function") forwardedRef(node);
            else if (forwardedRef) forwardedRef.current = node;
          }}
          className="text-control"
          onKeyDown={(event) => {
            props.onKeyDown?.(event);
            if (
              event.altKey &&
              event.key === "ArrowDown" &&
              !props.disabled &&
              !props.readOnly
            ) {
              event.preventDefault();
              setOpen(true);
            }
          }}
        />
        <button
          ref={trigger}
          type="button"
          className="date-trigger"
          disabled={props.disabled || props.readOnly}
          aria-label="Abrir calendario"
          aria-describedby={props["aria-labelledby"]}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <rect x="3" y="5" width="18" height="16" rx="3" />
            <path d="M7 3v4m10-4v4M3 10h18m-13 4h2m4 0h2" />
          </svg>
        </button>
        <Presence>
          {open && (
            <Popup
              anchor={trigger}
              title={title}
              onClose={() => setOpen(false)}
              className="date-popup"
              dialog
            >
              <CalendarPicker
                value={String(props.value ?? input.current?.value ?? "")}
                min={String(props.min ?? "")}
                max={String(props.max ?? "")}
                required={props.required}
                withTime={props.type === "datetime-local"}
                onChange={commit}
                onClose={() => setOpen(false)}
                title={title}
              />
            </Popup>
          )}
        </Presence>
      </div>
    );
  },
);

function CalendarPicker({
  value,
  min,
  max,
  required,
  withTime,
  onChange,
  onClose,
  title,
}: {
  value: string;
  min: string;
  max: string;
  required?: boolean;
  withTime: boolean;
  onChange: (value: string) => void;
  onClose: () => void;
  title: string;
}) {
  const initial = parseDate(value);
  const [cursor, setCursor] = React.useState(initial);
  const [view, setView] = React.useState<"days" | "months" | "years">("days");
  const [focusDate, setFocusDate] = React.useState(iso(initial));
  const grid = React.useRef<HTMLTableElement>(null);
  const shouldFocus = React.useRef(false);
  const year = cursor.getFullYear(),
    month = cursor.getMonth();
  const yearStart = Math.floor(year / 12) * 12;
  const start = new Date(year, month, 1, 12);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  const days = Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return date;
  });
  const allowed = (date: Date) =>
    (!min || iso(date) >= min.slice(0, 10)) &&
    (!max || iso(date) <= max.slice(0, 10)) &&
    date.getFullYear() >= 1 &&
    date.getFullYear() <= 9999;
  const periodAllowed = (from: Date, to: Date) =>
    (!min || iso(to) >= min.slice(0, 10)) &&
    (!max || iso(from) <= max.slice(0, 10)) &&
    to.getFullYear() >= 1 &&
    from.getFullYear() <= 9999;
  React.useLayoutEffect(() => {
    if (shouldFocus.current && view === "days") {
      grid.current
        ?.querySelector<HTMLButtonElement>(`[data-date="${focusDate}"]`)
        ?.focus({ preventScroll: true });
      shouldFocus.current = false;
    }
  }, [focusDate, view]);
  function choose(date: Date) {
    if (!allowed(date)) return;
    let next =
      iso(date) + (withTime ? "T" + (value.slice(11, 16) || "09:00") : "");
    if (withTime && min && next < min) next = min;
    if (withTime && max && next > max) next = max;
    onChange(next);
    if (!withTime) onClose();
  }
  function step(amount: number) {
    setCursor(
      view === "days"
        ? new Date(year, month + amount, 1, 12)
        : new Date(year + amount * (view === "years" ? 12 : 1), month, 1, 12),
    );
  }
  function dayKeys(event: React.KeyboardEvent, day: Date) {
    const delta: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7,
      Home: -(day.getDay() + 6) % 7,
      End: 6 - ((day.getDay() + 6) % 7),
    };
    const next = new Date(day);
    if (event.key in delta) next.setDate(next.getDate() + delta[event.key]);
    else if (event.key === "PageUp" || event.key === "PageDown") {
      const direction = event.key === "PageUp" ? -1 : 1;
      next.setDate(1);
      next.setMonth(next.getMonth() + direction * (event.shiftKey ? 12 : 1));
      next.setDate(
        Math.min(
          day.getDate(),
          new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate(),
        ),
      );
    } else return;
    event.preventDefault();
    if (allowed(next)) {
      shouldFocus.current = true;
      setFocusDate(iso(next));
      setCursor(next);
    }
  }
  return (
    <div className="calendar-picker" role="group" aria-label="Calendario">
      <div className="date-navigation">
        <button
          type="button"
          className="button ghost icon-only"
          aria-label={view === "days" ? "Mes anterior" : "Años anteriores"}
          onClick={() => step(-1)}
        >
          ‹
        </button>
        <div>
          <button
            type="button"
            className="date-heading"
            aria-label="Elegir mes"
            onClick={() => setView(view === "months" ? "days" : "months")}
          >
            {monthNames[month]}
          </button>
          <button
            type="button"
            className="date-heading"
            aria-label="Elegir año"
            onClick={() => setView(view === "years" ? "days" : "years")}
          >
            {view === "years" ? `${yearStart}–${yearStart + 11}` : year}
          </button>
        </div>
        <button
          type="button"
          className="button ghost icon-only"
          aria-label={view === "days" ? "Mes siguiente" : "Años siguientes"}
          onClick={() => step(1)}
        >
          ›
        </button>
      </div>
      <span className="sr-only" aria-live="polite">
        {monthNames[month]} de {year}
      </span>
      {view === "days" ? (
        <table
          ref={grid}
          className="date-grid"
          role="grid"
          aria-label={monthNames[month] + " de " + year}
        >
          <thead>
            <tr>
              {["L", "M", "X", "J", "V", "S", "D"].map((day, index) => (
                <th
                  scope="col"
                  key={day}
                  abbr={
                    [
                      "lunes",
                      "martes",
                      "miércoles",
                      "jueves",
                      "viernes",
                      "sábado",
                      "domingo",
                    ][index]
                  }
                >
                  {day}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 6 }, (_, week) => (
              <tr key={week}>
                {days.slice(week * 7, week * 7 + 7).map((day) => (
                  <td
                    key={iso(day)}
                    aria-selected={iso(day) === value.slice(0, 10)}
                  >
                    <button
                      type="button"
                      data-date={iso(day)}
                      data-autofocus={iso(day) === focusDate ? true : undefined}
                      tabIndex={iso(day) === focusDate ? 0 : -1}
                      disabled={!allowed(day)}
                      aria-label={dayLabel(day)}
                      aria-current={
                        iso(day) === iso(new Date()) ? "date" : undefined
                      }
                      className={classes(
                        "date-day",
                        (day.getMonth() !== month ? "outside " : "") +
                          (iso(day) === value.slice(0, 10) ? "selected" : ""),
                      )}
                      onClick={() => choose(day)}
                      onKeyDown={(event) => dayKeys(event, day)}
                    >
                      {day.getDate()}
                    </button>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div
          className="date-periods"
          role="group"
          aria-label={view === "months" ? "Meses" : "Años"}
        >
          {Array.from({ length: 12 }, (_, index) => {
            const targetYear = view === "years" ? yearStart + index : year;
            const targetMonth = view === "months" ? index : month;
            return (
              <button
                type="button"
                key={index}
                className={
                  (view === "months" ? index === month : targetYear === year)
                    ? "selected"
                    : ""
                }
                disabled={
                  !periodAllowed(
                    new Date(targetYear, view === "months" ? index : 0, 1),
                    new Date(targetYear, view === "months" ? index + 1 : 12, 0),
                  )
                }
                onClick={() => {
                  const next = new Date(targetYear, targetMonth, 1, 12);
                  setCursor(next);
                  setFocusDate(iso(next));
                  shouldFocus.current = true;
                  setView(view === "years" ? "months" : "days");
                }}
              >
                {view === "months" ? monthNames[index] : targetYear}
              </button>
            );
          })}
        </div>
      )}
      {withTime && (
        <label className="date-time">
          Hora
          <TextInput
            type="time"
            aria-label="Hora de la fecha"
            value={value.slice(11, 16) || "09:00"}
            min={
              value.slice(0, 10) === min.slice(0, 10)
                ? min.slice(11, 16)
                : undefined
            }
            max={
              value.slice(0, 10) === max.slice(0, 10)
                ? max.slice(11, 16)
                : undefined
            }
            onChange={(event) => {
              if (event.target.value)
                onChange(
                  (value.slice(0, 10) || iso(cursor)) +
                    "T" +
                    event.target.value,
                );
            }}
          />
        </label>
      )}
      <div className="date-footer">
        <button
          type="button"
          className="button ghost"
          disabled={!allowed(new Date())}
          onClick={() => choose(new Date())}
        >
          Hoy
        </button>
        {!required && (
          <button
            type="button"
            className="button ghost"
            onClick={() => {
              onChange("");
              onClose();
            }}
          >
            Borrar fecha
          </button>
        )}
        {withTime && (
          <button type="button" className="button primary" onClick={onClose}>
            Listo
          </button>
        )}
      </div>
    </div>
  );
}
