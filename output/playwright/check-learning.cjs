async (page) => {
  const checks = [];
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: '知识中心', exact: true }).click();
  await page.getByRole('tab', { name: '历史案例', exact: true }).click();
  await page.getByRole('textbox', { name: '搜索历史案例' }).fill('验收与案例闭环验证');
  await page.getByText('验收与案例闭环验证-1015', { exact: true }).waitFor();
  await page.getByText('验收与案例闭环验证-1015', { exact: true }).click();
  await page.getByText('真实模型服务返回 HTTP 503，保留失败证据；不视为用户需求失败。', { exact: true }).waitFor();
  await page.screenshot({ path: 'output/playwright/case-library-desktop.png', fullPage: true });
  checks.push({ view: 'cases-desktop', ...await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth })) });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'output/playwright/case-library-mobile.png', fullPage: true });
  checks.push({ view: 'cases-mobile', ...await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth })) });
  await page.getByRole('button', { name: 'Session 驾驶舱', exact: true }).click();
  await page.getByRole('heading', { name: '验收与案例闭环验证-1015', exact: true }).waitFor();
  await page.getByRole('region', { name: '执行异常' }).waitFor();
  await page.screenshot({ path: 'output/playwright/cockpit-mobile.png', fullPage: true });
  checks.push({ view: 'cockpit-mobile', ...await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth })) });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: 'output/playwright/cockpit-desktop.png', fullPage: true });
  checks.push({ view: 'cockpit-desktop', ...await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth })) });
  return checks;
}
