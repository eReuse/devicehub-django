import { test, expect } from '@playwright/test';

const TEST_SITE = process.env.TEST_SITE || 'http://127.0.0.1:8001'
const TEST_REFURBISHER_USER = process.env.TEST_REFURBISHER_USER || 'user@example.org'
const TEST_PASSWD = process.env.TEST_PASSWD || '1234'

const TEST_DONOR_USER = process.env.TEST_DONOR_USER || 'donor@example.org'
const TEST_CIRCUIT_USER = process.env.TEST_CIRCUIT_USER || 'circuit-manager@example.org'
const TEST_SHOP_USER = process.env.TEST_SHOP_USER || 'shop@example.org'
const TEST_BENEFICIARY_USER = process.env.TEST_BENEFICIARY_USER || 'beneficiary1@example.org'

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
    await page.getByRole('link', { name: 'Subscriptions' }).click();
    await page.getByRole('button', { name: ' Add Subscription' }).click();
    await page.getByRole('button', { name: 'Add subscription' }).click();
    await page.getByRole('textbox', { name: 'Email' }).click();
    await page.getByRole('textbox', { name: 'Email' }).fill('circuit-manager@example.org');
    await page.getByRole('radio', { name: 'Circuit Manager' }).check();
    await page.getByRole('button', { name: 'Subscribe' }).click();

});

test('B2B (2/2): Circuit Manager', async ({ page }) => {
    await login(page, TEST_CIRCUIT_USER, TEST_PASSWD);

    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: 'donante-orgB' }).click();
    await page.getByRole('link', { name: 'Donor' }).click();
    await page.getByRole('textbox', { name: 'Email' }).fill('donor@example.org');
    await page.getByRole('button', { name: ' Add Donor' }).click();

    // For simplicity, right now, circularity manager does the donor
    //   role on this test

    const previousUrl = page.url();
    // TODO verify donor web URL is the same as email
    await page.getByRole('link', { name: ' Donor\'s web' }).click();
    // Donor accepts conformity
    await page.getByRole('link', { name: 'Accept' }).click();

    await page.goto(previousUrl);
    await page.getByRole('link', { name: 'Participants' }).click();
    // this is the "shield" that it is accepted
    await expect(page.getByRole('cell', { name: '' })).toBeVisible();
});

test('B2C (1/2): Refurbisher creates lot', async ({ page }) => {
    await login(page, TEST_REFURBISHER_USER, TEST_PASSWD);


    // Refurbisher add devices to shop's lot
    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: 'donante-orgB' }).click();
    await page.locator('#select-all-checkbox').check();
    await page.getByRole('button', { name: ' Assign to lot' }).click();
    await page.locator('div').filter({ hasText: 'Salida (2 open Lot/s)' }).nth(3).click();

    await page.getByText('beneficiario-org1').click();
    await page.getByRole('button', { name: 'Assign' }).click();


    // Add shop
    await page.getByRole('link', { name: 'Subscriptions' }).click();
    await page.getByRole('button', { name: ' Add Subscription' }).click();
    await page.getByRole('radio', { name: 'Shop' }).check();
    await page.getByRole('textbox', { name: 'Email' }).fill('shop@example.org');
    await page.getByRole('button', { name: 'Subscribe' }).click();

});

test('B2C (2/2): Shop', async ({ page }) => {
    await login(page, TEST_SHOP_USER, TEST_PASSWD);

    //await page.pause();
    await page.getByRole('link', { name: 'Salida' }).click();
    await page.getByRole('link', { name: 'beneficiario-org1' }).click();
    // add beneficiary
    await page.getByRole('link', { name: 'Beneficiaries' }).click();
    await page.getByRole('button', { name: ' Add Beneficiary' }).click();
    await page.getByRole('textbox', { name: 'Email' }).fill('beneficiary1@example.org');
    await page.getByRole('button', { name: 'Add', exact: true }).click();

    // Shop assign devices to beneficiary
    await page.locator('a').filter({ hasText: /^Devices$/ }).click();
    await page.getByRole('row').nth(1).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Add to beneficiary' }).click();
    await page.getByRole('link', { name: ' Assign' }).click();
    // TODO verify

    // For simplicity, right now, shop does the beneficiary role on
    //   this test

    // Beneficiary accepts conformity
    const previousUrl = page.url();
    await page.getByRole('link', { name: 'Beneficiaries' }).nth(1).click();
    await page.getByRole('link', { name: 'web' }).click();
    await page.getByRole('link', { name: 'Accept' }).click();
    await page.goto(previousUrl);

    await page.getByRole('link', { name: 'Beneficiaries' }).nth(1).click();
    await page.getByRole('cell', { name: 'Devices' }).click();
    await expect(page.locator('.bi.bi-shield-check')).toBeVisible();

    await page.getByRole('table').getByRole('link', { name: 'Devices' }).click();
    // Shop changes state
    //   change status to confirmed
    await page.locator('#id_form-0-status').selectOption('2');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('cell', { name: 'Confirmed' })).toBeVisible();

    // attempt to register a second device
    //
    await page.getByRole('link', { name: 'Devices' }).click();
    await page.getByRole('row').nth(2).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Add to beneficiary' }).click();
    await page.getByRole('link', { name: ' Assign' }).click();
    await page.locator('#id_form-1-status').selectOption('2');
    await page.getByRole('button', { name: 'Save' }).click();

});

test('B2C: Prevent assigning already assigned devices', async ({ page }) => {
    await login(page, TEST_SHOP_USER, TEST_PASSWD);
    //await page.pause();

    // go to a lot and select a device we KNOW is already assigned
    await page.getByRole('link', { name: 'Salida' }).click();
    await page.getByRole('link', { name: 'beneficiario-org1' }).click();
    await page.getByRole('link', { name: 'Devices' }).first().click();


    // select the first device in the lot (which B2C 2/2 just assigned to beneficiary@example.org)
    await page.getByRole('row').nth(1).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Add to beneficiary' }).click();

    // assert the UI blocks it and shows the red warning card
    await expect(page.getByRole('heading', { name: ' 1 Already assigned Devices' })).toBeVisible();
    await expect(page.locator('.assign-device-warning')).toBeVisible();
    await expect(page.locator('div').filter({ hasText: /^beneficiary1@example\.org$/ })).toBeVisible();

    // create a SECOND beneficiary and try to steal the device
    await page.getByRole('button', { name: ' Add Beneficiary' }).click();
    await page.getByRole('textbox', { name: 'Email' }).fill('beneficiary2@example.org');
    await page.getByRole('button', { name: 'Add', exact: true }).click();

    // TODO: assert the backend rejected it and showed an error message
});


test('B2C: Empty session UI validation', async ({ page }) => {
    await login(page, TEST_SHOP_USER, TEST_PASSWD);

    await page.getByRole('link', { name: 'Salida' }).click();
    await page.getByRole('link', { name: 'beneficiario-org1' }).click();

    await page.getByRole('row').nth(1).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Add to beneficiary' }).click();

    // ensure session is cleared using the button
    await expect(page.getByRole('link', { name: ' Clear selection' })).toBeVisible();
    await page.getByRole('link', { name: ' Clear selection' }).click();

    //TODO: improve test when merge is done

});


test('B2C: Allow assignment if device is returned ', async ({ page }) => {
    await login(page, TEST_SHOP_USER, TEST_PASSWD);

    await page.getByRole('link', { name: 'Salida' }).click();
    await page.getByRole('link', { name: 'beneficiario-org1' }).click();

    await page.getByRole('link', { name: 'Beneficiaries' }).click();
    await page.getByRole('link', { name: 'Devices' }).nth(1).click();
    await page.locator('#id_form-0-status').click();
    await page.locator('#id_form-0-status').selectOption('4');
    await page.getByRole('button', { name: 'Save' }).click();
    await page.getByRole('link', { name: 'Devices' }).click();

    await page.getByRole('row').nth(1).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Add to beneficiary' }).click();
    await page.getByRole('link', { name: ' Assign' }).nth(1).click();
    await expect(page.getByText('1 device(s) successfully')).toBeVisible();


});


test('B2C: Disallow rollback state if device was taken ', async ({ page }) => {
    await login(page, TEST_SHOP_USER, TEST_PASSWD);

    await page.getByRole('link', { name: 'Salida' }).click();
    await page.getByRole('link', { name: 'beneficiario-org1' }).click();

    await page.getByRole('link', { name: 'Beneficiaries' }).click();

    await page.getByRole('link', { name: 'Devices' }).nth(1).click();
    await page.locator('#id_form-0-status').selectOption('1');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByText('Cannot change status. Device')).toBeVisible();


});

test('B2C: Disallow assignment over other lot', async ({ page }) => {
    await login(page, TEST_SHOP_USER, TEST_PASSWD);

    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: 'donante-orgB' }).click();

    await page.getByRole('link', { name: 'Subscriptions' }).click();
    await page.getByRole('button', { name: ' Add Subscription' }).click();
    await page.getByRole('textbox', { name: 'Email' }).fill('shop@example.org');
    await page.getByRole('radio', { name: 'Shop' }).check();
    await page.getByRole('button', { name: 'Subscribe' }).click();

    await page.getByRole('link', { name: 'Devices' }).click();

    await page.getByRole('row').nth(1).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Add to beneficiary' }).click();
    await page.getByRole('button', { name: ' Add Beneficiary' }).click();

    await page.getByRole('textbox', { name: 'Email' }).fill('beneficiary3@example.org');
    await page.getByRole('button', { name: 'Add', exact: true }).click();

    await expect(page.getByText('Beneficiary saved, but NO')).toBeVisible();

});
