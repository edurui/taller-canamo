import AxeBuilder from "@axe-core/playwright";
import type { Locator, Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { test, expect } from "./fixtures";

type Rpc = <T = Record<string, unknown>>(action: string, params?: Record<string, unknown>) => Promise<T>;
type Seed = { customer: string; vehicle: string; document: string; product: string; supplier: string };

async function seed(rpc: Rpc, paged = false): Promise<Seed> {
  const { data_directory } = await rpc<{ data_directory: string }>("bootstrap");
  const python = resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  return JSON.parse(execFileSync(python, ["-c", `
import sys,json
sys.path.insert(0,'backend')
from taller.app import App
from taller.db import dumps
app=App(sys.argv[1])
a=app.contacts.save_customer({'name':'Álamo de prueba','phone':'100000001','city':'Sevilla','notes':'Nota sintética conservada'})
b=app.contacts.save_customer({'name':'Beta de prueba','phone':'200000001','city':'Madrid'})
z=app.contacts.save_customer({'name':'Zeta de prueba','phone':'900000001','city':'Cádiz'})
count=56 if sys.argv[2]=='yes' else 3
for i in range(3,count): app.contacts.save_customer({'name':f'Intermedio {i:02}','phone':f'6000000{i:02}','city':'Sevilla'})
vehicles=[]
for i in range(count): vehicles.append(app.contacts.save_vehicle({'customer_id':a['id'] if i!=1 else b['id'],'plate':f'ORD-{i:02}','kind':f'Modelo {i:02}','km':i+1}))
doc=app.documents.save({'customer_id':a['id'],'vehicle_id':vehicles[0]['id'],'lines':[{'description':'Trabajo sintético','unit_price':'10'}]})
for number,amount,day in [('ORD-10','10','2024-01-01'),('ORD-20','20','2024-01-03'),('ORD-30','30','2024-01-02')]:
 d=app.documents.save({'customer_id':a['id'],'vehicle_id':vehicles[0]['id'],'lines':[{'description':'Trabajo sintético','unit_price':amount}]})
 payload=d['payload']; payload['historical']=True; payload['payment_state']='unknown'
 with app.db.transaction() as conn: conn.execute("UPDATE documents SET status='historical',full_number=?,issue_date=?,payload=? WHERE id=?",(number,day,dumps(payload),d['id']))
supplier=app.catalogue.save_supplier({'name':'Proveedor Álamo','phone':'300000001','email':'alamo@example.invalid'})
app.catalogue.save_supplier({'name':'Proveedor Zeta','phone':'100000001','email':'zeta@example.invalid'})
products=[]
for name,sku,price in [('Artículo diez','Z-REF','10'),('Artículo dos','A-REF','2')]:
 products.append(app.catalogue.save_product({'name':name,'sku':sku,'unit_price':price,'supplier_id':supplier['id'],'track_stock':True}))
for i,quantity in enumerate(('2','10','3')): app.catalogue.move(products[0]['id'],quantity,f'Movimiento {i+1}',f'list-movement-{i}',doc['id'] if i==0 else None)
print(json.dumps({'customer':a['id'],'vehicle':vehicles[0]['id'],'document':doc['id'],'product':products[0]['id'],'supplier':supplier['id']}))
`, data_directory, paged ? "yes" : "no"], { cwd: resolve("."), encoding: "utf8" }));
}

async function sidebar(page: Page, label: string) {
  await expect(page.getByRole("banner")).toBeVisible();
  const opener = page.getByRole("button", { name: "Abrir menú", exact: true });
  if (await opener.isVisible()) await opener.click();
  const nav = page.locator(".sidebar");
  const target = nav.getByRole("button", { name: label, exact: true });
  if (!(await target.isVisible())) await nav.getByRole("button", { name: "Más herramientas", exact: true }).click();
  await target.click();
}
function row(page: Page, label: string) {
  return page.getByRole("row").filter({ has: page.getByRole("button", { name: label, exact: true }) });
}
function sortButton(container: Page | Locator, label: string) {
  return container.getByRole("button", { name: new RegExp(`^${label}: ordenar `) });
}
async function menu(page: Page, label: string, action: string) {
  await page.getByRole("button", { name: `Acciones de ${label}`, exact: true }).click();
  await page.getByRole("menuitem", { name: action, exact: true }).click();
}
async function settle(page: Page) {
  await page.evaluate(async () => {
    while (true) {
      const animations = document.getAnimations().filter(animation => animation.playState === "running" && Number.isFinite(animation.effect?.getComputedTiming().endTime));
      if (!animations.length) return;
      await Promise.all(animations.map(animation => animation.finished.catch(() => undefined)));
    }
  });
}

test("clientes ordenan globalmente, vuelven a primera página y respetan enlaces y clic de celda", async ({ page, rpc }) => {
  await seed(rpc, true);
  await page.goto("/");
  await sidebar(page, "Clientes");
  const names = page.locator("tbody .row-link strong");
  await expect(names.first()).toHaveText("Álamo de prueba");
  const original = await names.allTextContents();
  await page.getByRole("button", { name: "Siguiente", exact: true }).click();
  await expect(page.locator(".pager")).toContainText("51–56");
  await sortButton(page, "Teléfono").focus();
  await sortButton(page, "Teléfono").press("Enter");
  await expect(page.locator(".pager")).toContainText("1–50");
  await expect(sortButton(page, "Teléfono")).toBeFocused();
  await sortButton(page, "Teléfono").press("Enter");
  await expect(names.first()).toHaveText("Zeta de prueba");
  await expect(page.getByRole("columnheader").filter({ has: sortButton(page, "Teléfono") })).toHaveAttribute("aria-sort", "descending");
  await sortButton(page, "Teléfono").press("Enter");
  await expect(names).toHaveText(original);
  await page.getByRole("textbox", { name: "Filtrar clientes", exact: true }).fill("Beta de prueba");
  await page.getByRole("row").filter({ hasText: "Beta de prueba" }).getByRole("button", { name: "ORD-01", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "ORD-01", exact: true })).toBeVisible();
  await sidebar(page, "Clientes");
  await page.getByRole("textbox", { name: "Filtrar clientes", exact: true }).fill("Beta de prueba");
  await page.getByRole("cell", { name: "200000001", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Beta de prueba", exact: true })).toBeVisible();
});

test("acciones de cliente funcionan con teclado, conservan datos y piden confirmar el archivo", async ({ page, rpc }) => {
  const ids = await seed(rpc);
  await page.goto("/");
  await sidebar(page, "Clientes");
  const trigger = page.getByRole("button", { name: "Acciones de Álamo de prueba", exact: true });
  await trigger.focus();
  await trigger.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Ver ficha", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await menu(page, "Álamo de prueba", "Editar cliente");
  const editor = page.getByRole("dialog", { name: "Editar cliente", exact: true });
  await expect(editor.getByLabel("Notas")).toHaveValue("Nota sintética conservada");
  await editor.getByRole("button", { name: "Cancelar", exact: true }).click();
  await menu(page, "Álamo de prueba", "Archivar cliente");
  const confirmation = page.getByRole("dialog", { name: "Archivar cliente", exact: true });
  await confirmation.getByRole("button", { name: "Volver", exact: true }).click();
  expect((await rpc<{ archived: number }>("customers.get", { identifier: ids.customer })).archived).toBe(0);
  await menu(page, "Álamo de prueba", "Archivar cliente");
  await confirmation.getByRole("button", { name: "Archivar", exact: true }).click();
  await expect(trigger).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Archivados", exact: true }).check();
  await menu(page, "Álamo de prueba", "Recuperar cliente");
  await page.getByRole("dialog", { name: "Recuperar cliente", exact: true }).getByRole("button", { name: "Recuperar", exact: true }).click();
  expect((await rpc<{ archived: number }>("customers.get", { identifier: ids.customer })).archived).toBe(0);
});

test("vehículos ordenan kilómetros como números y separan titular, fila y edición", async ({ page, rpc }) => {
  await seed(rpc, true);
  await page.goto("/");
  await sidebar(page, "Vehículos");
  await sortButton(page, "Kilómetros").click();
  await sortButton(page, "Kilómetros").click();
  await expect(page.locator("tbody tr").first()).toContainText("ORD-55");
  await row(page, "ORD-55").getByRole("button", { name: "Álamo de prueba", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Álamo de prueba", exact: true })).toBeVisible();
  await sidebar(page, "Vehículos");
  await row(page, "ORD-00").getByRole("cell", { name: "Modelo 00", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "ORD-00", exact: true })).toBeVisible();
  await sidebar(page, "Vehículos");
  await menu(page, "ORD-00", "Editar vehículo");
  const editor = page.getByRole("dialog", { name: "Editar vehículo", exact: true });
  await expect(editor.getByRole("textbox", { name: "Matrícula", exact: true })).toHaveValue("ORD-00");
  await editor.getByRole("button", { name: "Cancelar", exact: true }).click();
});

test("archivar el único cliente de la última página vuelve a la primera", async ({ page, rpc }) => {
  await seed(rpc, true);
  const extra = await rpc<{ items: { id: string }[] }>("customers.list", { query: "Intermedio" });
  for (const customer of extra.items.slice(0, 5))
    await rpc("customers.archive", { identifier: customer.id, archived: true });
  await page.goto("/");
  await sidebar(page, "Clientes");
  await page.getByRole("button", { name: "Siguiente", exact: true }).click();
  await expect(page.locator(".pager")).toContainText("51–51");
  await menu(page, "Zeta de prueba", "Archivar cliente");
  await page.getByRole("dialog", { name: "Archivar cliente", exact: true }).getByRole("button", { name: "Archivar", exact: true }).click();
  await expect(page.locator(".pager")).toHaveCount(0);
  await expect(page.locator("tbody tr")).toHaveCount(50);
  await expect(page.locator("tbody .row-link strong").first()).toHaveText("Álamo de prueba");
});

for (const surface of [
  { title: "Artículos y stock", action: "products.list", entity: "Artículo dos", cell: "2 €", editor: "Editar artículo" },
  { title: "Proveedores", action: "suppliers.list", entity: "Proveedor Álamo", cell: "300000001", editor: "Editar proveedor" },
]) {
  test(`${surface.title}: un fallo de recarga conserva la tabla pero impide abrir datos obsoletos`, async ({ page, rpc }) => {
    await seed(rpc);
    await page.goto("/");
    await sidebar(page, surface.title);
    const trigger = page.getByRole("button", { name: `Acciones de ${surface.entity}`, exact: true });
    await expect(trigger).toBeEnabled();
    let unavailable = true;
    await page.route("**/api", async route => {
      const request = route.request().postDataJSON() as { action: string };
      if (request.action === surface.action && unavailable)
        await route.fulfill({ json: { ok: false, error: { message: "Fallo sintético de recarga" } } });
      else await route.fallback();
    });
    await page.getByRole("checkbox", { name: "Mostrar archivados", exact: true }).check();
    await expect(page.getByRole("alert")).toContainText("Fallo sintético de recarga");
    await expect(trigger).toBeDisabled();
    await expect(page.getByRole("button", { name: surface.entity, exact: true })).toBeDisabled();
    await page.getByRole("cell", { name: surface.cell, exact: true }).click();
    await expect(page.getByRole("dialog", { name: surface.editor, exact: true })).toHaveCount(0);
    if (surface.action === "products.list")
      for (const link of await page.getByRole("button", { name: "Proveedor Álamo", exact: true }).all()) await expect(link).toBeDisabled();
    unavailable = false;
    await page.getByRole("button", { name: "Reintentar", exact: true }).click();
    await expect(trigger).toBeEnabled();
    await page.getByRole("cell", { name: surface.cell, exact: true }).click();
    await expect(page.getByRole("dialog", { name: surface.editor, exact: true })).toBeVisible();
  });
}

test("catálogo y proveedores ordenan valores, abren la fila y conservan protecciones del almacén", async ({ page, rpc }) => {
  await seed(rpc);
  await page.goto("/");
  await sidebar(page, "Artículos y stock");
  await sortButton(page, "Precio sin IVA").click();
  await expect(page.locator("tbody tr").first()).toContainText("Artículo dos");
  await sortButton(page, "Precio sin IVA").click();
  await expect(page.locator("tbody tr").first()).toContainText("Artículo diez");
  await row(page, "Artículo dos").getByRole("cell", { name: "2 €", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Editar artículo", exact: true })).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Cancelar", exact: true }).click();
  await menu(page, "Artículo diez", "Archivar");
  await expect(page.getByText(/Antes de archivar, deja las existencias a cero/)).toBeVisible();
  await menu(page, "Artículo diez", "Existencias");
  const stock = page.getByRole("dialog", { name: "Existencias · Artículo diez", exact: true });
  await sortButton(stock, "Unidades").click();
  await expect(stock.locator("tbody tr td:nth-child(3)")).toHaveText(["2", "3", "10"]);
  await stock.getByRole("cell", { name: "3", exact: true }).click();
  const detail = page.getByRole("dialog", { name: "Detalle del movimiento", exact: true });
  await expect(detail).toContainText("Movimiento 3");
  await expect(detail).toContainText("Artículo diez");
  await detail.getByRole("button", { name: "Volver al almacén", exact: true }).click();
  await stock.getByRole("textbox", { name: "Motivo", exact: true }).fill("Movimiento local sin guardar");
  await stock.getByRole("button", { name: "Consultar documento del movimiento", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Movimiento sin registrar", exact: true })).toBeVisible();
  await page.getByRole("dialog", { name: "Movimiento sin registrar", exact: true }).getByRole("button", { name: "Volver", exact: true }).click();
  await expect(stock.getByRole("textbox", { name: "Motivo", exact: true })).toHaveValue("Movimiento local sin guardar");
  await stock.getByRole("button", { name: "Volver", exact: true }).click();
  await row(page, "Artículo dos").getByRole("button", { name: "Proveedor Álamo", exact: true }).click();
  const supplier = page.getByRole("dialog", { name: "Editar proveedor", exact: true });
  await expect(supplier.getByRole("textbox", { name: "Nombre", exact: true })).toHaveValue("Proveedor Álamo");
  await supplier.getByRole("button", { name: "Cancelar", exact: true }).click();
  await page.getByRole("checkbox", { name: "Mostrar archivados", exact: true }).uncheck();
  await sortButton(page, "Teléfono").click();
  await expect(page.locator("tbody tr").first()).toContainText("Proveedor Zeta");
  await menu(page, "Proveedor Zeta", "Archivar");
  await expect(row(page, "Proveedor Zeta")).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Mostrar archivados", exact: true }).check();
  await menu(page, "Proveedor Zeta", "Restaurar");
  await expect(row(page, "Proveedor Zeta")).not.toContainText("Archivado");
});

test("historiales de cliente y vehículo ordenan importes y permiten abrir cualquier celda", async ({ page, rpc }) => {
  await seed(rpc);
  await page.goto("/");
  await sidebar(page, "Clientes");
  await page.locator(".row-link").filter({ has: page.getByText("Álamo de prueba", { exact: true }) }).click();
  const customerTable = page.locator("section").filter({ has: page.getByRole("heading", { name: "Historial de facturas", exact: true }) });
  await sortButton(customerTable, "Importe").click();
  await sortButton(customerTable, "Importe").click();
  await expect(customerTable.locator("tbody tr").first()).toContainText("ORD-30");
  await customerTable.getByRole("row").filter({ hasText: "ORD-30" }).getByRole("cell", { name: /36,30/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("ORD-30");
  await sidebar(page, "Vehículos");
  await row(page, "ORD-00").getByRole("button", { name: "ORD-00", exact: true }).click();
  const vehicleTable = page.locator("section").filter({ has: page.getByRole("heading", { name: "Facturas del vehículo", exact: true }) });
  await sortButton(vehicleTable, "Fecha").click();
  await expect(vehicleTable.locator("tbody tr").first()).toContainText("ORD-10");
  await menu(page, "ORD-10", "Abrir factura");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("ORD-10");
});

test("series y copias ordenan y abren sus datos sin modificar ni restaurar automáticamente", async ({ page, rpc }) => {
  await rpc("series.save", { data: { kind: "invoice", label: "Serie Z de prueba", year: 2030, prefix: "Z2030-", padding: 4, next_number: 700 } });
  await rpc("series.save", { data: { kind: "invoice", label: "Serie A de prueba", year: 2030, prefix: "A2030-", padding: 4, next_number: 20 } });
  await rpc("backup.create");
  const backups = await rpc<{ name: string; bytes: number }[]>("backup.list");
  await page.goto("/");
  await sidebar(page, "Configuración");
  await page.getByRole("button", { name: "Facturación", exact: true }).click();
  await sortButton(page, "Próximo número").click();
  await sortButton(page, "Próximo número").click();
  await expect(page.locator("tbody tr").first()).toContainText("Serie Z de prueba");
  await row(page, "Serie Z de prueba").getByRole("cell", { name: "2030", exact: true }).click();
  const series = page.getByRole("dialog", { name: "Editar serie", exact: true });
  await expect(series).toBeVisible();
  await series.getByRole("button", { name: "Cancelar", exact: true }).click();
  await menu(page, "Serie A de prueba", "Editar serie");
  await expect(series).toBeVisible();
  await series.getByRole("button", { name: "Cancelar", exact: true }).click();
  await page.getByRole("button", { name: "Copias y traslado", exact: true }).click();
  const table = page.locator("section").filter({ has: page.getByRole("heading", { name: "Últimas copias locales", exact: true }) });
  await sortButton(table, "Tamaño").click();
  await table.getByRole("button", { name: backups[0].name, exact: true }).click();
  const detail = page.getByRole("dialog", { name: "Detalle de la copia local", exact: true });
  await expect(detail).toContainText(backups[0].name);
  await expect(detail).toContainText(Number(backups[0].bytes).toLocaleString("es-ES") + " bytes");
  await expect(detail.getByRole("button", { name: /Restaurar/ })).toHaveCount(0);
  await detail.getByRole("button", { name: "Cerrar detalle", exact: true }).click();
  expect(await rpc("backup.list")).toEqual(backups);
});

test("diagnóstico y conciliación ordenan sus métricas sin transformar ceros ni datos ausentes", async ({ page }) => {
  const totals = {
    source_invoices: 2, destination_invoices: 2, source_lines: 10, destination_lines: 10,
    source_base_cents: 1000, destination_base_cents: 1000,
    source_tax_cents: null, destination_tax_cents: 0,
    source_total_cents: 1210, destination_total_cents: 1210,
    source_unknown_tax_cents: 1, destination_unknown_tax_cents: 0,
    unknown_payment: 2, excluded: 0, differences: 1,
  };
  const review = {
    batch_id: "synthetic-batch", source_id: "synthetic-source", status: "completed", cursor: 12,
    capacity: { used_bytes: 1024, limit_bytes: 1048576, within_limit: true, files: 1, file_limit: 100, projected_after_import: true },
    counts: { invoices: 2, lines: 10 }, actions: { inserted: 12 }, profile: { version: 1 },
    diagnostic: { name: "Sintético", engine: "JSON", source_sha256: "synthetic-hash", source_bytes: 1024, tables: [
      { name: "Zeta", rows: 2, linked: false, columns: [] },
      { name: "Álamo", rows: 10, linked: false, columns: [] },
      { name: "Vinculada", rows: null, linked: true, columns: [] },
    ] },
    incident_counts: { error: 0, warning: 0 }, incidents: [], summary: {}, page: 0, page_size: 50,
  };
  const responses: Record<string, unknown> = {
    "import.sources": [{ id: "synthetic-source", name: "Origen de prueba" }],
    "import.profiles": [],
    "import.batches": { items: [{ id: "synthetic-batch", status: "completed", created_at: "2024-01-01" }], total: 1 },
    "import.review": review,
    "import.records": { items: [], total: 0 },
    "import.reconcile": { balanced: false, status: "completed", totals, items: [], page: 0 },
  };
  await page.route("**/api", async route => {
    const request = route.request().postDataJSON() as { action: string };
    if (Object.hasOwn(responses, request.action)) await route.fulfill({ json: { ok: true, result: responses[request.action] } });
    else await route.fallback();
  });
  await page.goto("/");
  await sidebar(page, "Configuración");
  await page.getByRole("button", { name: "Importar Access", exact: true }).click();
  await page.getByText("Lotes conservados de este origen (1)", { exact: true }).click();
  await page.getByRole("button", { name: /^2024-01-01 ·/ }).click();
  const diagnostic = page.locator("section").filter({ has: page.getByRole("heading", { name: "2. Diagnóstico y mapeo", exact: true }) });
  await sortButton(diagnostic, "Filas").click();
  await expect(diagnostic.locator("tbody td:first-child")).toHaveText(["Zeta", "Álamo", "Vinculada"]);
  await sortButton(diagnostic, "Filas").click();
  await expect(diagnostic.locator("tbody td:first-child")).toHaveText(["Álamo", "Zeta", "Vinculada"]);
  const reconciliation = page.locator("section").filter({ has: page.getByRole("heading", { name: "5. Conciliación", exact: true }) });
  await sortButton(reconciliation, "Origen incluido").click();
  await expect(reconciliation.locator("tbody th")).toHaveText(["Facturas", "Líneas", "Base", "Total", "Cuota IVA"]);
  await expect(reconciliation.locator("tbody tr").last()).toContainText("No consta (1 históricos)");
  await sortButton(reconciliation, "Destino activo").click();
  await expect(reconciliation.locator("tbody th").first()).toHaveText("Cuota IVA");
  await expect(reconciliation.locator("tbody tr").first().locator("td").last()).toContainText("0,00");
  await expect(diagnostic.getByRole("button", { name: /^Acciones de/ })).toHaveCount(0);
  await expect(reconciliation.getByRole("button", { name: /^Acciones de/ })).toHaveCount(0);
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [1366, 390]) {
    test(`menús y cabeceras accesibles sin desbordamiento: ${theme} ${width}`, async ({ page, rpc }, info) => {
      await seed(rpc);
      await rpc("settings.save", { section: "appearance", values: { theme } });
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await sidebar(page, "Artículos y stock");
      await sortButton(page, "Referencia").click();
      await expect(page.locator("tbody tr").first()).toContainText("Artículo dos");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(`tabla-entidades-${theme}-${width}.png`), fullPage: true });
      const trigger = page.getByRole("button", { name: "Acciones de Artículo diez", exact: true });
      await trigger.click();
      await expect(page.getByRole("menuitem", { name: "Existencias", exact: true })).toBeVisible();
      await expect(page.getByRole("dialog", { name: "Editar artículo", exact: true })).toHaveCount(0);
      await settle(page);
      const violations = (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations;
      expect(violations).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(`menu-entidades-${theme}-${width}.png`), fullPage: true });
      await page.keyboard.press("Escape");
      await expect(page.getByRole("menu")).toHaveCount(0);
      await expect(trigger).toBeFocused();
    });
  }
}
