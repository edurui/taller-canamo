import AxeBuilder from "@axe-core/playwright";
import { randomBytes } from "node:crypto";
import type { Download } from "@playwright/test";
import { test, expect } from "./fixtures";

async function downloadedBytes(download: Download) {
  const stream = await download.createReadStream();
  const parts: Buffer[] = [];
  for await (const part of stream!) parts.push(Buffer.from(part));
  return Buffer.concat(parts);
}

test("copia AES mayor de 4 MiB descarga y restaura por bloques sin perder originales", async ({
  page,
  rpc,
  backend,
}) => {
  await rpc("demo.load");
  const source = await rpc<{ id: string }>("import.source_save", {
    name: "Original sintético para transporte, sin diagnosticar",
  });
  const original = randomBytes(6 * 1024 ** 2);
  const uploaded = await rpc<{ upload_id: string; chunk_bytes: number }>(
    "import.upload_start",
    {
      name: "original-sintetico.csv",
      size: original.length,
      source_id: source.id,
    },
  );
  for (
    let offset = 0;
    offset < original.length;
    offset += uploaded.chunk_bytes
  ) {
    await rpc("import.upload_chunk", {
      upload_id: uploaded.upload_id,
      offset,
      content: original
        .subarray(offset, offset + uploaded.chunk_bytes)
        .toString("base64"),
    });
  }
  const calls: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api") && request.method() === "POST")
      calls.push(request.postDataJSON().action);
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Configuración", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Copias y traslado", exact: true })
    .click();
  const password = page.getByLabel(
    "Contraseña de cifrado (opcional, mínimo 10 caracteres)",
    { exact: true },
  );
  await password.fill("clave-sintetica-local");
  const downloading = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Crear y guardar copia", exact: true })
    .click();
  const download = await downloading;
  const backup = await downloadedBytes(download);
  expect(backup.length).toBeGreaterThan(4 * 1024 ** 2);
  expect(backup.subarray(0, 8).toString()).toBe("CANAMO1\0");
  expect(
    calls.filter((action) => action === "backup.download_chunk").length,
  ).toBeGreaterThan(4);
  await rpc("customers.save", {
    data: { name: "Alta posterior que no pertenece a la copia" },
  });
  await page.getByLabel("Seleccionar copia para restaurar").setInputFiles({
    name: download.suggestedFilename(),
    mimeType: "application/octet-stream",
    buffer: backup,
  });
  await password.fill("contraseña-incorrecta");
  await page
    .getByRole("button", { name: "Comprobar copia", exact: true })
    .click();
  await expect(
    page.getByText("Contraseña incorrecta o copia dañada.", { exact: true }),
  ).toBeVisible();
  expect(
    (
      await rpc<{ items: unknown[] }>("customers.list", {
        query: "Alta posterior",
      })
    ).items,
  ).toHaveLength(1);
  const uploadCalls = calls.filter(
    (action) => action === "backup.upload_chunk",
  ).length;
  expect(uploadCalls).toBeGreaterThan(4);
  await password.fill("clave-sintetica-local");
  await page
    .getByRole("button", { name: "Continuar comprobación", exact: true })
    .click();
  await expect(
    page.getByLabel(
      "Escribe RESTAURAR para reemplazar los datos de este equipo",
    ),
  ).toBeVisible();
  expect(
    calls.filter((action) => action === "backup.upload_chunk"),
  ).toHaveLength(uploadCalls);
  await page
    .getByLabel("Escribe RESTAURAR para reemplazar los datos de este equipo")
    .fill("RESTAURAR");
  await page
    .getByRole("button", { name: "Restaurar datos", exact: true })
    .click();
  await expect(
    page.getByText(/Copia restaurada\. Se guardó una copia previa:/),
  ).toBeVisible();
  expect(
    (
      await rpc<{ items: unknown[] }>("customers.list", {
        query: "Alta posterior",
      })
    ).items,
  ).toHaveLength(0);
  const recovered = await rpc<{ received: number }>("import.upload_status", {
    upload_id: uploaded.upload_id,
  });
  expect(recovered.received).toBe(original.length);
  // Repeated fragments are accepted only when every stored byte is identical.
  for (
    let offset = 0;
    offset < original.length;
    offset += uploaded.chunk_bytes
  ) {
    await rpc("import.upload_chunk", {
      upload_id: uploaded.upload_id,
      offset,
      content: original
        .subarray(offset, offset + uploaded.chunk_bytes)
        .toString("base64"),
    });
  }
  await backend.restart();
  expect(
    (
      await rpc<{ received: number }>("import.upload_status", {
        upload_id: uploaded.upload_id,
      })
    ).received,
  ).toBe(original.length);
  await page.screenshot({
    path: "reports/e2e-backup-streaming/restauracion.png",
    fullPage: true,
  });
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(axe.violations).toEqual([]);
});

test("cargas interrumpidas son visibles y descartables después de reiniciar", async ({
  page,
  rpc,
  backend,
}) => {
  const pending = await rpc<{ upload_id: string }>("backup.upload_start", {
    name: "copia-interrumpida.canamo",
    total_bytes: 2048,
  });
  await rpc("backup.upload_chunk", {
    upload_id: pending.upload_id,
    offset: 0,
    content: Buffer.alloc(1024, 42).toString("base64"),
  });
  await backend.restart();
  await page.goto("/");
  await page
    .getByRole("button", { name: "Configuración", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Copias y traslado", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Cargas anteriores pendientes" }),
  ).toBeVisible();
  await expect(
    page.getByText("copia-interrumpida.canamo · 1 KB recibidos"),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Descartar carga copia-interrumpida.canamo",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("heading", { name: "Cargas anteriores pendientes" }),
  ).toBeHidden();
  expect(await rpc("backup.upload_list")).toEqual([]);
});
