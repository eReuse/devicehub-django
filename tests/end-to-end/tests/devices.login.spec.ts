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
//});


test('Devices assign/deassign to lot', async ({ page }) => {
    await login(page);


    //assign all paginated devices to lot donante-orgB
    await page.getByRole('link', { name: ' Devices' }).click();
    await page.getByRole('link', { name: 'All' }).click();
    await page.locator('#select-all').check();
    await page.getByRole('button', { name: ' Assign to lot' }).click();
    await page.getByRole('row', { name: 'Entrada/donante-orgB' }).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Save' }).click();

    //check we are on selected lot
    await expect(page.locator('h5')).toContainText('donante-orgB');

    //deassign devices
    await page.locator('#select-all').check();
    await page.getByRole('button', { name: ' Unassign' }).click();
    await expect(page.locator('#devices-form')).toContainText('0');

});


test('Export devices', async ({ page }) => {
    await login(page);

    //assign all paginated devices to lot donante-orgB
    await page.getByRole('link', { name: ' Devices' }).click();
    await page.getByRole('link', { name: 'All' }).click();
    await page.locator('#select-all').check();
    await page.getByRole('button', { name: ' Assign to lot' }).click();
    await page.getByRole('row', { name: 'Entrada/donante-orgB' }).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Save' }).click();

    //check we are on selected lot
    await expect(page.locator('h5')).toContainText('donante-orgB');

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('link', { name: ' Export all (.csv)' }).click();
    const download = await downloadPromise;
    const download1Promise = page.waitForEvent('download');
    await page.getByRole('link', { name: ' Export all (.xlsx)' }).click();
    const download1 = await download1Promise;
});

test('Bulk changed state', async ({ page }) => {
    await login(page);

    //assign all paginated devices to lot donante-orgB
    await page.getByRole('link', { name: ' Devices' }).click();
    await page.getByRole('link', { name: 'All' }).click();
    await page.locator('#select-all').check();
    await page.getByRole('button', { name: ' Assign to lot' }).click();
    await page.getByRole('row', { name: 'Entrada/donante-orgB' }).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Save' }).click();

    //check we are on selected lot
    await expect(page.locator('h5')).toContainText('donante-orgB');

    await page.locator('#select-all').check();
    await page.getByText('Change state').click();
    await page.getByRole('button', { name: 'INBOX' }).click();
    await expect(page.getByRole('alert')).toContainText('State changed Successfully');
    await expect(page.locator('tbody')).toContainText('INBOX');

});

test('Search', async ({ page }) => {

    await login(page);

    //assign all paginated devices to lot donante-orgB
    await page.getByRole('link', { name: ' Devices' }).click();
    await page.getByRole('link', { name: 'All' }).click();
    await page.locator('#select-all').check();
    await page.getByRole('button', { name: ' Assign to lot' }).click();
    await page.getByRole('row', { name: 'Entrada/donante-orgB' }).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Save' }).click();

    //check we are on selected lot
    await expect(page.locator('h5')).toContainText('donante-orgB');

    //search by all
    const search_item = 'Search devices within lot'
    await page.getByPlaceholder(search_item).fill('7');
    await page.getByRole('button', { name: '' }).click();

    //search by id
    await page.getByPlaceholder(search_item).fill('7:shortid');
    await page.getByRole('button', { name: '' }).click();

    //search by cpu
    await page.getByPlaceholder(search_item).fill('7:cpu');
    await page.getByRole('button', { name: '' }).click();

    //search by current_state
    await page.getByPlaceholder(search_item).fill('inbox:current_state');
    await page.getByRole('button', { name: '' }).click();

    //search by manufacturer
    await page.getByPlaceholder(search_item).fill('dell:manufacturer');
    await page.getByRole('button', { name: '' }).click();


});

test('Paginate devices', async ({ page }) => {
    await login(page);

    //assign all paginated devices to lot donante-orgB
    await page.getByRole('link', { name: ' Devices' }).click();
    await page.getByRole('link', { name: 'All' }).click();
    await page.locator('#select-all').check();
    await page.getByRole('button', { name: ' Assign to lot' }).click();
    await page.getByRole('row', { name: 'Entrada/donante-orgB' }).getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Save' }).click();

    //check we are on selected lot
    await expect(page.locator('h5')).toContainText('donante-orgB');

    await page.getByLabel('Show').selectOption('20');
    await page.getByLabel('Show').selectOption('50');
    await page.getByLabel('Show').selectOption('100');

    // option 0 is show all (only for lots)
    await page.getByLabel('Show').selectOption('0');
    await page.getByLabel('Show').selectOption('10');

});
