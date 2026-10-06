# Unreleased

## Highlights

- **Towards generic product management**: extend with dynamic product types, and devices become products.
- **UNTP 0.7.0 support** for credential custody and management.
- **Simpler navigation menu**: Dashboard and Inbox are now one click away, and Inbox shows a counter when it has devices.
- **Lots and beneficiaries**: re-assign returned devices (even across lots), beneficiaries paginator, and default lot type selection.
- **Demo data and tests**: improved demo to see B2C data, and fixed test suite errors.

## More details

Merged PRs

<details>

- dashboard_inbox ([#198](https://farga.pangea.org/ereuse/devicehub-django/pulls/198))
- Support for UNTP 0.7.0 credential custody and management ([#188](https://farga.pangea.org/ereuse/devicehub-django/pulls/188))
- ProductHub: (1) dynamic product types, (2) devices -> products ([#145](https://farga.pangea.org/ereuse/devicehub-django/pulls/145))
- fix tests ([#193](https://farga.pangea.org/ereuse/devicehub-django/pulls/193))
- add environment to load_demo_data for b2c ([#197](https://farga.pangea.org/ereuse/devicehub-django/pulls/197))
- Re-assign returned devices (including from different lots) ([#172](https://farga.pangea.org/ereuse/devicehub-django/pulls/172))
- Implement beneficiaries paginator ([#155](https://farga.pangea.org/ereuse/devicehub-django/pulls/155))
- Select default lot type ([#152](https://farga.pangea.org/ereuse/devicehub-django/pulls/152))

</details>

# v2026.2

## Highlights

- **Dashboard**: new view with overall information about the inventory.
- **Faster tables**: caching, fixed sorting and search for devices.
- **Customizable QR labels**: admins can now pick the content included in the QR label including the logo, the device properties to print, and the label size and font.
- **Root alias**: bugfixes related to custom IDs for devices and lots.
- **More robust evidence handling**: image linking to websnapshots, better parsing and error handling, and improved migration from devicehub-teal (legacy) with new backup/restore commands (that include database and evidences).
- **Multitenant security**: fixes for data isolation vulnerabilities between tenants.
- **UX and beneficiary workflow improvements**: breadcrumbs, paginator, clearing beneficiaries, and richer exports.

## More details

Merged PRs

<details>

- Dashboard with overall info about the inventory ([#105](https://farga.pangea.org/ereuse/devicehub-django/pulls/105))
- gquery_588 ([#187](https://farga.pangea.org/ereuse/devicehub-django/pulls/187))
- fix some broken methods and attributes ([#190](https://farga.pangea.org/ereuse/devicehub-django/pulls/190))
- Link image to websnapshot on one form and manual entry overhaul ([#117](https://farga.pangea.org/ereuse/devicehub-django/pulls/117))
- fix someparsing for legacy evidence ([#185](https://farga.pangea.org/ereuse/devicehub-django/pulls/185))
- fix shortid when the api response ([#184](https://farga.pangea.org/ereuse/devicehub-django/pulls/184))
- add link in beneficiary and donor page in short_id tu public page ([#182](https://farga.pangea.org/ereuse/devicehub-django/pulls/182))
- test/ninja-api-lots ([#89](https://farga.pangea.org/ereuse/devicehub-django/pulls/89))
- bugfix_parser_746 ([#181](https://farga.pangea.org/ereuse/devicehub-django/pulls/181))
- Add cache for tables. Fix sorts, search and benchmarks ([#179](https://farga.pangea.org/ereuse/devicehub-django/pulls/179))
- Allow customization of QR label ([#164](https://farga.pangea.org/ereuse/devicehub-django/pulls/164))
- add error handling when problems parsing evidence ([#176](https://farga.pangea.org/ereuse/devicehub-django/pulls/176))
- drop blank spaces in cels ([#174](https://farga.pangea.org/ereuse/devicehub-django/pulls/174))
- lot export: add column beneficiary_status ([#175](https://farga.pangea.org/ereuse/devicehub-django/pulls/175))
- canonical_id__root_alias ([#161](https://farga.pangea.org/ereuse/devicehub-django/pulls/161))
- docker.restore.sh: rm DB before restore ([#173](https://farga.pangea.org/ereuse/devicehub-django/pulls/173))
- Improve breadcrumb UX ([#160](https://farga.pangea.org/ereuse/devicehub-django/pulls/160))
- Fix for lots not showing up on some devices (migration tau) ([#163](https://farga.pangea.org/ereuse/devicehub-django/pulls/163))
- bugfix photo evidence: use algorithm namespace-prefix ([#162](https://farga.pangea.org/ereuse/devicehub-django/pulls/162))
- improve-docker-scripts ([#159](https://farga.pangea.org/ereuse/devicehub-django/pulls/159))
- Vulnerabilidades de aislamiento de datos en entorno Multitenant ([#146](https://farga.pangea.org/ereuse/devicehub-django/pulls/146))
- Implement select all devices ([#153](https://farga.pangea.org/ereuse/devicehub-django/pulls/153))
- assign_custom_id_lot ([#158](https://farga.pangea.org/ereuse/devicehub-django/pulls/158))
- custom_id_properties ([#156](https://farga.pangea.org/ereuse/devicehub-django/pulls/156))
- add commands evidence_backup, evidence_restore, remove_duplicate_snapshots ([#149](https://farga.pangea.org/ereuse/devicehub-django/pulls/149))
- get smart from legacy ([#150](https://farga.pangea.org/ereuse/devicehub-django/pulls/150))
- Improve data migration from devicehub-teal (legacy) ([#120](https://farga.pangea.org/ereuse/devicehub-django/pulls/120))
- fix search by shortid and xapian ([#139](https://farga.pangea.org/ereuse/devicehub-django/pulls/139))
- Implement clear assign beneficiary ([#138](https://farga.pangea.org/ereuse/devicehub-django/pulls/138))
- Fix paginator style inconsistency ([#135](https://farga.pangea.org/ereuse/devicehub-django/pulls/135))
- subscription and beneficiary view: Minor UX fixes ([#137](https://farga.pangea.org/ereuse/devicehub-django/pulls/137))

</details>

Full Changelog: https://github.com/eReuse/devicehub-django/commits/v2026.2

# v2026.1

## Highlights

- **QR codes** in device details, with print support and the short ID shown next to the QR.
- **Photographic evidence**, plus a new evidences table and user panel.
- **Environmental impact** calculation for lots.
- **Root alias** for devices ID flexibility, with better search and device queries (and performance fixes).
- **Import/export**: improved file upload, device list export, and a migration script from the legacy version.
- **Better UI**: redesigned lots view, beneficiary view, side navigation, tokens view, and navbar responsiveness, plus clearer error handling.
- **Deployment and operations**: Postgres service with reverse proxy in Docker, database backup and restore with dbbackup.

## More details

Merged PRs

<details>

- fix/devices_performance ([#125](https://farga.pangea.org/ereuse/devicehub-django/pulls/125))
- bugfix beneficiary assignment ([#129](https://farga.pangea.org/ereuse/devicehub-django/pulls/129))
- Implement QR print logic ([#134](https://farga.pangea.org/ereuse/devicehub-django/pulls/134))
- Improve beneficiary view UX ([#130](https://farga.pangea.org/ereuse/devicehub-django/pulls/130))
- device_web: less IDs, add Short ID close to QR ([#131](https://farga.pangea.org/ereuse/devicehub-django/pulls/131))
- Improve lots view ([#114](https://farga.pangea.org/ereuse/devicehub-django/pulls/114))
- implement QR in device details ([#127](https://farga.pangea.org/ereuse/devicehub-django/pulls/127))
- SideNav bulk fixes ([#122](https://farga.pangea.org/ereuse/devicehub-django/pulls/122))
- Handle some errors in UI ([#124](https://farga.pangea.org/ereuse/devicehub-django/pulls/124))
- display status field if there is at latest one ([#121](https://farga.pangea.org/ereuse/devicehub-django/pulls/121))
- Fixes on Tokens view ([#119](https://farga.pangea.org/ereuse/devicehub-django/pulls/119))
- script-migration ([#42](https://farga.pangea.org/ereuse/devicehub-django/pulls/42))
- feature/324-impacto-ambiental-lote ([#110](https://farga.pangea.org/ereuse/devicehub-django/pulls/110))
- [Issue 481] Improve alias error message and correctly display device Evidence Table ([#115](https://farga.pangea.org/ereuse/devicehub-django/pulls/115))
- fix search and cleanup device queries ([#116](https://farga.pangea.org/ereuse/devicehub-django/pulls/116))
- Postgres docker service and rproxy ([#86](https://farga.pangea.org/ereuse/devicehub-django/pulls/86))
- implement root alias ([#111](https://farga.pangea.org/ereuse/devicehub-django/pulls/111))
- Issue_ 372: Protection of admin user #1 ([#92](https://farga.pangea.org/ereuse/devicehub-django/pulls/92))
- Implement photographic evidence ([#104](https://farga.pangea.org/ereuse/devicehub-django/pulls/104))
- Fix navbar responsiveness ([#100](https://farga.pangea.org/ereuse/devicehub-django/pulls/100))
- dbbackup ([#106](https://farga.pangea.org/ereuse/devicehub-django/pulls/106))
- Fix premature return from loop [Issue #419] ([#97](https://farga.pangea.org/ereuse/devicehub-django/pulls/97))
- Fixes for e2e tests on evidences and admin panel ([#91](https://farga.pangea.org/ereuse/devicehub-django/pulls/91))
- automatization_pangea (B2B & B2C) ([#80](https://farga.pangea.org/ereuse/devicehub-django/pulls/80))
- New table for Evidences and user panel ([#87](https://farga.pangea.org/ereuse/devicehub-django/pulls/87))
- fix credential snapshot parsing ([#90](https://farga.pangea.org/ereuse/devicehub-django/pulls/90))
- Changes to import/upload File ([#76](https://farga.pangea.org/ereuse/devicehub-django/pulls/76))
- Re-do of lots tab on device details ([#84](https://farga.pangea.org/ereuse/devicehub-django/pulls/84))
- User dropdown with help link ([#73](https://farga.pangea.org/ereuse/devicehub-django/pulls/73))
- Changes on Admin/User Template ([#71](https://farga.pangea.org/ereuse/devicehub-django/pulls/71))
- Disable add device to archived lots and changes on template ([#62](https://farga.pangea.org/ereuse/devicehub-django/pulls/62))
- Changes on devices list and added device export ([#82](https://farga.pangea.org/ereuse/devicehub-django/pulls/82))
- bugfix_snapshot_empty ([#78](https://farga.pangea.org/ereuse/devicehub-django/pulls/78))
- Bugfix for Webform not showing up ([#81](https://farga.pangea.org/ereuse/devicehub-django/pulls/81))

</details>

Full Changelog: https://github.com/eReuse/devicehub-django/commits/v2026.1

# v2025.1

- DPP/DLT functionality ([#36](https://farga.pangea.org/ereuse/devicehub-django/pulls/36))
- Properties rework, States, StatesDefinitions, DeviceLog, and Notes ([#37](https://farga.pangea.org/ereuse/devicehub-django/pulls/37))
- inxi (take 2) ([#38](https://farga.pangea.org/ereuse/devicehub-django/pulls/38))
- upload_legacy_snapshot ([#40](https://farga.pangea.org/ereuse/devicehub-django/pulls/40))
- docker-add-idhub ([#43](https://farga.pangea.org/ereuse/devicehub-django/pulls/43))
- add did document link to device details page ([#44](https://farga.pangea.org/ereuse/devicehub-django/pulls/44))
- admin lot tags ([#47](https://farga.pangea.org/ereuse/devicehub-django/pulls/47))
- redefine_algorithm_names ([#48](https://farga.pangea.org/ereuse/devicehub-django/pulls/48))
- bugfix integration with dpp/dlt ([#50](https://farga.pangea.org/ereuse/devicehub-django/pulls/50))
- bugfix/170_180 ([#52](https://farga.pangea.org/ereuse/devicehub-django/pulls/52))
- fix parse for get better the mac in inxi file ([#53](https://farga.pangea.org/ereuse/devicehub-django/pulls/53))
- timestamp ([#54](https://farga.pangea.org/ereuse/devicehub-django/pulls/54))
- ordered from update list of devices ([#55](https://farga.pangea.org/ereuse/devicehub-django/pulls/55))
- fix search and pagination with search ([#57](https://farga.pangea.org/ereuse/devicehub-django/pulls/57))
- Adecuación de despliegue quickstart y correspondiente README.md para release 2025.1 ([#58](https://farga.pangea.org/ereuse/devicehub-django/pulls/58))
- add_lots_initial_data and other demo facilities ([#60](https://farga.pangea.org/ereuse/devicehub-django/pulls/60))
- Ui changes for issue: ereuse/projectes#194 ([#63](https://farga.pangea.org/ereuse/devicehub-django/pulls/63))
- Lot Groups view changes and e2e tests ([#64](https://farga.pangea.org/ereuse/devicehub-django/pulls/64))
- Localization ([#65](https://farga.pangea.org/ereuse/devicehub-django/pulls/65))
- Minor changes to Evidences details ([#66](https://farga.pangea.org/ereuse/devicehub-django/pulls/66))
- f31/environmental impact: Add initial implementation presented from demo-day ([#68](https://farga.pangea.org/ereuse/devicehub-django/pulls/68))
- Login changes rebase ([#69](https://farga.pangea.org/ereuse/devicehub-django/pulls/69))
- Allow reorder of Lot groups ([#70](https://farga.pangea.org/ereuse/devicehub-django/pulls/70))
- env-impact-224/initial-itu-l-1024 ([#74](https://farga.pangea.org/ereuse/devicehub-django/pulls/74))

Full Changelog: https://github.com/eReuse/IdHub/commits/v2025.1
