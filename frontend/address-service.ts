import { api } from "./core.js";

export type AddressFields = {
  address: string;
  postal_code: string;
  city: string;
  province: string;
  country: string;
};
export type AddressSuggestion = AddressFields & {
  id: string;
  label: string;
  country: "ES";
};
export type AddressReply = {
  status: "ok" | "unavailable";
  items: AddressSuggestion[];
};
type AddressQuery = Omit<AddressFields, "address"> & { query: string };
const unavailable = (): AddressReply => ({ status: "unavailable", items: [] });

// The local RPC itself cannot be aborted. Release its caller immediately and
// consume any eventual response/rejection without applying stale suggestions.
function interruptible<T>(operation: Promise<T>, signal?: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const abort = () => reject(new Error("Address search cancelled"));
    if (signal?.aborted) abort();
    else signal?.addEventListener("abort", abort, { once: true });
    operation.then(resolve, reject).finally(() => signal?.removeEventListener("abort", abort));
  });
}
function pause(signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, 150);
    signal.addEventListener("abort", done, { once: true });
    if (signal.aborted) done();
  });
}
function cancel(identifier: string) {
  // Cancellation is best effort and must never delay typing or saving a form.
  void api("addresses.cancel", { identifier }).catch(() => undefined);
}

export async function searchAddresses(fields: AddressQuery, signal?: AbortSignal): Promise<AddressReply> {
  if (signal?.aborted) return unavailable();
  if (!window.__TAURI__) {
    try {
      return await interruptible(api<AddressReply>("addresses.search", fields), signal);
    } catch {
      return unavailable();
    }
  }

  // Desktop uses one serialized stdio channel. Start a bounded background job
  // and poll short local calls so customer saves never wait for the provider.
  const lifetime = new AbortController();
  const abort = () => lifetime.abort();
  signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, 12000);
  let identifier: string | null = null;
  try {
    const started = api<{ identifier: string | null }>("addresses.start", fields).then(reply => {
      identifier = typeof reply?.identifier === "string" && reply.identifier ? reply.identifier : null;
      // An abort can precede this acknowledgement; reclaim that late job too.
      if (identifier && lifetime.signal.aborted) cancel(identifier);
      return reply;
    });
    await interruptible(started, lifetime.signal);
    if (!identifier) return unavailable();
    while (!lifetime.signal.aborted) {
      const reply = await interruptible(api<{ ready: boolean; result?: AddressReply }>(
        "addresses.result", { identifier },
      ), lifetime.signal);
      if (reply?.ready === true) return reply.result ?? unavailable();
      if (reply?.ready !== false) return unavailable();
      await pause(lifetime.signal);
    }
    return unavailable();
  } catch {
    return unavailable();
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
    lifetime.abort();
    if (identifier) cancel(identifier);
  }
}
