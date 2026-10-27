import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { test, expect, navigateSidebar } from "./fixtures";

type Rpc = <T = Record<string, unknown>>(action: string, params?: Record<string, unknown>) => Promise<T>;
async function seed(rpc: Rpc, count = 56) {
  const { data_directory } = await rpc<{ data_directory: string }>("bootstrap");
  const python = resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  return JSON.parse(execFileSync(python, ["-X", "utf8", "-c", `
import json,sys
from datetime import date,timedelta
sys.path.insert(0,'backend')
from taller.app import App
from taller.db import dumps
app=App(sys.argv[1])
customer=app.contacts.save_customer({'name':'Cliente ordenación sintético','tax_id':'12345678Z'})
vehicle=app.contacts.save_vehicle({'customer_id':customer['id'],'plate':'LIST-001','kind':'Vehículo sintético'})
for i in range(${count}):
 d=app.documents.save({'customer_id':customer['id'],'vehicle_id':vehicle['id'],'issue_date':str(date(2024,1,1)+timedelta(days=i)),'lines':[{'description':'Trabajo de ordenación sintético','unit_price':str(i+1)}]})
 payload={**d['payload'],'historical':True,'payment_state':'unknown','customer':{'name':customer['name']},'vehicle':{'plate':'LIST-001'}}
 with app.db.transaction() as conn: conn.execute("UPDATE documents SET status='historical',full_number=?,payload=? WHERE id=?",(f'LIST-{i:03}',dumps(payload),d['id']))
print(json.dumps({'customer':customer['id'],'vehicle':vehicle['id']}))
`, data_directory], { cwd: resolve("."), encoding: "utf8" }));
}
async function sidebar(page: Page, name: string) {
  await navigateSidebar(page, name);
}
async function invoices(page: Page) { await page.goto("/"); await sidebar(page, "Facturas"); }
function sort(page: Page, label: string) { return page.getByRole("button", { name: new RegExp(`^${label}: ordenar `) }); }
const numbers = (page: Page) => page.locator("tbody tr td:first-child strong");
async function settle(page: Page) {
  await page.evaluate(async () => {
    while (true) {
      const running = document.getAnimations().filter(a => a.playState === "running" && Number.isFinite(a.effect?.getComputedTiming().endTime));
      if (!running.length) return;
      await Promise.all(running.map(a => a.finished.catch(() => undefined)));
    }
  });
}

test("facturas ordenan globalmente antes de paginar, preservan foco y recuperan orden original", async ({ page, rpc }) => {
  await seed(rpc); await invoices(page);
  await expect(numbers(page).first()).toHaveText("LIST-055");
  await page.getByRole("button", { name: "Siguiente", exact: true }).click();
  await expect(page.locator(".pager")).toContainText("51–56");
  await sort(page, "Total").focus(); await sort(page, "Total").press("Enter");
  await expect(numbers(page).first()).toHaveText("LIST-000");
  await expect(page.locator(".pager")).toContainText("1–50");
  await expect(sort(page, "Total")).toBeFocused();
  await expect(page.getByRole("columnheader").filter({ has: sort(page, "Total") })).toHaveAttribute("aria-sort", "ascending");
  await page.getByRole("button", { name: "Siguiente", exact: true }).click();
  await expect(numbers(page)).toHaveText(["LIST-050", "LIST-051", "LIST-052", "LIST-053", "LIST-054", "LIST-055"]);
  await sort(page, "Total").click(); await expect(numbers(page).first()).toHaveText("LIST-055");
  await sort(page, "Total").click(); await expect(numbers(page).first()).toHaveText("LIST-055");
  await expect(page.getByRole("columnheader").filter({ has: sort(page, "Total") })).toHaveAttribute("aria-sort", "none");
  await sort(page, "Número").click(); await expect(numbers(page).first()).toHaveText("LIST-000");
  await sort(page, "Fecha").click(); await expect(numbers(page).first()).toHaveText("LIST-000");
  await page.getByRole("textbox", { name: "Buscar documentos", exact: true }).fill("LIST-054");
  const row = page.getByRole("row").filter({ has: page.getByRole("button", { name: "LIST-054", exact: true }) });
  await row.getByRole("cell").nth(4).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("LIST-054");
});

test("la respuesta antigua de ordenación no reemplaza la actual y los errores bloquean filas anteriores", async ({ page, rpc }) => {
  await seed(rpc); await invoices(page); await expect(numbers(page).first()).toHaveText("LIST-055");
  let release!: () => void; const blocked = new Promise<void>(resolve => { release = resolve; });
  let started!: () => void; const waiting = new Promise<void>(resolve => { started = resolve; });
  let fail = false;
  await page.route("**/api", async route => {
    const request = route.request().postDataJSON();
    if (request.action === "documents.list" && fail) {
      await route.fulfill({ json: { ok: false, error: { code: "unavailable", message: "Fallo sintético de ordenación" } } });
    } else if (request.action === "documents.list" && request.params.sort_by === "total_cents" && request.params.sort_direction === "asc") {
      const response = await route.fetch(); started(); await blocked; await route.fulfill({ response });
    } else await route.fallback();
  });
  try {
    await sort(page, "Total").click(); await waiting;
    await expect(page.getByRole("button", { name: "LIST-055", exact: true })).toBeDisabled();
    await sort(page, "Total").click(); await expect(page.getByRole("table")).toHaveAttribute("aria-busy", "false");
    await expect(numbers(page).first()).toHaveText("LIST-055"); release();
    await expect(page.getByRole("columnheader").filter({ has: sort(page, "Total") })).toHaveAttribute("aria-sort", "descending");
    fail = true; await sort(page, "Fecha").click();
    await expect(page.getByText("Fallo sintético de ordenación", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "LIST-055", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Acciones de LIST-055", exact: true })).toBeDisabled();
    fail = false; await sort(page, "Fecha").click();
    await expect(page.getByRole("button", { name: "LIST-055", exact: true })).toBeEnabled();
  } finally { release(); }
});

test("menú de borrador exige confirmar y vuelve a una página válida tras eliminar el último", async ({ page, rpc }) => {
  const ids = await seed(rpc, 50);
  const draft = await rpc<{ id: string }>("documents.save", { data: { customer_id: ids.customer, lines: [{ description: "Borrador descartable", unit_price: "10" }] } });
  await invoices(page);
  await sort(page, "Fecha").click();
  await page.getByRole("button", { name: "Siguiente", exact: true }).click();
  await expect(page.locator(".pager")).toContainText("51–51");
  await page.getByRole("button", { name: "Acciones de borrador", exact: true }).click();
  await page.getByRole("menuitem", { name: "Eliminar borrador", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Eliminar borrador", exact: true });
  await dialog.getByRole("button", { name: "Volver", exact: true }).click();
  expect((await rpc<{ id: string }>("documents.get", { identifier: draft.id })).id).toBe(draft.id);
  await page.getByRole("button", { name: "Acciones de borrador", exact: true }).click();
  await page.getByRole("menuitem", { name: "Eliminar borrador", exact: true }).click();
  await dialog.getByRole("button", { name: "Eliminar borrador", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Acciones de borrador", exact: true })).toHaveCount(0);
  expect((await rpc<{ total: number }>("documents.list")).total).toBe(50);
  await expect(page.locator("tbody tr")).toHaveCount(50);
  await expect(numbers(page).first()).toHaveText("LIST-000");
});

for (const theme of ["light", "dark"] as const) for (const width of [1366, 390]) {
  test(`menús, columnas y enlaces accesibles: ${theme} ${width}`, async ({ page, rpc }, info) => {
    await seed(rpc); await rpc("settings.save", { section: "appearance", values: { theme } });
    await page.setViewportSize({ width, height: 900 }); await invoices(page);
    const trigger = page.getByRole("button", { name: "Acciones de LIST-055", exact: true });
    await trigger.focus(); await trigger.press("Enter");
    const menu = page.getByRole("menu", { name: "Acciones de LIST-055", exact: true });
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: "Abrir documento", exact: true })).toBeFocused();
    const actionBounds = await menu.getByRole("menuitem", { name: "Abrir documento", exact: true }).boundingBox();
    expect(actionBounds!.x).toBeGreaterThanOrEqual(8);
    expect(actionBounds!.x + actionBounds!.width).toBeLessThanOrEqual(width - 8);
    await page.keyboard.press("End"); await expect(menu.getByRole("menuitem", { name: "Ver vehículo", exact: true })).toBeFocused();
    await page.keyboard.press("ArrowUp"); await expect(menu.getByRole("menuitem", { name: "Ver cliente", exact: true })).toBeFocused();
    await page.keyboard.press("Home"); await expect(menu.getByRole("menuitem", { name: "Abrir documento", exact: true })).toBeFocused();
    await settle(page);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: info.outputPath(`menu-${theme}-${width}.png`) });
    await page.keyboard.press("Escape"); await expect(menu).toHaveCount(0); await expect(trigger).toBeFocused();
    await settle(page);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const row = page.getByRole("row").filter({ has: trigger });
    await row.getByRole("button", { name: "Cliente ordenación sintético", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Cliente ordenación sintético", exact: true })).toBeVisible();
  });
}

test("Inicio y resúmenes ordenan sólo su conjunto sin modificar los importes", async ({ page, rpc }) => {
  await seed(rpc); await page.goto("/");
  const recent = page.locator("section").filter({ has: page.getByRole("heading", { name: "Últimas facturas", exact: true }) });
  await expect(recent.locator("tbody tr")).toHaveCount(5);
  await recent.getByRole("button", { name: "Total: ordenar ascendente", exact: true }).click();
  await expect(recent.locator("tbody tr").first()).toContainText("LIST-051");
  await sidebar(page, "Resumen"); await page.getByRole("button", { name: "Todo el historial", exact: true }).click();
  const monthly = page.getByRole("table", { name: "Importes de facturas por mes", exact: true });
  const original = await monthly.locator("tbody").textContent();
  await monthly.getByRole("button", { name: "Mes: ordenar ascendente", exact: true }).click();
  await expect(monthly.locator("tbody tr").first()).toContainText("enero de 2024");
  await monthly.getByRole("button", { name: "Mes: ordenar descendente", exact: true }).click();
  await expect(monthly.locator("tbody tr").first()).toContainText("febrero de 2024");
  await monthly.getByRole("button", { name: "Mes: ordenar original", exact: true }).click();
  await expect(monthly.locator("tbody")).toHaveText(original!);
});
