import AxeBuilder from "@axe-core/playwright";
import type { Locator, Page, TestInfo } from "@playwright/test";
import { test, expect } from "./fixtures";

type SearchParams = {
  query: string;
  postal_code: string;
  city: string;
  province: string;
  country: string;
};
type Address = {
  id: string;
  label: string;
  address: string;
  postal_code: string;
  city: string;
  province: string;
  country: string;
};
type SearchReply = { status: "ok" | "unavailable"; items: Address[] };
type MockReply = SearchReply | { rpcError: true } | { networkError: true };
type Rpc = <T = Record<string, unknown>>(
  action: string,
  params?: Record<string, unknown>,
) => Promise<T>;

const first: Address = {
  id: "synthetic-address-1",
  label:
    "Calle del Ensayo Sintético, 12 · 28080 · Municipio Alfa · Provincia Alfa",
  address: "Calle del Ensayo Sintético, 12",
  postal_code: "28080",
  city: "Municipio Alfa",
  province: "Provincia Alfa",
  country: "ES",
};
const second: Address = {
  id: "synthetic-address-2",
  label:
    "Avenida de la Prueba Sintética, 24 · 50080 · Municipio Beta · Provincia Beta",
  address: "Avenida de la Prueba Sintética, 24",
  postal_code: "50080",
  city: "Municipio Beta",
  province: "Provincia Beta",
  country: "ES",
};
const unavailable =
  "No se han podido obtener sugerencias. Puedes escribir la dirección manualmente.";
const success = (...items: Address[]): SearchReply => ({ status: "ok", items });

function signal() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

// Intercept this RPC without route.fetch: address tests never contact CartoCiudad.
// Other RPCs still exercise the real, fresh synthetic SQLite fixture.
async function mockAddresses(
  page: Page,
  handler: (
    params: SearchParams,
    index: number,
  ) => MockReply | Promise<MockReply>,
) {
  const calls: SearchParams[] = [];
  const completed: SearchParams[] = [];
  await page.route("**/api", async (route) => {
    const request = route.request().postDataJSON();
    if (request.action !== "addresses.search") {
      await route.continue();
      return;
    }
    const params = request.params as SearchParams;
    calls.push(params);
    const reply = await handler(params, calls.length - 1);
    if ("networkError" in reply) await route.abort("internetdisconnected");
    else
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        json:
          "rpcError" in reply
            ? {
                ok: false,
                error: {
                  code: "synthetic_unavailable",
                  message: "Fallo sintético de consulta",
                },
              }
            : { ok: true, result: reply },
      });
    completed.push(params);
  });
  return { calls, completed };
}

async function mockNativeAddresses(
  page: Page,
  handler: (
    action: string,
    params: Record<string, unknown>,
  ) => unknown | Promise<unknown>,
) {
  const calls: { action: string; params: Record<string, unknown> }[] = [];
  const completed: string[] = [];
  await page.exposeFunction(
    "syntheticNativeAddressRpc",
    async (action: string, params: Record<string, unknown>) => {
      calls.push({ action, params });
      const result = await handler(action, params);
      completed.push(action);
      return { ok: true, result };
    },
  );
  await page.addInitScript(() => {
    const bridge = window as unknown as {
      syntheticNativeAddressRpc: (
        action: string,
        params: Record<string, unknown>,
      ) => Promise<unknown>;
      __CANAMO_DEV_TOKEN__?: string;
    };
    Object.defineProperty(window, "__TAURI__", {
      value: {
        core: {
          invoke: async (
            command: string,
            payload: { action: string; params: Record<string, unknown> },
          ) => {
            if (command === "set_document_dirty") return null;
            if (command !== "rpc")
              throw new Error(
                "Unexpected synthetic native command: " + command,
              );
            if (payload.action.startsWith("addresses.")) {
              return bridge.syntheticNativeAddressRpc(
                payload.action,
                payload.params,
              );
            }
            const response = await fetch("/api", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-Canamo-Token": bridge.__CANAMO_DEV_TOKEN__ || "",
              },
              body: JSON.stringify(payload),
            });
            return response.json();
          },
        },
      },
    });
  });
  return { calls, completed };
}

async function settle(page: Page) {
  await page.evaluate(async () => {
    while (true) {
      const active = document
        .getAnimations()
        .filter(
          (animation) =>
            animation.playState === "running" &&
            Number.isFinite(animation.effect?.getComputedTiming().endTime),
        );
      if (!active.length) return;
      await Promise.all(
        active.map((animation) => animation.finished.catch(() => undefined)),
      );
    }
  });
}

async function flushResponse(page: Page) {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
}

async function openNew(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.getByRole("button", { name: /Nuevo cliente/ }).click();
  const form = page.getByRole("dialog", { name: "Nuevo cliente", exact: true });
  await expect(form).toBeVisible();
  await form
    .getByRole("textbox", { name: "Nombre o razón social", exact: true })
    .fill("Cliente sintético de direcciones");
  return form;
}

async function addressInput(page: Page, form: Locator) {
  const picker = page.getByRole("dialog", { name: "Dirección", exact: true });
  return (await picker.isVisible())
    ? picker.getByRole("combobox", { name: "Dirección", exact: true })
    : form.getByRole("combobox", { name: "Dirección", exact: true });
}

async function manualContext(form: Locator) {
  await form.getByLabel("Código postal", { exact: true }).fill("41099");
  await form
    .getByLabel("Población", { exact: true })
    .fill("Municipio manual sintético");
  await form
    .getByLabel("Provincia", { exact: true })
    .fill("Provincia manual sintética");
  await form.getByLabel("País (dos letras)", { exact: true }).fill("ES");
}

async function expectAddress(
  form: Locator,
  value: Omit<Address, "id" | "label">,
) {
  await expect(
    form.getByRole("combobox", { name: "Dirección", exact: true }),
  ).toHaveValue(value.address);
  await expect(form.getByLabel("Código postal", { exact: true })).toHaveValue(
    value.postal_code,
  );
  await expect(form.getByLabel("Población", { exact: true })).toHaveValue(
    value.city,
  );
  await expect(form.getByLabel("Provincia", { exact: true })).toHaveValue(
    value.province,
  );
  await expect(
    form.getByLabel("País (dos letras)", { exact: true }),
  ).toHaveValue(value.country);
}

async function savedCustomer(rpc: Rpc) {
  const list = await rpc<{ items: { id: string }[] }>("customers.list");
  expect(list.items).toHaveLength(1);
  return rpc<Record<string, unknown>>("customers.get", {
    identifier: list.items[0].id,
  });
}

async function freezeAfterOpen(page: Page) {
  await settle(page);
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 1000));
}

test("dirección manual corta y país distinto de ES no consultan y permiten guardar", async ({
  page,
  rpc,
}) => {
  await page.clock.install();
  const remote = await mockAddresses(page, () => success(first));
  const form = await openNew(page);
  await freezeAfterOpen(page);
  const input = form.getByRole("combobox", { name: "Dirección", exact: true });
  await input.fill("  Ca  ");
  await page.clock.runFor(1000);
  expect(remote.calls).toHaveLength(0);
  await form.getByLabel("País (dos letras)", { exact: true }).fill("PT");
  await input.fill("Rua manual sintética, 7");
  await page.clock.runFor(1000);
  expect(remote.calls).toHaveLength(0);
  await expect(
    form.getByRole("button", { name: "Guardar cliente", exact: true }),
  ).toBeEnabled();
  await page.clock.resume();
  await form
    .getByRole("button", { name: "Guardar cliente", exact: true })
    .click();
  await expect(form).toBeHidden();
  const saved = await savedCustomer(rpc);
  expect(saved.address).toBe("Rua manual sintética, 7");
  expect(saved.country).toBe("PT");
});

test("consulta desde tres caracteres con debounce de 300 ms y sólo los cinco campos de dirección", async ({
  page,
}) => {
  await page.clock.install();
  const remote = await mockAddresses(page, () => success(first));
  const form = await openNew(page);
  await manualContext(form);
  await form
    .getByLabel("Teléfono principal", { exact: true })
    .fill("600000099");
  await form.getByLabel("NIF / CIF", { exact: true }).fill("12345678Z");
  await freezeAfterOpen(page);
  const input = form.getByRole("combobox", { name: "Dirección", exact: true });
  await input.fill("Calle anterior");
  await page.clock.runFor(200);
  expect(remote.calls).toHaveLength(0);
  await input.fill("  Cal  ");
  await page.clock.runFor(299);
  expect(remote.calls).toHaveLength(0);
  await page.clock.runFor(1);
  await expect.poll(() => remote.calls.length).toBe(1);
  expect(remote.calls[0]).toEqual({
    query: "Cal",
    postal_code: "41099",
    city: "Municipio manual sintético",
    province: "Provincia manual sintética",
    country: "ES",
  });
  await page.clock.resume();
  await expect(
    page.getByRole("option", { name: first.label, exact: true }),
  ).toBeVisible();
});

test("editar una ficha existente, enfocar Dirección o cambiar el contexto no envía su dirección guardada", async ({
  page,
  rpc,
}) => {
  await page.clock.install();
  const remote = await mockAddresses(page, () => success(first));
  await rpc("customers.save", {
    data: {
      name: "Ficha sintética existente",
      address: "Dirección conservada sin consultar, 8",
      postal_code: "41099",
      city: "Municipio conservado",
      province: "Provincia conservada",
      country: "ES",
    },
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Clientes", exact: true }).click();
  await page.locator("tbody td:first-child").getByRole("button", { name: /Ficha sintética existente/ }).click();
  await page.getByRole("button", { name: "Editar ficha", exact: true }).click();
  const form = page.getByRole("dialog", {
    name: "Editar cliente",
    exact: true,
  });
  await expect(form).toBeVisible();
  await freezeAfterOpen(page);
  await page.clock.runFor(1000);
  const input = form.getByRole("combobox", { name: "Dirección", exact: true });
  await input.focus();
  await page.clock.runFor(500);
  await form
    .getByLabel("Población", { exact: true })
    .fill("Municipio corregido manualmente");
  await page.clock.runFor(500);
  expect(remote.calls).toHaveLength(0);
  await expect(input).toHaveValue("Dirección conservada sin consultar, 8");
  await page.clock.resume();
});

test("flechas y Enter aplican todos los campos una vez, mantienen el foco y Tab continúa el formulario", async ({
  page,
  rpc,
}) => {
  await page.clock.install();
  const remote = await mockAddresses(page, () => success(first, second));
  const form = await openNew(page);
  await manualContext(form);
  const input = await addressInput(page, form);
  await input.fill("Ensayo sintético");
  const list = page.getByRole("listbox", {
    name: "Direcciones sugeridas",
    exact: true,
  });
  await expect(list.getByRole("option")).toHaveCount(2);
  await expect(input).toHaveAttribute("aria-autocomplete", "list");
  await expect(input).toHaveAttribute("aria-expanded", "true");
  await expect(list.getByRole("option").first()).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await input.press("ArrowDown");
  await expect(list.getByRole("option").nth(1)).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await input.press("ArrowUp");
  await expect(list.getByRole("option").first()).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(input).toHaveAttribute(
    "aria-activedescendant",
    (await list.getByRole("option").first().getAttribute("id")) as string,
  );
  await input.press("Enter");
  await expectAddress(form, first);
  await expect(input).toBeFocused();
  await expect(list).toBeHidden();
  await page.clock.runFor(800);
  expect(remote.calls).toHaveLength(1);
  await input.press("Tab");
  await expect(form.getByLabel("Código postal", { exact: true })).toBeFocused();
  expect(
    (await rpc<{ items: unknown[] }>("customers.list")).items,
  ).toHaveLength(0);
  await form
    .getByRole("button", { name: "Guardar cliente", exact: true })
    .click();
  await expect(form).toBeHidden();
  const saved = await savedCustomer(rpc);
  for (const key of [
    "address",
    "postal_code",
    "city",
    "province",
    "country",
  ] as const)
    expect(saved[key]).toBe(first[key]);
});

test("un ratón inmóvil bajo el desplegable no cambia la primera dirección ni la elegida con teclado", async ({ page }) => {
  await mockAddresses(page, () => success(first, second));
  const form = await openNew(page);
  const input = await addressInput(page, form);
  const list = page.getByRole("listbox", { name: "Direcciones sugeridas", exact: true });
  await input.fill("Primera consulta sintética");
  const secondRow = list.getByRole("option").nth(1);
  await expect(secondRow).toBeVisible();
  await settle(page);
  const box = await secondRow.boundingBox();
  expect(box).not.toBeNull();
  await input.fill("");
  await expect(list).toBeHidden();
  // Leave the real pointer beneath the future second row before results arrive.
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await input.fill("Segunda consulta sintética");
  await expect(list.getByRole("option")).toHaveCount(2);
  await settle(page);
  await expect(list.getByRole("option").first()).toHaveAttribute("aria-selected", "true");
  await input.press("ArrowDown");
  await expect(secondRow).toHaveAttribute("aria-selected", "true");
  await input.press("ArrowUp");
  await expect(list.getByRole("option").first()).toHaveAttribute("aria-selected", "true");
  // A real move still activates the row and a click still applies it.
  await page.mouse.move(box!.x + box!.width / 2 + 5, box!.y + box!.height / 2);
  await expect(secondRow).toHaveAttribute("aria-selected", "true");
  await secondRow.click();
  await expectAddress(form, second);
});

test("el ratón selecciona y los cinco campos siguen admitiendo correcciones manuales", async ({
  page,
  rpc,
}) => {
  await mockAddresses(page, () => success(first, second));
  const form = await openNew(page);
  await (await addressInput(page, form)).fill("Prueba sintética");
  await page.getByRole("option", { name: second.label, exact: true }).click();
  await expectAddress(form, second);
  await form
    .getByRole("combobox", { name: "Dirección", exact: true })
    .fill("Avenida corregida a mano, 24, local 2");
  await form.getByLabel("Código postal", { exact: true }).fill("50081");
  await form
    .getByLabel("Población", { exact: true })
    .fill("Municipio manual final");
  await form
    .getByLabel("Provincia", { exact: true })
    .fill("Provincia manual final");
  await form.getByLabel("País (dos letras)", { exact: true }).fill("PT");
  await form
    .getByRole("button", { name: "Guardar cliente", exact: true })
    .click();
  await expect(form).toBeHidden();
  const saved = await savedCustomer(rpc);
  expect(saved).toMatchObject({
    address: "Avenida corregida a mano, 24, local 2",
    postal_code: "50081",
    city: "Municipio manual final",
    province: "Provincia manual final",
    country: "PT",
  });
});

test("una sugerencia parcial conserva el CP, población y provincia escritos y no modifica otros datos", async ({
  page,
  rpc,
}) => {
  const partial = { ...first, postal_code: "", city: "", province: "" };
  await mockAddresses(page, () => success(partial));
  const form = await openNew(page);
  await manualContext(form);
  await form
    .getByLabel("Teléfono principal", { exact: true })
    .fill("600000098");
  await form
    .getByLabel("Notas del cliente", { exact: true })
    .fill("Nota sintética que se conserva");
  await (await addressInput(page, form)).fill("Calle parcial");
  await page.getByRole("option", { name: partial.label, exact: true }).click();
  await expectAddress(form, {
    ...first,
    postal_code: "41099",
    city: "Municipio manual sintético",
    province: "Provincia manual sintética",
  });
  await form
    .getByRole("button", { name: "Guardar cliente", exact: true })
    .click();
  await expect(form).toBeHidden();
  expect(await savedCustomer(rpc)).toMatchObject({
    phone: "600000098",
    notes: "Nota sintética que se conserva",
    postal_code: "41099",
    city: "Municipio manual sintético",
    province: "Provincia manual sintética",
  });
});

test("respuestas invertidas no sustituyen las sugerencias del texto más reciente", async ({
  page,
}) => {
  const arrived = signal(),
    release = signal();
  const remote = await mockAddresses(page, async (params) => {
    if (params.query === "Consulta anterior") {
      arrived.resolve();
      await release.promise;
      return success(first);
    }
    return success(second);
  });
  const form = await openNew(page);
  const input = await addressInput(page, form);
  try {
    await input.fill("Consulta anterior");
    await arrived.promise;
    await input.fill("Consulta reciente");
    await expect(
      page.getByRole("option", { name: second.label, exact: true }),
    ).toBeVisible();
    release.resolve();
    await expect.poll(() => remote.completed.length).toBe(2);
    await flushResponse(page);
    await expect(
      page.getByRole("option", { name: second.label, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("option", { name: first.label, exact: true }),
    ).toHaveCount(0);
    await expect(input).toHaveValue("Consulta reciente");
    await expect(form.getByLabel("Población", { exact: true })).not.toHaveValue(
      first.city,
    );
  } finally {
    release.resolve();
  }
});

for (const [field, label, changed] of [
  ["postal_code", "Código postal", "28099"],
  ["city", "Población", "Municipio posterior"],
  ["province", "Provincia", "Provincia posterior"],
  ["country", "País (dos letras)", "PT"],
] as const) {
  test(`cambiar ${field} invalida la respuesta pendiente sin consultar hasta otra edición de Dirección`, async ({
    page,
  }) => {
    const arrived = signal(),
      release = signal();
    const remote = await mockAddresses(page, async (_, index) => {
      if (index === 0) {
        arrived.resolve();
        await release.promise;
        return success(first);
      }
      return success(second);
    });
    const form = await openNew(page);
    const input = await addressInput(page, form);
    try {
      await input.fill("Consulta con contexto previo");
      await arrived.promise;
      await form.getByLabel(label, { exact: true }).fill(changed);
      release.resolve();
      await expect.poll(() => remote.completed.length).toBe(1);
      await flushResponse(page);
      await expect(
        page.getByRole("listbox", {
          name: "Direcciones sugeridas",
          exact: true,
        }),
      ).toBeHidden();
      await expect(form.getByLabel(label, { exact: true })).toHaveValue(
        changed,
      );
      expect(remote.calls).toHaveLength(1);
      if (field === "country")
        await form.getByLabel(label, { exact: true }).fill("ES");
      await input.fill("Consulta con contexto actual");
      await expect(
        page.getByRole("option", { name: second.label, exact: true }),
      ).toBeVisible();
      expect(remote.calls).toHaveLength(2);
      expect(remote.calls[1][field]).toBe(field === "country" ? "ES" : changed);
    } finally {
      release.resolve();
    }
  });
}

test("Escape cierra sólo las sugerencias y una respuesta tardía no vuelve a abrirlas", async ({
  page,
}) => {
  const arrived = signal(),
    release = signal();
  const remote = await mockAddresses(page, async () => {
    arrived.resolve();
    await release.promise;
    return success(first);
  });
  const form = await openNew(page);
  const input = await addressInput(page, form);
  try {
    await input.fill("Dirección manual antes de Escape");
    await arrived.promise;
    await input.press("Escape");
    await expect(form).toBeVisible();
    release.resolve();
    await expect.poll(() => remote.completed.length).toBe(1);
    await flushResponse(page);
    await expect(
      page.getByRole("listbox", { name: "Direcciones sugeridas", exact: true }),
    ).toBeHidden();
    await expect(input).toHaveValue("Dirección manual antes de Escape");
    await expect(input).toHaveAttribute("aria-expanded", "false");
  } finally {
    release.resolve();
  }
});

test("una selección descarta errores antiguos y no consulta de nuevo al autocompletar", async ({
  page,
}) => {
  await page.clock.install();
  const arrived = signal(),
    release = signal();
  const remote = await mockAddresses(page, async (_, index) => {
    if (index === 0) {
      arrived.resolve();
      await release.promise;
      return { status: "unavailable", items: [] };
    }
    return success(second);
  });
  const form = await openNew(page);
  const input = await addressInput(page, form);
  try {
    await input.fill("Consulta antigua que fallará");
    await arrived.promise;
    await input.fill("Consulta actual para seleccionar");
    await page.getByRole("option", { name: second.label, exact: true }).click();
    release.resolve();
    await expect.poll(() => remote.completed.length).toBe(2);
    await flushResponse(page);
    await page.clock.runFor(800);
    expect(remote.calls).toHaveLength(2);
    await expectAddress(form, second);
    await expect(page.getByText(unavailable, { exact: true })).toHaveCount(0);
    await expect(
      page.getByRole("listbox", { name: "Direcciones sugeridas", exact: true }),
    ).toBeHidden();
  } finally {
    release.resolve();
  }
});

for (const scenario of [
  "empty",
  "unavailable",
  "rpc-error",
  "network-error",
] as const) {
  test(`${scenario}: conserva la dirección manual y permite guardar sin sugerencia`, async ({
    page,
    rpc,
  }) => {
    await mockAddresses(page, () =>
      scenario === "empty"
        ? success()
        : scenario === "unavailable"
          ? { status: "unavailable", items: [] }
          : scenario === "rpc-error"
            ? { rpcError: true }
            : { networkError: true },
    );
    const form = await openNew(page);
    await manualContext(form);
    await (
      await addressInput(page, form)
    ).fill("Calle manual sin confirmar, 99");
    await expect(
      page.getByText(
        scenario === "empty"
          ? "Sin sugerencias. Puedes escribir la dirección y guardar igualmente."
          : unavailable,
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      form.getByRole("button", { name: "Guardar cliente", exact: true }),
    ).toBeEnabled();
    await form
      .getByRole("button", { name: "Guardar cliente", exact: true })
      .click();
    await expect(form).toBeHidden();
    expect(await savedCustomer(rpc)).toMatchObject({
      address: "Calle manual sin confirmar, 99",
      postal_code: "41099",
      city: "Municipio manual sintético",
      province: "Provincia manual sintética",
    });
  });
}

test("se puede guardar mientras busca y la respuesta posterior no altera la ficha ni el nuevo formulario", async ({
  page,
  rpc,
}) => {
  const arrived = signal(),
    release = signal();
  const remote = await mockAddresses(page, async () => {
    arrived.resolve();
    await release.promise;
    return success(first);
  });
  const form = await openNew(page);
  await manualContext(form);
  try {
    const input = await addressInput(page, form);
    await input.fill("Dirección guardada durante la consulta");
    await arrived.promise;
    await expect(input).toHaveAttribute("aria-busy", "true");
    await expect(
      page.getByText("Buscando direcciones…", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      form.getByRole("button", { name: "Guardar cliente", exact: true }),
    ).toBeEnabled();
    await form
      .getByRole("button", { name: "Guardar cliente", exact: true })
      .click();
    await expect(form).toBeHidden();
    await page
      .getByRole("button", { name: "Ir a inicio", exact: true })
      .click();
    await page.getByRole("button", { name: /Nuevo cliente/ }).click();
    const fresh = page.getByRole("dialog", {
      name: "Nuevo cliente",
      exact: true,
    });
    await expect(fresh).toBeVisible();
    release.resolve();
    await expect.poll(() => remote.completed.length).toBe(1);
    await flushResponse(page);
    await expect(
      fresh.getByRole("combobox", { name: "Dirección", exact: true }),
    ).toHaveValue("");
    await expect(
      page.getByRole("option", { name: first.label, exact: true }),
    ).toHaveCount(0);
    expect(await savedCustomer(rpc)).toMatchObject({
      address: "Dirección guardada durante la consulta",
      postal_code: "41099",
      city: "Municipio manual sintético",
    });
  } finally {
    release.resolve();
  }
});

test("adaptador de escritorio simulado: sondea sin bloquear y aplica el resultado antes de cancelar el trabajo", async ({
  page,
  rpc,
}) => {
  let polls = 0;
  const remote = await mockNativeAddresses(page, (action, params) => {
    if (action === "addresses.start")
      return { identifier: "synthetic-native-ready" };
    if (action === "addresses.result") {
      expect(params).toEqual({ identifier: "synthetic-native-ready" });
      return ++polls === 1
        ? { ready: false }
        : { ready: true, result: success(first) };
    }
    if (action === "addresses.cancel") return { cancelled: true };
    throw new Error("Unexpected address action: " + action);
  });
  const form = await openNew(page);
  await manualContext(form);
  await (await addressInput(page, form)).fill("Consulta nativa sintética");
  await page.getByRole("option", { name: first.label, exact: true }).click();
  await expectAddress(form, first);
  await expect
    .poll(
      () =>
        remote.calls.filter((call) => call.action === "addresses.cancel")
          .length,
    )
    .toBe(1);
  expect(polls).toBe(2);
  expect(
    remote.calls.filter((call) => call.action === "addresses.search"),
  ).toEqual([]);
  expect(
    remote.calls.find((call) => call.action === "addresses.start")?.params,
  ).toEqual({
    query: "Consulta nativa sintética",
    postal_code: "41099",
    city: "Municipio manual sintético",
    province: "Provincia manual sintética",
    country: "ES",
  });
  await form
    .getByRole("button", { name: "Guardar cliente", exact: true })
    .click();
  await expect(form).toBeHidden();
  expect(await savedCustomer(rpc)).toMatchObject({
    address: first.address,
    postal_code: first.postal_code,
    city: first.city,
    province: first.province,
  });
});

test("adaptador de escritorio simulado: cambiar la consulta y Escape cancelan los trabajos e ignoran sus respuestas tardías", async ({
  page,
}) => {
  const firstArrived = signal(),
    secondArrived = signal(),
    releaseFirst = signal(),
    releaseSecond = signal();
  const remote = await mockNativeAddresses(page, async (action, params) => {
    if (action === "addresses.start")
      return {
        identifier:
          params.query === "Consulta nativa anterior"
            ? "synthetic-native-old"
            : "synthetic-native-current",
      };
    if (action === "addresses.cancel") return { cancelled: true };
    if (action === "addresses.result") {
      if (params.identifier === "synthetic-native-old") {
        firstArrived.resolve();
        await releaseFirst.promise;
        return { ready: true, result: success(first) };
      }
      secondArrived.resolve();
      await releaseSecond.promise;
      return { ready: true, result: success(second) };
    }
    throw new Error("Unexpected address action: " + action);
  });
  const form = await openNew(page);
  const input = await addressInput(page, form);
  const cancelled = () =>
    remote.calls
      .filter((call) => call.action === "addresses.cancel")
      .map((call) => call.params.identifier);
  try {
    await manualContext(form);
    await input.fill("Consulta nativa anterior");
    await firstArrived.promise;
    await input.fill("Consulta nativa actual");
    await expect.poll(cancelled).toContain("synthetic-native-old");
    await secondArrived.promise;
    await input.press("Escape");
    await expect.poll(cancelled).toContain("synthetic-native-current");
    releaseFirst.resolve();
    releaseSecond.resolve();
    await expect
      .poll(
        () =>
          remote.completed.filter((action) => action === "addresses.result")
            .length,
      )
      .toBe(2);
    await flushResponse(page);
    await expect(form).toBeVisible();
    await expect(input).toHaveValue("Consulta nativa actual");
    await expect(input).toHaveAttribute("aria-expanded", "false");
    await expect(
      page.getByRole("listbox", { name: "Direcciones sugeridas", exact: true }),
    ).toBeHidden();
    await expectAddress(form, {
      address: "Consulta nativa actual",
      postal_code: "41099",
      city: "Municipio manual sintético",
      province: "Provincia manual sintética",
      country: "ES",
    });
    expect(
      remote.calls.filter((call) => call.action === "addresses.search"),
    ).toEqual([]);
  } finally {
    releaseFirst.resolve();
    releaseSecond.resolve();
  }
});

async function audit(page: Page, info: TestInfo, name: string) {
  await settle(page);
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  await info.attach(name + "-axe", {
    body: JSON.stringify(result.violations),
    contentType: "application/json",
  });
  expect(result.violations, JSON.stringify(result.violations)).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath(name + ".png"),
    fullPage: false,
  });
}

for (const theme of ["light", "dark"] as const) {
  for (const width of [320, 390, 768, 1366]) {
    test(`direcciones ${theme} a ${width} px: lista, teclado y formulario accesibles`, async ({
      page,
      rpc,
    }, info) => {
      const long = {
        ...first,
        label:
          "CalleSintéticaSinEspacios".repeat(8) +
          " · 28080 · Municipio sintético de etiqueta extensa · Provincia sintética",
      };
      await mockAddresses(page, () => success(long, second));
      await rpc("settings.save", { section: "appearance", values: { theme } });
      await page.setViewportSize({ width, height: 900 });
      const form = await openNew(page);
      await (
        await addressInput(page, form)
      ).fill("Dirección sintética extensa");
      const list = page.getByRole("listbox", {
        name: "Direcciones sugeridas",
        exact: true,
      });
      await expect(list.getByRole("option")).toHaveCount(2);
      const input = await addressInput(page, form);
      await expect(input).toHaveAttribute("aria-expanded", "true");
      const bounds = await list.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1);
      await audit(page, info, `direcciones-${theme}-${width}-lista`);
      await input.press("ArrowDown");
      await expect(list.getByRole("option").nth(1)).toHaveAttribute(
        "aria-selected",
        "true",
      );
      await input.press("Enter");
      await expectAddress(form, second);
      await expect(list).toBeHidden();
      await audit(page, info, `direcciones-${theme}-${width}-seleccion`);
    });
  }
}
