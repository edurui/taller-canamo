import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";
import { test, expect, chooseOption, navigateSidebar } from "./fixtures";

type Rpc = <T = Record<string, unknown>>(
  action: string,
  params?: Record<string, unknown>,
) => Promise<T>;
type RecordRow = {
  id: string;
  version: number;
  full_number: string;
  [key: string]: unknown;
};

async function seed(rpc: Rpc) {
  await rpc("settings.save", {
    section: "company",
    values: {
      legal_name: "TALLER DE NAVEGACIÓN SINTÉTICO",
      tax_id: "89890001K",
    },
  });
  const customer = await rpc<RecordRow>("customers.save", {
    data: {
      name: "Cliente navegación sintético",
      tax_id: "12345678Z",
      address: "Dirección sintética",
      postal_code: "41300",
      city: "Localidad sintética",
    },
  });
  const replacement = await rpc<RecordRow>("customers.save", {
    data: { name: "Segundo titular sintético" },
  });
  const vehicle = await rpc<RecordRow>("vehicles.save", {
    data: {
      customer_id: customer.id,
      plate: "NAV-001",
      kind: "Vehículo sintético de navegación",
    },
  });
  const document = await rpc<RecordRow>("documents.save", {
    data: {
      customer_id: customer.id,
      vehicle_id: vehicle.id,
      lines: [
        {
          description: "Trabajo sintético navegable",
          quantity: "1",
          unit_price: "10",
          tax_rate: "21",
        },
      ],
    },
  });
  return { customer, replacement, vehicle, document };
}

async function sidebar(page: Page, name: string) {
  await navigateSidebar(page, name);
}

async function audit(page: Page, info: TestInfo, name: string) {
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
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  await info.attach(name + "-axe", {
    body: JSON.stringify(result.violations),
    contentType: "application/json",
  });
  expect(result.violations).toEqual([]);
  await page.screenshot({
    path: info.outputPath(name + ".png"),
    fullPage: true,
  });
}

test("cliente, vehículo y titulares se abren por sus referencias sin activar la fila contenedora", async ({
  page,
  rpc,
}) => {
  const { customer, replacement, vehicle } = await seed(rpc);
  // A legacy row can retain an empty display label despite having a real ID.
  // Only this synthetic list response changes; the linked vehicle stays real.
  let legacyLabelApplied = false;
  await page.route("**/api", async (route) => {
    if (
      route.request().postDataJSON().action !== "customers.list" ||
      legacyLabelApplied
    ) {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    const body = await response.json();
    const owner = body.result.items.find(
      (item: { id: string }) => item.id === customer.id,
    );
    owner.vehicles.find(
      (item: { id: string }) => item.id === vehicle.id,
    ).plate = " \t ";
    legacyLabelApplied = true;
    await route.fulfill({ response, json: body });
  });
  await page.goto("/");
  await sidebar(page, "Clientes");
  const vehicleReference = page
    .getByRole("table", { name: "Clientes", exact: true })
    .getByRole("button", { name: "Consultar vehículo", exact: true });
  await vehicleReference.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("NAV-001");
  await page
    .locator(".vehicle-owner-card")
    .first()
    .getByRole("button", { name: "Cliente navegación sintético", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Cliente navegación sintético",
  );
  await rpc("vehicles.transfer", {
    identifier: vehicle.id,
    customer_id: replacement.id,
    reason: "Cambio sintético documentado",
  });
  await rpc("customers.archive", { identifier: customer.id, archived: true });
  await sidebar(page, "Vehículos");
  const row = page.getByRole("row").filter({ hasText: "NAV-001" });
  await row
    .getByRole("button", { name: "Segundo titular sintético", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Segundo titular sintético",
  );
  await page
    .getByRole("button", { name: "Historial y titular", exact: true })
    .click();
  await page
    .locator(".vehicle-owners")
    .getByRole("button", { name: "Cliente navegación sintético", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Cliente navegación sintético",
  );
  expect(
    (await rpc<RecordRow>("customers.get", { identifier: customer.id }))
      .archived,
  ).toBe(1);
});

test("facturas e inicio conservan la etiqueta histórica y abren la identidad real con teclado", async ({
  page,
  rpc,
}) => {
  const { customer, vehicle, document } = await seed(rpc);
  const issued = await rpc<RecordRow>("documents.publish", {
    identifier: document.id,
  });
  const current = await rpc<RecordRow>("customers.get", {
    identifier: customer.id,
  });
  await rpc("customers.save", {
    data: { ...current, name: "Ficha actual renombrada sintética" },
  });
  const latestVehicle = await rpc<RecordRow>("vehicles.get", {
    identifier: vehicle.id,
  });
  await rpc("vehicles.save", { data: { ...latestVehicle, plate: "NAV-002" } });
  await page.goto("/");
  await sidebar(page, "Facturas");
  let row = page.getByRole("row").filter({ hasText: issued.full_number });
  await row
    .getByRole("button", { name: "Cliente navegación sintético", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Ficha actual renombrada sintética",
  );
  const historical = page
    .getByRole("row")
    .filter({ hasText: issued.full_number });
  await historical
    .getByRole("button", { name: "NAV-001", exact: true })
    .focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("NAV-002");
  await page
    .getByRole("button", { name: issued.full_number, exact: true })
    .click();
  await expect(page.locator(".selected-customer")).toContainText(
    "Cliente navegación sintético",
  );
  await page
    .getByRole("button", { name: "Ver vehículo: NAV-001", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("NAV-002");
  await sidebar(page, "Inicio");
  row = page.getByRole("row").filter({ hasText: issued.full_number });
  await row
    .getByRole("button", { name: "Cliente navegación sintético", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Ficha actual renombrada sintética",
  );
});

test("referencias del editor, inicio y regreso al listado respetan los cambios sin guardar", async ({
  page,
  rpc,
}) => {
  const { document } = await seed(rpc);
  await page.goto("/");
  await sidebar(page, "Facturas");
  await page
    .getByRole("button", { name: "Borrador sin número", exact: true })
    .click();
  const concept = page.getByLabel("Concepto 1", { exact: true });
  await concept.fill("Trabajo sintético aún sin guardar");
  for (const name of [
    "Cliente navegación sintético",
    "Ver vehículo: NAV-001",
  ]) {
    await page
      .locator("#main-content")
      .getByRole("button", { name, exact: true })
      .click();
    const confirmation = page.getByRole("dialog", {
      name: "Hay cambios sin guardar",
    });
    await expect(confirmation).toBeVisible();
    await confirmation
      .getByRole("button", { name: "Volver", exact: true })
      .click();
    await expect(concept).toHaveValue("Trabajo sintético aún sin guardar");
  }
  await page.locator(".back-link").click();
  await page
    .getByRole("dialog", { name: "Hay cambios sin guardar" })
    .getByRole("button", { name: "Volver", exact: true })
    .click();
  await sidebar(page, "Inicio");
  await page
    .getByRole("dialog", { name: "Hay cambios sin guardar" })
    .getByRole("button", { name: "Volver", exact: true })
    .click();
  await expect(concept).toHaveValue("Trabajo sintético aún sin guardar");
  const unchanged = await rpc<{
    payload: { lines: { description: string }[] };
  }>("documents.get", { identifier: document.id });
  expect(unchanged.payload.lines[0].description).toBe(
    "Trabajo sintético navegable",
  );
  await page
    .getByRole("button", { name: "Guardar cambios", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Guardar borrador", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Ver vehículo: NAV-001", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("NAV-001");
  await page.getByRole("button", { name: "Borrador", exact: true }).click();
  await expect(concept).toHaveValue("Trabajo sintético aún sin guardar");
});

test("registros fiscales y B2B abren la factura vinculada conservada", async ({
  page,
  rpc,
}) => {
  const { document } = await seed(rpc);
  const issued = await rpc<RecordRow>("documents.publish", {
    identifier: document.id,
  });
  await rpc("b2b.prepare", {
    document_id: issued.id,
    recipient_business: true,
  });
  await page.goto("/");
  await sidebar(page, "Configuración");
  await page
    .getByRole("button", { name: "Factura electrónica B2B", exact: true })
    .click();
  await page
    .getByRole("row")
    .filter({ hasText: issued.full_number })
    .getByRole("button", { name: `Acciones de ${issued.full_number}`, exact: true })
    .click();
  await page.getByRole("menuitem", { name: "Ver factura original", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    issued.full_number,
  );
  await sidebar(page, "Configuración");
  await page
    .getByRole("button", { name: "Factura electrónica B2B", exact: true })
    .click();
  await chooseOption(
    page.getByRole("combobox", { name: "Factura emitida", exact: true }),
    issued.id,
  );
  await page
    .locator(".entity-reference")
    .filter({ hasText: "Cliente navegación sintético" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Cliente navegación sintético",
  );
  await sidebar(page, "Configuración");
  await page
    .getByRole("button", { name: "VERI*FACTU (pruebas)", exact: true })
    .click();
  let fiscalTransports = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().endsWith("/api") &&
      ["certificate.save", "fiscal.send"].includes(
        request.postDataJSON().action,
      )
    )
      fiscalTransports++;
  });
  const producer = page.getByLabel("Nombre fiscal del productor", {
    exact: true,
  });
  const password = page.getByLabel("Contraseña del certificado", {
    exact: true,
  });
  const certificate = page.getByLabel("Certificado PFX o P12", { exact: true });
  await producer.fill("Productor sintético sin guardar");
  await password.fill("contraseña ficticia inválida");
  await certificate.setInputFiles({
    name: "ficticio.pfx",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("SYNTHETIC-NON-CERTIFICATE"),
  });
  const fiscalRow = page
    .getByRole("row")
    .filter({ hasText: issued.full_number });
  const fiscalReference = fiscalRow.getByRole("button", {
    name: issued.full_number,
    exact: true,
  });
  const unsaved = page.getByRole("dialog", {
    name: "Cambios fiscales sin guardar",
    exact: true,
  });
  await fiscalReference.click();
  await unsaved.getByRole("button", { name: "Volver", exact: true }).click();
  await expect(producer).toHaveValue("Productor sintético sin guardar");
  await expect(password).toHaveValue("contraseña ficticia inválida");
  expect(
    await certificate.evaluate(
      (node) => (node as HTMLInputElement).files?.[0]?.name,
    ),
  ).toBe("ficticio.pfx");
  await fiscalRow.getByRole("button", { name: /^Acciones de / }).click();
  await page.getByRole("menuitem", { name: "Detalle", exact: true }).click();
  const fiscalDetail = page.getByRole("dialog", {
    name: "Detalle del registro",
    exact: true,
  });
  await fiscalDetail
    .getByRole("button", { name: issued.full_number, exact: true })
    .click();
  await unsaved.getByRole("button", { name: "Volver", exact: true }).click();
  await fiscalDetail
    .getByRole("button", { name: "Cerrar ventana", exact: true })
    .click();
  await expect(producer).toHaveValue("Productor sintético sin guardar");
  await fiscalReference.click();
  await unsaved
    .getByRole("button", { name: "Salir sin guardar", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    issued.full_number,
  );
  expect(fiscalTransports).toBe(0);
});

test("resumen abre artículo y proveedor por ID, incluso archivado, y la consulta conserva el formulario", async ({
  page,
  rpc,
}) => {
  const { document, customer, vehicle } = await seed(rpc);
  await rpc("suppliers.save", {
    data: { name: "Proveedor duplicado sintético", tax_id: "OTRO-SINTETICO" },
  });
  const supplier = await rpc<RecordRow>("suppliers.save", {
    data: {
      name: "Proveedor duplicado sintético",
      tax_id: "CORRECTO-SINTETICO",
      notes: "Notas sintéticas de la ficha vinculada",
    },
  });
  const product = await rpc<RecordRow>("products.save", {
    data: {
      name: "Artículo enlazado sintético",
      supplier_id: supplier.id,
      unit_price: "10",
      min_stock: "2",
      track_stock: true,
    },
  });
  await rpc("suppliers.archive", { identifier: supplier.id, archived: true });
  await page.goto("/");
  await sidebar(page, "Resumen");
  await page
    .getByRole("button", { name: "Artículo enlazado sintético", exact: true })
    .click();
  const edit = page.getByRole("dialog", {
    name: "Editar artículo",
    exact: true,
  });
  await expect(
    edit.getByRole("textbox", { name: "Nombre", exact: true }),
  ).toHaveValue("Artículo enlazado sintético");
  await edit
    .getByRole("textbox", { name: "Nombre", exact: true })
    .fill("Cambio local sin perder");
  await edit
    .getByRole("button", {
      name: "Consultar Proveedor duplicado sintético",
      exact: true,
    })
    .click();
  const detail = page.getByRole("dialog", {
    name: "Proveedor duplicado sintético",
    exact: true,
  });
  await expect(detail).toContainText("CORRECTO-SINTETICO");
  await expect(detail).toContainText("Proveedor archivado");
  await detail
    .getByRole("button", { name: "Volver al artículo", exact: true })
    .click();
  await expect(
    edit.getByRole("textbox", { name: "Nombre", exact: true }),
  ).toHaveValue("Cambio local sin perder");
  await edit.getByRole("button", { name: "Cancelar", exact: true }).click();
  await sidebar(page, "Resumen");
  await page
    .getByRole("button", { name: "Proveedor duplicado sintético", exact: true })
    .click();
  const supplierEdit = page.getByRole("dialog", {
    name: "Editar proveedor",
    exact: true,
  });
  await expect(
    supplierEdit.getByLabel("NIF / CIF", { exact: true }),
  ).toHaveValue("CORRECTO-SINTETICO");
  await supplierEdit
    .getByRole("button", { name: "Cancelar", exact: true })
    .click();
  const latest = await rpc<RecordRow>("documents.get", {
    identifier: document.id,
  });
  await rpc("documents.save", {
    data: {
      id: document.id,
      version: latest.version,
      customer_id: customer.id,
      vehicle_id: vehicle.id,
      lines: [
        {
          product_id: product.id,
          description: "Descripción histórica del artículo",
          quantity: "1",
          unit_price: "10",
          tax_rate: "21",
        },
      ],
    },
  });
  await rpc("products.archive", { identifier: product.id, archived: true });
  await sidebar(page, "Facturas");
  await page
    .getByRole("button", { name: "Borrador sin número", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Consultar artículo vinculado", exact: true })
    .click();
  await expect(
    edit.getByRole("textbox", { name: "Nombre", exact: true }),
  ).toHaveValue("Artículo enlazado sintético");
});

test("movimiento de almacén consulta el documento sólo al pulsar y protege entradas locales", async ({
  page,
  rpc,
}) => {
  const { document } = await seed(rpc);
  const product = await rpc<RecordRow>("products.save", {
    data: {
      name: "Artículo movimiento sintético",
      unit_price: "10",
      track_stock: true,
    },
  });
  await rpc("products.move", {
    product_id: product.id,
    quantity: "1",
    reason: "Entrada vinculada sintética",
    document_id: document.id,
    idempotency_key: "entity-navigation-stock",
  });
  await page.goto("/");
  await sidebar(page, "Artículos y stock");
  await page
    .getByRole("row")
    .filter({ hasText: "Artículo movimiento sintético" })
    .getByRole("button", { name: /^Acciones de / })
    .click();
  await page.getByRole("menuitem", { name: "Existencias", exact: true }).click();
  const stock = page.getByRole("dialog", {
    name: "Existencias · Artículo movimiento sintético",
    exact: true,
  });
  await stock
    .getByRole("textbox", { name: "Motivo", exact: true })
    .fill("Entrada local pendiente");
  await stock
    .getByRole("button", {
      name: "Consultar documento del movimiento",
      exact: true,
    })
    .click();
  const confirm = page.getByRole("dialog", {
    name: "Movimiento sin registrar",
    exact: true,
  });
  await confirm.getByRole("button", { name: "Volver", exact: true }).click();
  await expect(
    stock.getByRole("textbox", { name: "Motivo", exact: true }),
  ).toHaveValue("Entrada local pendiente");
  await stock
    .getByRole("button", {
      name: "Consultar documento del movimiento",
      exact: true,
    })
    .click();
  await confirm
    .getByRole("button", { name: "Salir sin registrar", exact: true })
    .click();
  await expect(page.getByLabel("Concepto 1", { exact: true })).toHaveValue(
    "Trabajo sintético navegable",
  );
  const movements = await rpc<unknown[]>("products.movements", {
    product_id: product.id,
  });
  expect(movements).toHaveLength(1);
});

for (const theme of ["light", "dark"] as const) {
  test(`referencias visibles y accesibles a 320 px en ${theme}`, async ({
    page,
    rpc,
  }, info) => {
    await seed(rpc);
    await rpc("settings.save", { section: "appearance", values: { theme } });
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto("/");
    await sidebar(page, "Clientes");
    await expect(
      page.getByRole("button", { name: "NAV-001", exact: true }),
    ).toBeVisible();
    await audit(page, info, `clientes-${theme}`);
    await page.getByRole("button", { name: "NAV-001", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("NAV-001");
    await audit(page, info, `vehiculo-${theme}`);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Borrador", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Ver vehículo: NAV-001", exact: true }),
    ).toBeVisible();
    await audit(page, info, `editor-${theme}`);
  });
}
