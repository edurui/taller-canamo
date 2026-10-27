import { test, expect } from "./fixtures";

test("cabecera visible al desplazar, búsqueda y salto accesibles en cuatro tamaños", async ({
  page,
  rpc,
}, info) => {
  await rpc("customers.save", { data: { name: "Cliente cabecera sintético" } });
  for (const width of [320, 390, 768, 1366]) {
    await page.setViewportSize({ width, height: 700 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Tu taller, a punto.");
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(100);
    const header = page.locator(".topbar");
    const bounds = await header.boundingBox();
    expect(bounds!.y).toBeCloseTo(0, 1);
    expect(bounds!.height).toBe(width <= 760 ? 70 : 80);
    const search = header.getByRole("combobox", {
      name: "Buscar cliente o matrícula",
    });
    await search.fill("Cliente cabecera");
    await expect(page.getByRole("option").first()).toContainText(
      "Cliente cabecera sintético",
    );
    const mobileSearch = page.getByRole("dialog", {
      name: "Buscar cliente o matrícula",
      exact: true,
    });
    if (await mobileSearch.isVisible())
      await mobileSearch.getByRole("combobox").press("Enter");
    else await search.press("Enter");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Cliente cabecera sintético",
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.getByRole("link", { name: "Saltar al contenido" }).focus();
    await expect(
      page.getByRole("link", { name: "Saltar al contenido" }),
    ).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
    const main = await page.locator("#main-content").boundingBox();
    expect(main!.y).toBeGreaterThanOrEqual(bounds!.height);
    await page.evaluate(async () => {
      const finite = document
        .getAnimations()
        .filter(
          (animation) =>
            animation.playState === "running" &&
            Number.isFinite(animation.effect?.getComputedTiming().endTime),
        );
      await Promise.all(
        finite.map((animation) => animation.finished.catch(() => undefined)),
      );
    });
    expect(
      await header.evaluate((element) => {
        const box = element.getBoundingClientRect();
        return element.contains(
          document.elementFromPoint(
            box.x + box.width / 2,
            box.y + box.height / 2,
          ),
        );
      }),
    ).toBe(true);
    await page.screenshot({ path: info.outputPath(`cabecera-${width}.png`) });
  }
});

test("aviso web respeta sonido, reintenta registro sin duplicar y protege el borrador al abrir Agenda", async ({
  page,
  rpc,
}) => {
  await rpc("settings.save", {
    section: "agenda",
    values: { desktop_notifications: true, sound: false },
  });
  const start = new Date(Date.now() - 60_000);
  const event = await rpc<Record<string, unknown>>("agenda.save", {
    data: {
      title: "Aviso sintético de navegación",
      start: start.toISOString(),
      end: new Date(start.getTime() + 3_600_000).toISOString(),
      reminders: [0],
    },
  });
  await page.addInitScript(() => {
    const notices: {
      options: NotificationOptions;
      onclick?: () => void;
      closed: boolean;
    }[] = [];
    class TestNotification {
      static permission = "granted";
      closed = false;
      onclick?: () => void;
      constructor(
        _title: string,
        public options: NotificationOptions,
      ) {
        notices.push(this);
      }
      close() {
        this.closed = true;
      }
    }
    Object.assign(window, {
      Notification: TestNotification,
      testNotices: notices,
    });
  });
  let deliveryAttempts = 0;
  await page.route("**/api", async (route) => {
    const request = route.request().postDataJSON();
    if (
      request.action === "notifications.mark" &&
      request.params.action === "delivered"
    ) {
      deliveryAttempts++;
      expect(Object.keys(request.params.expected_due_at)).toEqual(
        request.params.identifiers,
      );
      expect(
        Object.values(request.params.expected_members).map(
          (members) => (members as unknown[]).length,
        ),
      ).toEqual([deliveryAttempts <= 2 ? 1 : 2]);
      if (deliveryAttempts === 1) {
        await route.fulfill({
          json: {
            ok: false,
            error: { code: "test", message: "Fallo sintético de registro" },
          },
        });
        return;
      }
    }
    await route.continue();
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Avisos: error de actualización" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      (window as any).testNotices.map((n: any) => n.options.silent),
    ),
  ).toEqual([true]);
  // Grow the same group before retrying. The retry may acknowledge only the
  // original notification, even though the latest list contains both members.
  await rpc("agenda.save", { data: { ...event, reminders: [0, 5] } });
  await page
    .getByRole("button", { name: "Avisos: error de actualización" })
    .click();
  const notices = page.getByRole("dialog", { name: "Tus avisos", exact: true });
  await expect(notices).toBeVisible();
  await expect.poll(() => deliveryAttempts).toBe(2);
  await expect(
    page.getByRole("button", { name: "Avisos: 1 pendientes" }),
  ).toBeVisible();
  expect(await page.evaluate(() => (window as any).testNotices.length)).toBe(1);
  const stored =
    await rpc<{ delivered_at: string | null; has_undelivered: boolean }[]>(
      "notifications.list",
    );
  expect(stored[0].delivered_at).toBeTruthy();
  expect(stored[0].has_undelivered).toBe(true);
  await notices.getByRole("button", { name: "Cerrar ventana" }).click();
  await page.getByRole("button", { name: "Avisos: 1 pendientes" }).click();
  await expect.poll(() => deliveryAttempts).toBe(3);
  expect(await page.evaluate(() => (window as any).testNotices.length)).toBe(2);
  expect(
    (await rpc<{ has_undelivered: boolean }[]>("notifications.list"))[0]
      .has_undelivered,
  ).toBe(false);
  await notices.getByRole("button", { name: "Cerrar ventana" }).click();
  await page.keyboard.press("F2");
  await page
    .getByLabel("Concepto 1", { exact: true })
    .fill("Cambio aún sin guardar");
  await expect(
    page.getByText("Cambios sin guardar", { exact: false }).first(),
  ).toBeVisible();
  await page.evaluate(() => (window as any).testNotices[1].onclick());
  const confirm = page.getByRole("dialog", {
    name: "Hay cambios sin guardar",
    exact: true,
  });
  await expect(confirm).toBeVisible();
  await expect(page.getByLabel("Concepto 1", { exact: true })).toHaveValue(
    "Cambio aún sin guardar",
  );
  await confirm
    .getByRole("button", { name: "Salir sin guardar", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Agenda");
  expect(await page.evaluate(() => (window as any).testNotices[1].closed)).toBe(
    true,
  );
});
