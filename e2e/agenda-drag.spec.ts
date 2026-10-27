import type { Locator, Page } from "@playwright/test";
import { test, expect, navigateSidebar } from "./fixtures";

type Row = Record<string, any>;
const title = "Cita de arrastre sintética";
const moveButton = (page: Page) => page.getByRole("button", { name: "Editar o mover " + title, exact: true });
const resizeButton = (page: Page) => page.getByRole("button", { name: "Cambiar duración de " + title, exact: true });
const editor = (page: Page) => page.getByRole("dialog", { name: "Editar evento", exact: true });
const base = { title, start_local: "2026-05-15T10:00", end_local: "2026-05-15T11:00", reminders: [] };

async function open(page: Page, date = "2026-05-15") {
  await page.goto("/");
  await navigateSidebar(page, "Agenda");
  await page.getByLabel("Ir a una fecha").fill(date);
  await page.getByRole("button", { name: "Día", exact: true }).click();
  await expect(moveButton(page)).toBeEnabled();
}
async function grab(page: Page, handle: Locator, dy: number, release = true) {
  await expect(handle).toBeEnabled();
  await handle.scrollIntoViewIfNeeded();
  const box = (await handle.boundingBox())!;
  // Upper content moves; the separate lower target resizes.
  const x = box.x + box.width / 2, y = box.y + 10;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + dy, { steps: 6 });
  if (release) await page.mouse.up();
  return { x, y };
}

test("clic y pequeño temblor abren edición; arrastre sin cambio, Escape y cancelación no guardan ni abren modal", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: base });
  let saves = 0;
  page.on("request", request => {
    if (request.url().endsWith("/api") && request.postDataJSON()?.action === "agenda.save") saves++;
  });
  await open(page);
  for (const handle of [moveButton(page), resizeButton(page)]) {
    await grab(page, handle, 2);
    await expect(editor(page)).toBeVisible();
    await editor(page).getByRole("button", { name: "Cancelar", exact: true }).click();
    await expect(editor(page)).toBeHidden();

    await grab(page, handle, 6); // gesture recognized, but no 15-minute step
    await expect(editor(page)).toBeHidden();
    const { x, y } = await grab(page, handle, 32, false);
    await page.mouse.move(x, y, { steps: 4 }); // returns to origin
    await page.mouse.up();
    await expect(editor(page)).toBeHidden();

    await grab(page, handle, 32, false);
    await page.keyboard.press("Escape");
    await page.mouse.up();
    await expect(editor(page)).toBeHidden();
    // A keyboard click after a cancelled pointer gesture must still work.
    await handle.focus();
    await page.keyboard.press("Enter");
    await expect(editor(page)).toBeVisible();
    await editor(page).getByRole("button", { name: "Cancelar", exact: true }).click();
    await expect(editor(page)).toBeHidden();

    for (const eventName of ["pointercancel", "lostpointercapture"]) {
      await handle.evaluate(element => element.addEventListener("pointerdown", event => {
        element.setAttribute("data-test-pointer", String((event as PointerEvent).pointerId));
      }, { once: true }));
      await grab(page, handle, 32, false);
      const pointerId = Number(await handle.getAttribute("data-test-pointer"));
      await handle.dispatchEvent(eventName, { pointerId, isPrimary: true, pointerType: "mouse" });
      await page.mouse.up();
      await expect(editor(page)).toBeHidden();
    }
  }
  expect(saves).toBe(0);
  expect((await rpc<Row>("agenda.get", { identifier: saved.id })).version).toBe(saved.version);
  await expect(moveButton(page)).toContainText("10:00 – 11:00");
});

test("soltar guarda una vez, conserva campos y bloquea una segunda edición mientras espera", async ({ page, rpc, backend }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: { ...base, notes: "Notas que deben conservarse", location: "Zona sintética", reminders: [10], kind: "maintenance" } });
  await open(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const writes: Row[] = [];
  await page.route("**/api", async route => {
    const payload = route.request().postDataJSON();
    if (payload.action === "agenda.save") {
      writes.push(payload.params.data);
      await held;
    }
    await route.continue();
  });
  try {
    await grab(page, moveButton(page), 64);
    await expect.poll(() => writes.length).toBe(1);
    await expect(editor(page)).toBeHidden();
    await expect(moveButton(page)).toContainText("11:00 – 12:00");
    await expect(moveButton(page)).toBeDisabled();
    await expect(resizeButton(page)).toBeDisabled();
    await expect(page.getByRole("status", { name: "" }).filter({ hasText: "Guardando cambio" })).toBeVisible();
    await moveButton(page).evaluate((button: HTMLButtonElement) => button.click());
    await resizeButton(page).evaluate((button: HTMLButtonElement) => button.click());
    expect(writes).toHaveLength(1);
    expect((await rpc<Row>("agenda.get", { identifier: saved.id })).start).toBe(saved.start);
  } finally {
    release();
  }
  await expect(moveButton(page)).toBeEnabled();
  await expect(editor(page)).toBeHidden();
  const updated = await rpc<Row>("agenda.get", { identifier: saved.id });
  expect(updated.version).toBe(saved.version + 1);
  expect(updated.start).toBe("2026-05-15T09:00:00+00:00");
  for (const key of ["title", "kind", "notes", "location", "reminders", "completed", "recurrence"]) expect(updated[key]).toEqual(saved[key]);
  await backend.restart();
  await page.reload();
  await navigateSidebar(page, "Agenda");
  await page.getByLabel("Ir a una fecha").fill("2026-05-15");
  await page.getByRole("button", { name: "Día", exact: true }).click();
  await expect(moveButton(page)).toContainText("11:00 – 12:00");
  expect(writes).toHaveLength(1);
});

test("fallo de guardado restaura la cita, muestra el error y permite volver a arrastrar", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: base });
  await open(page);
  await page.route("**/api", async route => {
    if (route.request().postDataJSON().action === "agenda.save")
      await route.fulfill({ json: { ok: false, error: { code: "synthetic", message: "Fallo sintético de guardado" } } });
    else await route.continue();
  });
  await grab(page, resizeButton(page), 32);
  await expect(page.getByText("No se ha podido cambiar la cita. Fallo sintético de guardado", { exact: true })).toBeVisible();
  await expect(moveButton(page)).toBeEnabled();
  await expect(moveButton(page)).toContainText("10:00 – 11:00");
  await expect(editor(page)).toBeHidden();
  expect((await rpc<Row>("agenda.get", { identifier: saved.id })).version).toBe(saved.version);
  await page.unroute("**/api");
  await grab(page, resizeButton(page), 32);
  await expect.poll(async () => (await rpc<Row>("agenda.get", { identifier: saved.id })).end).toBe("2026-05-15T09:30:00+00:00");
  await expect(moveButton(page)).toBeEnabled();
  await expect(moveButton(page)).toContainText("10:00 – 11:30");
  await expect(editor(page)).toBeHidden();
});

test("un conflicto de versión conserva la edición externa y recarga la cita vigente", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: base });
  await open(page);
  const external = await rpc<Row>("agenda.save", { data: { ...saved, notes: "Cambio externo que debe conservarse", end_local: "2026-05-15T11:45" } });
  await grab(page, moveButton(page), 64);
  await expect(page.getByText("No se ha podido cambiar la cita. La cita ha cambiado. Vuelve a abrirla.", { exact: true })).toBeVisible();
  await expect(moveButton(page)).toBeEnabled();
  await expect(moveButton(page)).toContainText("10:00 – 11:45");
  await expect(editor(page)).toBeHidden();
  const current = await rpc<Row>("agenda.get", { identifier: saved.id });
  expect(current).toEqual({ ...external, exceptions: [] });
});

test("si falla refrescar tras guardar, reintentar recupera la versión antes de permitir otro cambio", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: base });
  await open(page);
  let savedOnce = false, failRefresh = true;
  await page.route("**/api", async route => {
    const action = route.request().postDataJSON().action;
    if (action === "agenda.save") {
      const response = await route.fetch();
      savedOnce = true;
      await route.fulfill({ response });
    } else if (action === "agenda.list" && savedOnce && failRefresh) {
      await route.fulfill({ json: { ok: false, error: { message: "Fallo sintético al refrescar" } } });
    } else await route.continue();
  });
  await grab(page, moveButton(page), 64);
  await expect(page.locator(".notice.error")).toContainText("Fallo sintético al refrescar");
  expect((await rpc<Row>("agenda.get", { identifier: saved.id })).version).toBe(saved.version + 1);
  await expect(moveButton(page)).toBeDisabled();
  await moveButton(page).evaluate((button: HTMLButtonElement) => button.click());
  await expect(editor(page)).toBeHidden();
  failRefresh = false;
  await page.getByRole("button", { name: "Reintentar carga", exact: true }).click();
  await expect(moveButton(page)).toBeEnabled();
  await expect(moveButton(page)).toContainText("11:00 – 12:00");
  await grab(page, resizeButton(page), 32);
  await expect(moveButton(page)).toBeEnabled();
  const current = await rpc<Row>("agenda.get", { identifier: saved.id });
  expect(current.version).toBe(saved.version + 2);
  expect(current.end).toBe("2026-05-15T10:30:00+00:00");
});

test("arrastrar una repetición cambia sólo esa cita y conserva las otras excepciones", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: { ...base, recurrence: { freq: "weekly", until: "2026-05-29", dst_policy: "skip" } } });
  const range = { start: "2026-05-01T00:00:00Z", end: "2026-06-01T00:00:00Z" };
  const initial = await rpc<Row[]>("agenda.list", range);
  await rpc("agenda.save", { data: { ...initial[0], scope: "occurrence", notes: "Excepción anterior conservada" } });
  await open(page, "2026-05-22");
  await grab(page, moveButton(page), 64);
  await expect(moveButton(page)).toBeEnabled();
  await expect(moveButton(page)).toContainText("11:00 – 12:00");
  await expect(editor(page)).toBeHidden();
  const updated = await rpc<Row[]>("agenda.list", range);
  expect(updated).toHaveLength(3);
  expect(updated[0].notes).toBe("Excepción anterior conservada");
  expect(updated[0].start).toBe(initial[0].start);
  expect(updated[2].start).toBe(initial[2].start);
  expect(updated[1].start).toBe("2026-05-22T09:00:00+00:00");
  expect(updated[1].occurrence_key).toBe(initial[1].occurrence_key);
  // A second drag uses the new master version without resetting other exceptions.
  await grab(page, resizeButton(page), 32);
  await expect(moveButton(page)).toBeEnabled();
  expect((await rpc<Row[]>("agenda.list", range))[1].end).toBe("2026-05-22T10:30:00+00:00");
  const master = await rpc<Row>("agenda.get", { identifier: saved.id });
  expect(master.start).toBe(saved.start);
  expect(master.exceptions).toHaveLength(2);
});

test("arrastrar una cita borrada desde otra ventana no la vuelve a crear", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: base });
  await open(page);
  await rpc("agenda.delete", { identifier: saved.id, version: saved.version });
  await grab(page, moveButton(page), 64);
  await expect(page.locator(".notice.error")).toContainText("No se ha podido cambiar la cita");
  await expect(page.locator(".time-event")).toHaveCount(0);
  await expect(editor(page)).toBeHidden();
  expect(await rpc<Row[]>("agenda.list", { start: "2026-05-15T00:00:00Z", end: "2026-05-16T00:00:00Z" })).toEqual([]);
});

test("cambiar de día durante el guardado no mezcla respuestas ni pierde el cambio", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: base });
  await open(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api", async route => {
    if (route.request().postDataJSON().action === "agenda.save") await held;
    await route.continue();
  });
  try {
    await grab(page, moveButton(page), 64);
    await expect(moveButton(page)).toBeDisabled();
    await page.getByLabel("Ir a una fecha").fill("2026-05-16");
    await expect(page.locator(".time-event")).toHaveCount(0);
  } finally {
    release();
  }
  await expect.poll(async () => (await rpc<Row>("agenda.get", { identifier: saved.id })).version).toBe(saved.version + 1);
  await expect(page.locator(".calendar-loading")).toBeHidden();
  await expect(page.locator(".time-event")).toHaveCount(0);
  await page.getByLabel("Ir a una fecha").fill("2026-05-15");
  await expect(moveButton(page)).toBeEnabled();
  await expect(moveButton(page)).toContainText("11:00 – 12:00");
  await expect(editor(page)).toBeHidden();
});


test("una cita posterior a las 23:45 conserva su hora al moverla horizontalmente", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: { ...base, start_local: "2026-05-15T23:50", end_local: "2026-05-15T23:59" } });
  await open(page);
  await page.getByRole("button", { name: "Semana", exact: true }).click();
  const button = moveButton(page);
  await expect(button).toBeEnabled();
  await button.scrollIntoViewIfNeeded();
  const box = (await button.boundingBox())!;
  const column = (await button.locator("../..").boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 10);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + column.width, box.y + 10, { steps: 6 });
  await page.mouse.up();
  await expect.poll(async () => (await rpc<Row>("agenda.get", { identifier: saved.id })).start).toBe("2026-05-16T21:50:00+00:00");
  await expect(button).toBeEnabled();
  await expect(button).toContainText("23:50 – 23:59");
  await expect(editor(page)).toBeHidden();
});

test("si se sale de Agenda durante un guardado que falla, el error sigue siendo visible", async ({ page, rpc }) => {
  await rpc("settings.save", { section: "appearance", values: { extras: true } });
  const saved = await rpc<Row>("agenda.save", { data: base });
  await open(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api", async route => {
    if (route.request().postDataJSON().action === "agenda.save") {
      await held;
      await route.fulfill({ json: { ok: false, error: { message: "Fallo sintético tras navegar" } } });
    } else await route.continue();
  });
  try {
    await grab(page, moveButton(page), 64);
    await expect(moveButton(page)).toBeDisabled();
    await page.getByRole("button", { name: "Inicio", exact: true }).click();
    await expect(page.locator(".calendar-content")).toHaveCount(0);
  } finally {
    release();
  }
  await expect(page.locator(".toast.error")).toHaveAttribute("role", "alert");
  await expect(page.locator(".toast.error")).toContainText("No se ha podido cambiar la cita. Fallo sintético tras navegar");
  expect((await rpc<Row>("agenda.get", { identifier: saved.id })).version).toBe(saved.version);
});

for (const { date, message } of [
  { date: "2026-03-29", message: "Esa hora no existe en Madrid" },
  { date: "2026-10-25", message: "Esa hora ocurre dos veces en Madrid" },
]) {
  test(`arrastre a una hora de cambio horario exige resolver la hora sin inventarla: ${date}`, async ({ page, rpc }) => {
    await rpc("settings.save", { section: "appearance", values: { extras: true } });
    const saved = await rpc<Row>("agenda.save", { data: { ...base, start_local: date + "T01:00", end_local: date + "T01:30" } });
    await open(page, date);
    await grab(page, moveButton(page), 96);
    await expect(page.locator(".notice.error")).toContainText(message);
    await expect(editor(page)).toBeHidden();
    await expect(moveButton(page)).toContainText("01:00 – 01:30");
    expect((await rpc<Row>("agenda.get", { identifier: saved.id })).version).toBe(saved.version);
  });
}
