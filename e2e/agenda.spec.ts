import { chooseOption } from "./fixtures";
import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";

type Event = Record<string, any>;
const autumn = { start: "2026-10-01T00:00:00Z", end: "2026-11-10T00:00:00Z" };

async function openAgenda(
  page: import("@playwright/test").Page,
  date = "2026-10-18",
) {
  await page.goto("/");
  await page.getByRole("button", { name: "Más herramientas" }).click();
  await page.getByRole("button", { name: "Agenda", exact: true }).click();
  await page.getByLabel("Ir a una fecha").fill(date);
}

test("editar una repetición, cancelar otra y restablecerla tras reinicio", async ({
  page,
  rpc,
  backend,
}) => {
  await rpc("settings.save", {
    section: "appearance",
    values: { extras: true },
  });
  await rpc("agenda.save", {
    data: {
      title: "Revisión semanal sintética",
      start_local: "2026-10-18T09:00",
      end_local: "2026-10-18T10:00",
      recurrence: { freq: "weekly", until: "2026-11-01", dst_policy: "skip" },
      reminders: [],
    },
  });
  await openAgenda(page, "2026-10-25");
  await page.getByRole("button", { name: "Día", exact: true }).click();
  await page
    .getByRole("button", { name: "Editar o mover Revisión semanal sintética" })
    .click();
  let dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
  await expect(dialog.getByLabel("Aplicar cambios a")).toHaveText(
    "Esta repetición",
  );
  await expect(
    dialog.getByRole("textbox", { name: "Comienza", exact: true }),
  ).toHaveValue("2026-10-25T09:00");
  await dialog.getByLabel("Título").fill("Solo el domingo 25");
  await dialog
    .getByRole("textbox", { name: "Comienza", exact: true })
    .fill("2026-10-25T11:00");
  await dialog
    .getByRole("textbox", { name: "Termina", exact: true })
    .fill("2026-10-25T12:30");
  await dialog.getByRole("button", { name: "Guardar evento" }).click();
  await expect(dialog).toBeHidden();
  let events = await rpc<Event[]>("agenda.list", autumn);
  expect(events.map((e) => e.title)).toEqual([
    "Revisión semanal sintética",
    "Solo el domingo 25",
    "Revisión semanal sintética",
  ]);
  await page.getByLabel("Ir a una fecha").fill("2026-10-18");
  await page
    .getByRole("button", { name: "Editar o mover Revisión semanal sintética" })
    .click();
  dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
  await dialog.getByRole("button", { name: "Eliminar", exact: true }).click();
  const confirm = page.getByRole("dialog", {
    name: "Eliminar evento",
    exact: true,
  });
  await expect(confirm).toContainText("solo esta repetición");
  await confirm.getByRole("button", { name: "Eliminar", exact: true }).click();
  await expect(dialog).toBeHidden();
  await page.getByLabel("Mostrar canceladas").check();
  await page
    .getByRole("button", { name: "Editar o mover Revisión semanal sintética" })
    .click();
  await expect(dialog).toContainText("Esta repetición está cancelada");
  await dialog.getByRole("button", { name: "Cerrar ventana" }).click();
  await page.getByLabel("Mostrar canceladas").uncheck();
  await backend.restart();
  events = await rpc<Event[]>("agenda.list", autumn);
  expect(events).toHaveLength(2);
  await page.reload();
  await page.getByRole("button", { name: "Más herramientas" }).click();
  await page.getByRole("button", { name: "Agenda", exact: true }).click();
  await page.getByLabel("Ir a una fecha").fill("2026-10-25");
  await page.getByRole("button", { name: "Día", exact: true }).click();
  await page
    .getByRole("button", { name: "Editar o mover Solo el domingo 25" })
    .click();
  dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
  await expect(dialog.getByLabel("Aplicar cambios a")).toBeEnabled();
  await chooseOption(dialog.getByLabel("Aplicar cambios a"), "series");
  await expect(
    dialog.getByRole("textbox", { name: "Comienza", exact: true }),
  ).toHaveValue("2026-10-18T09:00");
  await dialog.getByText("Repeticiones modificadas o eliminadas (2)").click();
  await dialog
    .locator(".linked-item")
    .filter({ hasText: "Eliminada" })
    .getByRole("button", { name: "Restablecer repetición" })
    .click();
  await expect(dialog).toBeHidden();
  expect(await rpc<Event[]>("agenda.list", autumn)).toHaveLength(3);
});

test("puntero mueve y redimensiona; teclado confirma fechas en una vista estrecha accesible", async ({
  page,
  rpc,
}, info) => {
  await rpc("settings.save", {
    section: "appearance",
    values: { extras: true, theme: "dark", font_size: "large" },
  });
  const created = await rpc<Event>("agenda.save", {
    data: {
      title: "Cita arrastrable",
      start_local: "2026-09-23T09:00",
      end_local: "2026-09-23T10:00",
      reminders: [],
    },
  });
  await page.setViewportSize({ width: 1024, height: 768 });
  await openAgenda(page, "2026-09-23");
  await page.getByRole("button", { name: "Semana", exact: true }).click();
  const move = page.getByRole("button", {
    name: "Editar o mover Cita arrastrable",
  });
  await move.scrollIntoViewIfNeeded();
  const before = await move.boundingBox();
  const column = await move.locator("../..").boundingBox();
  expect(before).not.toBeNull();
  expect(column).not.toBeNull();
  await page.mouse.move(before!.x + before!.width / 2, before!.y + 12);
  await page.mouse.down();
  await page.mouse.move(
    before!.x + before!.width / 2 + column!.width,
    before!.y + 76,
    { steps: 8 },
  );
  await page.mouse.up();
  let dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
  await expect(
    dialog.getByRole("textbox", { name: "Comienza", exact: true }),
  ).toHaveValue("2026-09-24T10:00");
  await dialog.getByRole("button", { name: "Guardar evento" }).click();
  await expect(dialog).toBeHidden();
  await expect(move).toContainText("10:00 – 11:00");
  await page.getByRole("button", { name: "Cerrar aviso", exact: true }).click();
  const resize = page.getByRole("button", {
    name: "Cambiar duración de Cita arrastrable",
  });
  await resize.scrollIntoViewIfNeeded();
  const handle = await resize.boundingBox();
  await page.mouse.move(
    handle!.x + handle!.width / 2,
    handle!.y + handle!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    handle!.x + handle!.width / 2,
    handle!.y + handle!.height / 2 + 32,
    { steps: 4 },
  );
  await page.mouse.up();
  dialog = page.getByRole("dialog", { name: "Editar evento", exact: true });
  await expect(
    dialog.getByRole("textbox", { name: "Termina", exact: true }),
  ).toHaveValue("2026-09-24T11:30");
  await dialog.getByRole("button", { name: "Guardar evento" }).click();
  await expect(dialog).toBeHidden();
  await move.focus();
  await page.keyboard.press("Enter");
  await dialog
    .getByRole("textbox", { name: "Termina", exact: true })
    .fill("2026-09-24T12:00");
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  await info.attach("agenda-form-axe.json", {
    body: JSON.stringify(axe, null, 2),
    contentType: "application/json",
  });
  expect(axe.violations, JSON.stringify(axe.violations)).toEqual([]);
  await dialog.getByRole("button", { name: "Guardar evento" }).click();
  await expect(dialog).toBeHidden();
  const saved = await rpc<Event>("agenda.get", { identifier: created.id });
  expect(saved.start).toBe("2026-09-24T08:00:00+00:00");
  expect(saved.end).toBe("2026-09-24T10:00:00+00:00");
  const calendarAxe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(
    calendarAxe.violations,
    JSON.stringify(calendarAxe.violations),
  ).toEqual([]);
  await page.screenshot({
    path: info.outputPath("agenda-pointer-dark-1024.png"),
    fullPage: true,
  });
});

test.describe("Zona del equipo distinta de Madrid", () => {
  test.use({ timezoneId: "America/New_York" });

  test("hora duplicada requiere elección y todo el día conserva fechas en un equipo de otra zona", async ({
    page,
    rpc,
  }) => {
    await rpc("settings.save", {
      section: "appearance",
      values: { extras: true },
    });
    await openAgenda(page, "2026-10-25");
    await page
      .getByRole("button", { name: "Nuevo evento", exact: true })
      .click();
    let dialog = page.getByRole("dialog", {
      name: "Nuevo evento",
      exact: true,
    });
    await dialog.getByLabel("Título").fill("Doble hora sintética");
    await dialog
      .getByRole("textbox", { name: "Comienza", exact: true })
      .fill("2026-10-25T02:30");
    await dialog
      .getByRole("textbox", { name: "Termina", exact: true })
      .fill("2026-10-25T02:30");
    await expect(dialog.getByLabel("Comienza: hora repetida")).toHaveText("Elige qué hora");
    await dialog.getByRole("button", { name: "Guardar evento" }).click();
    await expect(dialog).toBeVisible();
    await chooseOption(dialog.getByLabel("Comienza: hora repetida"), "0");
    await chooseOption(dialog.getByLabel("Termina: hora repetida"), "1");
    await dialog.getByRole("button", { name: "Guardar evento" }).click();
    await expect(dialog).toBeHidden();
    let rows = await rpc<Event[]>("agenda.list", autumn);
    expect(rows[0].start).toBe("2026-10-25T00:30:00+00:00");
    expect(rows[0].end).toBe("2026-10-25T01:30:00+00:00");
    await page
      .getByRole("button", { name: "Nuevo evento", exact: true })
      .click();
    dialog = page.getByRole("dialog", { name: "Nuevo evento", exact: true });
    await dialog.getByLabel("Título").fill("Cierre varios días");
    await dialog.getByRole("checkbox", { name: "Todo el día" }).click();
    await dialog.getByLabel("Primer día").fill("2026-10-24");
    await dialog.getByLabel("Último día (incluido)").fill("2026-10-26");
    await dialog.getByRole("button", { name: "Guardar evento" }).click();
    await expect(dialog).toBeHidden();
    rows = await rpc<Event[]>("agenda.list", autumn);
    const allDay = rows.find((row) => row.all_day);
    expect(allDay?.start_date).toBe("2026-10-24");
    expect(allDay?.end_date).toBe("2026-10-27");
    await page
      .getByRole("button", { name: "Nuevo evento", exact: true })
      .click();
    dialog = page.getByRole("dialog", { name: "Nuevo evento", exact: true });
    await dialog
      .getByLabel("Título")
      .fill("Madrid 02:30 con equipo en Nueva York");
    await dialog
      .getByRole("textbox", { name: "Comienza", exact: true })
      .fill("2026-03-08T02:30");
    await dialog
      .getByRole("textbox", { name: "Termina", exact: true })
      .fill("2026-03-08T03:30");
    await dialog.getByRole("button", { name: "Guardar evento" }).click();
    await expect(dialog).toBeHidden();
    const march = await rpc<Event[]>("agenda.list", {
      start: "2026-03-01T00:00:00Z",
      end: "2026-04-01T00:00:00Z",
    });
    expect(march[0].start).toBe("2026-03-08T01:30:00+00:00");
  });
});

test("avisos atrasados agrupados: posponer en pantalla conserva el estado al reiniciar", async ({
  page,
  rpc,
  backend,
}) => {
  const start = new Date(Date.now() - 3 * 86400000 - 60000);
  const event = await rpc<Event>("agenda.save", {
    data: {
      title: "Avisos sintéticos acumulados",
      start: start.toISOString(),
      end: new Date(start.getTime() + 3600000).toISOString(),
      recurrence: {
        freq: "daily",
        until: new Date(Date.now() + 86400000).toISOString().slice(0, 10),
      },
      reminders: [0, 15],
    },
  });
  const summaries = await rpc<Event[]>("notifications.list");
  expect(summaries).toHaveLength(1);
  expect(summaries[0].missed_count).toBeGreaterThanOrEqual(6);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Avisos: 1 pendientes", exact: true })
    .click();
  const notices = page.getByRole("dialog", { name: "Tus avisos", exact: true });
  await expect(notices.locator("article")).toHaveCount(1);
  await expect(notices).toContainText("avisos pendientes");
  await notices
    .getByRole("button", { name: "Posponer 15 min", exact: true })
    .click();
  await expect(notices.locator("article")).toHaveCount(0);
  await notices.getByRole("button", { name: "Cerrar ventana" }).click();
  await backend.restart();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Avisos: 0 pendientes", exact: true }),
  ).toBeVisible();
  await rpc("agenda.save", {
    data: { ...event, title: "Solo corregir el texto" },
  });
  expect(await rpc<Event[]>("notifications.list")).toEqual([]);
});
