import { test, expect } from '@playwright/test';

// TODO after the tests, put again demo.ereuse.org as default
const TEST_SITE = process.env.TEST_SITE || 'http://localhost:8001'
const TEST_USER = process.env.TEST_USER || 'user@example.org'
const TEST_PASSWD = process.env.TEST_PASSWD || '1234'

// when introducing a new test, use only temporarily to just enable that test
//
//test.only('NEW example', async ({ page }) => {
//    await login(page);
//    test.setTimeout(0)
//    await page.pause();
//});

test('Login success', async ({ page }) => {
    await page.goto(TEST_SITE);

    //await page.pause();
    await page.getByPlaceholder('Email address').click();
    await page.getByPlaceholder('Email address').fill(TEST_USER);
    await page.getByPlaceholder('Password').fill(TEST_PASSWD);
    await page.getByPlaceholder('Password').press('Enter');

    //checks that ui is now logged in
    await expect(page.getByRole('link', { name: ' Evidences' })).toBeVisible();
});

test('Login failed', async ({ page }) => {
    await page.goto(TEST_SITE);

    //await page.pause();
    await page.getByPlaceholder('Email address').click();
    await page.getByPlaceholder('Email address').fill(TEST_USER);
    await page.getByPlaceholder('Password').fill("incorrect password");
    await page.getByPlaceholder('Password').press('Enter');

    await expect(page.getByText('Login error. Check')).toBeVisible();


});

test.only('Recover Password ', async ({ page }) => {
    await page.goto(TEST_SITE);

    await page.pause();
    await page.getByRole('link', { name: 'Forgot your password?' }).click();
    await page.getByPlaceholder('Email').click();

    await page.getByPlaceholder('Email').fill(TEST_USER);
    await page.getByRole('button', { name: 'Reset Password' }).click();
    await expect(page.getByRole('heading', { name: 'Password reset sent' })).toBeVisible();
    await page.getByRole('link', { name: 'Back to login' }).click();


});
