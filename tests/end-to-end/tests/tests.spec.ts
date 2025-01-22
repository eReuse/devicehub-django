import { test, expect } from '@playwright/test';

// TODO after the tests, put again demo.ereuse.org as default
const TEST_SITE = process.env.TEST_SITE || 'https://lab1.ereuse.org'
const TEST_USER = 'user@example.org'
const TEST_PASSWD = '1234'

async function login(page, date, time) {
        await page.goto(TEST_SITE);
        await page.getByPlaceholder('Email address').click();
        await page.getByPlaceholder('Email address').fill(TEST_USER);
        await page.getByPlaceholder('Password').fill(TEST_PASSWD);
        await page.getByPlaceholder('Password').press('Enter');
        await page.getByRole('button', { name: 'Next' }).click();
}

test('example', async ({ page }) => {
        await login(page);
        await page.pause();
});
