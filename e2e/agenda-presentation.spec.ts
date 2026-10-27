import AxeBuilder from "@axe-core/playwright";
import { writeFile } from "node:fs/promises";
import type { Page } from "@playwright/test";
import { test, expect } from "./fixtures";

type Event = Record<string, any>;

for (const theme of ["light", "dark"] as const) {
  test(`el control de duración conserva el color y el texto de la cita al pasar el cursor: ${theme}`, async ({ page, rpc }, info) => {
    await rpc("settings.save", { section: "appearance", values: { extras: true, theme } });
    const saved = await rpc<Event>("agenda.save", { data: {
      title: "Cita breve", start_local: "2026-05-15T10:00", end_local: "2026-05-15T10:30", reminders: [],
    } });
    await openAgenda(page, "2026-05-15");
    const event = page.locator(`[data-event-id="${saved.id}"]`);
    const handle = event.getByRole("button", { name: "Cambiar duración de Cita breve", exact: true });
    for (const width of [1366, 390]) {
      await page.setViewportSize({ width, height: 900 });
      for (const view of ["Día", "Semana"]) {
        await page.getByRole("button", { name: view, exact: true }).click();
        await handle.scrollIntoViewIfNeeded();
        const before = await event.boundingBox();
        await handle.hover();
        await event.screenshot({ path: info.outputPath(`resize-hover-${theme}-${width}-${view}.png`) });
        // The hit area must not paint over the event's title/time or alter its size.
        await expect(handle).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
        await expect(handle).toHaveCSS("cursor", "ns-resize");
        expect(await event.boundingBox()).toEqual(before);
        const geometry = await event.evaluate(element => {
          const handle = element.querySelector<HTMLElement>(".event-resize-handle")!;
          const main = element.querySelector<HTMLElement>(".time-event-main")!;
          const time = main.querySelector("span")!.getBoundingClientRect();
          const bounds = element.getBoundingClientRect();
          return { hitHeight: handle.getBoundingClientRect().height, timeBottom: time.bottom, bottom: bounds.bottom };
        });
        expect(geometry.hitHeight).toBeGreaterThanOrEqual(24);
        expect(geometry.timeBottom).toBeLessThanOrEqual(geometry.bottom - 5);
        await event.getByRole("button", { name: "Editar o mover Cita breve", exact: true }).focus();
        await page.keyboard.press("Tab");
        await expect(handle).toBeFocused();
        await expect(handle).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
        expect(await handle.evaluate(element => {
          const style = getComputedStyle(element);
          return style.outlineStyle !== "none" && parseFloat(style.outlineWidth) >= 2;
        })).toBe(true);
        const axe = await new AxeBuilder({ page }).include(".time-calendar")
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
        expect(axe.violations, JSON.stringify(axe.violations)).toEqual([]);
      }
    }
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
    await expect(dialog.getByRole("textbox", { name: "Termina", exact: true })).toHaveValue("2026-05-15T10:30");
    await dialog.getByRole("button", { name: "Cancelar", exact: true }).click();
    expect((await rpc<Event>("agenda.get", { identifier: saved.id })).end).toBe("2026-05-15T08:30:00+00:00");
  });
}

async function openAgenda(page: Page, date: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Más herramientas" }).click();
  await page.getByRole("button", { name: "Agenda", exact: true }).click();
  await page.getByLabel("Ir a una fecha").fill(date);
}

// Keep saved event data real; replace only the dashboard's server-current-day
// selection so both seasonal dates can be checked without changing its clock.
async function dashboardEvents(page: Page, events: Event[]) {
  await page.route("**/api", async (route) => {
    if (route.request().postDataJSON().action !== "dashboard") {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    const body = await response.json();
    body.result.today_events = events;
    await route.fulfill({ response, json: body });
  });
}

test("Mes mantiene 42 cuadrados y todos los eventos accesibles a 320, 390, 768 y 1366 px", async ({ page, rpc }, info) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true, theme: "dark", font_size: "extra" } });
  const date = "2026-05-15";
  const titles: string[] = [];
  for (let index = 0; index < 8; index++) {
    const title = `Evento de desbordamiento ${index + 1}` + (index === 7 ? " con descripción extensa que se abre completa y conserva todas sus palabras" : "");
    titles.push(title);
    const hour = String(10 + Math.floor(index / 2)).padStart(2, "0");
    const minute = index % 2 ? "30" : "00";
    await rpc("agenda.save", { data: {
      title, start_local: `${date}T${hour}:${minute}`,
      end_local: `${date}T${hour}:${index % 2 ? "45" : "15"}`, reminders: [],
    } });
  }
  await rpc("agenda.save", { data: {
    title: "Cierre de varios días", all_day: true,
    start_date: "2026-05-14", end_date: "2026-05-17", reminders: [],
  } });
  await openAgenda(page, date);
  const measurements: unknown[] = [];
  for (const width of [320, 390, 768, 1366]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByRole("button", { name: "Mes", exact: true }).click();
    await expect(page.locator(".month-cell")).toHaveCount(42);
    const cell = page.locator(`.month-cell[data-date="${date}"]`);
    await expect(cell.getByRole("button", { name: `Ver día ${date}, 9 eventos`, exact: true })).toBeVisible();
    const dimensions = await page.locator(".month-cell").evaluateAll((cells) => cells.map((cell) => {
      const box = cell.getBoundingClientRect();
      return { width: box.width, height: box.height, overflow: cell.scrollHeight - cell.clientHeight };
    }));
    expect(dimensions.every((box) => Math.abs(box.width - box.height) <= 1)).toBe(true);
    expect(dimensions.every((box) => box.overflow <= 1)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const axe = await new AxeBuilder({ page }).include(".month-calendar").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(axe.violations, JSON.stringify(axe.violations)).toEqual([]);
    measurements.push({ viewport: width, dimensions, axe_violations: axe.violations.length });
    if (width === 320 || width === 1366) {
      await page.locator(".calendar-panel").screenshot({ path: info.outputPath(`month-square-${width}.png`) });
    }
    const more = cell.getByRole("button", { name: `Ver los 9 eventos del ${date}`, exact: true });
    const open = await more.isVisible() ? more : cell.getByRole("button", { name: `Ver día ${date}, 9 eventos`, exact: true });
    await open.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator(".time-calendar.day")).toBeVisible();
    await expect(page.locator(".time-event")).toHaveCount(8);
    await expect(page.locator(".all-day-row")).toContainText("Cierre de varios días");
    await page.getByRole("button", { name: `Editar o mover ${titles[7]}`, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
    await expect(dialog.getByLabel("Título")).toHaveValue(titles[7]);
    await dialog.getByRole("button", { name: "Cancelar", exact: true }).click();
    await expect(dialog).toBeHidden();
  }
  const evidence = info.outputPath("month-dimensions.json");
  await writeFile(evidence, JSON.stringify(measurements, null, 2));
  await info.attach("month-dimensions.json", { path: evidence, contentType: "application/json" });
});

for (const timezoneId of ["Europe/Madrid", "America/New_York"]) {
  test.describe(`Horas de taller con navegador ${timezoneId}`, () => {
    test.use({ timezoneId });
    for (const season of [
      { date: "2026-03-29", midnightOffset: "+01:00", utc: "17:00", month: "marzo" },
      { date: "2026-10-25", midnightOffset: "+02:00", utc: "18:00", month: "octubre" },
    ]) {
      test(`19:00 se guarda y se muestra igual en Agenda e Inicio tras cambio DST ${season.date}`, async ({ page, rpc }) => {
        await rpc("settings.save", { section: "appearance", values: { extras: true } });
        await page.clock.setFixedTime(new Date(`${season.date}T00:30:00${season.midnightOffset}`));
        await openAgenda(page, season.date);
        await page.getByRole("button", { name: "Nuevo evento", exact: true }).click();
        const dialog = page.getByRole("dialog", { name: "Nuevo evento", exact: true });
        await dialog.getByLabel("Título").fill("Cita sintética a las siete");
        await dialog.getByRole("textbox", { name: "Comienza", exact: true }).fill(`${season.date}T19:00`);
        await dialog.getByRole("textbox", { name: "Termina", exact: true }).fill(`${season.date}T19:45`);
        await dialog.getByRole("button", { name: "Guardar evento", exact: true }).click();
        await expect(dialog).toBeHidden();
        const events = await rpc<Event[]>("agenda.list", { start: `${season.date}T00:00:00Z`, end: `${season.date}T23:59:59Z` });
        expect(events).toHaveLength(1);
        expect(events[0].start).toBe(`${season.date}T${season.utc}:00+00:00`);
        expect(new Date(events[0].occurrence_start).toISOString()).toBe(`${season.date}T${season.utc}:00.000Z`);
        await page.getByRole("button", { name: "Día", exact: true }).click();
        await expect(page.locator(".time-event-main")).toContainText("19:00 – 19:45");
        await page.getByRole("button", { name: "Editar o mover Cita sintética a las siete", exact: true }).click();
        const edit = page.getByRole("dialog", { name: "Editar evento", exact: true });
        await expect(edit.getByRole("textbox", { name: "Comienza", exact: true })).toHaveValue(`${season.date}T19:00`);
        await edit.getByRole("button", { name: "Cancelar", exact: true }).click();
        await dashboardEvents(page, events);
        await page.getByRole("button", { name: "Inicio", exact: true }).click();
        await expect(page.locator(".today-entry .today-time")).toHaveText("19:00");
        await expect(page.locator(".page-head .eyebrow")).toContainText(`${Number(season.date.slice(-2))} de ${season.month}`);
      });
    }
  });
}

test("el evento abre fichas mediante sus identificadores y conserva datos al volver", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const customer = await rpc<Event>("customers.save", { data: { name: "Cliente de agenda sintético" } });
  const vehicle = await rpc<Event>("vehicles.save", { data: { customer_id: customer.id, plate: "7000SYN", kind: "Vehículo de agenda sintético" } });
  await rpc("agenda.save", { data: {
    title: "Cita vinculada sintética", start_local: "2026-05-15T19:00", end_local: "2026-05-15T20:00",
    customer_id: customer.id, vehicle_id: vehicle.id, reminders: [],
  } });
  await openAgenda(page, "2026-05-15");
  await page.getByRole("button", { name: "Día", exact: true }).click();
  await page.getByRole("button", { name: "Editar o mover Cita vinculada sintética", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
  await dialog.getByText("Cliente, lugar y notas (opcional)", { exact: true }).click();
  await expect(dialog.locator("button button")).toHaveCount(0);
  await dialog.getByRole("button", { name: "7000SYN", exact: true }).click();
  await expect(page.getByRole("heading", { name: "7000SYN", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Cliente de agenda sintético", exact: true }).first()).toBeVisible();
  const events = await rpc<Event[]>("agenda.list", { start: "2026-05-15T00:00:00Z", end: "2026-05-16T00:00:00Z" });
  expect(events[0].customer_id).toBe(customer.id);
  expect(events[0].vehicle_id).toBe(vehicle.id);
  expect(new Date(events[0].occurrence_start).toISOString()).toBe("2026-05-15T17:00:00.000Z");
});

test("los enlaces de Agenda conservan la edición al volver y sólo la descartan con confirmación", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const customer = await rpc<Event>("customers.save", { data: { name: "Cliente de borrador sintético" } });
  const vehicle = await rpc<Event>("vehicles.save", { data: { customer_id: customer.id, plate: "7100SYN" } });
  const saved = await rpc<Event>("agenda.save", { data: {
    title: "Evento guardado sintético", start_local: "2026-05-15T19:00", end_local: "2026-05-15T20:00",
    customer_id: customer.id, vehicle_id: vehicle.id, reminders: [],
  } });
  await openAgenda(page, "2026-05-15");
  await page.getByRole("button", { name: "Día", exact: true }).click();
  await page.getByRole("button", { name: "Editar o mover Evento guardado sintético", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
  await dialog.getByLabel("Título").fill("Edición pendiente sintética");
  await dialog.getByText("Cliente, lugar y notas (opcional)", { exact: true }).click();
  await dialog.getByLabel("Notas", { exact: true }).fill("Notas pendientes que deben conservarse al volver");
  await dialog.getByRole("button", { name: "Cliente de borrador sintético", exact: true }).click();
  const confirmation = page.getByRole("dialog", { name: "Evento sin guardar", exact: true });
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", { name: "Volver", exact: true }).click();
  await expect(confirmation).toBeHidden();
  await expect(dialog.getByLabel("Título")).toHaveValue("Edición pendiente sintética");
  await expect(dialog.getByLabel("Notas", { exact: true })).toHaveValue("Notas pendientes que deben conservarse al volver");
  await dialog.getByRole("button", { name: "7100SYN", exact: true }).click();
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", { name: "Salir sin guardar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "7100SYN", exact: true })).toBeVisible();
  const unchanged = await rpc<Event>("agenda.get", { identifier: saved.id });
  expect(unchanged.title).toBe("Evento guardado sintético");
  expect(unchanged.notes).toBe("");
});

test("los vínculos de Agenda quedan bloqueados mientras se guarda el evento", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const customer = await rpc<Event>("customers.save", { data: { name: "Cliente de espera sintético" } });
  const vehicle = await rpc<Event>("vehicles.save", { data: { customer_id: customer.id, plate: "7200SYN" } });
  const saved = await rpc<Event>("agenda.save", { data: {
    title: "Evento a guardar sintético", start_local: "2026-05-15T19:00", end_local: "2026-05-15T20:00",
    customer_id: customer.id, vehicle_id: vehicle.id, reminders: [],
  } });
  await openAgenda(page, "2026-05-15");
  await page.getByRole("button", { name: "Día", exact: true }).click();
  await page.getByRole("button", { name: "Editar o mover Evento a guardar sintético", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
  await dialog.getByLabel("Título").fill("Evento confirmado sintético");
  await dialog.getByText("Cliente, lugar y notas (opcional)", { exact: true }).click();
  let releaseSave!: () => void;
  const held = new Promise<void>(resolve => { releaseSave = resolve; });
  await page.route("**/api", async route => {
    if (route.request().postDataJSON().action === "agenda.save") await held;
    await route.continue();
  });
  try {
    await dialog.getByRole("button", { name: "Guardar evento", exact: true }).click();
    const customerLink = dialog.getByRole("button", { name: "Cliente de espera sintético", exact: true });
    const vehicleLink = dialog.getByRole("button", { name: "7200SYN", exact: true });
    await expect(customerLink).toBeDisabled();
    await expect(vehicleLink).toBeDisabled();
    await vehicleLink.evaluate((button: HTMLButtonElement) => button.click());
    await expect(dialog).toBeVisible();
    expect((await rpc<Event>("agenda.get", { identifier: saved.id })).title).toBe("Evento a guardar sintético");
  } finally {
    releaseSave();
  }
  await expect(dialog).toBeHidden();
  expect((await rpc<Event>("agenda.get", { identifier: saved.id })).title).toBe("Evento confirmado sintético");
});
