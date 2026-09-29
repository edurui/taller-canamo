import { test, expect } from "./fixtures";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

type Row = { id: string; version: number; [key: string]: unknown };

test("buscar matrícula conserva los kilómetros al crear, emitir y reabrir la factura", async ({
  page,
  rpc,
}) => {
  await rpc("settings.save", {
    section: "company",
    values: { legal_name: "TALLER SINTÉTICO", tax_id: "89890001K" },
  });
  const customer = await rpc<Row>("customers.save", {
    data: {
      name: "Kilómetros sintéticos",
      tax_id: "12345678Z",
      address: "Calle de prueba 1",
      postal_code: "41300",
      city: "Localidad sintética",
    },
  });
  const vehicle = await rpc<Row>("vehicles.save", {
    data: { customer_id: customer.id, plate: "0540BZD", km: 32000 },
  });
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
  });
  await search.fill("0540 bzd");
  await expect(page.getByRole("option").first()).toContainText("0540BZD");
  await search.press("Enter");
  await page
    .getByRole("button", { name: "Nueva factura", exact: true })
    .click();
  const kilometres = page.getByLabel("Kilómetros", { exact: true });
  await expect(kilometres).toHaveValue("32000");
  await kilometres.fill("32123");
  await page
    .getByLabel("Concepto 1", { exact: true })
    .fill("Revisión sintética");
  await page.getByLabel("Precio 1", { exact: true }).fill("10");
  await page.getByRole("button", { name: "Revisar y emitir" }).click();
  await page
    .getByRole("button", { name: "Emitir prueba", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/FAC-/);
  const number = await page.getByRole("heading", { level: 1 }).innerText();
  const listed = await rpc<{ items: Row[] }>("documents.list");
  const issued = await rpc<{ payload: { kilometres: number } }>(
    "documents.get",
    {
      identifier: listed.items[0].id,
    },
  );
  expect(issued.payload.kilometres).toBe(32123);
  await page.getByRole("button", { name: "Vista previa / PDF" }).click();
  await expect(page.getByTitle("Vista previa de la factura")).toBeVisible();
  const pdf = await rpc<{ content: string }>("documents.pdf", {
    identifier: listed.items[0].id,
  });
  const text = execFileSync(
    resolve(
      process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
    ),
    [
      "-c",
      "import base64,io,sys; from pypdf import PdfReader; print('\\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(sys.stdin.read()))).pages))",
    ],
    { input: pdf.content, encoding: "utf8" },
  );
  expect(text).toContain("Kilómetros: 32123");
  await page.keyboard.press("Escape");
  const latest = await rpc<Row>("vehicles.get", { identifier: vehicle.id });
  await rpc("vehicles.save", { data: { ...latest, km: 45000 } });
  await page.getByRole("button", { name: "Ver ficha", exact: true }).click();
  await page.getByRole("button", { name: number, exact: true }).click();
  await expect(kilometres).toHaveValue("32123");
});

test("una respuesta tardía del vehículo no pisa kilómetros escritos a mano", async ({
  page,
  rpc,
}) => {
  const customer = await rpc<Row>("customers.save", {
    data: { name: "Cliente de respuesta pendiente" },
  });
  await rpc("vehicles.save", {
    data: { customer_id: customer.id, plate: "5678BCD", km: 52000 },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Nueva factura/ }).click();
  let release!: () => void;
  let arrived!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const pending = new Promise<void>((resolve) => {
    arrived = resolve;
  });
  await page.route("**/api", async (route) => {
    const action = route.request().postDataJSON().action;
    if (action === "vehicles.list" || action === "vehicles.get") {
      const response = await route.fetch();
      arrived();
      await gate;
      await route.fulfill({ response });
    } else await route.continue();
  });
  try {
    const search = page.getByRole("combobox", {
      name: "Busca por nombre o matrícula",
      exact: true,
    });
    await search.fill("5678BCD");
    await expect(page.getByRole("option").first()).toContainText("5678BCD");
    await search.press("Enter");
    await pending;
    const kilometres = page.getByLabel("Kilómetros", { exact: true });
    await kilometres.fill("53001");
    release();
    await page
      .getByLabel("Concepto 1", { exact: true })
      .fill("Entrada sintética");
    await expect(kilometres).toHaveValue("53001");
    await page
      .getByRole("button", { name: "Guardar cambios", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Guardar borrador", exact: true }),
    ).toBeVisible();
    const listed = await rpc<{ items: Row[] }>("documents.list");
    const draft = await rpc<{ payload: { kilometres: number } }>(
      "documents.get",
      {
        identifier: listed.items[0].id,
      },
    );
    expect(draft.payload.kilometres).toBe(53001);
  } finally {
    release();
  }
});

test("la ficha permite abrir la factura 51 y reinicia la página al filtrar vehículo", async ({
  page,
  rpc,
}) => {
  const customer = await rpc<Row>("customers.save", {
    data: { name: "Historial sintético completo" },
  });
  const vehicle = await rpc<Row>("vehicles.save", {
    data: { customer_id: customer.id, plate: "9012BCD" },
  });
  for (let index = 0; index < 51; index++) {
    await rpc("documents.save", {
      data: {
        customer_id: customer.id,
        vehicle_id: index === 0 ? vehicle.id : "",
        lines: [{ description: `Trabajo sintético ${index}`, unit_price: "1" }],
      },
    });
  }
  const lastPage = await rpc<{ total: number; items: Row[] }>(
    "documents.list",
    {
      customer_id: customer.id,
      page: 1,
    },
  );
  expect(lastPage.total).toBe(51);
  expect(lastPage.items).toHaveLength(1);
  const oldest = await rpc<{ payload: { lines: { description: string }[] } }>(
    "documents.get",
    {
      identifier: lastPage.items[0].id,
    },
  );
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
  });
  await search.fill("Historial sintético completo");
  await expect(page.getByRole("option").first()).toBeVisible();
  await search.press("Enter");
  await page
    .getByRole("button", { name: "Ver todos los vehículos", exact: true })
    .click();
  const history = page.locator("section").filter({
    has: page.getByRole("heading", {
      name: "Historial de facturas",
      exact: true,
    }),
  });
  await expect(history.locator("tbody tr")).toHaveCount(50);
  await history.getByRole("button", { name: "Siguiente", exact: true }).click();
  await expect(history.locator("tbody tr")).toHaveCount(1);
  await history.getByRole("button", { name: "Borrador", exact: true }).click();
  await expect(page.getByLabel("Concepto 1", { exact: true })).toHaveValue(
    oldest.payload.lines[0].description,
  );
  await page.getByRole("button", { name: "Ver ficha", exact: true }).click();
  await history.getByRole("button", { name: "Siguiente", exact: true }).click();
  await page
    .getByRole("button", { name: /9012BCD/ })
    .first()
    .click();
  await expect(history.locator("tbody tr")).toHaveCount(1);
  await expect(
    history.getByRole("button", { name: "Siguiente", exact: true }),
  ).toHaveCount(0);
});

test("búsqueda exacta de código, NIF y teléfono; alta de contacto extranjero sin datos fiscales", async ({
  page,
  rpc,
}) => {
  await rpc("customers.save", {
    data: {
      name: "A coincidencia parcial sintética",
      legacy_code: "1001",
      tax_id: "912345678Z",
      phone: "960 012 345 6",
    },
  });
  await rpc("customers.save", {
    data: {
      name: "Z coincidencia exacta sintética",
      legacy_code: "001",
      tax_id: "12345678Z",
      phone: "600 123 456",
    },
  });
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
  });
  for (const query of ["001", "12345678-z", "600-123-456"]) {
    await search.fill(query);
    await expect(page.getByRole("option").first()).toContainText(
      "Z coincidencia exacta sintética",
    );
    await expect(page.getByRole("option").first()).toHaveAttribute(
      "aria-selected",
      "true",
    );
  }
  await search.press("Enter");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Z coincidencia exacta sintética",
  );
  await page.getByRole("button", { name: "Ir a inicio" }).click();
  await page.getByRole("button", { name: /Nuevo cliente/ }).click();
  const form = page.getByRole("dialog", { name: "Nuevo cliente", exact: true });
  await form
    .getByLabel("Nombre o razón social")
    .fill("Contacto portugués sintético");
  await form.getByLabel("País (dos letras)").fill("pt");
  await form.getByLabel("Código postal").fill("4700-235");
  await form.getByRole("button", { name: "Guardar cliente" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Contacto portugués sintético",
  );
  await page.getByRole("button", { name: "Editar ficha", exact: true }).click();
  const saved = page.getByRole("dialog", {
    name: "Editar cliente",
    exact: true,
  });
  await expect(saved.getByLabel("País (dos letras)")).toHaveValue("PT");
  await expect(saved.getByLabel("Código postal")).toHaveValue("4700-235");
  await expect(saved.getByLabel("NIF / CIF")).toHaveValue("");
});

test("alta de vehículo desde factura usa sus km y protege la edición durante su carga", async ({
  page,
  rpc,
}) => {
  await rpc("customers.save", { data: { name: "Cliente de vehículo nuevo" } });
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
  });
  await search.fill("Cliente de vehículo nuevo");
  await expect(page.getByRole("option").first()).toBeVisible();
  await search.press("Enter");
  await page
    .getByRole("button", { name: "Nueva factura", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Añadir vehículo", exact: true })
    .click();
  const vehicleForm = page.getByRole("dialog", {
    name: "Añadir vehículo",
    exact: true,
  });
  await vehicleForm
    .getByRole("textbox", { name: "Matrícula", exact: true })
    .fill("3456BCD");
  await vehicleForm.getByLabel("Kilómetros actuales").fill("82000");
  await vehicleForm.getByRole("button", { name: "Guardar vehículo" }).click();
  await expect(vehicleForm).toBeHidden();
  const kilometres = page.getByLabel("Kilómetros", { exact: true });
  await expect(kilometres).toHaveValue("82000");

  let releaseCreation!: () => void;
  let creationArrived!: () => void;
  let releaseKilometres!: () => void;
  let kilometresArrived!: () => void;
  const creationGate = new Promise<void>((resolve) => {
    releaseCreation = resolve;
  });
  const creationPending = new Promise<void>((resolve) => {
    creationArrived = resolve;
  });
  const kilometresGate = new Promise<void>((resolve) => {
    releaseKilometres = resolve;
  });
  const kilometresPending = new Promise<void>((resolve) => {
    kilometresArrived = resolve;
  });
  await page.route("**/api", async (route) => {
    const action = route.request().postDataJSON().action;
    if (action === "vehicles.save" || action === "vehicles.get") {
      const response = await route.fetch();
      if (action === "vehicles.save") {
        creationArrived();
        await creationGate;
      } else {
        kilometresArrived();
        await kilometresGate;
      }
      await route.fulfill({ response });
    } else await route.continue();
  });
  try {
    await page
      .getByRole("button", { name: "Añadir vehículo", exact: true })
      .click();
    await vehicleForm
      .getByRole("textbox", { name: "Matrícula", exact: true })
      .fill("3457BCD");
    await vehicleForm.getByLabel("Kilómetros actuales").fill("83000");
    await vehicleForm.getByRole("button", { name: "Guardar vehículo" }).click();
    await creationPending;
    await expect(
      vehicleForm.getByRole("button", { name: "Cancelar", exact: true }),
    ).toBeDisabled();
    releaseCreation();
    await expect(vehicleForm).toBeHidden();
    await kilometresPending;
    await kilometres.fill("83007");
    releaseKilometres();
    await page
      .getByLabel("Concepto 1", { exact: true })
      .fill("Entrada de vehículo sintético");
    await expect(kilometres).toHaveValue("83007");
    await page
      .getByRole("button", { name: "Guardar cambios", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Guardar borrador", exact: true }),
    ).toBeVisible();
    const listed = await rpc<{ items: Row[] }>("documents.list");
    const saved = await rpc<{
      payload: { kilometres: number };
      vehicle_id: string;
    }>("documents.get", {
      identifier: listed.items[0].id,
    });
    expect(saved.payload.kilometres).toBe(83007);
    const selected = await rpc<{ plate: string }>("vehicles.get", {
      identifier: saved.vehicle_id,
    });
    expect(selected.plate).toBe("3457BCD");
  } finally {
    releaseCreation();
    releaseKilometres();
  }
});
