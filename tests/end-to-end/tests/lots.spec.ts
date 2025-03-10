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


test.only('Lot CRUD', async ({ page }) => {
    await login(page);
    //await page.pause();

    // Create Lot
    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: 'New lot' }).click();
    await page.getByLabel('Type').selectOption('2');
    await page.getByPlaceholder('Name').fill('Organizaci');
    await page.getByPlaceholder('Code').click();
    await page.getByPlaceholder('Code').fill('Codigo');
    await page.getByPlaceholder('Description').fill('Descripcion muy extensa de una organizacion muy extensa');
    await page.getByRole('button', { name: ' Save' }).click();

    // Edit Lot
    await page.getByRole('link', { name: ' Edit' }).first().click();
    await page.getByPlaceholder('Name').click();
    await page.getByPlaceholder('Name').fill('Organización');
    await page.getByPlaceholder('Name').press('Enter');

    // Delete Lot
    await page.getByRole('row', { name: ' Organización Descripcion' }).getByRole('checkbox').check();
    await page.getByRole('button', { name: ' Delete Selected' }).click();
    await page.getByRole('button', { name: '' }).click();
    await page.getByRole('button', { name: '' }).click();
    await page.getByRole('button', { name: ' Delete' }).click();

    await page.close();
});


test('Search function', async ({ page }) => {
    //Searches for a demo loaded lot (orgC)
    await login(page);
    //await page.pause();

    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByPlaceholder('Search by name or description').click();
    await page.getByPlaceholder('Search by name or description').fill('orgC');
    await page.getByRole('button', { name: '' }).click();
    await page.getByRole('link', { name: 'donante-orgC' }).click();

});

test('Show archived', async ({ page }) => {
    await login(page);
    //await page.pause();

    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByText('Archived (1)').click();
    await page.getByRole('link', { name: 'donante-orgA' }).click();

});

test('Sort by different columns', async ({ page }) => {
    await login(page);

    //await page.pause();
    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByText('All Lots (3)').click();
    await page.getByRole('link', { name: 'Status' }).click();
    await page.getByRole('link', { name: 'Status' }).click();
    await page.getByRole('link', { name: 'Lot Name' }).click();
    await page.getByRole('link', { name: 'Lot Name' }).click();
    await page.getByRole('link', { name: 'Description' }).click();
    await page.getByRole('link', { name: 'Description' }).click();
    await page.getByRole('link', { name: 'Devices' }).click();
    await page.getByRole('link', { name: 'Devices' }).click();
    await page.getByRole('link', { name: 'Created On' }).click();
    await page.getByRole('link', { name: 'Created On' }).click();
    await page.getByRole('link', { name: 'Created By' }).click();
    await page.getByRole('link', { name: 'Created By' }).click();

});

test('Select all and delete all', async ({ page }) => {
    await login(page);
    // await page.pause();

    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.locator('#select-all').check();
    await page.getByRole('button', { name: ' Delete Selected' }).click();
    await page.getByRole('button', { name: ' Delete' }).click();

});
