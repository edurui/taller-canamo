import type { Locator, Page } from "@playwright/test";
import { test, expect } from "./fixtures";

type Rpc = <T = Record<string, unknown>>(action: string, params?: Record<string, unknown>) => Promise<T>;
type Invoice = { id: string; full_number: string; total_cents: number };
type FiscalRecord = { id: string; full_number: string; environment: string; status: string };

async function seed(rpc: Rpc) {
  const settings = await rpc<{ fiscal: { mode: string } }>("settings.get");
  expect(settings.fiscal.mode).toBe("local_test");
  await rpc("settings.save", { section: "company", values: {
    legal_name: "TALLER DE ORDENACIÓN SINTÉTICO", tax_id: "89890001K",
  } });
  const customer = await rpc<{ id: string }>("customers.save", { data: {
    name: "Cliente de adaptadores sintético", tax_id: "12345678Z",
    address: "Dirección sintética", postal_code: "41300", city: "Localidad sintética",
  } });
  const invoices: Invoice[] = [];
  for (const [letter, price] of [["A", "10"], ["C", "30"], ["B", "20"]]) {
    const series = await rpc<{ id: string }>("series.save", { data: {
      kind: "invoice", label: `Serie sintética ${letter}`, prefix: `SORT-${letter}-`,
      year: 0, padding: 3, next_number: 1,
    } });
    const draft = await rpc<{ id: string }>("documents.save", { data: {
      customer_id: customer.id, series_id: series.id,
      lines: [{ description: "Trabajo sintético de ordenación", quantity: "1", unit_price: price, tax_rate: "21" }],
    } });
    invoices.push(await rpc<Invoice>("documents.publish", { identifier: draft.id }));
  }
  return invoices;
}

async function openPanel(page: Page, name: string) {
  await page.goto("/");
  await page.locator(".sidebar").getByRole("button", { name: "Configuración", exact: true }).click();
  await page.getByRole("button", { name, exact: true }).click();
}

async function order(table: Locator, label: string, next: string, ariaSort: string) {
  const button = table.getByRole("button", { name: `${label}: ordenar ${next}`, exact: true });
  await button.click();
  await expect(table.getByRole("columnheader", { name: new RegExp(`^${label}: ordenar `) }))
    .toHaveAttribute("aria-sort", ariaSort);
  await expect(table).toHaveAttribute("aria-busy", "false");
}

test("Fiscal ordena ascendente, descendente y original; abrir una fila sólo consulta su detalle", async ({ page, rpc }) => {
  const invoices = await seed(rpc);
  const before = await rpc<FiscalRecord[]>("fiscal.list");
  expect(before).toHaveLength(3);
  expect(before.every(record => record.environment === "local_test" && record.status === "local_only")).toBe(true);
  await openPanel(page, "VERI*FACTU (pruebas)");
  const table = page.getByRole("table", { name: "Registros fiscales", exact: true });
  const numbers = table.locator("tbody tr td:first-child .entity-reference");
  await expect(numbers).toHaveText(before.map(record => record.full_number));
  const ascending = invoices.map(invoice => invoice.full_number).sort();
  await order(table, "Documento", "ascendente", "ascending");
  await expect(numbers).toHaveText(ascending);
  await order(table, "Documento", "descendente", "descending");
  await expect(numbers).toHaveText([...ascending].reverse());
  await order(table, "Documento", "original", "none");
  await expect(numbers).toHaveText(before.map(record => record.full_number));
  await table.locator("tbody tr").first().getByRole("cell").nth(1).click();
  const detail = page.getByRole("dialog", { name: "Detalle del registro", exact: true });
  await expect(detail).toBeVisible();
  await expect(detail.getByRole("button", { name: before[0].full_number, exact: true })).toBeVisible();
  await expect(detail.getByText("No recibido", { exact: true })).toBeVisible();
  await expect(detail.getByText("local_test", { exact: true })).toBeVisible();
  await detail.getByRole("button", { name: "Cerrar ventana", exact: true }).click();
  await expect(detail).toHaveCount(0);
  expect(await rpc("fiscal.list")).toEqual(before);
});

test("B2B ordena importes en ambos sentidos y recupera el original; la fila abre el archivo local", async ({ page, rpc }) => {
  const invoices = await seed(rpc);
  for (const invoice of invoices) {
    const prepared = await rpc<{ remote_delivered: boolean; test_document: boolean }>("b2b.prepare", {
      document_id: invoice.id, recipient_business: true,
    });
    expect(prepared.remote_delivered).toBe(false);
    expect(prepared.test_document).toBe(true);
  }
  const before = await rpc<{ items: { id: string; invoice_number: string }[]; total: number }>("b2b.list");
  expect(before.total).toBe(3);
  await openPanel(page, "Factura electrónica B2B");
  const table = page.getByRole("table", { name: "Facturas electrónicas conservadas", exact: true });
  const numbers = table.locator("tbody tr td:first-child .entity-reference");
  await expect(numbers).toHaveText(before.items.map(record => record.invoice_number));
  const ascending = [...invoices].sort((a, b) => a.total_cents - b.total_cents).map(invoice => invoice.full_number);
  await order(table, "Total", "ascendente", "ascending");
  await expect(numbers).toHaveText(ascending);
  await order(table, "Total", "descendente", "descending");
  await expect(numbers).toHaveText([...ascending].reverse());
  await order(table, "Total", "original", "none");
  await expect(numbers).toHaveText(before.items.map(record => record.invoice_number));
  await table.locator("tbody tr").first().getByRole("cell").nth(3).click();
  const selected = before.items[0];
  const detail = page.getByRole("dialog", { name: `Factura electrónica ${selected.invoice_number}`, exact: true });
  await expect(detail).toBeVisible();
  await expect(detail.getByText("Documento de prueba sin validez fiscal.", { exact: true })).toBeVisible();
  await expect(detail.getByText(/validación local superada/)).toBeVisible();
  await detail.getByRole("button", { name: "Cerrar ventana", exact: true }).click();
  await expect(detail).toHaveCount(0);
  expect(await rpc("b2b.list")).toEqual(before);
  for (const record of before.items) {
    expect((await rpc<{ remote_delivered: boolean }>("b2b.get", { identifier: record.id })).remote_delivered).toBe(false);
  }
});
