import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { test, expect, navigateSidebar } from "./fixtures";

type Rpc = <T = Record<string, unknown>>(action: string, params?: Record<string, unknown>) => Promise<T>;

async function seed(rpc: Rpc): Promise<Record<string, string>> {
  const { data_directory } = await rpc<{ data_directory: string }>("bootstrap");
  const python = resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  return JSON.parse(execFileSync(python, ["-X", "utf8", "-c", `
import json,sys
sys.path.insert(0,'backend')
from taller.app import App
from taller.db import dumps
app=App(sys.argv[1])
customer=app.contacts.save_customer({'name':'Cliente sintético de informes'})
line={'description':'Reparación sintética','quantity':None,'unit_price':None,'discount':None,'base_cents':None,'tax_cents':None,'total_cents':None,'amount_raw':'200','tax_rate':None,'tax_kind':'historical'}
cases=[('original','2024-06-15',[],10000,2100,12100),('zero','2024-06-16',[],0,0,0),('estimate','2024-06-17',[line],None,None,None),('verified','2024-06-18',[dict(line,amount_raw='300')],None,None,None),('pending','2024-06-19',[],None,None,None),('unknown_month','2024-07-01',[],None,None,None),('undated',None,[line],None,None,None)]
result={}
for name,date,lines,base,tax,total in cases:
 d=app.documents.save({'customer_id':customer['id'],'lines':[{'description':'Borrador sintético','unit_price':'1'}]})
 payload={'historical':True,'preservation':'partial' if total is None else 'complete','payment_state':'unknown','date_state':'known' if date else 'missing','base_cents':base,'tax_cents':tax,'total_cents':total,'amounts_provenance':{'policy':'source_only_no_rounding','line_amount':'unclassified'},'lines':lines,'taxes':[],'customer':{},'issuer':{},'branding':{}}
 with app.db.transaction() as conn:
  conn.execute("UPDATE documents SET status='historical',full_number=?,issue_date=?,due_date='',payload=?,base_cents=?,tax_cents=?,total_cents=? WHERE id=?",('INF-'+name,date,dumps(payload),base,tax,total,d['id']))
 result[name]=d['id']
app.documents.get(result['verified'])
app.historical_reviews.save(result['verified'],expected_version=0,tax_rate='18',reason='Contraste sintético',verified=True,evidence='Original sintético: base 300, IVA 54, total 354')
print(json.dumps(result))
`, data_directory], { cwd: resolve("."), encoding: "utf8" }));
}

async function openReports(page: Page) {
  await page.goto("/");
  await navigateSidebar(page, "Resumen");
  await page.getByRole("button", { name: "Todo el historial", exact: true }).click();
}

async function applyPeriod(page: Page, start: string, end: string) {
  await page.getByLabel("Desde", { exact: true }).fill(start);
  await page.getByLabel("Hasta", { exact: true }).fill(end);
  await page.getByRole("button", { name: "Aplicar período", exact: true }).click();
}

async function settleAnimations(page: Page) {
  await page.evaluate(async () => {
    const running = document.getAnimations().filter(animation =>
      animation.playState === "running" && Number.isFinite(animation.effect?.getComputedTiming().endTime));
    await Promise.all(running.map(animation => animation.finished.catch(() => undefined)));
  });
}

for (const theme of ["light", "dark"] as const) {
  for (const width of [1366, 390]) {
    test(`Resumen distingue originales, contrastados, estimados y desconocidos: ${theme} ${width}`, async ({ page, rpc }, info) => {
      await seed(rpc);
      await rpc("settings.save", { section: "appearance", values: { theme } });
      await page.setViewportSize({ width, height: 900 });
      await openReports(page);
      const card = page.locator(".stat-card").filter({ hasText: "Importe de facturas del período" });
      await expect(card).toContainText("717,00");
      await expect(card).toContainText("4 de 6 facturas con importe");
      await expect(card).toContainText(/Incluye 242,00\s*€ estimados/);
      await expect(page.getByText(/2 facturas del período siguen sin importe disponible/)).toBeVisible();
      await expect(page.getByText(/1 históricos no conservan fecha confirmada/)).toBeVisible();
      const monthly = page.getByRole("table", { name: "Importes de facturas por mes", exact: true });
      const june = monthly.getByRole("row").filter({ hasText: "junio de 2024" });
      await expect(june.getByRole("cell")).toHaveText(["junio de 2024 5 facturas", /121,00/, /354,00/, /242,00/, /717,00/, "1"]);
      await expect(june.getByRole("cell").first().locator("small")).toHaveText("5 facturas");
      const july = monthly.getByRole("row").filter({ hasText: "julio de 2024" });
      await expect(july).toContainText("No consta");
      await expect(july).not.toContainText("0,00");
      for (const label of ["Cobros netos del período", "Pendiente de cobro hoy", "Pendiente de devolver hoy"]) {
        await expect(page.locator(".stat-card").filter({ hasText: label })).toContainText("0,00");
      }
      await page.getByText("Desglose fiscal original", { exact: true }).click();
      const original = page.getByRole("table", { name: "Desglose fiscal original por mes", exact: true });
      await expect(original.getByRole("row").filter({ hasText: "junio de 2024" }).getByRole("cell")).toHaveText(["junio de 2024", "2", /100,00/, /21,00/, /121,00/]);
      const downloadEvent = page.waitForEvent("download");
      await page.getByRole("button", { name: "Exportar importes de facturas", exact: true }).click();
      const downloaded = await downloadEvent;
      const csv = await readFile((await downloaded.path())!, "utf8");
      expect(csv).toContain("month;count;amount_count;unknown_count;total_cents;original_count;original_cents;verified_count;verified_cents;estimated_count;estimated_cents");
      expect(csv).toContain("2024-06;5;4;1;71700;2;12100;1;35400;1;24200");
      expect(csv).toContain("2024-07;1;0;1;;0;0;0;0;0;0");
      if (width === 390) {
        const region = page.getByRole("region", { name: "Tabla de importes de facturas", exact: true });
        await region.focus();
        await page.keyboard.press("ArrowRight");
        await expect.poll(() => region.evaluate(element => element.scrollLeft)).toBeGreaterThan(0);
      }
      await settleAnimations(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const violations = (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations;
      await info.attach("informes-axe.json", { body: JSON.stringify(violations), contentType: "application/json" });
      expect(violations).toEqual([]);
      await page.getByRole("heading", { level: 1, name: "Resumen del taller", exact: true }).click();
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: info.outputPath(`informes-${theme}-${width}.png`), fullPage: true });
    });
  }
}

test("el período y la revisión actualizan los importes sin inventar ceros ni duplicar versiones", async ({ page, rpc }) => {
  const ids = await seed(rpc);
  await openReports(page);
  const card = page.locator(".stat-card").filter({ hasText: "Importe de facturas del período" });
  await expect(card).toContainText("717,00");
  await applyPeriod(page, "2024-07-01", "2024-07-31");
  await expect(card).toContainText("No consta");
  await expect(card).toContainText("0 de 1 facturas con importe");
  await expect(card).not.toContainText("0,00");
  await applyPeriod(page, "2024-08-01", "2024-08-31");
  await expect(card).toContainText("0,00");
  await expect(card).toContainText("0 de 0 facturas con importe");
  await expect(page.getByText("Sin facturas en este período", { exact: true })).toBeVisible();
  await applyPeriod(page, "2024-06-16", "2024-06-16");
  await expect(card).toContainText("0,00");
  await expect(card).toContainText("1 de 1 facturas con importe");
  await rpc("historical.review_save", { identifier: ids.estimate, expected_version: 0, tax_rate: "18", reason: "Cambio sintético de revisión" });
  await page.getByRole("button", { name: "Todo el historial", exact: true }).click();
  await expect(card).toContainText("711,00");
  await expect(card).toContainText(/Incluye 236,00\s*€ estimados/);
  const original = await rpc<{ total_cents: null; payment_known: boolean }>("documents.get", { identifier: ids.estimate });
  expect(original.total_cents).toBeNull();
  expect(original.payment_known).toBe(false);
});

test("un fallo al cambiar de período no presenta cifras anteriores y permite reintentar", async ({ page, rpc }) => {
  await seed(rpc);
  await openReports(page);
  const card = page.locator(".stat-card").filter({ hasText: "Importe de facturas del período" });
  await expect(card).toContainText("717,00");
  let fail = true;
  await page.route("**/api", async route => {
    const request = route.request().postDataJSON();
    if (fail && request.action === "reports" && request.params.start === "2024-07-01") {
      await route.fulfill({ json: { ok: false, error: { code: "unavailable", message: "Fallo sintético al consultar el período." } } });
    } else await route.fallback();
  });
  await applyPeriod(page, "2024-07-01", "2024-07-31");
  await expect(page.getByText("Fallo sintético al consultar el período.", { exact: true })).toBeVisible();
  await expect(card).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Exportar importes de facturas", exact: true })).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "Reintentar resumen", exact: true }).click();
  await expect(card).toContainText("No consta");
  await expect(card).toContainText("0 de 1 facturas con importe");
  await expect(page.getByText("Fallo sintético al consultar el período.", { exact: true })).toHaveCount(0);
});
