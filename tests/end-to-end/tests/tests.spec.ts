import { test, expect } from '@playwright/test';

// TODO after the tests, put again demo.ereuse.org as default
const TEST_SITE = process.env.TEST_SITE || 'https://lab1.ereuse.org'
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

test('Evidence: create and destroy tag (custom id)', async ({ page }) => {
    await login(page);
    await page.goto(`${TEST_SITE}/evidence/`);
    await page.locator('table a').first().click();
    await page.getByRole('link', { name: 'Tag' }).click();

    // create tag
    await page.getByPlaceholder('Tag').click();
    await page.getByPlaceholder('Tag').fill('test');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('alert')).toContainText('Tag mytag has been added.');

    // delete tag
    await page.getByRole('link', { name: 'Tag' }).click();
    await page.getByRole('link', { name: 'Delete' }).click();
    await expect(page.getByRole('alert')).toContainText('Tag mytag has been deleted.');
});

test('Property: create key-value, edit key, edit value, delete property property', async ({ page }) => {
    const last_log = '#log tr:nth-child(1) td:nth-child(2)'
    await login(page);
    // assuming after login, we are in devices page, and there, there is a table with devices
    await page.locator('table a').first().click();

    // new property; key: init1, value: 1
    await page.getByRole('link', { name: 'User properties' }).click();
    await page.getByRole('link', { name: ' New user property' }).click();
    await page.getByPlaceholder('Key').click();
    await page.getByPlaceholder('Key').fill('init1');
    await page.getByPlaceholder('Key').press('Tab');
    await page.getByPlaceholder('Value').fill('1');
    await page.getByRole('button', { name: 'Save' }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('User property init1 has been added.');
    await page.getByRole('link', { name: 'Log' }).click();
    await expect(page.locator(last_log)).toContainText('<Created> UserProperty: init1: 1');

    // edit property; key: init2, value: 1
    await page.getByRole('link', { name: 'User properties' }).click();
    await page.getByRole('button', { name: ' Edit' }).first().click();
    await page.getByLabel('Key').click();
    await page.getByLabel('Key').fill('init2');
    await page.getByRole('button', { name: 'Save changes' }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('User property init2 has been updated.');
    await page.getByRole('link', { name: 'Log' }).click();
    await expect(page.locator(last_log)).toContainText('<Updated> UserProperty: init1: 1 to init2: 1');

    // edit property; key: init2, value: 2
    await page.getByRole('link', { name: 'User properties' }).click();
    await page.getByRole('button', { name: ' Edit' }).first().click();
    await page.getByLabel('Value').fill('2');
    await page.getByRole('button', { name: 'Save changes' }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('User property init2 has been updated.');
    await page.getByRole('link', { name: 'Log' }).click();
    await expect(page.locator(last_log)).toContainText('<Updated> UserProperty: init2: 1 to init2: 2');

    // delete property; key: init2, value: 2
    await page.getByRole('link', { name: 'User properties' }).click();
    await page.getByRole('button', { name: ' Delete' }).click();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('User property init2 has been updated.');
    await page.getByRole('link', { name: 'Log' }).click();
    await expect(page.locator(last_log)).toContainText('<Deleted> User Property: init2:2');
});

test('Property: duplication tests', async ({ page }) => {
    await login(page);
    // assuming after login, we are in devices page, and there, there is a table with devices
    await page.locator('table a').first().click();

    // new property; key: uniq1, value: 1
    await page.getByRole('link', { name: 'User properties' }).click();
    await page.getByRole('link', { name: ' New user property' }).click();
    await page.getByPlaceholder('Key').click();
    await page.getByPlaceholder('Key').fill('uniq1');
    await page.getByPlaceholder('Key').press('Tab');
    await page.getByPlaceholder('Value').fill('1');
    await page.getByRole('button', { name: 'Save' }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('User property uniq1 has been added.');

    // new property (duplicate); key: uniq1, value: 1
    await page.getByRole('link', { name: 'User properties' }).click();
    await page.getByRole('link', { name: ' New user property' }).click();
    await page.getByPlaceholder('Key').click();
    await page.getByPlaceholder('Key').fill('uniq1');
    await page.getByPlaceholder('Key').press('Tab');
    await page.getByPlaceholder('Value').fill('1');
    await page.getByRole('button', { name: 'Save' }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('User property uniq1 already exists.');

    // delete property; key: uniq1, value: 1
    await page.getByRole('link', { name: 'User properties' }).click();
    await page.getByRole('button', { name: ' Delete' }).first().click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('User property uniq1 deleted has been.');
});


test.only('States: duplication tests', async ({ page }) => {
    await login(page);
    await page.getByRole('link', { name: ' Admin' }).click();
    await page.getByRole('link', { name: 'States' }).click();

    // create state: TEST_STATE
    await page.getByRole('button', { name: 'Add' }).click();
    await page.getByRole('textbox', { name: 'State' }).click();
    await page.getByRole('textbox', { name: 'State' }).fill('TEST_STATE');
    await page.getByRole('button', { name: 'Add state definition' }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('State definition TEST_STATE has been added.');

    // create state (duplicate): TEST_STATE
    await page.getByRole('button', { name: 'Add' }).click();
    await page.getByRole('textbox', { name: 'State' }).click();
    await page.getByRole('textbox', { name: 'State' }).fill('TEST_STATE');
    await page.getByRole('button', { name: 'Add state definition' }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('State definition TEST_STATE is already defined.');

    // edit state: TEST_STATE -> TEST_STATE_EDIT
    await page.getByRole('row', { name: 'TEST_STATE  Edit  Delete' }).getByRole('button').first().click();
    await page.getByRole('textbox', { name: 'State' }).fill('TEST_STATE_EDIT');
    await page.getByRole('button', { name: 'Save Changes' }).click();

    // create state: TEST_STATE
    await page.getByRole('button', { name: 'Add' }).click();
    await page.getByRole('textbox', { name: 'State' }).click();
    await page.getByRole('textbox', { name: 'State' }).fill('TEST_STATE');
    await page.getByRole('button', { name: 'Add state definition' }).click();

    // TODO uncomment. "Cannot create key that already exists (UNIQUE constraint)"
    // edit state (duplicated during edit): TEST_STATE_EDIT -> TEST_STATE
    //await page.getByRole('row', { name: 'TEST_STATE  Edit  Delete' }).getByRole('button').first().click();
    //await page.getByRole('textbox', { name: 'State' }).fill('TEST_STATE_EDIT');
    //await page.getByRole('button', { name: 'Save Changes' }).click();

    // delete state: TEST_STATE_EDIT
    await page.getByRole('row', { name: 'TEST_STATE_EDIT  Edit  Delete' }).getByRole('button').nth(1).click();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('State definition TEST_STATE has been deleted.');

    // delete state: TEST_STATE
    await page.getByRole('row', { name: 'TEST_STATE  Edit  Delete' }).getByRole('button').nth(1).click();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    // TODO uncomment
    //await expect(page.getByRole('alert')).toContainText('State definition TEST_STATE has been deleted.');

});

test('Lot: duplication tests', async ({ page }) => {
    await login(page);

    // add lot
    await page.getByRole('link', { name: ' Lots' }).click();
    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: ' Add new lot' }).click();
    await page.getByLabel('Type').selectOption('1');
    await page.getByPlaceholder('Name').click();
    await page.getByPlaceholder('Name').fill('testlot');
    await page.getByPlaceholder('Name').press('Tab');
    await page.getByPlaceholder('Code').fill('testlot');
    await page.getByPlaceholder('Code').press('Tab');
    await page.getByPlaceholder('Description').fill('testlot');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('alert')).toContainText('Lot testlot has been added.');

    // add (duplicate) lot
    await page.getByRole('link', { name: ' Lots' }).click();
    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: ' Add new lot' }).click();
    await page.getByLabel('Type').selectOption('1');
    await page.getByPlaceholder('Name').click();
    await page.getByPlaceholder('Name').fill('testlot');
    await page.getByPlaceholder('Name').press('Tab');
    await page.getByPlaceholder('Code').fill('testlot');
    await page.getByPlaceholder('Code').press('Tab');
    await page.getByPlaceholder('Description').fill('testlot');
    await page.getByPlaceholder('Description').press('Enter');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.getByRole('alert')).toContainText('Lot testlot is already defined.');

    // delete lot
    await page.getByRole('link', { name: ' Lots' }).click();
    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: '' }).nth(3).click();
    await page.getByRole('link', { name: 'Cancel' }).click();
    await page.getByRole('link', { name: ' Lots' }).click();
    await page.getByRole('link', { name: 'Entrada' }).click();
    await page.getByRole('link', { name: '' }).first().click();
    await page.getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByRole('alert')).toContainText('Lot testlot has been deleted.');
});

// TODO falta probar la parte de notas

// falta vista https://lab1.ereuse.org/dashboard/ con columna de state actual; si no hay None pero con un estilo diferente (cursiva y gris?)

//test('Bug 4: Missing logs for actions', async ({ page }) => {
//    await login(page);
//    await page.goto(`${TEST_SITE}/device/7b769bd6e9191d5ff163fa4a206b9220dad10c47b45d210d3d4d31d586f6a4b6/#log`);
//    // Add your assertions and steps to test if logs are missing
//});
//
//test('Bug 6: Log note is not visible', async ({ page }) => {
//    await login(page);
//    // Add the specific URL or steps for testing log note visibility
//});
