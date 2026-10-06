import { chooseOption } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test, expect } from "./fixtures";

test("Access real: diagnosticar, mapear, simular, importar, conciliar y revertir sin datos operativos", async ({
  page,
  rpc,
}) => {
  test.setTimeout(90_000);
  const directory = await mkdtemp(join(tmpdir(), "canamo-access-e2e-á-"));
  const file = join(directory, "Copia sintética.accdb");
  try {
    const python = resolve(
      process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
    );
    execFileSync(
      python,
      [
        "-c",
        "import sys,subprocess;sys.path.insert(0,'backend');from taller.access import java_command;subprocess.run([*java_command(),'fixture',sys.argv[1],'accdb'],check=True)",
        file,
      ],
      { cwd: resolve(".") },
    );
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/");
    await page
      .getByRole("button", { name: "Configuración", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Importar Access", exact: true })
      .click();
    await page
      .getByLabel("Nombre de un nuevo origen")
      .fill("Access sintético del ensayo");
    await page
      .getByRole("button", { name: "Crear origen", exact: true })
      .click();
    await expect(page.getByLabel("Origen de los datos")).toContainText("Access sintético del ensayo");
    await page
      .getByLabel("Copia Access o archivo intermedio")
      .setInputFiles(file);
    await page
      .getByRole("button", { name: "Diagnosticar copia", exact: true })
      .click();
    await expect(
      page.getByText("Vínculo bloqueado", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/Jackcess 5\.0\.1/)).toBeVisible();
    await page
      .getByRole("button", {
        name: "Validar mapeo y previsualizar",
        exact: true,
      })
      .click();
    await expect(page.getByText(/0 incidencias bloqueantes/)).toBeVisible();
    expect((await rpc<{ total: number }>("customers.list")).total).toBe(0);
    const accessibility = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(accessibility.violations).toEqual([]);
    await page
      .getByLabel(
        "He revisado las advertencias, discrepancias aceptadas y datos desconocidos.",
      )
      .check();
    await page
      .getByRole("button", { name: "Simular sin cambiar fichas", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "4. Simulación terminada" }),
    ).toBeVisible();
    expect((await rpc<{ total: number }>("customers.list")).total).toBe(0);
    await page
      .getByRole("button", {
        name: "Continuar con la importación",
        exact: true,
      })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Importar datos", exact: true })
      .click();
    await expect(
      page.getByText(
        "Lote conciliado: registros e importes coinciden con el origen seleccionado.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      page.getByText(/Facturas con cobro no documentado: 2/),
    ).toBeVisible();
    const invoices = await rpc<{
      items: { id: string; paid_cents: null; full_number: string }[];
      total: number;
    }>("documents.list");
    expect(invoices.total).toBe(2);
    expect(invoices.items.map((item) => item.full_number)).toEqual([
      "0007",
      "0007",
    ]);
    expect(invoices.items.every((item) => item.paid_cents === null)).toBe(true);
    expect(
      (await rpc<{ pending_cents: number }>("dashboard")).pending_cents,
    ).toBe(0);
    await page.screenshot({
      path: "reports/e2e-access/conciliacion.png",
      fullPage: true,
    });
    const download = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Guardar informe completo", exact: true })
      .click();
    expect((await download).suggestedFilename()).toMatch(
      /importacion-.+\.jsonl$/,
    );
    await page
      .getByLabel("Motivo de reversión")
      .fill("Fin del ensayo sintético");
    await page
      .getByRole("button", { name: "Revisar reversión del lote", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Revertir con comprobación", exact: true })
      .click();
    await expect
      .poll(async () => (await rpc<{ total: number }>("documents.list")).total)
      .toBe(0);
    for (const invoice of invoices.items) {
      expect(
        (
          await rpc<{ status: string }>("documents.get", {
            identifier: invoice.id,
          })
        ).status,
      ).toBe("import_reverted");
    }
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("CSV: conflicto de código exige vínculo explícito y la reimportación conserva la ficha", async ({
  page,
  rpc,
}) => {
  await rpc("customers.save", {
    data: { legacy_code: "001", name: "Ficha ya revisada", phone: "600000010" },
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Configuración", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Importar Access", exact: true })
    .click();
  await page.getByRole("button", { name: "Crear origen", exact: true }).click();
  await page
    .getByLabel("Copia Access o archivo intermedio")
    .setInputFiles({
      name: "clientes.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "codigo;nombre;telefono\n001;Nombre antiguo;600000011\n",
      ),
    });
  await page
    .getByRole("button", { name: "Diagnosticar copia", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Validar mapeo y previsualizar", exact: true })
    .click();
  await expect(page.getByText(/1 incidencias bloqueantes/)).toBeVisible();
  await page.getByText("Revisar incidencias individuales y sus claves", { exact: true }).click();
  await page.getByText(/Revisar · Clientes/).click();
  await chooseOption(page
    .getByRole("combobox", { name: "Resolución", exact: true }), "link");
  await page.getByLabel("Buscar ficha para vincular").fill("Ficha ya revisada");
  await page.getByRole("button", { name: "Buscar ficha", exact: true }).click();
  await chooseOption(page
    .getByLabel("Ficha que has comprobado"), { label: "Ficha ya revisada · 001" });
  await page
    .getByLabel("Motivo documentado")
    .fill("Identidad contrastada en ensayo");
  await page
    .getByRole("button", { name: "Aplicar resolución y revisar", exact: true })
    .click();
  await expect(page.getByText(/0 incidencias bloqueantes/)).toBeVisible();
  await page
    .getByLabel(
      "He revisado las advertencias, discrepancias aceptadas y datos desconocidos.",
    )
    .check();
  await page
    .getByRole("button", { name: "Simular sin cambiar fichas", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Continuar con la importación", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Importar datos", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "5. Conciliación" }),
  ).toBeVisible();
  const customers = await rpc<{
    items: { name: string; phone: string }[];
    total: number;
  }>("customers.list");
  expect(customers.total).toBe(1);
  expect(customers.items[0]).toMatchObject({
    name: "Ficha ya revisada",
    phone: "600000010",
  });
});
