import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";
import { test, expect } from "./fixtures";

type Rpc = <T = Record<string, unknown>>(
  action: string,
  params?: Record<string, unknown>,
) => Promise<T>;
type Vehicle = {
  id: string;
  customer_id: string;
  plate: string;
  make: string;
  model: string;
  kind: string;
  version: number;
  owners: { reason: string }[];
};
const longDescription = "ModeloSintético".repeat(8);
const descriptions = [
  ["UI-VEH-01", "", "", "Modelo de prueba XL", "Modelo de prueba XL"],
  [
    "UI-VEH-02",
    " Marca sintética ",
    " Modelo de ensayo ",
    "Tipo alternativo",
    "Marca sintética Modelo de ensayo",
  ],
  ["UI-VEH-03", "", "", "", "Vehículo sin descripción"],
  [
    "UI-VEH-04",
    "Marca independiente",
    "",
    "Tipo alternativo",
    "Marca independiente",
  ],
  [
    "UI-VEH-05",
    "",
    "Modelo independiente",
    "Tipo alternativo",
    "Modelo independiente",
  ],
  ["UI-VEH-06", "", "", longDescription, longDescription],
] as const;

// The import and its automatic ownership reason are produced by the real local
// backend inside the fixture's fresh synthetic database, not mocked UI replies.
async function seedVehicles(rpc: Rpc) {
  const batch = await rpc<{
    batch_id: string;
    incident_counts: { error: number };
  }>("import.preview", {
    format: "json",
    text: JSON.stringify({
      format: "canamo-import-v2",
      customers: [
        {
          legacy_code: "UI-001",
          name: "Titular sintético de presentación",
          phone: "600000031",
        },
      ],
      vehicles: descriptions.map(([plate, make, model, kind]) => ({
        legacy_customer_code: "UI-001",
        plate,
        make,
        model,
        kind,
        km: 100,
      })),
      invoices: [],
    }),
  });
  expect(batch.incident_counts.error).toBe(0);
  expect(
    (
      await rpc<{ done: boolean }>("import.simulate", {
        batch_id: batch.batch_id,
        acknowledge_warnings: true,
      })
    ).done,
  ).toBe(true);
  expect(
    (await rpc<{ done: boolean }>("import.run", { batch_id: batch.batch_id }))
      .done,
  ).toBe(true);
  const vehicles = await rpc<{ items: Vehicle[] }>("vehicles.page");
  expect(vehicles.items).toHaveLength(descriptions.length);
  return { batchId: batch.batch_id, vehicles: vehicles.items };
}

async function openCustomer(page: Page) {
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
    exact: true,
  });
  await search.fill("UI-VEH-01");
  await expect(page.getByRole("option").first()).toContainText("UI-VEH-01");
  const mobileSearch = page.getByRole("dialog", {
    name: "Buscar cliente o matrícula",
    exact: true,
  });
  if (await mobileSearch.isVisible())
    await mobileSearch.getByRole("combobox").press("Enter");
  else await search.press("Enter");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Titular sintético de presentación",
  );
}

function vehicleCard(page: Page, plate: string) {
  return page
    .locator(".vehicle-card")
    .filter({ has: page.getByText(plate, { exact: true }) });
}

async function checkPanelGaps(
  page: Page,
  selector: string,
  expectedCount: number,
) {
  const panels = page.locator(selector);
  await expect(panels).toHaveCount(expectedCount);
  const gaps = await panels.evaluateAll((elements) =>
    elements.slice(1).map((element, index) => {
      const previous = elements[index].getBoundingClientRect();
      return element.getBoundingClientRect().top - previous.bottom;
    }),
  );
  for (const gap of gaps) expect(gap).toBeGreaterThanOrEqual(23.5);
  return gaps;
}

async function audit(page: Page, info: TestInfo, name: string) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  await info.attach(name + "-axe.json", {
    body: JSON.stringify(result, null, 2),
    contentType: "application/json",
  });
  expect(result.violations, JSON.stringify(result.violations)).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath(name + ".png"),
    fullPage: true,
    animations: "disabled",
  });
}

test("vehículos presentan marca/modelo, texto de origen o ausencia en tarjetas, listado y ficha", async ({
  page,
  rpc,
}) => {
  const { batchId, vehicles } = await seedVehicles(rpc);
  await openCustomer(page);
  for (const [plate, , , , description] of descriptions) {
    await expect(
      vehicleCard(page, plate).locator(".vehicle-select strong"),
    ).toHaveText(description);
  }
  await vehicleCard(page, "UI-VEH-01")
    .getByRole("button", { name: "Historial y titular", exact: true })
    .click();
  await expect(page.locator(".page-head p")).toHaveText("Modelo de prueba XL");
  await expect(page.locator(".vehicle-owners")).toContainText(
    "Alta desde importación",
  );
  await expect(page.locator(".vehicle-owners")).not.toContainText(batchId);
  const original = await rpc<Vehicle>("vehicles.get", {
    identifier: vehicles[0].id,
  });
  expect(original.owners[0].reason).toBe("Importación: " + batchId);
  expect(original.make).toBe("");
  expect(original.model).toBe("");
  expect(original.kind).toBe("Modelo de prueba XL");

  await page.locator(".back-link").click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Vehículos");
  await expect(page.locator(".list-toolbar")).toContainText("6 vehículos");
  await expect(
    page.getByText("Hasta 300 coincidencias", { exact: true }),
  ).toHaveCount(0);
  for (const [plate, , , , description] of descriptions) {
    const row = page
      .getByRole("row")
      .filter({ has: page.getByRole("button", { name: plate, exact: true }) });
    await expect(row.locator(".vehicle-description")).toHaveText(description);
  }
  const search = page.getByRole("textbox", {
    name: "Buscar vehículos",
    exact: true,
  });
  await search.fill("Modelo de prueba XL");
  await expect(
    page.getByRole("button", { name: "UI-VEH-01", exact: true }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator(".list-toolbar")).toContainText("1 vehículo");
  await search.fill("");
  await expect(page.locator("tbody tr")).toHaveCount(6);
  for (const [plate, , , , description] of descriptions) {
    await page.getByRole("button", { name: plate, exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(plate);
    await expect(page.locator(".page-head p")).toHaveText(description);
    await page.locator(".back-link").click();
    await expect(page.locator("tbody tr")).toHaveCount(6);
  }
});

test("el historial oculta sólo el UUID automático y conserva íntegros los motivos manuales", async ({
  page,
  rpc,
}, info) => {
  const { batchId, vehicles } = await seedVehicles(rpc);
  const vehicle = vehicles.find((item) => item.plate === "UI-VEH-01")!;
  const manualId = "ffffffff-ffff-4fff-8fff-ffffffffffff";
  const reason = `Importación: ${manualId} · anotación manual\n${"ReferenciaManualSintética".repeat(9)}\nTexto final que debe permanecer.`;
  const replacement = await rpc<{ id: string }>("customers.save", {
    data: { name: "Titular nuevo sintético" },
  });
  await rpc("vehicles.transfer", {
    identifier: vehicle.id,
    customer_id: replacement.id,
    reason,
    expected_version: vehicle.version,
  });
  const returned = await rpc<Vehicle>("vehicles.get", {
    identifier: vehicle.id,
  });
  const secondReason =
    "Importación: lote revisado manualmente, sin identificador automático.";
  await rpc("vehicles.transfer", {
    identifier: vehicle.id,
    customer_id: vehicle.customer_id,
    reason: secondReason,
    expected_version: returned.version,
  });
  await page.setViewportSize({ width: 320, height: 768 });
  await openCustomer(page);
  await vehicleCard(page, "UI-VEH-01")
    .getByRole("button", { name: "Historial y titular", exact: true })
    .click();
  const entries = page.locator(".vehicle-owners li");
  await expect(entries).toHaveCount(3);
  await expect(entries.nth(0)).toContainText("Alta desde importación");
  await expect(entries.nth(0)).not.toContainText(batchId);
  expect(
    await entries.nth(1).locator(".vehicle-owner-reason").textContent(),
  ).toBe(" · " + reason);
  await expect(entries.nth(2)).toContainText(secondReason);
  expect(
    (await rpc<Vehicle>("vehicles.get", { identifier: vehicle.id })).owners.map(
      (owner) => owner.reason,
    ),
  ).toEqual(["Importación: " + batchId, reason, secondReason]);
  await audit(page, info, "titularidad-manual-completa-320");
});

for (const theme of ["light", "dark"]) {
  test(`tarjetas de vehículos separadas y accesibles a 1024 y 320 px: ${theme}`, async ({
    page,
    rpc,
  }, info) => {
    test.setTimeout(60_000);
    await rpc("settings.save", {
      section: "appearance",
      values: { theme, font_size: "large" },
    });
    const { batchId } = await seedVehicles(rpc);
    const measurements: {
      width: number;
      customerGaps: number[];
      vehicleGaps: number[];
    }[] = [];
    for (const width of [1024, 320]) {
      await page.setViewportSize({ width, height: 768 });
      await openCustomer(page);
      await expect(vehicleCard(page, "UI-VEH-06")).toContainText(
        longDescription,
      );
      const customerGaps = await checkPanelGaps(
        page,
        ".customer-main > section",
        2,
      );
      await audit(page, info, `cliente-vehiculos-${theme}-${width}`);
      await vehicleCard(page, "UI-VEH-06")
        .getByRole("button", { name: "Historial y titular", exact: true })
        .click();
      await expect(page.locator(".page-head p")).toHaveText(longDescription);
      await expect(page.locator(".vehicle-owners")).toContainText(
        "Alta desde importación",
      );
      await expect(page.locator(".vehicle-owners")).not.toContainText(batchId);
      const vehicleGaps = await checkPanelGaps(
        page,
        ".vehicle-detail > section",
        3,
      );
      measurements.push({ width, customerGaps, vehicleGaps });
      await audit(page, info, `ficha-vehiculo-${theme}-${width}`);
      await page.locator(".back-link").click();
      await expect(page.locator("tbody tr")).toHaveCount(6);
      const description = page.locator("td.vehicle-description").first();
      expect((await description.boundingBox())!.width).toBeGreaterThanOrEqual(
        180,
      );
      if (width === 320) await description.scrollIntoViewIfNeeded();
      await audit(page, info, `listado-vehiculos-${theme}-${width}`);
    }
    await info.attach("separacion-paneles.json", {
      body: JSON.stringify(measurements, null, 2),
      contentType: "application/json",
    });
  });
}
