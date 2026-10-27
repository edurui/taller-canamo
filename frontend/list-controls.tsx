import * as React from "react";
import { Popup } from "./overlays.js";
import { api } from "./core.js";

export type ListSort = { key: string; direction: "asc" | "desc" } | null;
type SortValue = string | number | null | undefined;
export type SortValues<T> = Record<string, (row: T) => SortValue>;
const noRows: never[] = [];
const noValues = {};
const clean = (text: string) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

/** Retain headings/focus on refresh, but never activate stale rows or late responses. */
export function useListData<T>(action: string, params: Record<string, unknown>, initial: T, refresh = 0): [T, boolean, string, boolean] {
  const key = action + ":" + JSON.stringify(params);
  const [request, setRequest] = React.useState({ key, refresh, generation: 0 });
  if (request.key !== key || request.refresh !== refresh)
    setRequest({ key, refresh, generation: request.generation + 1 });
  const [result, setResult] = React.useState({ data: initial, generation: -1, error: "" });
  React.useEffect(() => {
    let live = true;
    api<T>(action, params).then(data => {
      if (live) setResult({ data, generation: request.generation, error: "" });
    }).catch((error: Error) => {
      if (live) setResult(previous => ({ ...previous, generation: request.generation, error: error.message }));
    });
    return () => { live = false; };
  }, [key, refresh, request.generation]);
  const loading = request.generation !== result.generation;
  const error = loading ? "" : result.error;
  return [result.data, loading, error, loading || !!error];
}

export function nextSort(current: ListSort, key: string): ListSort {
  if (current?.key !== key) return { key, direction: "asc" };
  return current.direction === "asc" ? { key, direction: "desc" } : null;
}

/** Complete datasets only. Paged lists pass the selection to their RPC before LIMIT. */
export function useListSort<T>(items: readonly T[] = noRows, values: SortValues<T> = noValues) {
  const [sort, setSort] = React.useState<ListSort>(null);
  const toggle = (key: string) => setSort(current => nextSort(current, key));
  const rows = React.useMemo(() => {
    if (!sort || !values[sort.key]) return items;
    const value = values[sort.key];
    return items.map((row, index) => ({ row, index, value: value(row) })).sort((a, b) => {
      // Unknowns stay last in either direction; equal values keep the supplied order.
      const absentA = a.value == null || a.value === "";
      const absentB = b.value == null || b.value === "";
      if (absentA || absentB) return Number(absentA) - Number(absentB) || a.index - b.index;
      const left = typeof a.value === "string" ? clean(a.value) : a.value!;
      const right = typeof b.value === "string" ? clean(b.value) : b.value!;
      const result = left < right ? -1 : left > right ? 1 : 0;
      return result * (sort.direction === "asc" ? 1 : -1) || a.index - b.index;
    }).map(item => item.row);
  }, [items, sort, values]);
  return { sort, toggle, rows };
}

export function SortHeader({ label, field, secondary, sort, onSort, className = "" }: {
  label: string;
  field: string;
  secondary?: { label: string; field: string };
  sort: ListSort;
  onSort: (key: string) => void;
  className?: string;
}) {
  const active = sort?.key === field || (secondary && sort?.key === secondary.field);
  const control = (key: string, text: string) => {
    const selected = sort?.key === key;
    const next = selected ? sort.direction === "asc" ? "descendente" : "original" : "ascendente";
    return <button type="button" className="sort-heading" onClick={() => onSort(key)}
      aria-label={`${text}: ordenar ${next}`} title={`${text}: ordenar ${next}`}>
      <span>{text}</span>
      <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        <path className={selected && sort.direction === "asc" ? "selected" : ""} d="M6 15V4m-3 3 3-3 3 3" />
        <path className={selected && sort.direction === "desc" ? "selected" : ""} d="M14 5v11m-3-3 3 3 3-3" />
      </svg>
    </button>;
  };
  return <th scope="col" className={className} aria-sort={active ? sort?.direction === "asc" ? "ascending" : "descending" : "none"}>
    <span className="sort-heading-group">
      {control(field, label)}{secondary && control(secondary.field, secondary.label)}
    </span>
  </th>;
}

/** Keep native table semantics and the primary link/button as the keyboard target. */
export function EntityRow({ onOpen, disabled = false, className = "", children, ...props }: React.HTMLAttributes<HTMLTableRowElement> & {
  onOpen?: () => void;
  disabled?: boolean;
}) {
  return <tr {...props} className={`${onOpen && !disabled ? "clickable " : ""}${className}`.trim()} onClick={event => {
    props.onClick?.(event);
    if (disabled || !onOpen || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const target = event.target as Element;
    if (!event.currentTarget.contains(target) || target.closest('button,a,input,select,textarea,summary,[role="button"],[role="menu"],[contenteditable="true"],[data-row-interactive]')) return;
    if (window.getSelection()?.toString()) return;
    onOpen();
  }}>{children}</tr>;
}

export type RowAction = { label: string; onSelect: () => void; disabled?: boolean; danger?: boolean };
export function RowActions({ label, items, disabled = false }: { label: string; items: RowAction[]; disabled?: boolean }) {
  const anchor = React.useRef<HTMLButtonElement>(null);
  const menu = React.useRef<HTMLDivElement>(null);
  const id = React.useId();
  const [open, setOpen] = React.useState(false);
  React.useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  const close = () => setOpen(false);
  return <>
    <button type="button" ref={anchor} className="row-actions-trigger" aria-label={`Acciones de ${label}`}
      aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} disabled={disabled}
      onClick={event => { event.stopPropagation(); setOpen(value => !value); }}
      onKeyDown={event => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); }
      }}>
      <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <circle cx="4" cy="10" r="1.6" /><circle cx="10" cy="10" r="1.6" /><circle cx="16" cy="10" r="1.6" />
      </svg>
    </button>
    {open && <Popup anchor={anchor} title={`Acciones de ${label}`} onClose={close} className="row-actions-popup">
      <div id={id} ref={menu} role="menu" aria-label={`Acciones de ${label}`} className="row-actions-menu"
        onClick={event => event.stopPropagation()} onKeyDown={event => {
          const options = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []);
          const index = options.indexOf(document.activeElement as HTMLButtonElement);
          let next: number;
          if (event.key === "ArrowDown") next = (index + 1) % options.length;
          else if (event.key === "ArrowUp") next = (index - 1 + options.length) % options.length;
          else if (event.key === "Home") next = 0;
          else if (event.key === "End") next = options.length - 1;
          else return;
          event.preventDefault(); options[next]?.focus();
        }}>
        {items.map((item, index) => <button key={item.label} type="button" role="menuitem" data-autofocus={index === 0 || undefined}
          className={item.danger ? "danger" : undefined} disabled={item.disabled}
          onClick={() => { close(); item.onSelect(); }}>{item.label}</button>)}
      </div>
    </Popup>}
  </>;
}
