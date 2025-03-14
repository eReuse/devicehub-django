import { test, expect, type Page } from '@playwright/test';

// TODO after the tests, put again demo.ereuse.org as default
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

// when introducing a new test, use only temporarily to just enable that test
//
//test.only('NEW example', async ({ page }) => {
//    await login(page);
//    test.setTimeout(0)
//    await page.pause();
//});


test.only('Change erasure server status', async ({ page }) => {
    await login(page);
    await page.pause();

    await page.getByRole('link', { name: ' Evidences' }).click();
    await page.getByRole('link', { name: 'List of evidences' }).click();
    await page.getByRole('link', { name: '7928afeb-e6a4-464a-a842-' }).click();

    await page.locator('#id_erase_server').check();
    await page.locator('#id_erase_server').uncheck();


    await page.close();
});

test('Change TAG', async ({ page }) => {
    await login(page);
    //await page.pause();

    await page.getByRole('link', { name: ' Evidences' }).click();
    await page.getByRole('link', { name: 'List of evidences' }).click();
    await page.getByRole('link', { name: '7928afeb-e6a4-464a-a842-' }).click();
    await page.getByRole('button', { name: 'Tag' }).click();
    await page.getByPlaceholder('Tag').click();
    await page.getByPlaceholder('Tag').fill('CUSTOMTAG');
    await page.getByRole('button', { name: 'Save' }).click();
    await page.getByRole('button', { name: 'Tag' }).click();
    await page.getByRole('link', { name: 'Delete' }).click();
    await expect(page.getByText('Evicende Tag deleted')).toBeVisible();


    await page.close();
});

test('Download Evidence', async ({ page }) => {
    await login(page);
    await page.pause();

    await page.getByRole('link', { name: ' Evidences' }).click();
    await page.getByRole('link', { name: 'List of evidences' }).click();
    await page.getByRole('link', { name: '7928afeb-e6a4-464a-a842-' }).click();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Download File' }).click();
    const download = await downloadPromise;

    await page.close();
});
