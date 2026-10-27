import * as React from "react";
import { Autocomplete, type AutocompleteOption } from "./controls.js";
import { Field } from "./core.js";
import { useClosing } from "./overlays.js";
import { searchAddresses, type AddressFields, type AddressSuggestion } from "./address-service.js";

export type { AddressFields } from "./address-service.js";
type Request = { sequence: number; context: string };
type Result = {
  request: Request;
  status: "loading" | "ok" | "unavailable";
  items: AddressSuggestion[];
};
const addressKeys = ["address", "postal_code", "city", "province", "country"] as const;
const isSuggestion = (item: unknown): item is AddressSuggestion => {
  if (!item || typeof item !== "object") return false;
  const entry = item as Record<string, unknown>;
  return ["id", "label", ...addressKeys].every(key => typeof entry[key] === "string") &&
    Boolean(entry.id && entry.label && entry.address) && entry.country === "ES";
};
const signature = (value: AddressFields) => JSON.stringify([
  value.address, value.postal_code, value.city, value.province, value.country,
]);

/** Only manual address input requests suggestions; opening a stored record is local. */
export function AddressAutocomplete({ value, onChange, disabled = false }: {
  value: AddressFields;
  onChange: (patch: Partial<AddressFields>) => void;
  disabled?: boolean;
}) {
  const closing = useClosing();
  const inactive = disabled || closing;
  const [result, setResult] = React.useState<Result | null>(null);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const controller = React.useRef<AbortController | null>(null);
  const sequence = React.useRef(0);
  const request = React.useRef<Request | null>(null);
  const current = React.useRef({ context: signature(value), disabled: inactive });
  current.current = { context: signature(value), disabled: inactive };
  const spanish = value.country.trim().toUpperCase() === "ES";

  function invalidate() {
    sequence.current++;
    request.current = null;
    controller.current?.abort();
    controller.current = null;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setResult(null);
  }
  function isCurrent(candidate: Request) {
    return candidate.sequence === sequence.current &&
      candidate.context === current.current.context && !current.current.disabled;
  }
  React.useEffect(() => {
    if (request.current && (!isCurrent(request.current) || !spanish)) invalidate();
  }, [value.address, value.postal_code, value.city, value.province, value.country, inactive]);
  React.useEffect(() => () => {
    sequence.current++;
    request.current = null;
    controller.current?.abort();
    if (timer.current) clearTimeout(timer.current);
  }, []);

  function editAddress(address: string) {
    invalidate();
    onChange({ address });
    const query = address.trim();
    if (inactive || !spanish || query.length < 3) return;
    const cancellation = new AbortController();
    controller.current = cancellation;
    const next = { ...value, address };
    const candidate = { sequence: sequence.current, context: signature(next) };
    request.current = candidate;
    setResult({ request: candidate, status: "loading", items: [] });
    timer.current = setTimeout(async () => {
      timer.current = null;
      if (!isCurrent(candidate)) return;
      try {
        const reply = await searchAddresses({
          query,
          postal_code: next.postal_code,
          city: next.city,
          province: next.province,
          country: next.country,
        }, cancellation.signal);
        if (!isCurrent(candidate)) return;
        const valid = reply?.status === "ok" && Array.isArray(reply.items) && reply.items.every(isSuggestion);
        setResult({
          request: candidate,
          status: valid ? "ok" : "unavailable",
          items: valid ? reply.items : [],
        });
      } catch {
        if (isCurrent(candidate)) setResult({ request: candidate, status: "unavailable", items: [] });
      }
    }, 300);
  }
  const visible = result && isCurrent(result.request) && spanish ? result : null;
  const options = (visible?.items ?? []).map(item => ({
    id: item.id, label: item.label, value: item.address,
  }));
  function select(option: AutocompleteOption) {
    if (!visible || !isCurrent(visible.request)) return;
    const selected = visible.items.find(item => item.id === option.id);
    if (!selected) return;
    invalidate();
    const patch: Partial<AddressFields> = {};
    // Missing provider fields never erase anything the user already entered.
    for (const key of addressKeys) {
      if (selected[key]?.trim()) patch[key] = selected[key];
    }
    onChange(patch);
  }
  const hint = visible?.status === "loading"
    ? "Buscando direcciones…"
    : visible?.status === "unavailable"
      ? "No se han podido obtener sugerencias. Puedes escribir la dirección manualmente."
      : visible?.status === "ok" && !visible.items.length
        ? "Sin sugerencias. Puedes escribir la dirección y guardar igualmente."
        : spanish
          ? "Escribe 3 caracteres para ver sugerencias. Puedes completar la dirección a mano."
          : "Escribe la dirección a mano para este país.";
  return (
    <Field label="Dirección" hint={<><span role="status">{hint}</span>{" "}CartoCiudad (IGN/CNIG) · CC BY 4.0.</>}>
      <Autocomplete
        aria-label="Dirección"
        value={value.address}
        disabled={inactive}
        options={options}
        onOption={select}
        filterSuggestions={false}
        pending={visible?.status === "loading"}
        listLabel="Direcciones sugeridas"
        emptyText="Buscando direcciones…"
        onDismiss={invalidate}
        onChange={event => editAddress(event.target.value)}
      />
    </Field>
  );
}
