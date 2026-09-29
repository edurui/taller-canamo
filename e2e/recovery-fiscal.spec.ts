import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";
import type { Download } from "@playwright/test";
import { test, expect } from "./fixtures";

async function bytes(download: Download) {
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks);
}

test("traslado preparado conserva el paquete y bloquea nuevas emisiones tras reiniciar", async ({
  page,
  rpc,
  backend,
}) => {
  await rpc("demo.load");
  await page.goto("/");
  await page
    .getByRole("button", { name: "Configuración", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Copias y traslado", exact: true })
    .click();
  await page.getByLabel("Copias diarias", { exact: true }).fill("3");
  await page
    .getByRole("button", { name: "Guardar configuración", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (
          await rpc<{ backup: { retention: { daily: number } } }>(
            "settings.get",
          )
        ).backup.retention.daily,
    )
    .toBe(3);
  await page
    .getByRole("button", { name: "Preparar traslado", exact: true })
    .click();
  const firstDownload = page.waitForEvent("download");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Preparar y guardar traslado" })
    .click();
  const original = await bytes(await firstDownload);
  await expect(
    page.getByText("Emisión detenida para proteger el historial.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Volver a guardar el paquete preparado" }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Volver a guardar el paquete preparado" })
    .click();
  const repeatedDownload = page.waitForEvent("download");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Preparar y guardar traslado" })
    .click();
  const repeated = await bytes(await repeatedDownload);
  expect(createHash("sha256").update(repeated).digest("hex")).toBe(
    createHash("sha256").update(original).digest("hex"),
  );
  const invoices = await rpc<{ items: { customer_id: string }[] }>(
    "documents.list",
  );
  const draft = await rpc<{ id: string }>("documents.save", {
    data: {
      customer_id: invoices.items[0].customer_id,
      lines: [
        {
          description: "Borrador durante traslado",
          quantity: "1",
          unit_price: "10",
        },
      ],
    },
  });
  // Emission remains blocked across a real service restart; reads and drafts remain available.
  await backend.restart();
  await page.reload();
  await expect(
    page.getByText("Emisión detenida para proteger el historial.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(
    (await rpc<{ blocked: boolean }>("backup.recovery_status")).blocked,
  ).toBe(true);
  await expect(
    rpc("documents.publish", { identifier: draft.id }),
  ).rejects.toThrow();
});

test("diagnóstico y subsanación fiscal local desde interfaz sin aceptación externa ficticia", async ({
  page,
  rpc,
}) => {
  await rpc("demo.load");
  await page.goto("/");
  await page
    .getByRole("button", { name: "Configuración", exact: true })
    .click();
  await page
    .getByRole("button", { name: "VERI*FACTU (pruebas)", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Diagnóstico de puesta en marcha" }),
  ).toBeVisible();
  await expect(
    page.getByText("Instala el certificado autorizado en este equipo.", {
      exact: true,
    }),
  ).toBeVisible();
  const before = await rpc<{ id: string; status: string }[]>("fiscal.list");
  await page
    .getByRole("button", { name: "Detalle", exact: true })
    .first()
    .click();
  const detail = page.getByRole("dialog", { name: "Detalle del registro" });
  await expect(detail.getByText("No recibido", { exact: true })).toBeVisible();
  await detail
    .getByRole("button", { name: "Subsanar registro", exact: true })
    .click();
  const correction = page.getByRole("dialog", {
    name: "Subsanar registro fiscal",
  });
  await correction
    .getByRole("textbox", { name: "Descripción del registro", exact: true })
    .fill("Descripción local revisada y sintética");
  await correction
    .getByRole("textbox", { name: "Motivo de la subsanación", exact: true })
    .fill("Prueba de corrección documental local");
  await correction
    .getByRole("button", { name: "Conservar subsanación" })
    .click();
  await expect(correction).toBeHidden();
  await expect(detail.getByText("Prueba local", { exact: true })).toBeVisible();
  await expect(detail.getByText("No recibido", { exact: true })).toBeVisible();
  const after = await rpc<{ id: string; status: string }[]>("fiscal.list");
  expect(after).toHaveLength(before.length + 1);
  expect(after[0].status).toBe("local_only");
  await detail.getByRole("button", { name: "Cerrar ventana" }).click();
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(
    axe.violations,
    JSON.stringify(
      axe.violations.map((v) => ({
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
    ),
  ).toEqual([]);
});
