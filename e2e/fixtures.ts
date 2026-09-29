import { test as base, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { once } from "node:events";

type Rpc = <T = Record<string, unknown>>(
  action: string,
  params?: Record<string, unknown>,
) => Promise<T>;
type Backend = { url: string; restart: () => Promise<void> };
type Fixtures = { backend: Backend; rpc: Rpc };

// Each test owns a fresh, synthetic SQLite directory. No existing data is opened.
export const test = base.extend<Fixtures>({
  backend: async ({}, use) => {
    const root = await mkdtemp(join(tmpdir(), "canamo-e2e-á "));
    const python = resolve(
      process.platform === "win32"
        ? ".venv/Scripts/python.exe"
        : ".venv/bin/python",
    );
    if (!existsSync(python))
      throw new Error(
        "Crea .venv e instala requirements-dev.lock antes de ejecutar E2E.",
      );
    let child: ChildProcess;
    let url = "";
    let diagnostics = "";
    const start = async (port = "0") => {
      child = spawn(
        python,
        ["scripts/run_preview.py", "--no-open", "--port", port, "--data", root],
        {
          cwd: resolve("."),
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      diagnostics = "";
      child.stderr!.on("data", (chunk: Buffer) => {
        diagnostics += chunk.toString();
      });
      await new Promise<void>((accept, reject) => {
        const timer = setTimeout(() => {
          reject(new Error("No arrancó el backend: " + diagnostics));
        }, 15_000);
        child.once("error", (err) => {
          clearTimeout(timer);
          reject(err);
        });
        child.once("exit", (code) => {
          clearTimeout(timer);
          reject(new Error(`Backend terminó (${code}): ${diagnostics}`));
        });
        let out = "";
        child.stdout!.on("data", (chunk: Buffer) => {
          out += chunk.toString();
          const found = out.match(/http:\/\/127\.0\.0\.1:\d+/);
          if (found) {
            url = found[0];
            clearTimeout(timer);
            accept();
          }
        });
      });
    };
    const stop = async () => {
      if (child && child.exitCode === null && child.signalCode === null) {
        const exited = once(child, "exit");
        child.kill();
        const timer = setTimeout(() => child.kill("SIGKILL"), 5_000);
        try {
          await exited;
        } finally {
          clearTimeout(timer);
        }
      }
    };
    try {
      await start();
      await use({
        get url() {
          return url;
        },
        restart: async () => {
          const port = new URL(url).port;
          await stop();
          await start(port);
        },
      });
    } finally {
      await stop();
      await rm(root, {
        recursive: true,
        force: true,
        maxRetries: 5,
        retryDelay: 200,
      });
    }
  },
  baseURL: async ({ backend }, use) => use(backend.url),
  rpc: async ({ backend, request }, use) => {
    await use(
      async <T>(action: string, params: Record<string, unknown> = {}) => {
        const runtime = await (
          await request.get(backend.url + "/runtime.js")
        ).text();
        const token = JSON.parse(
          runtime.slice(runtime.indexOf("=") + 1, runtime.lastIndexOf(";")),
        ) as string;
        const response = await request.post(backend.url + "/api", {
          headers: { "X-Canamo-Token": token },
          data: { action, params },
        });
        expect(response.ok()).toBe(true);
        const answer = (await response.json()) as {
          ok: boolean;
          result: T;
          error?: { message: string };
        };
        expect(answer.ok, answer.error?.message).toBe(true);
        return answer.result;
      },
    );
  },
});

export { expect };

// Exercise the visible picker, including options portalled outside a parent dialog.
export async function chooseOption(
  control: import("@playwright/test").Locator,
  option: string | { label: string },
) {
  const page = control.page();
  control = control.and(page.getByRole("combobox"));
  if ((await control.getAttribute("aria-expanded")) !== "true")
    await control.click();
  await expect(control).toHaveAttribute("aria-expanded", "true");
  const listId = await control.getAttribute("aria-controls");
  expect(listId).toBeTruthy();
  // A previous picker may still be animating out. Use this control's active list.
  const list = page.getByRole("listbox").and(
    page.locator("[id=" + JSON.stringify(listId) + "]"),
  );
  const target =
    typeof option === "string"
      ? list.getByRole("option").and(
          page.locator("[data-value=" + JSON.stringify(option) + "]"),
        )
      : list.getByRole("option", { name: option.label, exact: true });
  await target.click();
  await expect(control).toHaveAttribute("aria-expanded", "false");
}
