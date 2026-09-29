import { chooseOption } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import type { Download, Page, TestInfo } from "@playwright/test";
import { test, expect } from "./fixtures";

async function bytes(download: Download) {
  const stream = await download.createReadStream();
  const parts: Buffer[] = [];
  for await (const part of stream!) parts.push(Buffer.from(part));
  return Buffer.concat(parts);
}

async function audit(page: Page, info: TestInfo, step: string) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  await info.attach(step + "-axe.json", {
    body: JSON.stringify(result, null, 2),
    contentType: "application/json",
  });
  await page.screenshot({
    path: info.outputPath(step + ".png"),
    fullPage: true,
  });
  expect(
    result.violations,
    JSON.stringify(
      result.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
    ),
  ).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
}

test("proveedor y catálogo: búsqueda, archivo, entradas, salidas y recuento accesible", async ({
  page,
  rpc,
  backend,
}, info) => {
  await rpc("settings.save", {
    section: "appearance",
    values: { extras: true, theme: "dark", font_size: "large" },
  });
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto("/");
  await page.getByRole("button", { name: "Más herramientas" }).click();
  await page.getByRole("button", { name: "Proveedores", exact: true }).click();
  await page
    .getByRole("button", { name: "Nuevo proveedor", exact: true })
    .click();
  const supplier = page.getByRole("dialog", {
    name: "Nuevo proveedor",
    exact: true,
  });
  await supplier
    .getByRole("textbox", { name: "Nombre", exact: true })
    .fill("Recámbios Sintéticos");
  await supplier.getByLabel("Teléfono", { exact: true }).fill("600000005");
  await supplier
    .getByLabel("Correo electrónico")
    .fill("pruebas@example.invalid");
  await supplier.getByRole("button", { name: "Guardar proveedor" }).click();
  await expect(supplier).toBeHidden();
  await page.getByLabel("Buscar proveedores").fill("recambios");
  const supplierRow = page
    .getByRole("row")
    .filter({ hasText: "Recámbios Sintéticos" });
  await expect(supplierRow).toContainText("600000005");
  await supplierRow
    .getByRole("button", { name: "Archivar", exact: true })
    .click();
  await expect(supplierRow).toHaveCount(0);
  await page.getByLabel("Mostrar archivados").check();
  await expect(supplierRow).toContainText("Archivado");
  await supplierRow
    .getByRole("button", { name: "Restaurar", exact: true })
    .click();
  await expect(
    supplierRow.getByRole("button", { name: "Archivar", exact: true }),
  ).toBeVisible();
  await audit(page, info, "proveedores-dark-large");
  await page
    .getByRole("button", { name: "Artículos y stock", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Nuevo artículo", exact: true })
    .click();
  const product = page.getByRole("dialog", {
    name: "Nuevo artículo o servicio",
    exact: true,
  });
  await product
    .getByRole("textbox", { name: "Nombre", exact: true })
    .fill("Filtro sintético de almacén");
  await product.getByLabel("Referencia (opcional)").fill("0007");
  await chooseOption(product
    .getByRole("combobox", { name: "Proveedor", exact: true }), { label: "Recámbios Sintéticos" });
  await product.getByLabel("Precio de venta sin IVA").fill("10");
  await product.getByLabel("Avisar por debajo de").fill("3");
  await product.getByRole("button", { name: "Guardar artículo" }).click();
  await expect(product).toBeHidden();
  const row = page
    .getByRole("row")
    .filter({ hasText: "Filtro sintético de almacén" });
  for (const [operation, amount, reason] of [
    ["entry", "10", "Compra sintética"],
    ["exit", "2", "Consumo externo sintético"],
    ["return", "1", "Devolución sintética"],
    ["adjust", "7,5", "Recuento físico sintético"],
  ]) {
    await row.getByRole("button", { name: "Existencias", exact: true }).click();
    const stock = page.getByRole("dialog", {
      name: "Existencias · Filtro sintético de almacén",
    });
    await chooseOption(stock.getByLabel("Tipo de movimiento"), operation);
    await stock
      .getByLabel(
        operation === "adjust"
          ? "Unidades contadas"
          : "Unidades del movimiento",
      )
      .fill(amount);
    await stock.getByLabel("Motivo").fill(reason);
    await stock
      .getByRole("button", { name: "Registrar movimiento" })
      .dblclick();
    await expect(stock).toBeHidden();
  }
  await expect(row).toContainText("7.5");
  await row.getByRole("button", { name: "Archivar", exact: true }).click();
  await expect(page.getByText(/existencias.*cero/)).toBeVisible();
  const products = await rpc<{ id: string; stock: string }[]>("products.list");
  expect(Number(products[0].stock)).toBe(7.5);
  const movements = await rpc<{ reason: string; quantity: string }[]>(
    "products.movements",
    { product_id: products[0].id },
  );
  expect(movements).toHaveLength(4);
  expect(movements.map((m) => Number(m.quantity))).toEqual([-1.5, 1, -2, 10]);
  await audit(page, info, "catalogue-dark-large");
  await backend.restart();
  expect(
    Number((await rpc<{ stock: string }[]>("products.list"))[0].stock),
  ).toBe(7.5);
});

test("presupuesto → orden → factura conserva líneas y un solo consumo; informes y exportación real", async ({
  page,
  rpc,
  backend,
}, info) => {
  await rpc("settings.save", {
    section: "company",
    values: { legal_name: "TALLER SINTÉTICO OPERATIVO", tax_id: "89890001K" },
  });
  await rpc("settings.save", {
    section: "appearance",
    values: { extras: true },
  });
  const customer = await rpc<{ id: string }>("customers.save", {
    data: {
      name: "Cliente sintético operaciones",
      tax_id: "12345678Z",
      phone: "612000007",
      address: "Calle sintética 8",
      postal_code: "41300",
      city: "Localidad sintética",
    },
  });
  const product = await rpc<{ id: string }>("products.save", {
    data: {
      name: "Filtro sintético de conversión",
      sku: "0008",
      unit_price: "10",
      min_stock: "9",
    },
  });
  await rpc("products.move", {
    product_id: product.id,
    quantity: "10",
    reason: "Entrada sintética",
    idempotency_key: "operations-in",
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Más herramientas" }).click();
  await page.getByRole("button", { name: "Presupuestos", exact: true }).click();
  await page
    .getByRole("button", { name: "Nuevo presupuesto", exact: true })
    .first()
    .click();
  const search = page.getByRole("main").getByRole("combobox", {
    name: "Busca por nombre o matrícula",
  });
  await search.fill("Cliente sintético operaciones");
  await expect(page.getByRole("option").first()).toBeVisible();
  await search.press("Enter");
  await page.getByRole("button", { name: "Del catálogo", exact: true }).click();
  await page
    .getByRole("dialog", { name: "Añadir del catálogo" })
    .getByRole("button", { name: /Filtro sintético de conversión/ })
    .click();
  await page.getByLabel("Cantidad 1", { exact: true }).fill("2");
  await page.getByLabel(/Descontar del almacén/).check();
  await page
    .getByRole("button", { name: "Confirmar presupuesto", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Confirmar documento" })
    .getByRole("button", { name: "Confirmar", exact: true })
    .click();
  await chooseOption(page
    .getByRole("combobox", { name: "Estado", exact: true }), "accepted");
  await page
    .getByRole("button", { name: "Crear orden de reparación", exact: true })
    .click();
  await expect(page.getByLabel("Concepto 1", { exact: true })).toHaveValue(
    "Filtro sintético de conversión",
  );
  await page.getByRole("button", { name: "Abrir orden", exact: true }).click();
  await page
    .getByRole("dialog", { name: "Confirmar documento" })
    .getByRole("button", { name: "Confirmar", exact: true })
    .click();
  await chooseOption(page
    .getByRole("combobox", { name: "Estado", exact: true }), "ready");
  await page
    .getByRole("button", { name: "Convertir en factura", exact: true })
    .click();
  await expect(page.getByLabel("Cantidad 1", { exact: true })).toHaveValue("2");
  await page
    .getByRole("button", { name: "Revisar y emitir", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Emitir prueba", exact: true })
    .dblclick();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    /FAC-\d{4}-00001/,
  );
  const invoice = (
    await rpc<{ items: { id: string; payload: any }[] }>("documents.list", {
      kind: "invoice",
    })
  ).items[0];
  const quotes = await rpc<{ items: { id: string }[] }>("documents.list", {
    kind: "quote",
  });
  const order = (
    await rpc<{ items: { id: string }[] }>("documents.list", { kind: "order" })
  ).items[0];
  expect(
    (
      await rpc<{ id: string }>("documents.convert", {
        identifier: quotes.items[0].id,
        target: "invoice",
      })
    ).id,
  ).toBe(invoice.id);
  expect(
    (
      await rpc<{ id: string }>("documents.convert", {
        identifier: order.id,
        target: "invoice",
      })
    ).id,
  ).toBe(invoice.id);
  const stock = await rpc<{ stock: string }[]>("products.list");
  expect(Number(stock[0].stock)).toBe(8);
  const movements = await rpc<{ document_id: string; quantity: string }[]>(
    "products.movements",
    { product_id: product.id },
  );
  expect(movements.filter((row) => row.document_id)).toEqual([
    expect.objectContaining({ document_id: invoice.id, quantity: "-2" }),
  ]);
  await page
    .getByRole("button", { name: "Registrar cobro", exact: true })
    .click();
  const payment = page.getByRole("dialog", { name: "Registrar cobro" });
  await payment
    .getByRole("textbox", { name: "Importe", exact: true })
    .fill("10");
  await payment
    .getByRole("button", { name: "Guardar cobro", exact: true })
    .click();
  await expect(payment).toBeHidden();
  await backend.restart();
  await page.reload();
  await page.getByRole("button", { name: "Más herramientas" }).click();
  await page.getByRole("button", { name: "Resumen", exact: true }).click();
  await page
    .getByRole("button", { name: "Todo el historial", exact: true })
    .click();
  await expect(
    page.locator(".stat-card").filter({ hasText: "Facturación del período" }),
  ).toContainText("24,20");
  await expect(
    page.locator(".stat-card").filter({ hasText: "Cobros netos del período" }),
  ).toContainText("10,00");
  await expect(
    page.locator(".stat-card").filter({ hasText: "Pendiente de cobro hoy" }),
  ).toContainText("14,20");
  await expect(
    page.getByText("1 documentos del período están marcados como pruebas."),
  ).toBeVisible();
  await audit(page, info, "reports-light");
  let downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Facturas y snapshots CSV", exact: true })
    .click();
  const csv = (await bytes(await downloadEvent)).toString("utf8");
  expect(csv).toContain("payload");
  expect(csv).toContain("Filtro sintético de conversión");
  downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Exportación portable completa", exact: true })
    .click();
  const portable = await downloadEvent;
  expect(portable.suggestedFilename()).toMatch(
    /^exportacion-portable-.*\.zip$/,
  );
  const raw = await bytes(portable);
  const python = resolve(
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );
  const data = JSON.parse(
    execFileSync(
      python,
      [
        "-c",
        "import io,json,sys,zipfile; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); print(z.read('data.json').decode('utf-8'))",
      ],
      { input: raw, encoding: "utf8" },
    ),
  );
  expect(data.format).toBe("canamo-portable-v1");
  expect(data.tables.documents).toHaveLength(3);
  expect(data.tables.stock_movements).toHaveLength(2);
  expect(data.tables.payments).toHaveLength(1);
  expect(
    data.tables.customers.find((row: any) => row.id === customer.id).name,
  ).toBe("Cliente sintético operaciones");
  expect(
    JSON.parse(
      data.tables.documents.find((row: any) => row.id === invoice.id).payload,
    ).lines[0],
  ).toEqual(expect.objectContaining({ quantity: "2", product_id: product.id }));
  expect(data.settings.fiscal.certificate_info).toBeUndefined();
  await expect(
    page.getByRole("status").filter({ hasText: "Descarga iniciada" }),
  ).toBeVisible();
});
