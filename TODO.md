# TODO

Gap assessment as of 10/31/2025.

## Admin

- [x] Art CRUD
  - [x] Update
  - [x] Delete
- [ ] Images CRUD
  - [x] create
  - [ ] update
  - [ ] delete
- [ ] Orders Read-only
  - [ ] list
  - [ ] detail
- [x] Form validation (esp. numeric inputs)
- [ ] Code cleanup

## Backend

- [ ] Endpoints
  - [x] Art Update
  - [x] Art Delete
  - [ ] Image Create w/ "primary" logic and GCS upload
    - [x] gcs upload
    - [ ] main image logic
  - [ ] Image Update w/ "primary" logic
  - [ ] Image Delete with GCS delete
  - [ ] Orders list
  - [ ] Orders detail
- [ ] Logging / error handling
- [ ] Write tests
- [ ] Code cleanup
- [ ] Code hardening
  - [ ] gcs client connection, ensure doesn't slow down rest of application
  - [ ] monitoring for errors and usage
  - [ ] ai audit

## Frontend

- [ ] Styling work w/ Violet
  - [ ] emails
  - [ ] navbar
  - [ ] sitewide styles
  - [ ] About page
    - [ ] consider "about" model
- [ ] Order return page?

## Types

- [ ] Ensure perfectly up-to-date as implementation settles

## General

- [ ] Deployment
  - [ ] domain setup
  - [ ] neon prod db setup and optimized config
  - [ ] automated deployments for stage/prod, consider "release" git tags
- [ ] GCP billing setup
- [ ] data migration
- [ ] take down vps

## Future

- order status/shipping updates
- admin site bulk actions
- Prints
  - image processing, scaling up/down, watermark
  - automated fulfillment
