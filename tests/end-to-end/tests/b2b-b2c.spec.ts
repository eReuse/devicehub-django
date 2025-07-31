import { test, expect } from '@playwright/test';

const TEST_SITE = process.env.TEST_SITE || 'http://127.0.0.1:8001'
const TEST_REFURBISHER_USER = process.env.TEST_REFURBISHER_USER || 'user@example.org'
const TEST_PASSWD = process.env.TEST_PASSWD || '1234'

const TEST_DONOR_USER = process.env.TEST_DONOR_USER || 'donor@example.org'
const TEST_CIRCUIT_USER = process.env.TEST_CIRCUIT_USER || 'circuit-manager@example.org'
const TEST_SHOP_USER = process.env.TEST_SHOP_USER || 'shop@example.org'
const TEST_BENEFICIARY_USER = process.env.TEST_BENEFICIARY_USER || 'beneficiary@example.org'

async function login(page, user, passwd) {
    const loginUser = user
    const loginPasswd = passwd
    await page.goto(TEST_SITE);
    await page.getByPlaceholder('Email address').click();
    await page.getByPlaceholder('Email address').fill(loginUser);
    await page.getByPlaceholder('Password').fill(loginPasswd);
    await page.getByPlaceholder('Password').press('Enter');
}

test('B2B (1/2): Refurbisher creates lot', async ({ page }) => {
    await login(page, TEST_REFURBISHER_USER, TEST_PASSWD);

    // Refurbisher add devices to donor's lot
    await page.getByRole('row').nth(1).getByRole('checkbox').check();
    await page.getByRole('row').nth(2).getByRole('checkbox').check();

    await page.getByRole('button', { name: ' Assign to lot' }).click();
    await page.getByRole('heading', { name: 'Entrada (2 open Lot/s)' }).locator('small').click();
    await page.getByText('donante-orgB').click();
    await page.getByRole('button', { name: 'Assign' }).click();

    // Add circularity manager
    await page.getByRole('link', { name: ' Subscription' }).click();
    await page.getByRole('button', { name: 'Add subscription' }).click();
    await page.getByPlaceholder('User').click();
    await page.getByPlaceholder('User').fill('circuit-manager@example.org');
    await page.getByRole('button', { name: 'Subscribe' }).click();
});

test('B2B (2/2): Circuit Manager', async ({ page }) => {
    await login(page, TEST_CIRCUIT_USER, TEST_PASSWD);

    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: 'donante-orgB' }).click();
    await page.getByRole('link', { name: 'Donor' }).click();
    await page.getByPlaceholder('User').click();
    await page.getByPlaceholder('User').fill('donor@example.org');
    await page.getByRole('button', { name: 'Add' }).click();

    // For simplicity, right now, circularity manager does the donor
    //   role on this test

    const previousUrl = page.url();
    await page.getByRole('link', { name: 'Donor' }).click();
    // TODO verify donor web URL is the same as email
    await page.getByRole('link', { name: 'Donor web' }).click();
    // Donor accepts conformity
    await page.getByRole('link', { name: 'Accept' }).click();
    await page.goto(previousUrl);
    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: 'donante-orgB' }).click();

    await page.getByRole('link', { name: 'Participants' }).click();
    // this is the "shield" that it is accepted
    await expect(page.getByRole('cell', { name: '' })).toBeVisible();
});

test('B2C (1/2): Refurbisher creates lot', async ({ page }) => {
    await login(page, TEST_REFURBISHER_USER, TEST_PASSWD);

    // Refurbisher add devices to shop's lot
    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: 'donante-orgB' }).click();
    await page.locator('#select-all').check();
    await page.getByRole('button', { name: ' Assign to lot' }).click();
    await page.getByRole('heading', { name: 'Salida (2 open Lot/s)' }).click();
    await page.getByText('beneficiario-org1').click();
    await page.getByRole('button', { name: 'Assign' }).click();

    // Add shop
    await page.getByRole('link', { name: ' Subscription' }).click();
    await page.getByRole('button', { name: 'Add subscription' }).click();
    await page.getByPlaceholder('User').click();
    await page.getByLabel('Type').selectOption('shop');
    await page.getByPlaceholder('User').click();
    await page.getByPlaceholder('User').fill('shop@example.org');
    await page.getByRole('button', { name: 'Subscribe' }).click();
});

test('B2C (2/2): Shop', async ({ page }) => {
    await login(page, TEST_SHOP_USER, TEST_PASSWD);

    await page.getByRole('link', { name: 'Salida' }).click();
    await page.getByRole('link', { name: 'beneficiario-org1' }).click();
    await page.getByRole('row').nth(1).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Beneficiary' }).click();
    // Shop add beneficiary
    await page.getByRole('button', { name: 'Add Beneficiary' }).click();
    await page.getByPlaceholder('Beneficiary').click();
    await page.getByPlaceholder('Beneficiary').fill('beneficiary@example.org');

    // TODO verify
    // Shop assign devices to beneficiary
    await page.getByRole('button', { name: 'Add', exact: true }).click();

    // For simplicity, right now, shop does the beneficiary role on
    //   this test

    // Beneficiary accepts conformity
    const previousUrl = page.url();
    await page.getByRole('link', { name: 'web' }).click();
    await page.getByRole('link', { name: 'Accept' }).click();
    await page.goto(previousUrl);

    // TODO add assert visibility acceptance from shop perspective

    await page.getByRole('cell', { name: 'Devices' }).click();
    // Shop changes state
    //   change status to confirmed
    await page.locator('#id_form-0-status').selectOption('Confirmed');
    await page.getByRole('button', { name: 'Save' }).click();

    // attempt to register a second device
    await page.getByRole('link', { name: 'Devices', exact: true }).click();
    await page.getByRole('row').nth(2).getByRole('checkbox').check();

    await page.getByRole('button', { name: 'Beneficiary' }).click();
    await page.getByRole('link', { name: ' Assign' }).click();
    await page.locator('#id_form-1-status').selectOption('Confirmed');
    await page.getByRole('button', { name: 'Save' }).click();
});
