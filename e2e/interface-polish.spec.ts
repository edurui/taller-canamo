import AxeBuilder from "@axe-core/playwright";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { test, expect } from "./fixtures";

const customerData = {
  name: "Cliente de interfaz sintético",
  tax_id: "12345678Z",
  phone: "612000123",
  address: "Prueba 1",
  postal_code: "41300",
  city: "Localidad ficticia",
};
async function openInvoice(page: import("@playwright/test").Page) {
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
  });
  await search.fill("Cliente de interfaz");
  await expect(page.getByRole("option").first()).toContainText(
    customerData.name,
  );
  await search.press("Enter");
  await page
    .getByRole("button", { name: "Nueva factura", exact: true })
    .click();
}
async function audit(
  page: import("@playwright/test").Page,
  info: import("@playwright/test").TestInfo,
  name: string,
) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  await info.attach(name + "-axe.json", {
    body: JSON.stringify(result, null, 2),
    contentType: "application/json",
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
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath(name + ".png"),
    fullPage: (await page.getByRole("dialog").count()) === 0,
    animations: "disabled",
  });
}

test("orden de líneas: teclado y arrastre conservan importes, borrador y orden real del PDF", async ({
  page,
  rpc,
}, info) => {
  const customer = await rpc<{ id: string }>("customers.save", {
    data: customerData,
  });
  await rpc("settings.save", {
    section: "company",
    values: { legal_name: "TALLER DE INTERFAZ FICTICIO", tax_id: "89890001K" },
  });
  await openInvoice(page);
  const descriptions = [
    "Aceite sintético de prueba",
    "Frenos sintéticos de prueba",
    "Mano de obra sintética",
  ];
  for (let i = 0; i < descriptions.length; i++) {
    if (i)
      await page
        .getByRole("button", { name: "Añadir concepto", exact: true })
        .click();
    await page
      .getByLabel("Concepto " + (i + 1), { exact: true })
      .fill(descriptions[i]);
    await page
      .getByLabel("Precio " + (i + 1), { exact: true })
      .fill(String([10, 25, 30][i]));
    await page
      .getByLabel("Cantidad " + (i + 1), { exact: true })
      .fill(["1", "2", "0.5"][i]);
  }
  await expect(page.locator(".summary-total")).toContainText("90,75");
  await page
    .getByRole("button", { name: "Arrastrar línea 2", exact: true })
    .focus();
  await page.keyboard.press("ArrowUp");
  await expect(page.getByLabel("Concepto 1", { exact: true })).toHaveValue(
    descriptions[1],
  );
  await expect(
    page.getByRole("button", { name: "Arrastrar línea 1", exact: true }),
  ).toBeFocused();
  await page
    .getByRole("button", { name: "Arrastrar línea 3", exact: true })
    .dragTo(page.locator(".invoice-line").first());
  await expect(page.getByLabel("Concepto 1", { exact: true })).toHaveValue(
    descriptions[2],
  );
  await expect(page.getByLabel("Cantidad 1", { exact: true })).toHaveValue(
    "0.5",
  );
  await expect(page.locator(".summary-total")).toContainText("90,75");
  await expect(page.locator(".line-total")).toHaveText([
    /15,00/,
    /50,00/,
    /10,00/,
  ]);
  await audit(page, info, "factura-ordenada");
  await page.getByRole("button", { name: "Vista previa / PDF" }).click();
  await expect(page.getByTitle("Vista previa de la factura")).toBeVisible();
  const docs = await rpc<{ items: { id: string }[] }>("documents.list", {
    customer_id: customer.id,
  });
  const document = await rpc<{
    payload: { lines: { description: string; _uiKey?: string }[] };
  }>("documents.get", { identifier: docs.items[0].id });
  expect(document.payload.lines.map((line) => line.description)).toEqual([
    descriptions[2],
    descriptions[1],
    descriptions[0],
  ]);
  expect(document.payload.lines.some((line) => line._uiKey)).toBe(false);
  const pdf = await rpc<{ content: string }>("documents.pdf", {
    identifier: docs.items[0].id,
  });
  const text = execFileSync(
    resolve(
      process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
    ),
    [
      "-c",
      'import sys,io;from pypdf import PdfReader;print("\\n".join(p.extract_text() for p in PdfReader(io.BytesIO(sys.stdin.buffer.read())).pages))',
    ],
    { input: Buffer.from(pdf.content, "base64") },
  ).toString();
  expect(text.indexOf(descriptions[2])).toBeGreaterThanOrEqual(0);
  expect(text.indexOf(descriptions[2])).toBeLessThan(
    text.indexOf(descriptions[1]),
  );
  expect(text.indexOf(descriptions[1])).toBeLessThan(
    text.indexOf(descriptions[0]),
  );
  await page.getByRole("button", { name: "Cerrar ventana" }).click();
  await page.reload();
  await page.getByRole("button", { name: "Facturas", exact: true }).click();
  await page
    .getByRole("button", { name: "Borrador sin número", exact: true })
    .click();
  await expect(page.getByLabel("Concepto 1", { exact: true })).toHaveValue(
    descriptions[2],
  );
});

test("calendario: año, mes, día bisiesto, teclado, límites y cierre con foco", async ({
  page,
  rpc,
}, info) => {
  await rpc("customers.save", { data: customerData });
  await openInvoice(page);
  const date = page.getByLabel("Fecha del documento", { exact: true });
  await date.fill("2026-09-29");
  const trigger = date
    .locator("..")
    .getByRole("button", { name: "Abrir calendario" });
  await trigger.click();
  await page.getByRole("button", { name: "Elegir año", exact: true }).click();
  await page
    .getByRole("group", { name: "Años", exact: true })
    .getByRole("button", { name: "2024", exact: true })
    .click();
  await page
    .getByRole("group", { name: "Meses", exact: true })
    .getByRole("button", { name: "febrero", exact: true })
    .click();
  await page
    .getByRole("button", { name: "jueves, 29 de febrero de 2024", exact: true })
    .click();
  await expect(date).toHaveValue("2024-02-29");
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(
    page.getByRole("button", {
      name: "jueves, 29 de febrero de 2024",
      exact: true,
    }),
  ).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  await expect(date).toHaveValue("2024-03-01");
  await trigger.click();
  await audit(page, info, "calendario-escritorio");
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  // Reports has a real minimum on its end date; earlier days cannot be selected.
  await page.getByRole("button", { name: "Más herramientas" }).click();
  await page.getByRole("button", { name: "Resumen", exact: true }).click();
  await page
    .getByRole("button", { name: "Salir sin guardar", exact: true })
    .click();
  await page.getByLabel("Desde", { exact: true }).fill("2024-02-20");
  const until = page.getByLabel("Hasta", { exact: true });
  await until.fill("2024-02-29");
  await until
    .locator("..")
    .getByRole("button", { name: "Abrir calendario" })
    .click();
  await expect(
    page.getByRole("button", {
      name: "lunes, 19 de febrero de 2024",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", {
      name: "martes, 20 de febrero de 2024",
      exact: true,
    }),
  ).toBeEnabled();
});

for (const theme of ["light", "dark"]) {
  test(`letra persistente y selectores a pantalla completa: ${theme}, 390 px`, async ({
    page,
    rpc,
    backend,
  }, info) => {
    await rpc("customers.save", { data: customerData });
    await rpc("settings.save", { section: "appearance", values: { theme } });
    await page.goto("/");
    await page
      .getByRole("button", { name: "Configuración", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Tamaño de letra y aspecto" })
      .click();
    await page.getByRole("button", { name: "Muy grande" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-font", "extra");
    await page
      .getByRole("button", { name: "Guardar cambios", exact: true })
      .click();
    await expect(
      page.getByText("Configuración guardada", { exact: true }),
    ).toBeVisible();
    await backend.restart();
    await page.reload();
    await expect(page.locator("html")).toHaveCSS("font-size", "20px");
    await page.setViewportSize({ width: 390, height: 844 });
    await audit(page, info, "inicio-movil-" + theme);
    await page
      .getByRole("combobox", { name: "Buscar cliente o matrícula" })
      .fill("Cliente");
    const search = page.getByRole("dialog", {
      name: "Buscar cliente o matrícula",
    });
    await expect(search).toBeVisible();
    await search.getByRole("combobox").fill("Cliente de interfaz");
    await expect(page.getByRole("option").first()).toContainText(
      customerData.name,
    );
    await audit(page, info, "buscador-movil-" + theme);
    await search.getByRole("combobox").press("Enter");
    await page
      .getByRole("button", { name: "Nueva factura", exact: true })
      .click();
    await audit(page, info, "factura-movil-" + theme);
    const payment = page.getByRole("combobox", {
      name: "Forma de pago",
      exact: true,
    });
    await payment.click();
    const selector = page.getByRole("dialog", {
      name: "Forma de pago",
      exact: true,
    });
    await expect
      .poll(async () =>
        selector.evaluate((element) => {
          const box = element.getBoundingClientRect();
          return {
            x: Math.round(box.x),
            y: Math.round(box.y),
            width: Math.round(box.width),
            height: Math.round(box.height),
          };
        }),
      )
      .toEqual({ x: 0, y: 0, width: 390, height: 844 });
    await audit(page, info, "selector-movil-" + theme);
    await page
      .getByRole("option", { name: "Transferencia", exact: true })
      .click();
    await expect(payment).toHaveText("Transferencia");
    await expect(payment).toBeFocused();
    const date = page.getByLabel("Fecha del documento", { exact: true });
    await date
      .locator("..")
      .getByRole("button", { name: "Abrir calendario" })
      .click();
    await audit(page, info, "calendario-movil-" + theme);
    await page.getByRole("button", { name: "Cerrar selector" }).click();
    await expect(page.locator("#root")).not.toHaveAttribute("inert");
  });
}

test("selectores dentro de modales: búsqueda, teclado, foco y movimiento reducido", async ({
  page,
  rpc,
}, info) => {
  await rpc("demo.load");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("button", { name: "Más herramientas" }).click();
  await page.getByRole("button", { name: "Agenda", exact: true }).click();
  await page.getByRole("button", { name: "Nuevo evento", exact: true }).click();
  const dialog = page.getByRole("dialog", {
    name: "Nuevo evento",
    exact: true,
  });
  const type = dialog.getByRole("combobox", {
    name: "Tipo de evento",
    exact: true,
  });
  await type.click();
  await audit(page, info, "selector-anidado");
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await expect(type).toBeFocused();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.locator("#root")).not.toHaveAttribute("inert");
});

test("espacios y alineación en fichas y resumen; texto grande en ventanas estrechas", async ({
  page,
  rpc,
}, info) => {
  const client = await rpc<{ id: string }>("customers.save", {
    data: customerData,
  });
  await rpc("vehicles.save", {
    data: {
      customer_id: client.id,
      plate: "1234BCD",
      make: "Vehículo sintético",
      model: "Prueba",
      km: 12000,
    },
  });
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
  });
  await search.fill("Cliente de interfaz");
  await expect(page.getByRole("option").first()).toContainText(
    customerData.name,
  );
  await search.press("Enter");
  const history = await page.locator(".history-search").boundingBox();
  const customer = await page.locator(".customer-layout").boundingBox();
  expect(customer!.y - history!.y - history!.height).toBeGreaterThanOrEqual(20);
  await audit(page, info, "ficha-espaciada");
  const historyAction = page.getByRole("button", {
    name: "Historial y titular",
    exact: true,
  });
  expect(
    await historyAction.evaluate(
      (element) => element.scrollWidth <= element.clientWidth + 1,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Nueva factura", exact: true })
    .click();
  const controls = page.locator(".vehicle-fields");
  const vehicle = await controls.getByRole("combobox").boundingBox();
  const kilometres = await controls.getByRole("spinbutton").boundingBox();
  const add = await controls
    .getByRole("button", { name: "Añadir vehículo" })
    .boundingBox();
  // At 1366 px the row can wrap as a group, while each input keeps the same height.
  expect(Math.abs(vehicle!.height - kilometres!.height)).toBeLessThanOrEqual(2);
  if (Math.abs(add!.y - kilometres!.y) < 10)
    expect(
      Math.abs(add!.y + add!.height - kilometres!.y - kilometres!.height),
    ).toBeLessThanOrEqual(2);
  await page.getByRole("button", { name: "Más herramientas" }).click();
  await page.getByRole("button", { name: "Resumen", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Resumen del taller" }),
  ).toBeVisible();
  await audit(page, info, "resumen-espaciado");
  await page
    .getByRole("button", { name: "Configuración", exact: true })
    .click();
  await page.getByRole("button", { name: "Tamaño de letra y aspecto" }).click();
  await page.getByRole("button", { name: "Muy grande" }).click();
  for (const width of [1280, 1024, 780, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page.screenshot({
      path: info.outputPath("letra-extra-" + width + ".png"),
      fullPage: true,
      animations: "disabled",
    });
  }
  // An unsaved preview must not silently replace the persisted preference.
  await page.setViewportSize({ width: 1366, height: 768 });
  await page
    .getByRole("button", { name: "Taller y logo", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-font", "normal");
});
