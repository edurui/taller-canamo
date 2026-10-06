import { test, expect } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("histórico incompleto conserva ausencias sin presentar cobros ni rectificativas", async ({ page, rpc }, testInfo) => {
  const bootstrap = await rpc<{ data_directory: string }>("bootstrap");
  const python = resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  execFileSync(python, ["-c", [
    "import sys;sys.path[:0]=['backend','tests']",
    "from taller.app import App",
    "from test_partial_history import partial_history",
    "app=App(sys.argv[1])",
    "customer=app.contacts.save_customer({'name':'Histórico sintético incompleto'})",
    "draft=app.documents.save({'customer_id':customer['id'],'lines':[{'description':'Temporal sintético','unit_price':'1'}]})",
    "partial_history(app,draft,lines=[{'description':'Concepto original conservado','quantity':None,'unit_price':None,'discount':None,'base_cents':None,'tax_cents':None,'total_cents':None,'amount_raw':'12.3456789','tax_rate':None,'tax_kind':'historical'}])",
  ].join(";"), bootstrap.data_directory], { cwd: resolve(".") });
  await page.goto("/");
  await page.getByRole("button", { name: "Facturas", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: "H-PARTIAL" });
  await expect(row).toContainText("No consta");
  await expect(row).not.toContainText("0,00");
  await page.getByRole("button", { name: "H-PARTIAL", exact: true }).click();
  await expect(page.getByText(/Histórico incompleto. Los datos ausentes/)).toBeVisible();
  await expect(page.getByText("Importe original sin clasificación fiscal: 12,3456789")).toBeVisible();
  await expect(page.getByRole("button", { name: "Crear rectificativa", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Documentar saldo inicial", exact: true })).toHaveCount(0);
  await expect(page.getByText("El total histórico no consta. No se puede calcular un saldo ni registrar cobros.")).toBeVisible();
  await expect(page.getByLabel("Fecha del documento", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Cantidad 1", { exact: true })).toHaveValue("");
  await expect(page.locator(".summary-total")).toContainText("No consta");
  await expect(page.locator(".line-total")).toContainText("No consta");
  await page.getByRole("button", { name: "Descuentos y exenciones", exact: true }).click();
  await expect(page.getByLabel("Descuento %", { exact: true })).toHaveValue("");
  await expect(page.getByRole("combobox", { name: "Tratamiento del IVA", exact: true })).toContainText("No consta clasificación fiscal");
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(accessibility.violations).toEqual([]);
  const screenshot = testInfo.outputPath("historico-incompleto-sintetico.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("historico-incompleto-sintetico", { path: screenshot, contentType: "image/png" });
});
