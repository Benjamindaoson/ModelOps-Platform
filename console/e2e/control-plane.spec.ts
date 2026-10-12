import { expect, test } from "@playwright/test";

test("authenticates and registers real metadata; refuses disconnected Kubernetes writes", async ({ page }) => {
  const token = process.env.MODELOPS_E2E_TOKEN;
  expect(token).toBeTruthy();

  await page.goto("/dashboard");
  await expect(page.getByText("ModelOps Platform")).toBeVisible();
  await page.getByLabel("OIDC or local development access token").fill(token!);
  await page.getByRole("button", { name: "Connect to workspace" }).click();
  await expect(page.getByRole("heading", { name: "Workspace overview" })).toBeVisible();
  await expect(page.getByText("DISCONNECTED")).toBeVisible();

  await page.getByRole("link", { name: "Model registry" }).click();
  await page.getByRole("button", { name: "Register model" }).click();
  await page.getByLabel("Model name").fill("qwen-smoke-model");
  await page.getByLabel("Version").fill("1");
  await page.getByLabel("HF revision / git SHA").fill("a".repeat(40));
  await page.getByLabel("Hugging Face repository / artifact source").fill("Qwen/Qwen2.5-0.5B-Instruct");
  await page.getByLabel("SHA-256 digest (64 hexadecimal characters)").fill("b".repeat(64));
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("qwen-smoke-model")).toBeVisible();
  await expect(page.getByText("DECLARED", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Datasets" }).click();
  await page.getByRole("button", { name: "Add dataset" }).click();
  await page.getByLabel("Dataset name").fill("support-dataset");
  await page.getByLabel("Version").fill("1");
  await page.getByLabel("S3 or HF dataset URI").fill("s3://datasets/support/v1/");
  await page.getByLabel("Dataset manifest SHA-256").fill("c".repeat(64));
  await page.getByLabel("Training examples").fill("100");
  await page.getByLabel("Heldout examples (minimum 20)").fill("20");
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("support-dataset")).toBeVisible();

  await page.getByRole("link", { name: "Training jobs" }).click();
  await expect(page.getByText("No training jobs.")).toBeVisible();
  await page.getByRole("button", { name: "New training job" }).click();
  // Model/dataset choices arrive from real asynchronous API calls. Do not
  // click submit while the browser has an invalid empty select.
  await expect(page.locator('select[name="artifact_id"]')).not.toHaveValue("");
  await expect(page.locator('select[name="dataset_id"]')).not.toHaveValue("");
  await page.getByLabel("Job name").fill("offline-lora");
  await page.getByLabel("Output model name").fill("offline-adapter");
  await expect.poll(async () =>
    page.locator("form.create-form").evaluate(form => (form as HTMLFormElement).checkValidity())
  ).toBe(true);
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.locator(".message.error[role='alert']")).toContainText("Runtime not connected");
  await page.getByRole("button", { name: "Close form" }).click();
  await expect(page.getByText("No training jobs.")).toBeVisible();

  await page.getByRole("link", { name: "Deployments" }).click();
  await page.getByRole("button", { name: "New deployment" }).click();
  await page.getByLabel("Deployment name").fill("qwen-k8s-smoke");
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.locator(".message.error[role='alert']")).toContainText("Runtime not connected");
  await expect(page.getByText("No deployments have been submitted to Kubernetes.")).toBeVisible();

  await page.getByRole("link", { name: "Audit events" }).click();
  await expect(page.getByText("artifact.register")).toBeVisible();
  await expect(page.getByText("dataset.register")).toBeVisible();
});

test("mobile navigation works without mock data", async ({ page, isMobile }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  const token = process.env.MODELOPS_E2E_TOKEN;
  await page.getByLabel("OIDC or local development access token").fill(token!);
  await page.getByRole("button", { name: "Connect to workspace" }).click();
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "Environment" }).click();
  await expect(page.getByRole("heading", { name: "Environment" })).toBeVisible();
});


test("rejects cross-origin mutations and oversized bodies before reaching the API", async ({ page }) => {
  const token = process.env.MODELOPS_E2E_TOKEN;
  expect(token).toBeTruthy();
  await page.goto("/dashboard");
  await page.context().addCookies([
    { name: "modelops_session", value: token!, domain: "localhost", path: "/" },
  ]);
  const url = "http://localhost:3000/api/control/models";
  const forbidden = await page.request.post(url, {
    headers: { Origin: "https://attacker.example.invalid", "Content-Type": "application/json" },
    data: "{}",
  });
  expect(forbidden.status()).toBe(403);

  const huge = await page.request.post(url, {
    headers: { Origin: "http://localhost:3000", "Content-Type": "application/json" },
    data: JSON.stringify({ arbitrary: "x".repeat(550 * 1024) }),
  });
  expect(huge.status()).toBe(413);
  const allModels = await page.request.get(url);
  expect(allModels.status()).toBe(200); // test is not a destructive write
});
