import AxeBuilder from "@axe-core/playwright";
import { resolve } from "node:path";
import { test, expect } from "./fixtures";
test.use({
  launchOptions: {
    args: [
      "--use-fake-device-for-media-stream",
      "--use-file-for-fake-audio-capture=" +
        resolve("tests/fixtures/assistance/dictado-sintetico.wav"),
    ],
  },
});

test("OCR y voz reales sin red: revisar, aplicar y guardar son pasos separados", async ({
  page,
  rpc,
}) => {
  await rpc("settings.save", {
    section: "assistant",
    values: { enabled: true, model: "" },
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Nuevo cliente/ }).click();
  const form = page.getByRole("dialog", {
    name: "Nuevo cliente",
    exact: true,
    includeHidden: true,
  });
  await form
    .getByRole("textbox", { name: "Nombre o razón social", exact: true })
    .fill("Cliente de asistencia sintético");
  await form
    .getByRole("textbox", { name: "Notas del cliente", exact: true })
    .fill("Observación conservada.");
  await form.getByRole("button", { name: "Dictar notas", exact: true }).click();
  const voice = page.getByRole("dialog", {
    name: "Dictado local",
    exact: true,
  });
  await voice
    .getByLabel("O seleccionar audio WAV")
    .setInputFiles(resolve("tests/fixtures/assistance/dictado-sintetico.wav"));
  await expect(voice.getByLabel("Dictado para revisar")).toHaveValue(
    /cambio de aceite/i,
  );
  expect(
    await page
      .locator('[role="dialog"][aria-label="Nuevo cliente"] textarea')
      .inputValue(),
  ).toBe("Observación conservada.");
  await voice
    .getByLabel("Dictado para revisar")
    .fill("Cambio de aceite y filtro, revisado por la persona.");
  await voice
    .getByRole("button", { name: "Insertar dictado revisado" })
    .click();
  await expect(voice).toBeHidden();
  await expect(
    form.getByRole("textbox", { name: "Notas del cliente", exact: true }),
  ).toHaveValue(
    "Observación conservada.\nCambio de aceite y filtro, revisado por la persona.",
  );
  await form.getByRole("button", { name: "Leer documentación" }).click();
  const ocr = page.getByRole("dialog", {
    name: "Leer imagen y revisar datos",
    exact: true,
  });
  await ocr
    .getByLabel("Imagen del documento")
    .setInputFiles(resolve("tests/fixtures/assistance/ficha-sintetica.png"));
  await expect(ocr.getByLabel("NIF / CIF leído", { exact: true })).toHaveValue(
    "12345678Z",
  );
  await expect(
    ocr.getByRole("button", { name: "Incorporar campos revisados" }),
  ).toBeDisabled();
  expect(
    await page
      .locator('[role="dialog"][aria-label="Nuevo cliente"] input')
      .evaluateAll((inputs) => {
        const input = inputs.find((element) =>
          Array.from((element as HTMLInputElement).labels || []).some((label) =>
            label.textContent?.includes("NIF / CIF"),
          ),
        );
        return (input as HTMLInputElement).value;
      }),
  ).toBe("");
  await ocr.getByLabel("Incorporar nif / cif", { exact: true }).check();
  expect((await rpc<{ total: number }>("customers.list")).total).toBe(0);
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
  await ocr
    .getByRole("button", { name: "Incorporar campos revisados" })
    .click();
  await expect(form.getByRole("textbox", { name: /^NIF \/ CIF/ })).toHaveValue(
    "12345678Z",
  );
  await expect(
    form.getByRole("textbox", { name: "Nombre o razón social", exact: true }),
  ).toHaveValue("Cliente de asistencia sintético");
  await form
    .getByRole("button", { name: "Guardar cliente", exact: true })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Cliente de asistencia sintético",
  );
  expect((await rpc<{ total: number }>("customers.list")).total).toBe(1);
});

test("consulta determinista y mensaje preparado no modifican ni envían la factura", async ({
  page,
  rpc,
}) => {
  await rpc("demo.load");
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Buscar cliente o matrícula",
    exact: true,
  });
  await search.fill("0826lfg");
  await expect(page.getByRole("option").first()).toContainText("Lucia Medina");
  await search.press("Enter");
  await page
    .getByRole("button", { name: "Consultar trabajos del historial" })
    .click();
  await page
    .getByLabel("Palabras que constan en el historial")
    .fill("aceite filtro");
  const match = page
    .locator(".pick-list")
    .getByRole("button", { name: /FAC-/ });
  await expect(match).toHaveCount(1);
  await match.click();
  const number = await page.getByRole("heading", { level: 1 }).innerText();
  await page
    .getByRole("button", { name: "Preparar mensaje", exact: true })
    .click();
  const message = page.getByRole("dialog", { name: "Mensaje para revisar" });
  await expect(message.getByLabel("Texto del mensaje")).toHaveValue(
    new RegExp(number),
  );
  await expect(message.getByText(/El mensaje no se ha enviado/)).toBeVisible();
  await message
    .getByLabel("Texto del mensaje")
    .fill("Borrador sintético editado y descartado.");
  await message.getByRole("button", { name: "Cerrar ventana" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(number);
  // No WhatsApp link is opened and no message is sent during this test.
  const docs = await rpc<{ items: { full_number: string; id: string }[] }>(
    "documents.list",
  );
  const record = docs.items.find((item) => item.full_number === number)!;
  const saved = await rpc<{ payload: { notes: string } }>("documents.get", {
    identifier: record.id,
  });
  expect(saved.payload.notes).not.toContain("Borrador sintético editado");
});

test.describe("captura de micrófono con dispositivo sintético del navegador", () => {
  test("AudioWorklet entrega WAV al motor y cerrar libera el micrófono", async ({
    page,
    rpc,
  }) => {
    await rpc("settings.save", {
      section: "assistant",
      values: { enabled: true, model: "" },
    });
    await page.context().grantPermissions(["microphone"]);
    await page.addInitScript(() => {
      const original = navigator.mediaDevices.getUserMedia.bind(
        navigator.mediaDevices,
      );
      const streams: MediaStream[] = [];
      (
        window as unknown as { testMicrophones: MediaStream[] }
      ).testMicrophones = streams;
      navigator.mediaDevices.getUserMedia = async (constraints) => {
        const stream = await original(constraints);
        streams.push(stream);
        return stream;
      };
    });
    await page.goto("/");
    await page.getByRole("button", { name: /Nuevo cliente/ }).click();
    await page
      .getByRole("button", { name: "Dictar notas", exact: true })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Dictado local",
      exact: true,
    });
    await dialog.getByRole("button", { name: "Iniciar micrófono" }).click();
    await expect(
      dialog.getByRole("button", {
        name: "Terminar dictado (3 s)",
        exact: true,
      }),
    ).toBeVisible();
    await dialog.getByRole("button", { name: /Terminar dictado/ }).click();
    await expect(dialog.getByLabel("Dictado para revisar")).toBeVisible();
    await expect(dialog.getByLabel("Dictado para revisar")).not.toHaveValue("");
    await dialog
      .getByRole("button", { name: "Descartar", exact: true })
      .click();
    await expect(dialog).toBeHidden();
    expect(
      await page.evaluate(() =>
        (
          window as unknown as { testMicrophones: MediaStream[] }
        ).testMicrophones.every((stream) =>
          stream.getTracks().every((track) => track.readyState === "ended"),
        ),
      ),
    ).toBe(true);
    await page
      .getByRole("button", { name: "Dictar notas", exact: true })
      .click();
    await dialog.getByRole("button", { name: "Iniciar micrófono" }).click();
    await expect(
      dialog.getByRole("button", { name: /Terminar dictado/ }),
    ).toBeVisible();
    await dialog.getByRole("button", { name: "Cerrar ventana" }).click();
    expect(
      await page.evaluate(
        () =>
          (window as unknown as { testMicrophones: MediaStream[] })
            .testMicrophones.length === 2 &&
          (
            window as unknown as { testMicrophones: MediaStream[] }
          ).testMicrophones.every((stream) =>
            stream.getTracks().every((track) => track.readyState === "ended"),
          ),
      ),
    ).toBe(true);

    await expect(
      page
        .getByRole("dialog", { name: "Nuevo cliente", exact: true })
        .getByLabel("Notas del cliente"),
    ).toHaveValue("");
  });
});
