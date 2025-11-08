# TODO

Gap assessment as of 10/31/2025.

## Admin

- [x] Art CRUD
  - [x] Update
  - [x] Delete
- [x] Images CRUD
  - [x] create
  - [x] update
  - [x] delete
- [x] Orders Read-only
  - [x] list
  - [x] detail
- [x] Form validation (esp. numeric inputs)
- [x] Code cleanup

## Backend

- [x] Endpoints
  - [x] Art Update
  - [x] Art Delete
  - [x] Image Create w/ "primary" logic and GCS upload
    - [x] gcs upload
    - [x] main image logic
  - [x] Image Update w/ "primary" logic
  - [x] Image Delete with GCS delete
  - [x] Orders list
  - [x] Orders detail
- [x] Drop GCP SDK for API imp
- [ ] Logging / error handling
- [ ] Write tests
- [ ] Code cleanup
- [ ] Code hardening
  - [ ] monitoring for errors and usage
  - [ ] ai audit

## Frontend

- [ ] Styling work w/ Violet
  - [ ] emails
  - [ ] navbar
  - [ ] sitewide styles
  - [ ] About page
    - [x] consider "about" model
- [x] Order return page?
- [ ] Optimistic UI instead of loading spinner

## Types

- [x] Ensure perfectly up-to-date as implementation settles

## General

- [x] Deployment
  - [x] domain setup
  - [x] neon prod db setup and optimized config
  - [x] automated deployments for stage/prod, consider "release" git tags
- [ ] GCP billing setup
- [x] data migration
- [ ] take down vps

## Future

- order status/shipping updates
- admin site bulk actions
- Prints
  - image processing, scaling up/down, watermark
  - automated fulfillment
