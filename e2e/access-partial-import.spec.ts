import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import type { Page } from "@playwright/test";
import { test, expect } from "./fixtures";

const python = resolve(process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");

async function diagnose(page: Page, file: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Configuración", exact: true }).click();
  await page.getByRole("button", { name: "Importar Access", exact: true }).click();
  await page.getByLabel("Nombre de un nuevo origen").fill("Archivo incompleto sintético");
  await page.getByRole("button", { name: "Crear origen", exact: true }).click();
  await page.getByLabel("Copia Access o archivo intermedio").setInputFiles(file);
  await page.getByRole("button", { name: "Diagnosticar copia", exact: true }).click();
  await expect(page.getByRole("button", { name: "Validar mapeo y previsualizar", exact: true })).toBeVisible();
}

test("Access parcial: grupos revisables, importación segura y reversión con originales", async ({ page, rpc }, testInfo) => {
  test.setTimeout(90_000);
  const directory = await mkdtemp(join(tmpdir(), "canamo-partial-e2e-"));
  const file = join(directory, "partial.zip");
  try {
    execFileSync(python, ["-c", [
      "import sys;sys.path[:0]=['backend','tests']",
      "from pathlib import Path",
      "from test_access_partial import archive,package",
      "package(Path(sys.argv[1]),archive())",
    ].join(";"), directory], { cwd: resolve(".") });
    await page.setViewportSize({ width: 1024, height: 768 });
    await diagnose(page, file);
    await expect(page.getByLabel("Conservación del histórico")).toContainText("Conservar datos incompletos sin reconstruirlos");
    await page.getByRole("button", { name: "Validar mapeo y previsualizar", exact: true }).click();
    await expect(page.getByText(/0 incidencias bloqueantes/)).toBeVisible();
    await expect(page.getByText(/Matrícula compartida sin titularidad acreditada/)).toBeVisible();
    await expect(page.getByText(/La conciliación de lo importado no equivale a resolver estos casos/)).toBeVisible();
    const grouped = page.locator("details").filter({ has: page.locator("summary", { hasText: "Incidencias agrupadas por motivo" }) });
    await expect(grouped).toHaveAttribute("open", "");
    await expect(grouped).toContainText("Línea sin clave completa");
    const individual = page.locator("details").filter({ has: page.locator("summary", { hasText: "Revisar incidencias individuales y sus claves" }) });
    await expect(individual).not.toHaveAttribute("open", "");
    expect((await rpc<{ total: number }>("customers.list")).total).toBe(0);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.getByLabel("He revisado las advertencias, discrepancias aceptadas y datos desconocidos.").check();
    await page.getByRole("button", { name: "Simular sin cambiar fichas", exact: true }).click();
    await expect(page.getByRole("heading", { name: "4. Simulación terminada" })).toBeVisible();
    expect((await rpc<{ total: number }>("customers.list")).total).toBe(0);
    expect((await rpc<{ total: number }>("documents.list")).total).toBe(0);
    await page.getByRole("button", { name: "Continuar con la importación", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Importar datos", exact: true }).click();
    await expect(page.getByRole("heading", { name: "5. Conciliación" })).toBeVisible();
    await expect(page.getByText("Lote conciliado: registros e importes coinciden con el origen seleccionado.", { exact: true })).toBeVisible();
    const totals = page.getByRole("row").filter({ has: page.getByRole("rowheader", { name: "Total", exact: true }) });
    await expect(totals.getByRole("cell")).toHaveText([
      "No consta (4 históricos)", "No consta (4 históricos)",
    ]);
    const invoices = await rpc<{ total: number; items: { id: string; full_number: string; total_cents: null; paid_cents: null }[] }>("documents.list");
    expect(invoices.total).toBe(4);
    expect(invoices.items.map(item => item.full_number).sort()).toEqual(["0", "7", "8", "9"]);
    expect(invoices.items.every(item => item.total_cents === null && item.paid_cents === null)).toBe(true);
    for (const invoice of invoices.items) {
      expect((await rpc<{ pending_cents: null }>("documents.get", { identifier: invoice.id })).pending_cents).toBeNull();
    }
    expect((await rpc<{ pending_cents: number }>("dashboard")).pending_cents).toBe(0);
    const ambiguous = invoices.items.find(item => item.full_number === "7")!;
    const detail = await rpc<{ issue_date: null; payload: { date_candidates: string[]; lines: { amount_raw: string; base_cents: null }[] } }>("documents.get", { identifier: ambiguous.id });
    expect(detail.issue_date).toBeNull();
    expect(detail.payload.date_candidates).toEqual(["2010-01-01", "2011-01-01"]);
    expect(detail.payload.lines.map(line => line.amount_raw)).toEqual(["0.0050", "0.0050"]);
    expect(detail.payload.lines.every(line => line.base_cents === null)).toBe(true);
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Guardar informe completo", exact: true }).click();
    const report = await download;
    expect(report.suggestedFilename()).toMatch(/importacion-.+\.jsonl$/);
    const exported = await readFile((await report.path())!, "utf8");
    expect(exported).toContain("0.0050");
    expect(exported).toContain("No atribuible");
    expect(exported).toContain("Versión antigua sintética");
    const screenshot = testInfo.outputPath("conciliacion-parcial-sintetica.png");
    await page.screenshot({ path: screenshot, fullPage: true });
    await testInfo.attach("conciliacion-parcial-sintetica", { path: screenshot, contentType: "image/png" });
    await page.getByLabel("Motivo de reversión").fill("Fin del ensayo parcial sintético");
    await page.getByRole("button", { name: "Revisar reversión del lote", exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Revertir con comprobación", exact: true }).click();
    await expect.poll(async () => (await rpc<{ total: number }>("documents.list")).total).toBe(0);
    expect((await rpc<{ total: number }>("customers.list")).total).toBe(0);
    expect((await rpc<{ status: string }>("documents.get", { identifier: ambiguous.id })).status).toBe("import_reverted");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("MDB nativo con contador interno obsoleto conserva filas y muestra diagnóstico", async ({ page }) => {
  const directory = await mkdtemp(join(tmpdir(), "canamo-stale-e2e-"));
  const file = join(directory, "stale.mdb");
  try {
    execFileSync(python, ["-c", "import sys,subprocess;sys.path.insert(0,'backend');from taller.access import java_command;subprocess.run([*java_command(),'fixture',sys.argv[1],'mdb-stale-count'],check=True)", file], { cwd: resolve(".") });
    await diagnose(page, file);
    const customers = page.getByRole("row").filter({ has: page.getByRole("cell", { name: "Clientes", exact: true }) });
    await expect(customers).toContainText("Contador interno: 1. Se conservan todas las filas recorridas.");
    await expect(customers.getByRole("cell").nth(1)).toContainText("2");
    await page.getByRole("button", { name: "Validar mapeo y previsualizar", exact: true }).click();
    await expect(page.getByText(/0 incidencias bloqueantes/)).toBeVisible();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
