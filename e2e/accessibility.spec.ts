import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";

for (const theme of ["light", "dark"]) {
  test(`accesibilidad ${theme}: inicio, formulario, factura y agenda estrecha`, async ({
    page,
    rpc,
  }, info) => {
    await rpc("demo.load");
    await rpc("settings.save", {
      section: "appearance",
      values: { theme, font_size: "large" },
    });
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const audit = async (step: string) => {
      const result = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      await info.attach(step + "-axe.json", {
        body: JSON.stringify(result, null, 2),
        contentType: "application/json",
      });
      await page.screenshot({
        path: info.outputPath(step + ".png"),
        fullPage: true,
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
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
    };
    await audit("inicio");
    await page.getByRole("button", { name: /Nuevo cliente/ }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await audit("cliente");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: /Nueva factura/ }).click();
    await audit("factura");
    await page.getByRole("button", { name: "Más herramientas" }).click();
    await page.getByRole("button", { name: "Agenda", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Agenda");
    await audit("agenda");
  });
}
