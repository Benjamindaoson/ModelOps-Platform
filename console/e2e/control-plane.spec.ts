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

  await page.getByRole("link", { name: "Dataset registry" }).click();
  await page.getByRole("button", { name: "Add dataset" }).click();
  await page.getByLabel("Dataset name").fill("support-dataset");
  await page.getByLabel("Version").fill("1");
  await page.getByLabel("S3 or HF dataset URI").fill("s3://datasets/support/v1/");
  await page.getByLabel("Dataset manifest SHA-256").fill("c".repeat(64));
  await page.getByLabel("Training examples").fill("100");
  await page.getByLabel("Heldout examples (minimum 20)").fill("20");
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByText("support-dataset")).toBeVisible();

  await page.getByRole("link", { name: "Deployments" }).click();
  await page.getByRole("button", { name: "New deployment" }).click();
  await page.getByLabel("Deployment name").fill("qwen-k8s-smoke");
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByRole("alert")).toContainText("Runtime not connected");
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
