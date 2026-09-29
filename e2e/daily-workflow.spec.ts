import { test, expect } from "./fixtures";

test("cliente y dos vehículos: matrícula normalizada, teléfono y teclado", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Nuevo cliente/ }).click();
  const customer = page.getByRole("dialog", { name: "Nuevo cliente" });
  await customer.getByLabel("Nombre o razón social").fill("Lucía Sintética");
  await customer.getByLabel("Teléfono principal").fill("612 000 001");
  await customer.getByRole("button", { name: "Guardar cliente" }).click();
  await expect(
    page.getByRole("heading", { name: "Lucía Sintética", level: 1 }),
  ).toBeVisible();
  for (const plate of ["0540-BZD", "1234 XYZ"]) {
    await page.getByRole("button", { name: "Añadir", exact: true }).click();
    const vehicle = page.getByRole("dialog", { name: "Añadir vehículo" });
    await vehicle
      .getByRole("textbox", { name: "Matrícula", exact: true })
      .fill(plate);
    await vehicle
      .getByLabel("Marca", { exact: true })
      .fill("Vehículo ficticio");
    await vehicle.getByRole("button", { name: "Guardar vehículo" }).click();
    await expect(vehicle).toBeHidden();
  }
  await page.getByRole("button", { name: "Ir a inicio" }).click();
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
  });
  for (const query of ["0", "0540 bzd", "0540BZD"]) {
    await search.fill(query);
    await expect(page.getByRole("option", { name: /0540-BZD/ })).toContainText(
      "612 000 001",
    );
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Tu taller, a punto.",
    );
  }
  await search.press("Escape");
  await expect(page.getByRole("listbox")).toBeHidden();
  await search.press("ArrowDown");
  await search.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Lucía Sintética", level: 1 }),
  ).toBeVisible();
  await expect(page.locator(".big-phone")).toHaveText("612 000 001");
});

for (const withVehicle of [true, false]) {
  test(`factura directa, cobro, PDF y reinicio: ${withVehicle ? "con vehículo" : "maquinaria sin extras"}`, async ({
    page,
    rpc,
    backend,
  }) => {
    await rpc("settings.save", {
      section: "company",
      values: { legal_name: "TALLER FICTICIO E2E", tax_id: "89890001K" },
    });
    await rpc("settings.save", {
      section: "appearance",
      values: { extras: withVehicle },
    });
    const customer = await rpc<{ id: string }>("customers.save", {
      data: {
        name: "Cliente E2E Ficticio",
        tax_id: "12345678Z",
        phone: "612 000 002",
        address: "Calle de pruebas 1",
        postal_code: "41300",
        city: "Localidad ficticia",
      },
    });
    if (withVehicle)
      await rpc("vehicles.save", {
        data: {
          customer_id: customer.id,
          plate: "5678 ABC",
          make: "Ficticio",
          model: "Pruebas",
          km: 32000,
        },
      });
    await page.goto("/");
    const search = page.getByRole("combobox", {
      name: "Buscar cliente o matrícula",
    });
    await search.fill(withVehicle ? "5678abc" : "Cliente E2E");
    await expect(page.getByRole("option").first()).toContainText(
      "Cliente E2E Ficticio",
    );
    await search.press("Enter");
    await page
      .getByRole("button", { name: "Nueva factura", exact: true })
      .click();
    await page
      .getByLabel("Concepto 1", { exact: true })
      .fill("Revisión de maquinaria — prueba");
    await page.getByLabel("Cantidad 1", { exact: true }).fill("1,5");
    await page.getByLabel("Precio 1", { exact: true }).fill("34");
    await expect(page.locator(".summary-total")).toContainText("61,71");
    await page.getByRole("button", { name: "Revisar y emitir" }).click();
    await page
      .getByRole("button", { name: "Emitir prueba", exact: true })
      .dblclick();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      /FAC-\d{4}-00001/,
    );
    const number = await page.getByRole("heading", { level: 1 }).innerText();
    for (const amount of ["20", "41,71"]) {
      await page
        .getByRole("button", { name: "Registrar cobro", exact: true })
        .click();
      const payment = page.getByRole("dialog", { name: "Registrar cobro" });
      await payment
        .getByRole("textbox", { name: "Importe", exact: true })
        .fill(amount);
      await payment
        .getByRole("button", { name: "Guardar cobro", exact: true })
        .click();
      await expect(payment).toBeHidden();
    }
    await expect(
      page.getByRole("button", { name: "Registrar cobro", exact: true }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Revertir", exact: true })
      .first()
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Revertir cobro", exact: true })
      .click();
    await expect(page.locator(".editor-side")).toContainText("20,00");
    await page.getByRole("button", { name: "Vista previa / PDF" }).click();
    const pdf = page.getByRole("dialog");
    await expect(pdf.getByTitle("Vista previa de la factura")).toBeVisible();
    const downloadPromise = page.waitForEvent("download");
    await pdf.getByRole("button", { name: "Guardar PDF" }).click();
    const download = await downloadPromise;
    const stream = await download.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
    expect(Buffer.concat(chunks).subarray(0, 5).toString()).toBe("%PDF-");
    await pdf.getByRole("button", { name: "Cerrar ventana" }).click();
    const docs = await rpc<{
      total: number;
      items: { id: string; total_cents: number }[];
    }>("documents.list");
    expect(docs.total).toBe(1);
    expect(docs.items[0].total_cents).toBe(6171);
    await backend.restart();
    await page.reload();
    await page.getByRole("button", { name: "Facturas", exact: true }).click();
    await page.getByRole("button", { name: number, exact: true }).click();
    await expect(page.getByLabel("Concepto 1", { exact: true })).toHaveValue(
      "Revisión de maquinaria — prueba",
    );
    if (!withVehicle) {
      await expect(
        page.getByRole("button", { name: "Más herramientas" }),
      ).toHaveCount(0);
      await expect(page.getByLabel("Vehículo (opcional)")).toHaveText("Sin vehículo");
    }
  });
}
