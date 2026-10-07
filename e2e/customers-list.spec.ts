import AxeBuilder from "@axe-core/playwright";
import type { Page, TestInfo } from "@playwright/test";
import { test, expect } from "./fixtures";

type ListParams = { query: string; page: number; archived: boolean };

function signal() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

// Delay only a synthetic response, after the real backend has answered it.
// One-use routes permit repeated filters (A → B → A) to have distinct gates.
async function holdList(
  page: Page,
  match: (params: ListParams) => boolean,
  error?: string,
) {
  const ready = signal(),
    release = signal(),
    delivered = signal();
  let claimed = false;
  await page.route("**/api", async (route) => {
    const body = route.request().postDataJSON();
    if (claimed || body.action !== "customers.list" || !match(body.params)) {
      await route.fallback();
      return;
    }
    claimed = true;
    const response = await route.fetch();
    ready.resolve();
    await release.promise;
    if (error)
      await route.fulfill({
        response,
        json: { ok: false, error: { code: "test_failure", message: error } },
      });
    else await route.fulfill({ response });
    delivered.resolve();
  });
  return {
    ready: ready.promise,
    release: release.resolve,
    async finish() {
      release.resolve();
      await delivered.promise;
      // Let fetch and React process a deliberately obsolete response before
      // asserting that it did not replace the latest data or expose an error.
      await page.evaluate(
        () =>
          new Promise<void>((resolve) => {
            requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
          }),
      );
    },
  };
}

async function openCustomers(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const menu = page.getByRole("button", { name: "Abrir menú", exact: true });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("button", { name: "Clientes", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Clientes");
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

test("Clientes conserva la tabla y descarta respuestas invertidas, incluso al volver al mismo filtro", async ({
  page,
  rpc,
}) => {
  await rpc("customers.save", {
    data: { name: "Alfa sintética", phone: "600000001" },
  });
  await rpc("customers.save", {
    data: { name: "Beta sintética", phone: "600000002" },
  });
  await openCustomers(page);
  const region = page.getByRole("region", { name: "Listado de clientes" });
  const filter = page.getByRole("textbox", { name: "Filtrar clientes" });
  await expect(region.getByRole("table")).toBeVisible();
  await expect(region.locator("tbody tr")).toHaveCount(2);
  await region.getByRole("table").evaluate((table) => {
    table.setAttribute("data-retained", "yes");
  });

  const alfa = await holdList(page, (params) => params.query === "Alfa");
  const beta = await holdList(page, (params) => params.query === "Beta");
  try {
    await filter.fill("Alfa");
    await alfa.ready;
    await expect(region).toHaveAttribute("aria-busy", "true");
    await expect(region.getByRole("table")).toHaveAccessibleName(
      "Resultados anteriores de clientes",
    );
    await expect(region.locator("tbody tr")).toHaveCount(2);
    await expect(
      region.getByRole("button", { name: /Alfa sintética/ }),
    ).toBeDisabled();
    await expect(
      region.getByRole("button", { name: /Beta sintética/ }),
    ).toBeDisabled();
    await expect(
      page.getByText("Anteriores: 2", { exact: true }),
    ).toBeVisible();
    await expect(region.locator(".loading")).toHaveCount(0);
    // Both the row itself and its keyboard control must reject obsolete matches.
    await region.getByRole("cell", { name: "600000001", exact: true }).click();
    await filter.press("Tab");
    await expect(
      page.getByRole("checkbox", { name: "Archivados" }),
    ).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(region.locator("button:focus")).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Clientes",
    );

    await filter.fill("Beta");
    await beta.ready;
    await beta.finish();
    await expect(region).toHaveAttribute("aria-busy", "false");
    await expect(region.locator("tbody tr")).toHaveCount(1);
    await expect(
      region.getByRole("button", { name: /Beta sintética/ }),
    ).toBeEnabled();
    await alfa.finish();
    await expect(region.locator("tbody tr")).toHaveCount(1);
    await expect(region).toContainText("Beta sintética");
    await expect(region).not.toContainText("Alfa sintética");
    await expect(region.getByRole("table")).toHaveAttribute(
      "data-retained",
      "yes",
    );

    const oldClear = await holdList(
      page,
      (params) => params.query === "",
      "Fallo obsoleto sintético",
    );
    const sameBeta = await holdList(page, (params) => params.query === "Beta");
    try {
      await filter.fill("");
      await oldClear.ready;
      await filter.fill("Beta");
      await sameBeta.ready;
      await expect(region).toHaveAttribute("aria-busy", "true");
      await expect(
        region.getByRole("button", { name: /Beta sintética/ }),
      ).toBeDisabled();
      await sameBeta.finish();
      await oldClear.finish();
      await expect(region).toHaveAttribute("aria-busy", "false");
      await expect(page.getByRole("alert")).toHaveCount(0);
      await expect(
        region.getByRole("button", { name: /Beta sintética/ }),
      ).toBeEnabled();
      await expect(region.locator("tbody tr")).toHaveCount(1);
      await region.getByRole("button", { name: /Beta sintética/ }).click();
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        "Beta sintética",
      );
    } finally {
      oldClear.release();
      sameBeta.release();
    }
  } finally {
    alfa.release();
    beta.release();
  }
});

test("Clientes conserva el rango previo al paginar y reinicia la página al filtrar o ver archivados", async ({
  page,
  rpc,
}) => {
  for (let index = 1; index <= 51; index++)
    await rpc("customers.save", {
      data: { name: `Cliente sintético ${String(index).padStart(3, "0")}` },
    });
  const archived = await rpc<{ id: string }>("customers.save", {
    data: { name: "Archivo sintético" },
  });
  await rpc("customers.archive", { identifier: archived.id });
  await openCustomers(page);
  const region = page.getByRole("region", { name: "Listado de clientes" });
  const filter = page.getByRole("textbox", { name: "Filtrar clientes" });
  await expect(region.locator("tbody tr")).toHaveCount(50);
  const next = await holdList(page, (params) => params.page === 1);
  try {
    await region.getByRole("button", { name: "Siguiente" }).click();
    await next.ready;
    await expect(region.locator(".pager")).toContainText(
      "Consulta anterior: 1–50 de 51",
    );
    await expect(
      region.getByRole("button", { name: "Siguiente" }),
    ).toBeDisabled();
    await expect(
      region.getByRole("button", { name: "Anterior" }),
    ).toBeDisabled();
    await next.finish();
    await expect(region.locator("tbody tr")).toHaveCount(1);
    await expect(region).toContainText("Cliente sintético 051");
    await expect(region.locator(".pager")).toContainText("51–51 de 51");
  } finally {
    next.release();
  }

  const filtered = await holdList(
    page,
    (params) => params.query === "001" && params.page === 0,
  );
  try {
    await filter.fill("001");
    await filtered.ready;
    await expect(region.locator(".pager")).toContainText(
      "Consulta anterior: 51–51 de 51",
    );
    await filtered.finish();
    await expect(region).toContainText("Cliente sintético 001");
    await expect(region.locator("tbody tr")).toHaveCount(1);
    await expect(region.locator(".pager")).toHaveCount(0);
  } finally {
    filtered.release();
  }
  await filter.fill("");
  await expect(region.locator("tbody tr")).toHaveCount(50);
  await region.getByRole("button", { name: "Siguiente" }).click();
  await expect(region).toContainText("Cliente sintético 051");

  const archive = await holdList(
    page,
    (params) => params.archived && params.page === 0,
  );
  try {
    await page.getByRole("checkbox", { name: "Archivados" }).check();
    await archive.ready;
    await expect(region).toHaveAttribute("aria-busy", "true");
    await expect(region.locator(".pager")).toContainText(
      "Consulta anterior: 51–51 de 51",
    );
    await archive.finish();
    await expect(region).toContainText("Archivo sintético");
    await expect(region.locator("tbody tr")).toHaveCount(1);
    await expect(region.locator(".pager")).toHaveCount(0);
  } finally {
    archive.release();
  }
});

test("Clientes muestra fallos iniciales y de recarga, y reintenta sin habilitar datos antiguos", async ({
  page,
  rpc,
}) => {
  await rpc("customers.save", { data: { name: "Reintento sintético" } });
  const initial = await holdList(page, () => true, "Fallo inicial sintético");
  await openCustomers(page);
  const region = page.getByRole("region", { name: "Listado de clientes" });
  try {
    await initial.ready;
    await expect(region).toHaveAttribute("aria-busy", "true");
    await expect(region.locator(".loading")).toBeVisible();
    await initial.finish();
    await expect(page.getByRole("alert")).toContainText(
      "Fallo inicial sintético",
    );
    await expect(region).toHaveAttribute("aria-busy", "false");
    await expect(
      page.getByText("Tu agenda de clientes, a mano", { exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Reintentar", exact: true }).click();
    await expect(
      region.getByRole("button", { name: /Reintento sintético/ }),
    ).toBeEnabled();
  } finally {
    initial.release();
  }

  const failure = await holdList(
    page,
    (params) => params.query === "Reintento",
    "Fallo de recarga sintético",
  );
  try {
    await page
      .getByRole("textbox", { name: "Filtrar clientes" })
      .fill("Reintento");
    await failure.ready;
    await failure.finish();
    await expect(page.getByRole("alert")).toContainText(
      "Fallo de recarga sintético",
    );
    await expect(
      region.getByRole("button", { name: /Reintento sintético/ }),
    ).toBeDisabled();
    await expect(
      page.getByText("Anteriores: 1", { exact: true }),
    ).toBeVisible();
    await expect(region).toHaveAttribute("aria-busy", "false");
    const retry = await holdList(
      page,
      (params) => params.query === "Reintento",
    );
    try {
      await page
        .getByRole("button", { name: "Reintentar", exact: true })
        .click();
      await retry.ready;
      await expect(page.getByRole("alert")).toHaveCount(0);
      await expect(region).toHaveAttribute("aria-busy", "true");
      await expect(
        region.getByRole("button", { name: /Reintento sintético/ }),
      ).toBeDisabled();
      await retry.finish();
      await expect(
        region.getByRole("button", { name: /Reintento sintético/ }),
      ).toBeEnabled();
      await expect(region).toHaveAttribute("aria-busy", "false");
    } finally {
      retry.release();
    }
  } finally {
    failure.release();
  }
});

for (const [theme, width] of [
  ["light", 1024],
  ["dark", 320],
] as const) {
  test(`Clientes accesible con tabla conservada: ${theme}, ${width}px y letra grande`, async ({
    page,
    rpc,
  }, info) => {
    await rpc("settings.save", {
      section: "appearance",
      values: { theme, font_size: "large" },
    });
    await rpc("customers.save", {
      data: { name: "Cliente visual sintético", phone: "600000003" },
    });
    await page.setViewportSize({ width, height: 768 });
    await openCustomers(page);
    const region = page.getByRole("region", { name: "Listado de clientes" });
    await expect(
      region.getByRole("button", { name: /Cliente visual sintético/ }),
    ).toBeEnabled();
    await audit(page, info, "clientes-" + theme);
    const tableBefore = await region.getByRole("table").boundingBox();
    const filterBefore = await page
      .getByRole("textbox", { name: "Filtrar clientes" })
      .boundingBox();
    const pending = await holdList(page, (params) => params.query === "visual");
    try {
      await page
        .getByRole("textbox", { name: "Filtrar clientes" })
        .fill("visual");
      await pending.ready;
      await expect(region).toHaveAttribute("aria-busy", "true");
      const tablePending = await region.getByRole("table").boundingBox();
      const filterPending = await page
        .getByRole("textbox", { name: "Filtrar clientes" })
        .boundingBox();
      expect(Math.abs(tablePending!.y - tableBefore!.y)).toBeLessThan(0.5);
      expect(Math.abs(filterPending!.width - filterBefore!.width)).toBeLessThan(
        0.5,
      );
      await audit(page, info, "clientes-pendientes-" + theme);
      await pending.finish();
      await expect(
        region.getByRole("button", { name: /Cliente visual sintético/ }),
      ).toBeEnabled();
    } finally {
      pending.release();
    }
  });
}
