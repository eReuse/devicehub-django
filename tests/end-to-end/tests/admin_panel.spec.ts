import { test, expect } from '@playwright/test';

const TEST_SITE = process.env.TEST_SITE || 'http://127.0.0.1:8001'
const TEST_USER = process.env.TEST_USER || 'user@example.org'
const TEST_PASSWD = process.env.TEST_PASSWD || '1234'

async function login(page, date, time) {
    await page.goto(TEST_SITE);
    await page.getByPlaceholder('Email address').click();
    await page.getByPlaceholder('Email address').fill(TEST_USER);
    await page.getByPlaceholder('Password').fill(TEST_PASSWD);
    await page.getByPlaceholder('Password').press('Enter');
}

test('Lot GROUP-CRUD', async ({ page }) => {
  await login(page);
  //await page.pause();

  // create lot group
  await page.getByRole('link', { name: ' Admin' }).click();
  await page.getByRole('link', { name: 'Lot Groups' }).click();
  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByRole('textbox', { name: 'Tag' }).fill('Newlotgroup');
  await page.getByRole('button', { name: 'Add Lot tag' }).click();
  await expect(page.getByText('Lot Group successfully added.')).toBeVisible();

  //Edit lot group
  await page.getByRole('button', { name: ' Edit' }).nth(4).click();
  await page.getByRole('textbox', { name: 'Tag' }).fill('NewlotgroupEdited');
  await page.getByRole('button', { name: 'Save Changes' }).click();
  await expect(page.getByText('Lot Group updated')).toBeVisible();
  await expect(page.getByRole('cell', { name: 'NewlotgroupEdited' })).toBeVisible();

  //Delete lot group
  await page.getByRole('button', { name: ' Delete' }).nth(4).click();
  await expect(page.getByText('Are you sure you want to delete this lot group? NewlotgroupEdited')).toBeVisible();
  await page.getByRole('button', { name: 'Delete', exact: true }).click();


});

test('Lot group already exists (Inbox)', async ({ page }) => {
  await login(page);
  //await page.pause();

  await page.getByRole('link', { name: ' Admin' }).click();
  await page.getByRole('link', { name: 'Lot Groups' }).click();

  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByRole('textbox', { name: 'Tag' }).fill('Newgroup');
  await page.getByRole('button', { name: 'Add Lot tag' }).click();

  await page.getByRole('button', { name: 'Add' }).click();
  await page.getByRole('textbox', { name: 'Tag' }).fill('Newgroup');
  await page.getByRole('button', { name: 'Add Lot tag' }).click();
  await expect(page.getByText('The name \'Newgroup\' exist.')).toBeVisible();
});
