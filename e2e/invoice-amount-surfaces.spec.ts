import AxeBuilder from "@axe-core/playwright";
import type { Locator, Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { test, expect } from "./fixtures";

type Rpc = <T = Record<string, unknown>>(action: string, params?: Record<string, unknown>) => Promise<T>;
type Seed = { customer: string; vehicle: string; documents: Record<string, string> };
const customerName = "Cliente de importes sintético";
const amounts = [
  ["IMP-ESTIMADA", "121,00", "Estimado"],
  ["IMP-CONTRASTADA", "236,00", "Contrastado con original"],
  ["IMP-PENDIENTE", "No consta", ""],
  ["IMP-ORIGINAL", "363,00", ""],
  ["IMP-CERO", "0,00", ""],
] as const;

// The fixture directory belongs to this E2E. No existing workshop data is opened.
async function seed(rpc: Rpc): Promise<Seed> {
  const { data_directory } = await rpc<{ data_directory: string }>("bootstrap");
  const python = resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  return JSON.parse(execFileSync(python, ["-X", "utf8", "-c", `
import sys,json
sys.path.insert(0,'backend')
from taller.app import App
from taller.db import dumps
app=App(sys.argv[1])
customer=app.contacts.save_customer({'name':'Cliente de importes sintético'})
vehicle=app.contacts.save_vehicle({'customer_id':customer['id'],'plate':'IMP-001','kind':'Vehículo de importes sintético'})
line={'description':'Reparación de importes sintética','quantity':None,'unit_price':None,'discount':None,'base_cents':None,'tax_cents':None,'total_cents':None,'amount_raw':'100','tax_rate':None,'tax_kind':'historical'}
cases=[('IMP-ESTIMADA',[line],None,None,None),('IMP-CONTRASTADA',[dict(line,amount_raw='200')],None,None,None),('IMP-PENDIENTE',[],None,None,None),('IMP-ORIGINAL',[],30000,6300,36300),('IMP-CERO',[],0,0,0)]
result={'customer':customer['id'],'vehicle':vehicle['id'],'documents':{}}
for index,(number,lines,base,tax,total) in enumerate(cases):
 document=app.documents.save({'customer_id':customer['id'],'vehicle_id':vehicle['id'],'lines':[{'description':'Borrador sintético','unit_price':'1'}]})
 payload={'invoice_type':'F1','historical':True,'preservation':'partial' if total is None else 'complete','payment_state':'unknown','date_state':'known','date_candidates':[],'base_cents':base,'tax_cents':tax,'total_cents':total,'amounts_provenance':{'policy':'source_only_no_rounding','line_amount':'unclassified'},'lines':lines,'taxes':[],'customer':{},'issuer':{},'branding':{},'kilometres':None,'payment_method':'unknown','footer':''}
 with app.db.transaction() as conn:
  conn.execute("UPDATE documents SET status='historical',full_number=?,issue_date=?,due_date='',payload=?,base_cents=?,tax_cents=?,total_cents=? WHERE id=?",(number,f'2024-06-{15+index:02}',dumps(payload),base,tax,total,document['id']))
 result['documents'][number]=document['id']
 app.documents.get(document['id'])
app.historical_reviews.save(result['documents']['IMP-CONTRASTADA'],expected_version=0,tax_rate='18',reason='Contraste sintético',verified=True,evidence='Original sintético: base 200, IVA 36, total 236')
print(json.dumps(result))
`, data_directory], { cwd: resolve("."), encoding: "utf8" }));
}

async function assertAmounts(container: Locator) {
  for (const [number, total, provenance] of amounts) {
    const row = container.getByRole("row").filter({ has: container.page().getByRole("button", { name: number, exact: true }) });
    await expect(row).toContainText(total);
    if (provenance) await expect(row.locator(".historical-list-total small")).toHaveText(provenance);
    else await expect(row.locator(".historical-list-total")).toHaveCount(0);
    if (number === "IMP-PENDIENTE") await expect(row).not.toContainText("0,00");
  }
}

async function settleAnimations(page: Page) {
  await page.evaluate(async () => {
    while (true) {
      const active = document.getAnimations().filter(animation => animation.playState === "running" && Number.isFinite(animation.effect?.getComputedTiming().endTime));
      if (!active.length) return;
      await Promise.all(active.map(animation => animation.finished.catch(() => undefined)));
    }
  });
}

for (const theme of ["light", "dark"] as const) {
  for (const width of [1366, 390]) {
    test(`importes y procedencia coherentes en Inicio, cliente, vehículo e historial: ${theme} ${width}`, async ({ page, rpc }, info) => {
      const ids = await seed(rpc);
      await rpc("settings.save", { section: "appearance", values: { theme } });
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      const home = page.locator("section").filter({ has: page.getByRole("heading", { name: "Últimas facturas", exact: true }) });
      await assertAmounts(home);
      await settleAnimations(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(`inicio-${theme}-${width}.png`), fullPage: true });
      await home.getByRole("button", { name: customerName, exact: true }).first().click();
      await expect(page.getByRole("heading", { level: 1, name: customerName, exact: true })).toBeVisible();
      const customerHistory = page.locator("section").filter({ has: page.getByRole("heading", { name: "Historial de facturas", exact: true }) });
      await assertAmounts(customerHistory);
      await settleAnimations(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(`cliente-${theme}-${width}.png`), fullPage: true });
      await page.getByRole("button", { name: "Historial y titular", exact: true }).click();
      await expect(page.getByRole("heading", { level: 1, name: "IMP-001", exact: true })).toBeVisible();
      const vehicleHistory = page.locator("section").filter({ has: page.getByRole("heading", { name: "Facturas del vehículo", exact: true }) });
      await assertAmounts(vehicleHistory);
      await page.getByRole("button", { name: "Consultar trabajos del historial", exact: true }).click();
      const historySearch = page.locator(".history-search");
      for (const [number, total, provenance] of amounts) {
        const result = historySearch.getByRole("button").filter({ hasText: number });
        await expect(result).toContainText(total);
        if (provenance) await expect(result.locator(".historical-list-total small")).toHaveText(provenance);
        else await expect(result.locator(".historical-list-total")).toHaveCount(0);
      }
      await historySearch.getByRole("textbox", { name: "Palabras que constan en el historial", exact: true }).fill("Reparación de importes sintética");
      await expect(historySearch.locator(".pick-list > button")).toHaveCount(2);
      await expect(historySearch.locator(".pick-list")).toContainText("121,00");
      await expect(historySearch.locator(".pick-list")).toContainText("236,00");
      await settleAnimations(page);
      const violations = (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations;
      await info.attach("importes-axe.json", { body: JSON.stringify(violations), contentType: "application/json" });
      expect(violations).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: info.outputPath(`vehiculo-historial-${theme}-${width}.png`), fullPage: true });
      await historySearch.getByRole("button").filter({ hasText: "IMP-ESTIMADA" }).click();
      await expect(page.getByRole("heading", { name: "Estimación del histórico", exact: true })).toBeVisible();
      const original = await rpc<{ total_cents: number | null; payment_known: boolean }>("documents.get", { identifier: ids.documents["IMP-ESTIMADA"] });
      expect(original.total_cents).toBeNull();
      expect(original.payment_known).toBe(false);
    });
  }
}
