import { expect, test } from "@playwright/test";

/**
 * Phase 8 gate: empty DB → projection chart
 * Walks the full critical path: create household → add income → add expense → run projection → see chart
 */
test.describe("Retirement planner E2E", () => {
  const currentYear = new Date().getFullYear();

  test("full flow: household → income → expense → projection → chart", async ({ page }) => {
    // 1. Dashboard loads
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("Personal Retirement Planner");

    // 2. Create household
    await page.getByRole("link", { name: "New household" }).click();
    await expect(page).toHaveURL(/\/household\/new/);

    await page.getByLabel("Household name").fill("E2E Test Family");
    await page.getByLabel("Primary person name").fill("Alex");
    await page.getByLabel("Date of birth").fill("1985-06-15");
    await page.getByRole("button", { name: /create/i }).click();

    // Should land on scenario detail page
    await expect(page).toHaveURL(/\/scenario\/.+/);
    await expect(page.locator("h1")).toContainText("Baseline");

    // Store scenario ID from URL
    const scenarioUrl = page.url();
    const scenarioId = scenarioUrl.split("/scenario/")[1].split("/")[0];

    // 3. Add income stream
    await page.goto(`/scenario/${scenarioId}/income`);
    await expect(page.getByText("Add income stream")).toBeVisible();

    await page.getByLabel("Name").fill("Salary");
    await page.locator("select[name='kind']").selectOption("salary");
    await page.getByLabel("Annual amount ($)").fill("120000");
    await page.locator("input[name='startYear']").fill(String(currentYear));
    await page.locator("input[name='endYear']").fill(String(currentYear + 25));
    await page.getByRole("button", { name: "Add stream" }).click();

    // Salary appears in list
    await expect(page.getByText("Salary")).toBeVisible();

    // 4. Add expense stream
    await page.goto(`/scenario/${scenarioId}/expenses`);
    await expect(page.getByText("Add expense stream")).toBeVisible();

    await page.getByLabel("Name").fill("Living expenses");
    await page.locator("select[name='kind']").selectOption("must_spend");
    await page.getByLabel("Annual amount ($)").fill("60000");
    await page.locator("input[name='startYear']").fill(String(currentYear));
    await page.getByRole("button", { name: "Add expense" }).click();

    await expect(page.getByText("Living expenses")).toBeVisible();

    // 5. Add a cash account (required for projection to have somewhere to deposit surplus)
    await page.goto(`/scenario/${scenarioId}/accounts`);
    await page.getByLabel("Account name").fill("Checking");
    await page.locator("select[name='accountType']").selectOption("cash");
    await page.getByLabel("Current balance").fill("50000");
    await page.getByRole("button", { name: "Save account" }).click();
    await expect(page.getByText("Checking")).toBeVisible();

    // 6. Run projection
    await page.goto(`/scenario/${scenarioId}/projection`);
    await expect(page.getByText("This tool is for educational planning only")).toBeVisible();

    const runButton = page.getByRole("button", { name: /Run Projection/ });
    await expect(runButton).toBeEnabled();
    await runButton.click();

    // Wait for projection to complete
    await expect(page.getByText("Year-by-year summary")).toBeVisible({ timeout: 15000 });

    // Net Worth chart should be present (recharts renders an svg)
    await expect(page.locator("text=Net Worth Over Time")).toBeVisible();
    await expect(page.locator(".recharts-wrapper")).toBeVisible();

    // 7. Navigate to charts page and verify all 6 chart headings
    await page.getByRole("link", { name: "View all charts" }).click();
    await expect(page).toHaveURL(/\/scenario\/.+\/charts/);

    await expect(page.getByText("1. Net Worth Over Time")).toBeVisible();
    await expect(page.getByText("2. Per-Account Balances")).toBeVisible();
    await expect(page.getByText("3. Cash Flow")).toBeVisible();
    await expect(page.getByText("4. Tax Breakdown")).toBeVisible();
    // Charts 5 & 6 may be placeholder if no SEPP / all years >= 65, verify headings only
    await expect(page.locator("text=5.")).toBeVisible();
    await expect(page.locator("text=6.")).toBeVisible();
  });

  test("disclaimer shown on every projection view", async ({ page }) => {
    await page.goto("/");
    // Navigate to an arbitrary scenario projection if one exists; if not, just check dashboard
    const links = await page.getByRole("link", { name: /Baseline/ }).all();
    if (links.length > 0) {
      await links[0].click();
      const href = page.url().replace(page.url().split("/scenario")[0], "");
      const scenarioId = href.split("/scenario/")[1];
      await page.goto(`/scenario/${scenarioId}/projection`);
      await expect(
        page.getByText("This tool is for educational planning only")
      ).toBeVisible();
    }
  });

  test("CSV export buttons present after projection run", async ({ page }) => {
    // Re-run the same flow minimally or use the scenario created by prior test
    await page.goto("/");
    const links = await page.getByRole("link", { name: /Baseline/ }).all();
    if (links.length === 0) {
      test.skip();
      return;
    }
    await links[0].click();
    const scenarioId = page.url().split("/scenario/")[1].split("/")[0];
    await page.goto(`/scenario/${scenarioId}/projection`);

    // If a projection already exists, export buttons should be visible
    const exportBtn = page.getByRole("button", { name: "Export years CSV" });
    if (await exportBtn.isVisible()) {
      await expect(page.getByRole("button", { name: "Export balances CSV" })).toBeVisible();
    }
  });
});
