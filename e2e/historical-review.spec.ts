import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { test, expect, chooseOption } from "./fixtures";

type Rpc = <T = Record<string, unknown>>(action: string, params?: Record<string, unknown>) => Promise<T>;
type Review = {
  state: "estimated" | "pending_review" | "verified";
  version: number;
  tax_rate: string | null;
  base_cents: number | null;
  tax_cents: number | null;
  total_cents: number | null;
};
type HistoricalDocument = {
  id: string;
  base_cents: number | null;
  tax_cents: number | null;
  total_cents: number | null;
  payment_known: boolean;
  can_rectify: boolean;
  payload: unknown;
  historical_review: Review | null;
};

async function seed(rpc: Rpc): Promise<Record<string, string>> {
  const { data_directory } = await rpc<{ data_directory: string }>("bootstrap");
  const python = resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  const script = `
import sys,json
sys.path.insert(0,'backend')
from taller.app import App
from taller.db import dumps
app=App(sys.argv[1])
customer=app.contacts.save_customer({'name':'Cliente de revisión sintético'})
line={'description':'Trabajo histórico sintético','quantity':None,'unit_price':None,'discount':None,'base_cents':None,'tax_cents':None,'total_cents':None,'amount_raw':'100','tax_rate':None,'tax_kind':'historical'}
cases=[
 ('H-16','2010-06-30',[line]),
 ('H-18-INICIO','2010-07-01',[line]),
 ('H-18-FIN','2012-08-31',[line]),
 ('H-21-INICIO','2012-09-01',[line]),
 ('H-21','2024-06-15',[line]),
 ('H-REDONDEO','2024-06-16',[dict(line,amount_raw='100.004'),dict(line,amount_raw='0.004')]),
 ('H-SIN-LINEAS','2024-06-17',[]),
 ('H-SIN-IMPORTE','2024-06-18',[dict(line,amount_raw=None)]),
 ('H-FECHA',None,[line]),
 ('H-DISCREPANCIA','2024-06-19',[dict(line,quantity='1',unit_price='99')]),
]
result={}
for number,issue_date,lines in cases:
 d=app.documents.save({'customer_id':customer['id'],'lines':[{'description':'Borrador sintético','unit_price':'1'}]})
 payload={'invoice_type':'F1','historical':True,'preservation':'partial','payment_state':'unknown','date_state':'known' if issue_date else 'conflict','date_candidates':[] if issue_date else ['2012-08-31','2012-09-01'],'base_cents':None,'tax_cents':None,'total_cents':None,'amounts_provenance':{'policy':'source_only_no_rounding','line_amount':'unclassified'},'lines':lines,'taxes':[],'customer':{},'issuer':{},'branding':{},'kilometres':None,'payment_method':'unknown','footer':''}
 with app.db.transaction() as conn:
  conn.execute("UPDATE documents SET status='historical',full_number=?,due_date='',payload=?,issue_date=?,base_cents=NULL,tax_cents=NULL,total_cents=NULL WHERE id=?",(number,dumps(payload),issue_date,d['id']))
 result[number]=d['id']
 app.documents.get(d['id'])
print(json.dumps(result))
`;
  return JSON.parse(execFileSync(python, ["-c", script, data_directory], { cwd: resolve("."), encoding: "utf8" }));
}

async function invoices(page: Page) {
  await page.goto("/");
  await expect(page.locator(".sidebar")).toBeAttached();
  const menu = page.getByRole("button", { name: "Abrir menú", exact: true });
  if (await menu.isVisible()) await menu.click();
  await page.locator(".sidebar").getByRole("button", { name: "Facturas", exact: true }).click();
}

async function settleAnimations(page: Page) {
  await page.evaluate(async () => {
    while (true) {
      const running = document.getAnimations().filter(animation =>
        animation.playState === "running" && Number.isFinite(animation.effect?.getComputedTiming().endTime));
      if (!running.length) return;
      await Promise.all(running.map(animation => animation.finished.catch(() => undefined)));
    }
  });
}

async function openDocument(page: Page, number = "H-21") {
  await invoices(page);
  await page.getByRole("button", { name: number, exact: true }).click();
  await expect(page.getByRole("heading", { name: "Estimación del histórico", exact: true })).toBeVisible();
}

test("tipos históricos, redondeo y filtro de incidencias se presentan como estimaciones", async ({ page, rpc }) => {
  const ids = await seed(rpc);
  await invoices(page);
  for (const [number, total] of [["H-16", "116,00"], ["H-18-INICIO", "118,00"], ["H-18-FIN", "118,00"], ["H-21-INICIO", "121,00"], ["H-REDONDEO", "121,01"]]) {
    const row = page.getByRole("row").filter({ has: page.getByRole("button", { name: number, exact: true }) });
    await expect(row).toContainText(total);
    await expect(row).toContainText(/Estimad[oa]/);
    const original = await rpc<HistoricalDocument>("documents.get", { identifier: ids[number] });
    expect(original.total_cents).toBeNull();
    expect(original.payment_known).toBe(false);
    expect(original.can_rectify).toBe(false);
  }
  await chooseOption(page.getByRole("combobox", { name: "Revisión del histórico", exact: true }), "pending_review");
  await expect(page.getByRole("button", { name: "H-21", exact: true })).toHaveCount(0);
  for (const number of ["H-SIN-LINEAS", "H-SIN-IMPORTE", "H-FECHA", "H-DISCREPANCIA"]) {
    const row = page.getByRole("row").filter({ has: page.getByRole("button", { name: number, exact: true }) });
    await expect(row).toContainText("Pendiente de revisión");
    await expect(row).toContainText("No consta");
    await expect(row).not.toContainText("0,00");
  }
});

test("el nombre del cliente vinculado permite buscar y navegar desde listado y detalle", async ({ page, rpc }) => {
  const ids = await seed(rpc);
  const original = await rpc<HistoricalDocument>("documents.get", { identifier: ids["H-21"] });
  await page.goto("/");
  const recent = page.getByRole("row").filter({ has: page.getByRole("button", { name: "H-DISCREPANCIA", exact: true }) });
  await recent.getByRole("button", { name: "Cliente de revisión sintético", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Cliente de revisión sintético", exact: true })).toBeVisible();
  await invoices(page);
  await page.getByPlaceholder("Número, cliente o matrícula").fill("Cliente de revisión sintético");
  const row = page.getByRole("row").filter({ has: page.getByRole("button", { name: "H-21", exact: true }) });
  await row.getByRole("button", { name: "Cliente de revisión sintético", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Cliente de revisión sintético", exact: true })).toBeVisible();
  await openDocument(page);
  await page.getByRole("button", { name: "Cliente de revisión sintético", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Cliente de revisión sintético", exact: true })).toBeVisible();
  const after = await rpc<HistoricalDocument>("documents.get", { identifier: ids["H-21"] });
  expect(after.payload).toEqual(original.payload);
});

test("ajustar un porcentaje y contrastarlo persiste aparte sin cambiar la factura ni crear saldo", async ({ page, rpc, backend }) => {
  const ids = await seed(rpc);
  const original = await rpc<HistoricalDocument>("documents.get", { identifier: ids["H-21"] });
  await openDocument(page);
  await page.getByRole("button", { name: "Revisar estimación", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "Revisar estimación", exact: true });
  await dialog.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true }).fill("18");
  await dialog.getByRole("textbox", { name: "Motivo de la revisión", exact: true }).fill("Porcentaje alternativo para la revisión sintética");
  await expect(dialog).toContainText("118,00");
  await dialog.getByRole("button", { name: "Guardar revisión", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  let saved = await rpc<HistoricalDocument>("documents.get", { identifier: ids["H-21"] });
  expect(saved.historical_review?.state).toBe("estimated");
  expect(saved.historical_review?.tax_rate).toBe("18");
  expect(saved.payload).toEqual(original.payload);
  expect(saved.total_cents).toBeNull();
  await page.getByRole("button", { name: "Revisar estimación", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Revisar estimación", exact: true });
  await dialog.getByRole("textbox", { name: "Motivo de la revisión", exact: true }).fill("Contraste con documento de prueba conservado");
  await dialog.getByLabel("He cotejado estos importes con el documento original", { exact: true }).check();
  await dialog.getByRole("textbox", { name: "Evidencia del contraste", exact: true }).fill("Documento exclusivamente sintético: base 100,00 EUR, IVA 18,00 EUR y total 118,00 EUR");
  await dialog.getByRole("button", { name: "Guardar revisión", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("Contrastada con original", { exact: true }).first()).toBeVisible();
  await backend.restart();
  saved = await rpc<HistoricalDocument>("documents.get", { identifier: ids["H-21"] });
  expect(saved.historical_review?.state).toBe("verified");
  expect(saved.payload).toEqual(original.payload);
  expect([saved.base_cents, saved.tax_cents, saved.total_cents]).toEqual([null, null, null]);
  expect(saved.payment_known).toBe(false);
  expect(saved.can_rectify).toBe(false);
  await openDocument(page);
  await expect(page.getByRole("button", { name: "Crear rectificativa", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Documentar saldo inicial", exact: true })).toHaveCount(0);
});

test("una respuesta antigua de cálculo no sustituye al porcentaje actual", async ({ page, rpc }) => {
  const ids = await seed(rpc);
  let release!: () => void;
  const blocked = new Promise<void>(resolve => { release = resolve; });
  let oldStarted!: () => void;
  const started = new Promise<void>(resolve => { oldStarted = resolve; });
  await page.route("**/api", async route => {
    const request = route.request().postDataJSON();
    if (request.action === "historical.review_preview" && request.params.tax_rate === "16") {
      const response = await route.fetch();
      oldStarted();
      await blocked;
      await route.fulfill({ response });
    } else await route.fallback();
  });
  try {
    await openDocument(page);
    await page.getByRole("button", { name: "Revisar estimación", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Revisar estimación", exact: true });
    await dialog.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true }).fill("16");
    await started;
    await dialog.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true }).fill("18");
    await dialog.getByRole("textbox", { name: "Motivo de la revisión", exact: true }).fill("Cambio sintético de porcentaje sin respuesta antigua");
    await expect(dialog).toContainText("118,00");
    release();
    await expect(dialog).not.toContainText("116,00");
    await dialog.getByRole("button", { name: "Guardar revisión", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    const saved = await rpc<HistoricalDocument>("documents.get", { identifier: ids["H-21"] });
    expect(saved.historical_review?.tax_rate).toBe("18");
    expect(saved.historical_review?.total_cents).toBe(11800);
  } finally { release(); }
});

test("un guardado fallido mantiene el formulario y la revisión anterior", async ({ page, rpc }) => {
  const ids = await seed(rpc);
  await page.route("**/api", async route => {
    if (route.request().postDataJSON().action === "historical.review_save") {
      await route.fulfill({ json: { ok: false, error: { code: "conflict", message: "Otra ventana ha revisado este histórico. Vuelve a abrir la revisión." } } });
    } else await route.fallback();
  });
  await openDocument(page);
  await page.getByRole("button", { name: "Revisar estimación", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Revisar estimación", exact: true });
  await dialog.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true }).fill("18");
  await dialog.getByRole("textbox", { name: "Motivo de la revisión", exact: true }).fill("Revisión sintética que no se debe guardar");
  await expect(dialog).toContainText("118,00");
  await dialog.getByRole("button", { name: "Guardar revisión", exact: true }).click();
  await expect(dialog).toContainText("Otra ventana ha revisado este histórico");
  await expect(dialog.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true })).toHaveValue("18");
  const saved = await rpc<HistoricalDocument>("documents.get", { identifier: ids["H-21"] });
  expect(saved.historical_review?.version).toBe(0);
  expect(saved.historical_review?.tax_rate).toBe("21");
});

for (const theme of ["light", "dark"] as const) {
  for (const width of [1366, 390] as const) {
    test(`detalle y revisión accesibles, sin solapamientos: ${theme} ${width}`, async ({ page, rpc }, info) => {
      await seed(rpc);
      await rpc("settings.save", { section: "appearance", values: { theme } });
      await page.setViewportSize({ width, height: 900 });
      await invoices(page);
      const row = page.getByRole("row").filter({ has: page.getByRole("button", { name: "H-21", exact: true }) });
      await expect(row.getByRole("button", { name: "Cliente de revisión sintético", exact: true })).toBeVisible();
      await expect(row).toContainText("Ficha actual");
      await expect(page.getByText("Cliente no conservado en el original", { exact: true })).toHaveCount(0);
      await page.getByRole("button", { name: "H-21", exact: true }).click();
      const currentCustomer = page.getByRole("button", { name: "Cliente de revisión sintético", exact: true });
      await expect(currentCustomer).toBeVisible();
      await expect(page.getByText(/Los datos del cliente no se conservan/)).toHaveCount(0);
      await expect(page.getByText("Consultar ficha actual del cliente", { exact: true })).toHaveCount(0);
      const message = await page.getByRole("button", { name: "Preparar mensaje", exact: true }).boundingBox();
      const status = await page.locator(".document-statusbar").boundingBox();
      expect(message).not.toBeNull(); expect(status).not.toBeNull();
      expect(status!.y - (message!.y + message!.height)).toBeGreaterThanOrEqual(8);
      const customerBox = await currentCustomer.boundingBox();
      const vehicle = await page.getByText("Vehículo (opcional)", { exact: true }).boundingBox();
      expect(vehicle!.y - (customerBox!.y + customerBox!.height)).toBeGreaterThanOrEqual(8);
      const notice = page.locator(".notice").filter({ hasText: "Histórico incompleto. Los datos ausentes" });
      const alignment = await notice.evaluate(element => {
        const icon = element.querySelector("svg")!.getBoundingClientRect();
        const box = element.getBoundingClientRect();
        return Math.abs((icon.y + icon.height / 2) - (box.y + box.height / 2));
      });
      expect(alignment).toBeLessThanOrEqual(2);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await settleAnimations(page);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: info.outputPath(`detalle-${theme}-${width}.png`), fullPage: true });
      await page.getByRole("button", { name: "Revisar estimación", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "Revisar estimación", exact: true });
      await expect(dialog).toBeVisible();
      await settleAnimations(page);
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
      await page.screenshot({ path: info.outputPath(`revision-${theme}-${width}.png`), fullPage: true });
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Revisar estimación", exact: true })).toBeFocused();
    });
  }
}

test("restablecer la estimación recupera el tipo automático y conserva las revisiones anteriores", async ({ page, rpc }) => {
  const ids = await seed(rpc);
  const original = await rpc<HistoricalDocument>("documents.get", { identifier: ids["H-21"] });
  await openDocument(page);
  await page.getByRole("button", { name: "Revisar estimación", exact: true }).click();
  const adjust = page.getByRole("dialog", { name: "Revisar estimación", exact: true });
  await adjust.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true }).fill("18");
  await adjust.getByRole("textbox", { name: "Motivo de la revisión", exact: true }).fill("Ajuste sintético previo al restablecimiento");
  await expect(adjust).toContainText("118,00");
  await adjust.getByRole("button", { name: "Guardar revisión", exact: true }).click();
  await expect(adjust).toHaveCount(0);

  const panel = page.getByRole("region", { name: "Estimación del histórico", exact: true });
  await panel.getByText("Hipótesis y revisiones", { exact: true }).click();
  await panel.getByRole("button", { name: "Restablecer estimación automática", exact: true }).click();
  const reset = page.getByRole("dialog", { name: "Restablecer estimación automática", exact: true });
  await reset.getByRole("textbox", { name: "Motivo del restablecimiento", exact: true }).fill("Volver a la propuesta automática en esta prueba");
  await expect(reset).toContainText("121,00");
  await reset.getByRole("button", { name: "Restablecer estimación", exact: true }).click();
  await expect(reset).toHaveCount(0);
  await expect(panel).toContainText("121,00");
  await expect(panel).toContainText("Ajuste sintético previo al restablecimiento");

  const saved = await rpc<HistoricalDocument & {
    historical_review: Review & { history: (Review & { action: string; reason: string })[] };
  }>("documents.get", { identifier: ids["H-21"] });
  expect(saved.historical_review.state).toBe("estimated");
  expect(saved.historical_review.tax_rate).toBe("21");
  expect(saved.historical_review.total_cents).toBe(12100);
  expect(saved.historical_review.version).toBe(2);
  expect(saved.historical_review.history).toEqual(expect.arrayContaining([
    expect.objectContaining({ action: "adjust", version: 1, tax_rate: "18", reason: "Ajuste sintético previo al restablecimiento" }),
    expect.objectContaining({ action: "reset", version: 2, tax_rate: "21", reason: "Volver a la propuesta automática en esta prueba" }),
  ]));
  expect(saved.payload).toEqual(original.payload);
  expect([saved.base_cents, saved.tax_cents, saved.total_cents]).toEqual([null, null, null]);
});

test("el contraste exige evidencia y cambiar el porcentaje elimina la confirmación explícita", async ({ page, rpc }) => {
  const ids = await seed(rpc);
  await openDocument(page);
  await page.getByRole("button", { name: "Revisar estimación", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Revisar estimación", exact: true });
  const confirm = dialog.getByLabel("He cotejado estos importes con el documento original", { exact: true });
  const save = dialog.getByRole("button", { name: "Guardar revisión", exact: true });
  await dialog.getByRole("textbox", { name: "Motivo de la revisión", exact: true }).fill("Comprobación sintética de evidencia y cambio de tipo");
  await confirm.check();
  const evidence = dialog.getByRole("textbox", { name: "Evidencia del contraste", exact: true });
  await expect(evidence).toBeVisible();
  await expect(evidence).toBeEmpty();
  await expect(save).toBeDisabled();
  await evidence.fill("Original sintético revisado: base 100,00 EUR, IVA 21,00 EUR y total 121,00 EUR");
  await expect(save).toBeEnabled();

  await dialog.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true }).fill("18");
  await expect(confirm).not.toBeChecked();
  await expect(evidence).toHaveCount(0);
  await expect(dialog).toContainText("118,00");
  await save.click();
  await expect(dialog).toHaveCount(0);
  const saved = await rpc<HistoricalDocument & { historical_review: Review & { evidence: string } }>("documents.get", { identifier: ids["H-21"] });
  expect(saved.historical_review.state).toBe("estimated");
  expect(saved.historical_review.tax_rate).toBe("18");
  expect(saved.historical_review.evidence).toBe("");
});

test("Escape conserva una revisión pendiente hasta descartar por teclado y devuelve el foco", async ({ page, rpc }) => {
  const ids = await seed(rpc);
  await openDocument(page);
  const open = page.getByRole("button", { name: "Revisar estimación", exact: true });
  await open.click();
  const dialog = page.getByRole("dialog", { name: "Revisar estimación", exact: true });
  await dialog.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true }).fill("18");
  await dialog.getByRole("textbox", { name: "Motivo de la revisión", exact: true }).fill("Borrador sintético que debe mantenerse al cancelar");
  await page.keyboard.press("Escape");
  const confirmation = page.getByRole("dialog", { name: "Revisión sin guardar", exact: true });
  await expect(confirmation).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(confirmation).toHaveCount(0);
  await expect(dialog.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true })).toHaveValue("18");
  await expect(dialog.getByRole("textbox", { name: "Motivo de la revisión", exact: true })).toHaveValue("Borrador sintético que debe mantenerse al cancelar");
  await expect(dialog).toContainText("118,00");

  await page.keyboard.press("Escape");
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", { name: "Descartar cambios", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(confirmation).toHaveCount(0);
  await expect(dialog).toHaveCount(0);
  await expect(open).toBeFocused();
  const saved = await rpc<HistoricalDocument>("documents.get", { identifier: ids["H-21"] });
  expect(saved.historical_review?.version).toBe(0);
  expect(saved.historical_review?.tax_rate).toBe("21");
  await open.click();
  await expect(dialog.getByRole("textbox", { name: "Tipo de IVA (%)", exact: true })).toHaveValue("21");
  await expect(dialog.getByRole("textbox", { name: "Motivo de la revisión", exact: true })).toBeEmpty();
});
