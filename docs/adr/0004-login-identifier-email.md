# ADR-0004 — Work email is the authentication identifier

- **Status:** Accepted — 2026-09-08
- **Deciders:** Khaled (owner), Claude (architect)
- **Related:** ADR-0027, grill B2, B3

## Context

`USERNAME_FIELD` is effectively immutable once users exist. The Phase 0 proposal assumed email; the grill flagged that the spec never confirmed it and that some offices onboard staff without individual email. The owner has now confirmed the office model.

## Decision

- Custom `User` = **subclass of `django.contrib.auth.models.AbstractUser`**.
- **`USERNAME_FIELD = "email"`.** Work email is the primary and only login identifier. `email` is required and unique. Django's `username` field is removed or left unused as an identifier.
- `REQUIRED_FIELDS` includes `first_name`, `last_name`.
- **Extension point for employee codes:** an `employee_code` field (nullable, unique-if-present) may be added later for HR/reference purposes and, if ever needed, as an alternate login — without changing `USERNAME_FIELD` semantics for existing users.
- A custom `UserManager` implements `create_user` / `create_superuser` keyed on email; email is normalized/lowercased.

## Consequences

- Every user must have a usable work email. Password self-service reset works for all users (ADR-0027 still provides an admin fallback).
- `AbstractUser` subclass keeps Django admin, permissions, and third-party integration low-risk (vs a from-scratch `AbstractBaseUser`).
- Case-insensitive uniqueness on email is enforced (functional unique index or normalization on save).
