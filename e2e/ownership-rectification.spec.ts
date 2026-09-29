import { chooseOption } from "./fixtures";
import { test, expect } from "./fixtures";

type RecordRow = {
  id: string;
  full_number: string;
  version: number;
  [key: string]: unknown;
};

test("cambiar titular conserva factura, matrícula original y teléfono del nuevo dueño", async ({
  page,
  rpc,
  backend,
}) => {
  await rpc("settings.save", {
    section: "company",
    values: { legal_name: "TALLER SINTÉTICO", tax_id: "89890001K" },
  });
  const original = await rpc<RecordRow>("customers.save", {
    data: {
      name: "Titular anterior sintético",
      tax_id: "12345678Z",
      phone: "612000010",
      address: "Calle de prueba",
      postal_code: "41300",
      city: "Localidad sintética",
    },
  });
  const replacement = await rpc<RecordRow>("customers.save", {
    data: {
      name: "Titular nuevo sintético",
      tax_id: "00000000T",
      phone: "612000020",
    },
  });
  const vehicle = await rpc<RecordRow>("vehicles.save", {
    data: {
      customer_id: original.id,
      plate: "0345BCD",
      make: "Prueba",
      model: "Sintético",
      km: 160000,
    },
  });
  const draft = await rpc<RecordRow>("documents.save", {
    data: {
      customer_id: original.id,
      vehicle_id: vehicle.id,
      lines: [
        {
          description: "Mantenimiento con titular anterior",
          quantity: "1",
          unit_price: "100",
          tax_rate: "21",
        },
      ],
    },
  });
  const invoice = await rpc<RecordRow>("documents.publish", {
    identifier: draft.id,
  });
  const originalPDF = await rpc<{ content: string }>("documents.pdf", {
    identifier: invoice.id,
  });
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
    exact: true,
  });
  await search.fill("0345 bcd");
  await expect(page.getByRole("option").first()).toContainText("612000010");
  await search.press("Enter");
  await page
    .getByRole("button", { name: "Historial y titular", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Cambiar propietario", exact: true })
    .click();
  const transfer = page.getByRole("dialog", {
    name: "Cambiar propietario",
    exact: true,
  });
  const owner = transfer.getByRole("combobox");
  await owner.fill("Titular nuevo");
  await expect(page.getByRole("option").first()).toContainText("612000020");
  await owner.press("Enter");
  await transfer
    .getByLabel("Motivo del cambio de propietario")
    .fill("Compraventa sintética documentada");
  await transfer
    .getByRole("button", { name: "Confirmar cambio de titular" })
    .click();
  await expect(transfer).toBeHidden();
  await expect(
    page
      .locator("section")
      .filter({
        has: page.getByRole("heading", { name: "Titular actual", exact: true }),
      }),
  ).toContainText("Titular nuevo sintético");
  const row = page.getByRole("row").filter({ hasText: invoice.full_number });
  await expect(row).toContainText("Titular anterior sintético");
  await row
    .getByRole("button", { name: invoice.full_number, exact: true })
    .click();
  await expect(page.locator(".selected-customer")).toContainText(
    "Titular anterior sintético",
  );
  expect(
    (
      await rpc<{ content: string }>("documents.pdf", {
        identifier: invoice.id,
      })
    ).content,
  ).toBe(originalPDF.content);
  await backend.restart();
  await page.reload();
  await search.fill("0345bcd");
  await expect(page.getByRole("option").first()).toContainText("612000020");
  const current = await rpc<{ customer_id: string; owners: unknown[] }>(
    "vehicles.get",
    { identifier: vehicle.id },
  );
  expect(current.customer_id).toBe(replacement.id);
  expect(current.owners).toHaveLength(2);
});

test("R3 por cuota conserva base cero y fecha original al revisar, guardar y emitir", async ({
  page,
  rpc,
}) => {
  await rpc("settings.save", {
    section: "company",
    values: { legal_name: "TALLER SINTÉTICO", tax_id: "89890001K" },
  });
  const customer = await rpc<RecordRow>("customers.save", {
    data: {
      name: "Cliente de cuota sintético",
      tax_id: "12345678Z",
      address: "Calle de pruebas",
      postal_code: "41300",
      city: "Localidad sintética",
    },
  });
  const draft = await rpc<RecordRow>("documents.save", {
    data: {
      customer_id: customer.id,
      operation_date: "2025-01-17",
      lines: [
        {
          description: "Trabajo original sintético",
          quantity: "1",
          unit_price: "100",
          tax_rate: "21",
        },
      ],
    },
  });
  const original = await rpc<RecordRow>("documents.publish", {
    identifier: draft.id,
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Facturas", exact: true }).click();
  await page
    .getByRole("button", { name: original.full_number, exact: true })
    .click();
  await page
    .getByRole("button", { name: "Crear rectificativa", exact: true })
    .click();
  const correction = page.getByRole("dialog", {
    name: "Crear factura rectificativa",
    exact: true,
  });
  await correction
    .getByRole("textbox", { name: "Motivo", exact: true })
    .fill("Incobro sintético: supuesto documentado de prueba");
  await chooseOption(correction
    .getByRole("combobox", { name: "Tipo de rectificación", exact: true }), "R3");
  await expect(
    correction.getByLabel(/Fecha de operación original/),
  ).toHaveValue("2025-01-17");
  await correction
    .getByRole("textbox", { name: "Cuota rectificativa en EUR 1", exact: true })
    .fill("-21,00");
  await correction
    .getByRole("button", { name: "Crear borrador rectificativo", exact: true })
    .click();
  await expect(correction).toBeHidden();
  await expect(page.getByLabel("Precio 1", { exact: true })).toBeDisabled();
  await expect(page.getByLabel("IVA 1", { exact: true })).toBeDisabled();
  await expect(
    page.getByLabel("Cuota IVA 21 % (EUR)", { exact: true }),
  ).toHaveValue("-21.00");
  await page.getByLabel("Cuota IVA 21 % (EUR)", { exact: true }).fill("-10,50");
  await expect(page.locator(".summary-total")).toContainText("-10,50");
  await page
    .getByRole("button", { name: "Revisar y emitir", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Emitir prueba", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /^REC-\d{4}-00001$/,
  );
  const rows = await rpc<{ items: RecordRow[] }>("documents.list");
  const created = rows.items.find((item) => item.id !== original.id)!;
  const data = await rpc<{
    base_cents: number;
    tax_cents: number;
    total_cents: number;
    payload: { operation_date: string; correction_mode: string };
  }>("documents.get", { identifier: created.id });
  expect(data.base_cents).toBe(0);
  expect(data.tax_cents).toBe(-1050);
  expect(data.total_cents).toBe(-1050);
  expect(data.payload.operation_date).toBe("2025-01-17");
  expect(data.payload.correction_mode).toBe("tax_only");
});

test("histórico incompleto muestra datos desconocidos y exige desglose manual al rectificar", async ({
  page,
  rpc,
}) => {
  await rpc("settings.save", {
    section: "company",
    values: { legal_name: "TALLER SINTÉTICO", tax_id: "89890001K" },
  });
  const data = {
    format: "canamo-import-v2",
    customers: [
      {
        legacy_code: "001",
        name: "Ficha actual distinta del original",
        tax_id: "12345678Z",
        address: "Calle sintética",
        postal_code: "41300",
        city: "Localidad ficticia",
      },
    ],
    vehicles: [],
    invoices: [
      {
        legacy_key: "historic-001",
        legacy_customer_code: "001",
        full_number: "HIST-0007",
        issue_date: "2010-05-20",
        lines: [
          {
            description: "Concepto conservado del histórico",
            base_cents: 1000,
          },
        ],
        base_cents: 1000,
        tax_cents: 210,
        total_cents: 1210,
      },
    ],
  };
  const preview = await rpc<{ batch_id: string }>("import.preview", {
    text: JSON.stringify(data),
    format: "json",
  });
  while (
    !(
      await rpc<{ done: boolean }>("import.simulate", {
        batch_id: preview.batch_id,
        acknowledge_warnings: true,
      })
    ).done
  ) {
    /* Explicit batch progress. */
  }
  while (
    !(
      await rpc<{ done: boolean }>("import.run", { batch_id: preview.batch_id })
    ).done
  ) {
    /* Explicit batch progress. */
  }
  const original = (await rpc<{ items: RecordRow[] }>("documents.list"))
    .items[0];
  const before = await rpc<{ payload: unknown }>("documents.get", {
    identifier: original.id,
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Facturas", exact: true }).click();
  await expect(
    page.getByRole("row").filter({ hasText: "HIST-0007" }),
  ).toContainText("Cliente no conservado en el original");
  await page.getByRole("button", { name: "HIST-0007", exact: true }).click();
  await expect(page.getByLabel("Cantidad 1", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Cantidad 1", { exact: true })).toHaveAttribute(
    "placeholder",
    "No consta",
  );
  await expect(page.getByLabel("Precio 1", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("IVA 1", { exact: true })).toHaveText("No consta");
  await expect(page.locator(".editor-side")).toContainText(
    "IVA histórico (tipo no conservado)",
  );
  await expect(
    page.getByText(/Los datos del cliente no se conservan/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Registrar cobro", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Crear rectificativa", exact: true })
    .click();
  const correction = page.getByRole("dialog", {
    name: "Crear factura rectificativa",
    exact: true,
  });
  await correction
    .getByRole("textbox", { name: "Motivo", exact: true })
    .fill("Diferencia comprobada con documento sintético conservado");
  await correction.getByLabel(/Fecha de operación original/).fill("2010-05-18");
  await correction
    .getByRole("textbox", { name: "Cantidad rectificativa 1", exact: true })
    .fill("-1");
  await correction
    .getByRole("textbox", { name: "Precio rectificativo 1", exact: true })
    .fill("10");
  await chooseOption(correction
    .getByRole("combobox", { name: "Tratamiento fiscal 1", exact: true }), "S1");
  await correction
    .getByRole("textbox", { name: "IVA rectificativo 1", exact: true })
    .fill("21");
  await correction
    .getByRole("button", { name: "Crear borrador rectificativo", exact: true })
    .click();
  await expect(correction).toBeHidden();
  await expect(page.locator(".summary-total")).toContainText("-12,10");
  expect(
    (
      await rpc<{ payload: unknown }>("documents.get", {
        identifier: original.id,
      })
    ).payload,
  ).toEqual(before.payload);
  expect(await rpc<unknown[]>("fiscal.list")).toHaveLength(0);
});
