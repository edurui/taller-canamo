import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";
import { test, expect } from "./fixtures";

type Rpc = <T = Record<string, unknown>>(
  action: string,
  params?: Record<string, unknown>,
) => Promise<T>;
type FontSize = "normal" | "large" | "extra";

async function settle(page: Page) {
  await page.evaluate(async () => {
    while (true) {
      const animations = document
        .getAnimations()
        .filter(
          (animation) =>
            animation.playState === "running" &&
            Number.isFinite(animation.effect?.getComputedTiming().endTime),
        );
      if (!animations.length) return;
      await Promise.all(
        animations.map((animation) =>
          animation.finished.catch(() => undefined),
        ),
      );
    }
  });
}

async function open(
  page: Page,
  rpc: Rpc,
  {
    width = 1366,
    height = 900,
    font = "normal",
    theme = "light",
  }: {
    width?: number;
    height?: number;
    font?: FontSize;
    theme?: "light" | "dark";
  } = {},
) {
  await rpc("settings.save", {
    section: "appearance",
    values: { theme, font_size: font, extras: true },
  });
  await page.setViewportSize({ width, height });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-font", font);
  const menu = page.getByRole("button", { name: "Abrir menú", exact: true });
  if (await menu.isVisible()) await menu.click();
  await settle(page);
}

const toggle = (page: Page) =>
  page.getByRole("button", { name: "Más herramientas", exact: true });
async function panel(page: Page) {
  const identifier = await toggle(page).getAttribute("aria-controls");
  expect(identifier).toBeTruthy();
  const controlled = page.locator("[id=" + JSON.stringify(identifier) + "]");
  await expect(controlled).toHaveCount(1);
  return controlled;
}

async function expand(page: Page) {
  await toggle(page).click();
  await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
  await settle(page);
}

async function geometry(page: Page) {
  return page.evaluate(() => {
    const box = (element: Element) => {
      const bounds = element.getBoundingClientRect();
      return {
        top: bounds.top,
        bottom: bounds.bottom,
        left: bounds.left,
        right: bounds.right,
        width: bounds.width,
        height: bounds.height,
      };
    };
    const sidebar = document.querySelector<HTMLElement>(".sidebar")!;
    const navigation = document.querySelector<HTMLElement>(
      ".sidebar-navigation",
    )!;
    return {
      viewport: { width: innerWidth, height: innerHeight },
      font: parseFloat(getComputedStyle(document.documentElement).fontSize),
      sidebar: {
        ...box(sidebar),
        clientHeight: sidebar.clientHeight,
        scrollHeight: sidebar.scrollHeight,
        scrollTop: sidebar.scrollTop,
        overflow: getComputedStyle(sidebar).overflowY,
      },
      navigation: {
        ...box(navigation),
        clientHeight: navigation.clientHeight,
        scrollHeight: navigation.scrollHeight,
        clientWidth: navigation.clientWidth,
        scrollWidth: navigation.scrollWidth,
        scrollTop: navigation.scrollTop,
        overflow: getComputedStyle(navigation).overflowY,
      },
      brand: box(document.querySelector(".sidebar .brand")!),
      footer: box(document.querySelector(".sidebar-bottom")!),
      pageScroll: scrollY,
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
    };
  });
}

function expectContained(measure: Awaited<ReturnType<typeof geometry>>) {
  expect(measure.horizontalOverflow).toBe(false);
  expect(measure.sidebar.top).toBeGreaterThanOrEqual(0);
  expect(measure.sidebar.bottom).toBeLessThanOrEqual(
    measure.viewport.height + 1,
  );
  expect(measure.sidebar.scrollHeight).toBeLessThanOrEqual(
    measure.sidebar.clientHeight + 1,
  );
  expect(measure.sidebar.scrollTop).toBe(0);
  expect(measure.sidebar.overflow).toBe("hidden");
  expect(measure.brand.top).toBeGreaterThanOrEqual(0);
  expect(measure.brand.bottom).toBeLessThanOrEqual(measure.navigation.top + 1);
  expect(measure.navigation.height).toBeGreaterThan(0);
  expect(measure.navigation.bottom).toBeLessThanOrEqual(measure.footer.top + 1);
  expect(measure.navigation.scrollWidth).toBeLessThanOrEqual(
    measure.navigation.clientWidth + 1,
  );
  expect(measure.footer.bottom).toBeLessThanOrEqual(
    measure.viewport.height + 1,
  );
}

async function audit(page: Page, info: TestInfo, name: string) {
  await settle(page);
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  await info.attach(name + "-axe.json", {
    body: JSON.stringify(result.violations),
    contentType: "application/json",
  });
  expect(result.violations, JSON.stringify(result.violations)).toEqual([]);
  await page.screenshot({
    path: info.outputPath(name + ".png"),
    fullPage: false,
  });
}

// Capture real rendered frames; no injected animation or artificial delay can
// turn an instantaneous unmount into a passing disclosure transition.
async function transitionFrames(page: Page) {
  return page.evaluate(async () => {
    const button = document.querySelector<HTMLButtonElement>(".extras-toggle")!;
    const disclosure =
      document.querySelector<HTMLElement>(".extras-disclosure")!;
    const frames: { height: number; running: boolean }[] = [];
    const sample = () => {
      const height = disclosure.getBoundingClientRect().height;
      const running = disclosure
        .getAnimations({ subtree: true })
        .some((animation) => animation.playState === "running");
      frames.push({ height, running });
      return running;
    };
    sample();
    button.click();
    const deadline = performance.now() + 2000;
    while (performance.now() < deadline) {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
      const running = sample();
      if (frames.length >= 3 && !running) break;
    }
    return frames;
  });
}

test("Más herramientas anima apertura y cierre y conserva el último estado al invertir rápidamente", async ({
  page,
  rpc,
}, info) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await open(page, rpc);
  const controlled = await panel(page);
  await expect(toggle(page)).toHaveAttribute("aria-expanded", "false");
  const closed = await geometry(page);
  const opening = await transitionFrames(page);
  await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
  await expect(controlled).toBeVisible();
  const full = opening.at(-1)!.height;
  expect(full).toBeGreaterThan(250);
  expect(opening[0].height).toBeLessThan(1);
  expect(
    opening.some(
      (frame) => frame.running && frame.height > 1 && frame.height < full - 1,
    ),
  ).toBe(true);
  const closing = await transitionFrames(page);
  expect(closing.at(-1)!.height).toBeLessThan(1);
  expect(
    closing.some(
      (frame) => frame.running && frame.height > 1 && frame.height < full - 1,
    ),
  ).toBe(true);
  await expect(toggle(page)).toHaveAttribute("aria-expanded", "false");
  await page.evaluate(async () => {
    const button = document.querySelector<HTMLButtonElement>(".extras-toggle")!;
    for (let index = 0; index < 5; index++) {
      button.click();
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      );
    }
  });
  await settle(page);
  await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
  await expect(controlled.getByRole("button")).toHaveCount(7);
  const after = await geometry(page);
  expectContained(after);
  expect(after.brand).toEqual(closed.brand);
  expect(after.footer).toEqual(closed.footer);
  await info.attach("transicion-real.json", {
    body: JSON.stringify({ opening, closing, after }),
    contentType: "application/json",
  });
});

test("las herramientas cerradas quedan fuera del foco y el teclado permite abrirlas y navegar", async ({
  page,
  rpc,
}) => {
  await open(page, rpc);
  const controlled = await panel(page);
  const disclosure = page.locator(".extras-disclosure");
  await expect(disclosure).toHaveAttribute("aria-hidden", "true");
  expect(
    await disclosure.evaluate((element) => (element as HTMLElement).inert),
  ).toBe(true);
  expect(await controlled.locator("button").count()).toBe(7);
  await toggle(page).focus();
  await page.keyboard.press("Tab");
  await expect(
    page
      .locator(".sidebar-bottom")
      .getByRole("button", { name: "Configuración", exact: true }),
  ).toBeFocused();
  for (const option of await controlled.locator("button").all()) {
    expect(
      await option.evaluate((element) => {
        (element as HTMLElement).focus();
        return document.activeElement === element;
      }),
    ).toBe(false);
  }
  await toggle(page).focus();
  await page.keyboard.press("Enter");
  await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
  await settle(page);
  expect(
    await disclosure.evaluate((element) => (element as HTMLElement).inert),
  ).toBe(false);
  await page.keyboard.press("Tab");
  await expect(
    controlled.getByRole("button", { name: "Agenda", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Space");
  await expect(toggle(page)).toHaveAttribute("aria-expanded", "false");
  await page.keyboard.press("Tab");
  await expect(
    page
      .locator(".sidebar-bottom")
      .getByRole("button", { name: "Configuración", exact: true }),
  ).toBeFocused();
  await toggle(page).focus();
  await page.keyboard.press("Space");
  await settle(page);
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Agenda");
});

for (const theme of ["light", "dark"] as const) {
  test(`el lateral ${theme} conserva logo y pie a 900/768 px con letra normal y grande`, async ({
    page,
    rpc,
  }, info) => {
    const measurements = [];
    for (const height of [900, 768]) {
      for (const font of ["normal", "large"] as const) {
        await open(page, rpc, { height, font, theme });
        const before = await geometry(page);
        await expand(page);
        const after = await geometry(page);
        await info.attach(`geometria-${height}-${font}.json`, {
          body: JSON.stringify(after),
          contentType: "application/json",
        });
        expectContained(after);
        expect(after.font).toBe(font === "normal" ? 16 : 18);
        expect(after.brand).toEqual(before.brand);
        expect(after.footer).toEqual(before.footer);
        expect(after.navigation.scrollHeight).toBeLessThanOrEqual(
          after.navigation.clientHeight + 1,
        );
        const last = page.locator(".sidebar-navigation").getByRole("button", {
          name: "Resumen",
          exact: true,
        });
        await expect(last).toBeInViewport({ ratio: 1 });
        const bounds = await last.boundingBox();
        expect(bounds).not.toBeNull();
        expect(bounds!.y).toBeGreaterThanOrEqual(after.navigation.top);
        expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(
          after.navigation.bottom,
        );
        measurements.push({ height, fontSetting: font, ...after });
        await audit(page, info, `sidebar-${theme}-${height}-${font}`);
      }
    }
    await info.attach("geometria.json", {
      body: JSON.stringify(measurements),
      contentType: "application/json",
    });
  });
}

test("en ventanas bajas con letra muy grande sólo se desplaza la navegación y todas sus opciones son alcanzables", async ({
  page,
  rpc,
}, info) => {
  for (const [width, height] of [
    [1366, 500],
    [1000, 380],
  ]) {
    await open(page, rpc, { width, height, font: "extra" });
    await expand(page);
    const before = await geometry(page);
    expectContained(before);
    expect(before.font).toBe(20);
    expect(before.navigation.scrollHeight).toBeGreaterThan(
      before.navigation.clientHeight,
    );
    expect(["auto", "scroll"]).toContain(before.navigation.overflow);
    const sidebar = page.locator(".sidebar");
    await sidebar.getByRole("button", { name: "Inicio", exact: true }).focus();
    for (const [index, name] of [
      "Inicio",
      "Clientes",
      "Facturas",
      "Más herramientas",
      "Agenda",
      "Vehículos",
      "Presupuestos",
      "Órdenes de trabajo",
      "Artículos y stock",
      "Proveedores",
      "Resumen",
      "Configuración",
    ].entries()) {
      if (index) await page.keyboard.press("Tab");
      const option = sidebar.getByRole("button", { name, exact: true });
      await expect(option).toBeFocused();
      const bounds = await option.boundingBox();
      const measure = await geometry(page);
      expectContained(measure);
      expect(measure.brand).toEqual(before.brand);
      expect(measure.footer).toEqual(before.footer);
      expect(measure.pageScroll).toBe(before.pageScroll);
      expect(bounds).not.toBeNull();
      const region =
        name === "Configuración" ? measure.footer : measure.navigation;
      expect(bounds!.y).toBeGreaterThanOrEqual(region.top - 1);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(region.bottom + 1);
      expect(
        await option.evaluate((element) => {
          const bounds = element.getBoundingClientRect();
          return element.contains(
            document.elementFromPoint(
              bounds.x + bounds.width / 2,
              bounds.y + bounds.height / 2,
            ),
          );
        }),
      ).toBe(true);
    }
    const after = await geometry(page);
    expect(after.navigation.scrollTop).toBeGreaterThan(0);
    await audit(page, info, `sidebar-bajo-${width}-${height}`);
  }
});

for (const [width, height] of [
  [390, 844],
  [320, 640],
]) {
  test(`menú móvil ${width}×${height}: cierre por fondo, Escape y navegación sin foco oculto`, async ({
    page,
    rpc,
  }, info) => {
    await open(page, rpc, { width, height });
    const menu = page.getByRole("button", { name: "Abrir menú", exact: true });
    const sidebar = page.locator(".sidebar");
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    const identifier = await menu.getAttribute("aria-controls");
    expect(identifier).toBeTruthy();
    await expect(sidebar).toHaveAttribute("id", identifier!);
    await expand(page);
    expectContained(await geometry(page));
    await audit(page, info, `sidebar-movil-${width}-${height}`);
    await page
      .locator(".sidebar-scrim")
      .click({ position: { x: width - 5, y: 30 } });
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await expect(sidebar).toBeHidden();
    await menu.focus();
    for (let index = 0; index < 5; index++) {
      await page.keyboard.press("Tab");
      expect(
        await page.evaluate(() =>
          Boolean(document.activeElement?.closest(".sidebar")),
        ),
      ).toBe(false);
    }
    await menu.click();
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    await settle(page);
    await page.keyboard.press("Escape");
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await expect(sidebar).toBeHidden();
    await expect(menu).toBeFocused();
    await menu.press("Enter");
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    await sidebar
      .getByRole("button", { name: "Clientes", exact: true })
      .click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Clientes",
    );
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await expect(sidebar).toBeHidden();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}

test("movimiento reducido conserva apertura, cierre y accesibilidad sin animación del desplegable", async ({
  page,
  rpc,
}, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page, rpc);
  const controlled = await panel(page);
  await toggle(page).click();
  await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
  await expect(controlled.getByRole("button")).toHaveCount(7);
  const durations = await page
    .locator(".extras-disclosure")
    .evaluate((element) => {
      const duration = getComputedStyle(element)
        .transitionDuration.split(",")
        .map((value) => parseFloat(value));
      const active = element
        .getAnimations({ subtree: true })
        .filter((animation) => animation.playState === "running").length;
      return {
        duration,
        active,
        height: element.getBoundingClientRect().height,
      };
    });
  expect(durations.duration.every((duration) => duration <= 0.001)).toBe(true);
  expect(durations.active).toBe(0);
  expect(durations.height).toBeGreaterThan(250);
  await audit(page, info, "sidebar-reduced-motion");
  await toggle(page).click();
  await expect(toggle(page)).toHaveAttribute("aria-expanded", "false");
  expect(
    await page
      .locator(".extras-disclosure")
      .evaluate((element) => (element as HTMLElement).inert),
  ).toBe(true);
  expect(
    await page
      .locator(".extras-disclosure")
      .evaluate((element) => element.getBoundingClientRect().height),
  ).toBeLessThan(1);
});
