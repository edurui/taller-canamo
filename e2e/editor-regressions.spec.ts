import { test, expect } from "./fixtures";

test("el buscador no abre una coincidencia anterior mientras llega la nueva consulta", async ({
  page,
  rpc,
}) => {
  await rpc("customers.save", {
    data: { name: "Ana Sintética", phone: "612000101" },
  });
  await rpc("customers.save", {
    data: { name: "Bruno Sintético", phone: "612000202" },
  });
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
  });
  await search.fill("Ana");
  await expect(page.getByRole("option")).toContainText("Ana Sintética");
  const previousList = await page.getByRole("listbox").elementHandle();
  let release!: () => void;
  let arrived!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const pending = new Promise<void>((resolve) => {
    arrived = resolve;
  });
  await page.route("**/api", async (route) => {
    const body = route.request().postDataJSON();
    if (body.action === "customers.search" && body.params.query === "Bruno") {
      const response = await route.fetch(); // Real backend, delayed delivery only.
      arrived();
      await gate;
      await route.fulfill({ response });
    } else await route.continue();
  });
  try {
    await search.fill("Bruno");
    await pending;
    await search.press("Enter");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Tu taller, a punto.",
    );
    await expect(page.getByRole("option")).toContainText("Ana Sintética");
    await expect(page.getByRole("option")).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await expect(page.getByRole("listbox")).toBeVisible();
    expect(await previousList!.evaluate((element) => element.isConnected)).toBe(
      true,
    );
    await expect(search).toBeFocused();
    release();
    await expect(page.getByRole("option")).toContainText("Bruno Sintético");
    await search.press("Enter");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Bruno Sintético",
    );
  } finally {
    release();
  }
});

test("editar durante guardado conserva texto nuevo y Ctrl+P funciona tras emitir", async ({
  page,
  rpc,
}) => {
  await rpc("settings.save", {
    section: "company",
    values: { legal_name: "TALLER FICTICIO", tax_id: "89890001K" },
  });
  await rpc("customers.save", {
    data: {
      name: "Cliente Sintético",
      tax_id: "12345678Z",
      address: "Calle ficticia 1",
      postal_code: "41300",
      city: "Localidad ficticia",
    },
  });
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
  });
  await search.fill("Cliente");
  await expect(page.getByRole("option")).toBeVisible();
  await search.press("Enter");
  await page
    .getByRole("button", { name: "Nueva factura", exact: true })
    .click();
  const concept = page.getByLabel("Concepto 1", { exact: true });
  await concept.fill("Versión enviada a guardar");
  await page.getByLabel("Precio 1", { exact: true }).fill("20");
  let release!: () => void;
  let arrived!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const pending = new Promise<void>((resolve) => {
    arrived = resolve;
  });
  let held = false;
  await page.route("**/api", async (route) => {
    if (!held && route.request().postDataJSON().action === "documents.save") {
      held = true;
      const response = await route.fetch();
      arrived();
      await gate;
      await route.fulfill({ response });
    } else await route.continue();
  });
  try {
    await page
      .getByRole("button", { name: "Guardar cambios", exact: true })
      .click();
    await pending;
    await concept.fill("Texto nuevo que debe conservarse");
    release();
    await expect(page.getByRole("alert")).toContainText("Has seguido editando");
    await expect(concept).toHaveValue("Texto nuevo que debe conservarse");
    await page
      .getByRole("button", { name: "Guardar cambios", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Guardar borrador", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Revisar y emitir" }).click();
    await page
      .getByRole("button", { name: "Emitir prueba", exact: true })
      .click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/FAC-/);
    await page.keyboard.press("Control+p");
    await expect(
      page.getByRole("dialog").getByTitle("Vista previa de la factura"),
    ).toBeVisible();
    const docs = await rpc<{ items: { id: string }[] }>("documents.list");
    const document = await rpc<{
      payload: { lines: { description: string }[] };
    }>("documents.get", { identifier: docs.items[0].id });
    expect(document.payload.lines[0].description).toBe(
      "Texto nuevo que debe conservarse",
    );
  } finally {
    release();
  }
});

test("una confirmación pendiente no se cierra con Escape", async ({
  page,
  rpc,
}) => {
  await rpc("settings.save", {
    section: "company",
    values: { legal_name: "TALLER FICTICIO", tax_id: "89890001K" },
  });
  const customer = await rpc<{ id: string }>("customers.save", {
    data: {
      name: "Emisión Sintética",
      tax_id: "12345678Z",
      address: "Prueba 1",
      postal_code: "41300",
      city: "Localidad ficticia",
    },
  });
  await rpc("documents.save", {
    data: {
      customer_id: customer.id,
      lines: [
        {
          description: "Prueba",
          quantity: "1",
          unit_price: "5",
          tax_rate: "21",
        },
      ],
    },
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Facturas", exact: true }).click();
  await page
    .getByRole("button", { name: "Borrador sin número", exact: true })
    .click();
  await page.getByRole("button", { name: "Revisar y emitir" }).click();
  let release!: () => void;
  let arrived!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const pending = new Promise<void>((resolve) => {
    arrived = resolve;
  });
  await page.route("**/api", async (route) => {
    if (route.request().postDataJSON().action === "documents.publish") {
      const response = await route.fetch();
      arrived();
      await gate;
      await route.fulfill({ response });
    } else await route.continue();
  });
  try {
    await page
      .getByRole("button", { name: "Emitir prueba", exact: true })
      .click();
    await pending;
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("dialog", { name: "Confirmar emisión de prueba" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Emitir prueba", exact: true }),
    ).toBeDisabled();
    release();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/FAC-/);
  } finally {
    release();
  }
});
