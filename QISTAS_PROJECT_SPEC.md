# قِسطاس — Qistas
## نظام إدارة الممارسة القانونية ومكاتب المحاماة

> إدارة قانونية أكثر تنظيمًا

---

# 1. DOCUMENT PURPOSE

This document is the primary product, architecture, UX, security, and development specification for Qistas.

Qistas is a professional Arabic-first Law Practice Management System designed to help law offices manage:

- Clients
- Cases
- Lawyers
- Courts
- Hearings
- Tasks
- Deadlines
- Documents
- Contracts
- Invoices
- Payments
- Expenses
- Reports
- Notifications
- Audit Logs
- Users and Permissions

This document defines:

- Product vision
- Functional requirements
- Technical architecture
- UI/UX direction
- Data model requirements
- Security requirements
- Business rules
- Testing requirements
- Development workflow
- Phase structure
- Review process
- Phase approval gates

This document MUST be treated as the primary source of truth for the project unless explicitly changed by the user.

---

# 2. PRODUCT IDENTITY

## Product Name

قِسطاس

English:

Qistas

## Tagline

إدارة قانونية أكثر تنظيمًا

## Product Positioning

Qistas is not a generic administration dashboard.

It is a specialized professional system for law offices.

The interface should communicate:

- Trust
- Organization
- Professionalism
- Confidentiality
- Reliability
- Clarity
- Control

The product should feel like software built specifically for legal professionals.

---

# 3. PRODUCT VISION

The primary goal is to transform the daily operations of a law office into an organized digital workflow.

The system should help the user quickly answer:

- What requires my attention today?
- Which hearings are scheduled today?
- Which cases need action?
- Which tasks are overdue?
- Which clients need follow-up?
- Which invoices remain unpaid?
- Which contracts are approaching expiration?
- Which documents were recently added?
- Which cases are high priority?
- Who is responsible for each task?
- What happened recently?
- Who changed important information?

The dashboard should focus on actionable information rather than vanity metrics.

---

# 4. DESIGN PHILOSOPHY

Qistas must look like a professionally designed product.

It must NOT look:

- AI-generated
- Like a generic SaaS template
- Like a cryptocurrency dashboard
- Like a futuristic AI product
- Like a medical dashboard
- Like a copied admin template

The design should be:

- Elegant
- Serious
- Calm
- Modern
- Professional
- Human
- Practical
- Information-focused

---

# 5. VISUAL DESIGN DIRECTION

## Primary Visual Character

Use:

- Deep navy
- Dark slate
- Warm off-white
- Neutral gray
- Subtle gold/bronze accents

The color palette must remain restrained.

Do not use excessive gradients.

Avoid:

- Neon colors
- Purple-heavy UI
- Excessive glassmorphism
- Giant decorative gradients
- Floating blobs
- Excessive shadows
- Excessive rounded cards
- Decorative animations

---

# 6. TYPOGRAPHY

Preferred Arabic font:

- IBM Plex Sans Arabic

Alternative:

- Cairo

Choose one primary font and use it consistently.

Typography must prioritize:

- Readability
- Hierarchy
- Professionalism
- Arabic rendering quality

Avoid unnecessary font variations.

---

# 7. RTL REQUIREMENTS

The application is Arabic-first.

RTL must be native rather than simulated.

Requirements:

- Sidebar on the right
- Navigation aligned correctly
- Tables adapted to RTL
- Forms adapted to RTL
- Icons positioned correctly
- Breadcrumbs adapted to RTL
- Dropdowns adapted to RTL
- Modal layouts adapted to RTL
- Calendar adapted appropriately
- Text alignment handled correctly

Do not simply apply `direction: rtl` and consider the problem solved.

Review the entire interface visually.

---

# 8. RESPONSIVE DESIGN

Support:

- Desktop
- Laptop
- Tablet
- Mobile

Desktop is the primary environment.

However, mobile must remain fully usable.

Responsive behavior must be intentionally designed for:

- Sidebar
- Navigation
- Tables
- Forms
- Dashboard
- Case details
- Documents
- Finance
- Calendar
- Modals

Do not simply shrink the desktop UI.

---

# 9. TECHNOLOGY STACK

Use:

### Backend

- Python
- Django
- Django REST Framework where useful

### Database

- PostgreSQL

### Frontend

- Django Templates
- Tailwind CSS
- HTMX
- Alpine.js where appropriate
- Chart.js

### Architecture

Prefer:

Django Monolith + Server Rendered UI

Do NOT introduce a SPA unless there is a strong technical reason.

Avoid unnecessary frontend complexity.

---

# 10. ARCHITECTURE PRINCIPLES

The codebase must prioritize:

- Maintainability
- Simplicity
- Security
- Testability
- Clear responsibilities
- Reusability
- Performance

Use:

- Django apps
- Models
- Forms
- Views
- Services when business logic becomes complex
- Selectors/query services where useful
- Permissions
- Transactions
- Reusable templates/components

Do not over-engineer simple functionality.

Do not create abstractions only for theoretical future requirements.

---

# 11. RECOMMENDED DJANGO APPS

Initial structure:

```text
core/
accounts/
clients/
cases/
courts/
hearings/
tasks/
calendar/
documents/
contracts/
finance/
notifications/
reports/
audit/
```

The structure may be adjusted if a better architecture is identified.

Any major structural change must be justified.

---

# 12. CORE USERS

Initial roles:

## مدير المكتب

Full administrative access.

Can manage:

- Users
- Permissions
- Cases
- Clients
- Finance
- Documents
- Reports
- Settings
- Audit logs

## محامي

Can access functionality according to permissions, primarily:

- Assigned cases
- Clients
- Hearings
- Tasks
- Documents
- Notes
- Calendar

## مساعد محامي

Limited access to assigned work.

## موظف إداري

Administrative operations.

## موظف مالي

Financial operations.

---

# 13. CUSTOM USER MODEL

Use a custom Django User model from the beginning.

Potential fields:

```text
id
email
phone
first_name
last_name
is_active
is_staff
role
created_at
updated_at
```

The exact fields may be adjusted based on requirements.

Do not unnecessarily collect sensitive personal data.

---

# 14. AUTHENTICATION

Implement:

- Login
- Logout
- Password hashing
- Password change
- Password reset architecture
- Session management
- CSRF protection
- Secure cookies

Production must not expose authentication errors or sensitive information.

---

# 15. AUTHORIZATION

Authorization is a critical requirement.

Permissions MUST be enforced server-side.

Never rely only on:

- Hidden buttons
- Hidden menu items
- Frontend checks

Object-level authorization must be implemented where required.

Example:

If:

```text
/cases/15/
```

is accessible to Lawyer A,

that does NOT mean Lawyer A can access:

```text
/cases/16/
```

simply by changing the URL.

---

# 16. MAIN NAVIGATION

RTL sidebar:

```text
الرئيسية

القضايا
    جميع القضايا
    إضافة قضية
    الجلسات
    المحاكم
    الأطراف

العملاء
    جميع العملاء
    إضافة عميل

المكتب
    المحامون
    الموظفون
    المهام
    التقويم

المستندات والعقود
    المستندات
    العقود

المالية
    الفواتير
    المدفوعات
    المصروفات
    رسوم القضايا

التقارير

الإشعارات

الإعدادات
```

Navigation must be permission-aware.

---

# 17. DASHBOARD

The dashboard is the operational center of Qistas.

Primary question:

> ما الذي يحتاج إلى انتباهي اليوم؟

Do not build a dashboard consisting only of decorative KPI cards.

---

# 18. DASHBOARD KPIs

Potential metrics:

- القضايا النشطة
- جلسات اليوم
- المهام المتأخرة
- القضايا العاجلة
- إجمالي العملاء
- المبالغ المستحقة
- العقود القريبة من الانتهاء

Each metric must have a clear business purpose.

---

# 19. DASHBOARD SECTIONS

## Today's Hearings

Display:

- Time
- Case
- Client
- Court
- Lawyer
- Status

## Attention Required

Examples:

- Overdue tasks
- Upcoming hearings
- Unpaid invoices
- Expiring contracts
- Missing documents
- High-priority cases

## Case Analytics

Examples:

- Cases by status
- Cases by type
- Cases by lawyer
- Cases by priority

## Financial Overview

Examples:

- Total invoiced
- Paid
- Outstanding
- Expenses

## Recent Activity

Examples:

- New case
- Client created
- Payment received
- Hearing updated
- Document uploaded
- Task completed

## Upcoming Deadlines

Display upcoming important dates.

---

# 20. CLIENTS MODULE

Clients can be:

- Individuals
- Companies

Potential fields:

```text
id
client_number
type
full_name
company_name
national_id
registration_number
phone
secondary_phone
email
address
city
status
notes
created_at
updated_at
```

Only collect information necessary for the application's business purpose.

---

# 21. CLIENT PROFILE

Client page:

```text
نظرة عامة
القضايا
المستندات
العقود
الفواتير
المدفوعات
الملاحظات
النشاط
```

Financial summary:

```text
إجمالي الفواتير
المدفوع
المتبقي
```

Show relationships clearly.

---

# 22. CASES MODULE

Cases are the central domain object.

Potential fields:

```text
id
case_number
internal_reference
title
type
client
assigned_lawyer
supporting_lawyers
court
department
status
stage
priority
filing_date
next_hearing
claim_amount
description
legal_notes
internal_notes
created_at
updated_at
```

---

# 23. CASE TYPES

Initial types:

```text
مدنية
تجارية
عمالية
جزائية
أحوال شخصية
إدارية
أخرى
```

Design the architecture so types can become configurable later.

---

# 24. CASE STATUSES

Initial statuses:

```text
جديدة
قيد المتابعة
قيد المحاكمة
معلقة
منتهية
مغلقة
```

---

# 25. CASE PRIORITIES

```text
منخفضة
متوسطة
عالية
عاجلة
```

Use badges consistently.

Do not use color as the only indicator.

---

# 26. CASE DETAILS

Case workspace:

```text
نظرة عامة
الأطراف
الجلسات
المهام
المستندات
الملاحظات
المراسلات
الفواتير
المدفوعات
الخط الزمني
```

The case page should function as the lawyer's central workspace.

---

# 27. CASE PARTIES

Cases can contain multiple parties.

Types:

```text
عميل
طرف مقابل
محامي
ممثل
جهة أخرى
```

Use a relationship model rather than assuming one opposing party.

---

# 28. COURTS

Court fields may include:

```text
id
name
type
city
department
address
phone
notes
```

Courts should be reusable across cases.

---

# 29. HEARINGS

Fields:

```text
case
court
date
time
hearing_type
lawyer
room
status
notes
result
next_action
next_hearing_date
```

Statuses:

```text
مجدولة
تمت
مؤجلة
ملغاة
```

---

# 30. HEARING WORKFLOW

When a hearing is completed, allow:

- Result
- Notes
- Next action
- Next hearing date

If a next hearing date is entered:

- Update the case where appropriate.
- Add it to the calendar.
- Add it to the timeline.
- Make it available to relevant notifications.

---

# 31. TASKS

Tasks may belong to:

- Case
- Client
- Employee
- Lawyer

Fields:

```text
id
title
description
assigned_to
case
client
priority
status
due_date
completed_at
created_by
created_at
updated_at
```

Statuses:

```text
جديدة
قيد التنفيذ
مكتملة
متأخرة
ملغاة
```

---

# 32. TASK RULES

A task is overdue when:

```text
due_date < current_date
AND status != completed
```

Overdue status must be reliably determined from server-side logic.

It must not depend only on JavaScript.

---

# 33. CALENDAR

Calendar includes:

- Hearings
- Tasks
- Meetings
- Deadlines
- Contract expirations

Views:

- Monthly
- Weekly
- Daily

Every event should link to its source entity.

---

# 34. DOCUMENTS

Documents are sensitive legal records.

Documents may belong to:

- Client
- Case
- Contract
- Invoice

Potential fields:

```text
id
name
document_type
file
description
uploaded_by
client
case
contract
created_at
updated_at
```

---

# 35. DOCUMENT SECURITY

Documents MUST NOT be publicly accessible.

Do not expose predictable public URLs.

Use:

- Private storage
- Authorization before download
- File validation
- File size limits
- Safe filenames
- Permission checks
- Secure download views
- Audit logging

Never trust the uploaded filename.

Never trust client-provided MIME type alone.

---

# 36. DOCUMENT VERSIONING

The architecture should allow future versioning.

Do not build complex version control unless required.

Keep the design extensible.

---

# 37. CONTRACTS

Potential fields:

```text
contract_number
client
contract_type
start_date
end_date
value
status
description
notes
```

Statuses:

```text
مسودة
ساري
منتهي
ملغى
```

Approaching expiration should appear in relevant dashboard and notification areas.

---

# 38. FINANCE

Finance includes:

- Invoices
- Payments
- Expenses
- Case fees

All important financial calculations must be server-side.

Never trust totals calculated only on the frontend.

---

# 39. INVOICES

Potential fields:

```text
invoice_number
client
case
issue_date
due_date
subtotal
discount
tax
total
paid_amount
remaining_amount
status
notes
```

Statuses:

```text
مسودة
غير مدفوعة
مدفوعة جزئيًا
مدفوعة
متأخرة
ملغاة
```

---

# 40. PAYMENT RULES

Rules:

```text
payment_amount > 0
payment_amount <= remaining_amount
remaining_amount >= 0
paid_amount >= 0
```

A payment must never produce a negative remaining balance.

Use database transactions.

---

# 41. EXPENSES

Expenses can be related to:

- Office
- Case
- Client

Potential fields:

```text
description
amount
category
date
case
created_by
notes
```

---

# 42. MONEY HANDLING

Never use floating-point numbers for money.

Use:

```text
Decimal
```

Financial operations must use:

- Decimal arithmetic
- Database constraints where appropriate
- Transactions
- Server-side calculations
- Audit logging

---

# 43. REPORTS

Reports should provide operational value.

## Case Reports

- By status
- By type
- By lawyer
- By court
- By date
- By priority

## Client Reports

- Total clients
- Active clients
- Clients with active cases

## Hearing Reports

- Upcoming
- Completed
- Postponed
- Cancelled

## Task Reports

- Pending
- Completed
- Overdue
- By employee

## Financial Reports

- Revenue
- Payments
- Outstanding invoices
- Expenses
- Case financial performance

---

# 44. REPORT FILTERS

Useful filters:

- Date range
- Lawyer
- Client
- Case
- Status
- Type
- Court

Exports:

- CSV
- Print
- PDF where useful

---

# 45. NOTIFICATIONS

Notifications must be useful and meaningful.

Potential events:

- Hearing approaching
- Task overdue
- Invoice overdue
- Contract expiring
- Case assignment
- Document uploaded
- Deadline approaching
- Important case update

Users should have:

- Read/unread state
- Notification list
- Relevant links

Avoid notification spam.

---

# 46. AUDIT LOGGING

Audit important actions.

Potential fields:

```text
user
action
entity_type
entity_id
timestamp
ip_address
old_values
new_values
```

Potential events:

```text
Case created
Case updated
Case assigned
Hearing changed
Payment created
Invoice changed
Document uploaded
Document downloaded
Permission changed
User created
```

Audit records should be protected from normal deletion.

---

# 47. SEARCH

Global search should support:

- Clients
- Cases
- Documents
- Contracts
- Invoices

Search MUST respect permissions.

Never expose unauthorized records through search.

---

# 48. FILTERING

Major lists should support:

- Search
- Filters
- Sorting
- Pagination

Examples:

## Cases

- Search
- Status
- Type
- Priority
- Lawyer
- Court
- Date

## Clients

- Search
- Type
- Status

## Tasks

- Search
- Status
- Priority
- Assignee
- Due date

---

# 49. UI COMPONENT SYSTEM

Create reusable components:

```text
Button
Input
Textarea
Select
DatePicker
Card
Table
Badge
Modal
Dropdown
Tabs
Breadcrumb
Alert
Toast
Pagination
EmptyState
LoadingState
ConfirmDialog
FileUpload
```

Avoid duplicated UI implementations.

---

# 50. TABLES

Tables should provide:

- Clear headers
- RTL support
- Row actions
- Status badges
- Pagination
- Search
- Filtering
- Empty state
- Loading state
- Responsive behavior

On mobile, hide or collapse low-priority columns.

---

# 51. FORMS

Forms must:

- Group related fields
- Have clear labels
- Validate input
- Display Arabic errors
- Preserve submitted values on failure
- Use correct input types
- Avoid unnecessary complexity

Long forms should use logical sections.

---

# 52. EMPTY STATES

Never show:

```text
No data
```

Use meaningful Arabic messages.

Example:

```text
لا توجد قضايا حتى الآن

ابدأ بإضافة أول قضية إلى النظام.
```

Provide a relevant action when appropriate.

---

# 53. ERROR HANDLING

Implement proper:

- 400
- 403
- 404
- 500
- Validation errors
- Permission errors
- File errors
- Database errors

Production must never expose stack traces.

Error pages must match the Qistas design.

---

# 54. SECURITY

Security is a first-class requirement.

Verify:

- CSRF protection
- XSS protection
- SQL injection protection
- Authentication
- Password hashing
- Server-side authorization
- Object-level authorization
- Secure file uploads
- Private document storage
- Secure cookies
- HTTPS readiness
- Security headers
- Rate limiting where appropriate
- Audit logging
- Input validation
- Output escaping

Never rely on client-side validation for security.

---

# 55. DATABASE

Use PostgreSQL.

Database design must be:

- Relational
- Normalized
- Consistent
- Indexed appropriately

Avoid storing relational data in arbitrary JSON fields.

Use proper foreign keys and relationships.

---

# 56. DATABASE CONSTRAINTS

Use constraints where appropriate:

- Unique constraints
- Check constraints
- Foreign keys
- Not-null requirements
- Valid relationships

Do not rely exclusively on application code for data integrity.

---

# 57. DELETION POLICY

Be careful with deleting legal records.

Do not casually cascade-delete:

- Cases
- Hearings
- Payments
- Invoices
- Documents
- Audit logs

Historical information should not disappear accidentally.

Prefer appropriate archive/soft-delete strategies where business requirements justify them.

---

# 58. INDEXING

Potential indexes:

```text
case_number
client_number
phone
invoice_number
hearing_date
status
due_date
created_at
```

Do not blindly index everything.

Index based on actual query patterns.

---

# 59. PERFORMANCE

Avoid:

- N+1 queries
- Huge unpaginated querysets
- Repeated expensive dashboard queries
- Heavy template calculations
- Loading unnecessary related objects

Use:

```python
select_related()
prefetch_related()
```

where appropriate.

---

# 60. TESTING

Testing is mandatory.

Test:

## Authentication

- Login
- Logout
- Password behavior
- Unauthorized access

## Permissions

- Role access
- Object access
- URL manipulation
- Unauthorized resources

## Clients

- Create
- Update
- Validation
- Search
- Permissions

## Cases

- Create
- Update
- Assignment
- Status
- Priority
- Permissions

## Hearings

- Create
- Update
- Reschedule
- Completion

## Tasks

- Assignment
- Completion
- Overdue behavior

## Finance

- Invoice creation
- Payment
- Partial payment
- Full payment
- Invalid payment
- Balance calculation

## Documents

- Upload
- Validation
- Authorization
- Download

## Audit

- Important actions logged

---

# 61. DEMO DATA

Create realistic Arabic demo data.

Do not use:

```text
John Doe
Lorem Ipsum
Foo Bar
Test User
```

Use realistic Arabic legal scenarios.

Example:

```text
شركة الوفاق التجارية
محمود أحمد
مكتب العدالة للمحاماة
محكمة البداية
```

Demo data must make the application feel real.

---

# 62. ACCESSIBILITY

Consider:

- Keyboard navigation
- Focus states
- Color contrast
- Semantic HTML
- Labels
- Form accessibility
- Screen reader support

Do not use color as the only way to communicate status.

---

# 63. SEO

The private dashboard is not the main SEO target.

Do not waste development effort on unnecessary SEO inside the authenticated application.

If a public website is created later, handle SEO separately.

---

# 64. CODE QUALITY

Follow:

- PEP 8
- Django conventions
- Clear naming
- Small focused functions
- Reusable components
- Meaningful comments only
- No dead code
- No unnecessary duplication

Do not optimize prematurely.

Do not make code clever when simple code is clearer.

---

# 65. ENVIRONMENT CONFIGURATION

Use environment variables for:

- Secret key
- Database credentials
- Email credentials
- Storage credentials
- External services

Never commit secrets.

Provide:

```text
.env.example
```

without real credentials.

---

# 66. LOGGING

Production logging should be structured and useful.

Do not log:

- Passwords
- Tokens
- Sensitive document contents
- Unnecessary personal data
- Financial secrets

Errors should contain enough context for debugging without leaking sensitive information.

---

# 67. DEVELOPMENT WORKFLOW

Before coding:

1. Inspect repository.
2. Understand current architecture.
3. Identify existing implementation.
4. Identify dependencies.
5. Identify current phase.
6. Read relevant requirements.
7. Identify ambiguities.
8. Challenge assumptions.
9. Create implementation plan.
10. Implement only approved scope.

---

# 68. GRILL-ME WORKFLOW

Use:

```text
/grill-me
```

before major architectural decisions or major phases.

The purpose is to challenge:

- Requirements
- Assumptions
- Architecture
- Database design
- Permissions
- Business rules
- Edge cases
- Security
- Scalability

Do not treat `/grill-me` as a replacement for engineering judgment.

---

# 69. CODE REVIEW WORKFLOW

Use the available:

```text
/code-review
```

after meaningful implementation.

Review:

- Correctness
- Security
- Maintainability
- Django conventions
- Database queries
- Permissions
- Tests
- Error handling
- Architecture
- Regression risks

Critical and high-priority issues MUST be fixed before phase completion.

---

# 70. SECURITY REVIEW

Sensitive areas require additional security review.

Especially:

- Authentication
- Authorization
- Documents
- Payments
- Financial calculations
- Audit logs
- User management

A security issue must not be ignored because the feature "works".

---

# 71. STRICT PHASE CONTROL

## CRITICAL PROJECT RULE

Qistas MUST be developed one phase at a time.

The AI MUST NEVER automatically continue to another phase.

The fundamental rule is:

```text
COMPLETED ≠ APPROVED
```

Technical completion of a phase does not authorize the next phase.

---

# 72. PHASE WORKFLOW

Every phase follows:

```text
PLAN
   ↓
IMPLEMENT
   ↓
TEST
   ↓
VALIDATE
   ↓
CODE REVIEW
   ↓
SECURITY REVIEW
   ↓
FIX ISSUES
   ↓
RETEST
   ↓
FINAL REVIEW
   ↓
PHASE REPORT
   ↓
STOP
   ↓
WAIT FOR USER APPROVAL
```

The AI MUST stop after the phase report.

---

# 73. ABSOLUTE PHASE RESTRICTION

While working on Phase N:

DO NOT:

- Start Phase N+1
- Implement future features
- Prepare future features
- Refactor unrelated future modules
- Create unnecessary future infrastructure
- Assume approval
- Continue after reporting completion

If future work is discovered, record it under:

```text
Deferred Items
```

---

# 74. PHASE SCOPE ISOLATION

Each phase has a defined scope.

If a feature is not part of the current phase:

DO NOT implement it unless it is an unavoidable dependency.

If it is required as a dependency:

1. Explain why.
2. Explain the minimum required implementation.
3. Do not implement unrelated future functionality.
4. Ask for approval if the dependency materially expands scope.

---

# 75. DEPENDENCY DETECTION

If Phase N requires something planned for Phase N+X:

Report:

```text
DEPENDENCY DETECTED

Current Phase:
Phase X

Required Dependency:
...

Originally Planned For:
Phase Y

Reason:
...

Impact:
...

Recommended Action:
...
```

Do not silently expand scope.

---

# 76. PHASE COMPLETION REPORT

At the end of every phase:

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QISTAS — PHASE COMPLETION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase:
[Number + Name]

Status:
COMPLETE / INCOMPLETE

Implemented:
- ...
- ...
- ...

Files Changed:
- ...
- ...
- ...

Database Changes:
- ...
- ...

Tests:
Total:
Passed:
Failed:

Code Review:
PASS / NEEDS FIXES

Security Review:
PASS / NEEDS FIXES / NOT REQUIRED

Performance Review:
PASS / NEEDS FIXES

Known Issues:
- ...

Deferred Items:
- ...

Technical Debt:
- ...

Assumptions:
- ...

Ready for Approval:
YES / NO

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WAITING FOR USER APPROVAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

After this report:

STOP.

---

# 77. APPROVAL PROTOCOL

The next phase may only begin when the user explicitly approves.

Accepted examples:

```text
APPROVE PHASE 1
```

or:

```text
ابدأ المرحلة 2
```

or another unambiguous instruction.

Statements like:

```text
Looks good
Nice
Great
Okay
```

must not automatically authorize the next phase if the intended action is ambiguous.

When uncertain, ask for explicit approval.

---

# 78. PROJECT STATUS FILE

Maintain:

```text
PROJECT_STATUS.md
```

Example:

```markdown
# Qistas Project Status

Current Phase: 1

## Phase 1
Foundation

Status: COMPLETED
Approval: PENDING

## Phase 2
Clients

Status: NOT STARTED
Approval: N/A
```

After user approval:

```text
Status: APPROVED
```

Only then may the next phase start.

---

# 79. DEFINITION OF DONE

A phase is technically complete only when:

- Requirements implemented
- Database migrations complete
- Relevant tests pass
- Permissions tested
- Validation implemented
- Error handling implemented
- UI states handled
- Security reviewed
- Performance reviewed
- Code reviewed
- Critical issues fixed
- High-priority issues fixed
- Documentation updated where appropriate

But:

```text
TECHNICAL COMPLETE
        ≠
USER APPROVED
```

---

# 80. NO SILENT MAJOR DECISIONS

Do not silently make major decisions affecting:

- Database architecture
- Permissions
- Authentication
- Financial calculations
- Legal workflows
- Document security
- Audit logs
- API contracts
- Business rules
- Major dependencies

Explain important decisions.

Ask for approval when the decision materially affects architecture or business behavior.

---

# 81. CURRENT PHASE VALIDATION

Before every task, determine:

```text
What phase are we currently in?

Does this request belong to that phase?

Does implementing it affect another phase?

Could it change architecture?

Could it affect security?

Could it affect business rules?
```

If the request is outside the current phase, do not automatically implement it.

---

# 82. IMPLEMENTATION PHASES

The project must be implemented in the following sequence.

---

## PHASE 1 — FOUNDATION

Scope:

- Django setup
- PostgreSQL
- Environment configuration
- Custom User
- Authentication
- RBAC foundation
- Core app
- Base layout
- RTL
- Tailwind
- Reusable UI components
- Navigation
- Error pages
- Testing foundation
- Project status tracking

STOP.

WAIT FOR APPROVAL.

---

## PHASE 2 — CLIENTS

Scope:

- Client model
- Individual/company
- CRUD
- Profile
- Search
- Filtering
- Pagination
- Permissions
- Tests

STOP.

WAIT FOR APPROVAL.

---

## PHASE 3 — CASES

Scope:

- Case model
- Case types
- Statuses
- Priorities
- CRUD
- Lawyer assignment
- Courts
- Parties
- Case workspace
- Timeline foundation
- Permissions
- Tests

STOP.

WAIT FOR APPROVAL.

---

## PHASE 4 — HEARINGS + COURTS + CALENDAR

Scope:

- Courts
- Hearings
- Hearing statuses
- Results
- Rescheduling
- Next hearing
- Calendar
- Daily view
- Weekly view
- Monthly view
- Case integration
- Tests

STOP.

WAIT FOR APPROVAL.

---

## PHASE 5 — TASKS + DEADLINES

Scope:

- Tasks
- Assignment
- Status
- Priority
- Due dates
- Overdue logic
- Case/client relationships
- Dashboard integration
- Calendar integration
- Tests

STOP.

WAIT FOR APPROVAL.

---

## PHASE 6 — DOCUMENTS

Scope:

- Document model
- Secure storage
- Upload
- Download
- Authorization
- File validation
- Categories
- Case/client relationships
- Audit integration
- Security tests

STOP.

WAIT FOR APPROVAL.

---

## PHASE 7 — CONTRACTS

Scope:

- Contract model
- CRUD
- Statuses
- Dates
- Values
- Client relationship
- Documents
- Expiration tracking
- Tests

STOP.

WAIT FOR APPROVAL.

---

## PHASE 8 — FINANCE

Scope:

- Invoices
- Invoice items if required
- Payments
- Expenses
- Case fees
- Partial payments
- Balances
- Financial statuses
- Transactions
- Permissions
- Tests

STOP.

WAIT FOR APPROVAL.

---

## PHASE 9 — DASHBOARD + ANALYTICS

Scope:

- Operational dashboard
- KPIs
- Today's hearings
- Attention required
- Case analytics
- Financial overview
- Recent activity
- Deadlines
- Charts
- Query optimization

The dashboard must use real data.

STOP.

WAIT FOR APPROVAL.

---

## PHASE 10 — REPORTS

Scope:

- Case reports
- Client reports
- Hearing reports
- Task reports
- Financial reports
- Filters
- CSV
- Print
- PDF where appropriate

STOP.

WAIT FOR APPROVAL.

---

## PHASE 11 — NOTIFICATIONS

Scope:

- Notification model
- In-app notifications
- Hearing reminders
- Task reminders
- Invoice reminders
- Contract reminders
- Deadline notifications
- Read/unread state

STOP.

WAIT FOR APPROVAL.

---

## PHASE 12 — AUDIT + ADVANCED SECURITY

Scope:

- Audit improvements
- Sensitive actions
- Permission review
- Document security review
- Authentication review
- Security headers
- Rate limiting where appropriate
- Security tests
- Audit integrity

STOP.

WAIT FOR APPROVAL.

---

## PHASE 13 — QUALITY + PERFORMANCE + UX

Scope:

- Full test review
- Integration tests
- Permission testing
- N+1 review
- Query optimization
- Dashboard optimization
- Accessibility
- Responsive design
- UX polish
- Error states
- Loading states
- Empty states
- Code cleanup

STOP.

WAIT FOR APPROVAL.

---

## PHASE 14 — PRODUCTION READINESS

Scope:

- Production settings
- Environment configuration
- Static files
- Media storage
- PostgreSQL production configuration
- Logging
- Security configuration
- HTTPS readiness
- Deployment documentation
- Backup strategy
- Monitoring considerations
- Final code review
- Final security review

STOP.

---

# 83. PRODUCTION CHECKLIST

## Security

- [ ] DEBUG=False
- [ ] Secrets secured
- [ ] Secure cookies
- [ ] CSRF configured
- [ ] HTTPS ready
- [ ] Authorization verified
- [ ] Object permissions verified
- [ ] Private documents protected
- [ ] File uploads validated
- [ ] Security headers configured
- [ ] No secrets committed

## Database

- [ ] PostgreSQL production database
- [ ] Migrations tested
- [ ] Indexes reviewed
- [ ] Constraints reviewed
- [ ] Backup strategy defined

## Performance

- [ ] N+1 queries reviewed
- [ ] Lists paginated
- [ ] Dashboard optimized
- [ ] Expensive queries reviewed

## Testing

- [ ] Authentication
- [ ] Authorization
- [ ] Clients
- [ ] Cases
- [ ] Hearings
- [ ] Tasks
- [ ] Documents
- [ ] Finance
- [ ] Audit

## UX

- [ ] RTL
- [ ] Mobile
- [ ] Desktop
- [ ] Forms
- [ ] Empty states
- [ ] Loading states
- [ ] Error states
- [ ] Accessibility

---

# 84. AI BEHAVIOR

Claude must behave as a senior software engineer.

Claude should:

- Think before coding.
- Inspect before modifying.
- Explain major decisions.
- Challenge weak requirements.
- Identify edge cases.
- Prioritize security.
- Prioritize data integrity.
- Prioritize maintainability.
- Test implementation.
- Review implementation.
- Avoid unnecessary dependencies.
- Avoid unnecessary abstractions.
- Keep scope controlled.

Claude must NOT:

- Build the whole project in one pass.
- Skip tests.
- Skip reviews.
- Skip permissions.
- Ignore security.
- Invent critical business rules.
- Over-engineer.
- Continue automatically between phases.

---

# 85. REQUEST PROCESSING RULE

For every new implementation request:

## Step 1

Understand the request.

## Step 2

Inspect the repository.

## Step 3

Identify the current phase.

## Step 4

Determine whether the request belongs to the current phase.

## Step 5

Check dependencies.

## Step 6

Plan.

## Step 7

Implement only approved scope.

## Step 8

Test.

## Step 9

Review.

## Step 10

Fix.

## Step 11

Report.

## Step 12

STOP.

Never skip Step 12.

---

# 86. GIT PRACTICES

Use Git consistently.

Before major work:

```text
git status
```

Review existing changes before modifying files.

Do not overwrite user changes.

Keep commits meaningful where appropriate.

Suggested commit style:

```text
feat(clients): add client management
feat(cases): add case management
feat(hearings): add hearing workflow
fix(finance): prevent overpayment
security(documents): protect private downloads
test(cases): add permission tests
```

Do not commit secrets.

---

# 87. MIGRATIONS

Every model change must include appropriate migrations.

Before considering a phase complete:

- Verify migrations.
- Apply migrations locally.
- Test migration behavior.
- Ensure no accidental destructive migration occurs.

Do not casually delete production data through migrations.

---

# 88. API PRINCIPLES

If APIs are required:

Use Django REST Framework.

APIs must:

- Authenticate users
- Enforce permissions
- Validate input
- Return appropriate status codes
- Avoid leaking sensitive information
- Use serializers
- Be documented where appropriate

Do not create APIs for every screen if server-rendered Django is sufficient.

---

# 89. HTMX PRINCIPLES

Use HTMX where it improves UX without creating unnecessary SPA complexity.

Good use cases:

- Inline updates
- Filters
- Search
- Modals
- Partial table updates
- Notifications
- Small interactive components

Do not turn the entire application into a complicated HTMX state machine.

---

# 90. FRONTEND JAVASCRIPT PRINCIPLES

Use Alpine.js only where lightweight client-side interaction is useful.

Do not move business logic to JavaScript.

Critical business rules must remain server-side.

---

# 91. CHART PRINCIPLES

Charts must communicate useful information.

Do not add charts merely to make the dashboard look impressive.

Every chart must answer a business question.

Examples:

```text
كيف تتوزع القضايا حسب الحالة؟

كم قضية لكل محامي؟

ما حجم المبالغ المحصلة مقارنة بالمستحقة؟

كيف تتغير القضايا خلال الفترة؟
```

---

# 92. DATA PRIVACY

Legal information is sensitive.

The system should follow data-minimization principles.

Avoid exposing:

- Unnecessary personal data
- Sensitive documents
- Financial data
- Internal legal notes

to users who do not need access.

---

# 93. AUDITABILITY

Important business actions should be traceable.

The system should allow authorized administrators to understand:

```text
Who?
What?
When?
Which record?
What changed?
```

Audit logs should not be easily manipulated by normal users.

---

# 94. BUSINESS-FIRST DEVELOPMENT

Every feature must answer:

```text
What real problem does this solve?
Who uses it?
What action does it enable?
What data does it require?
What permissions does it need?
What happens when it fails?
```

Avoid features that exist only because they are common in SaaS templates.

---

# 95. NO AI-LOOKING DESIGN

Explicitly avoid:

- Purple gradients
- Excessive rounded cards
- Glass panels
- Floating decorative elements
- Generic AI icons
- Excessive sparkles
- Fake analytics
- Excessive animations
- Generic dashboard illustrations

Qistas should look like a serious professional legal application.

---

# 96. REALISTIC UX

Use realistic workflows.

Example:

A lawyer should be able to:

```text
Open dashboard
→ See today's hearings
→ Open a case
→ Review recent activity
→ View documents
→ Check pending tasks
→ Record hearing result
→ Schedule next hearing
```

The system should reduce unnecessary navigation.

---

# 97. CASE-CENTERED WORKFLOW

The case is the central workspace.

From a case, users should be able to reach relevant:

- Parties
- Hearings
- Tasks
- Documents
- Notes
- Contracts
- Invoices
- Payments
- Timeline

Avoid forcing users to repeatedly search for related records.

---

# 98. FINANCE-CENTERED WORKFLOW

From a client/case, authorized financial users should be able to understand:

```text
Invoices
Payments
Outstanding balance
Expenses
Financial history
```

Financial data must remain permission-controlled.

---

# 99. NOTIFICATION PRINCIPLE

Notifications should lead to action.

Bad:

```text
You have a notification.
```

Good:

```text
جلسة قضية أحمد علي غدًا الساعة 10:00 صباحًا.
```

Clicking should lead to the relevant record.

---

# 100. FINAL QUALITY STANDARD

Before calling Qistas production-ready, ask:

### Product

Does the system solve real law-office workflows?

### UX

Can users understand what to do without explanation?

### UI

Does it look professional and trustworthy?

### Security

Can users access data they should not see?

### Data

Can important records be accidentally deleted or corrupted?

### Finance

Are financial calculations reliable?

### Performance

Does the application remain fast with realistic data?

### Testing

Are important workflows covered?

### Maintainability

Can another Django developer understand the code?

---

# 101. FINAL DEVELOPMENT CONTRACT

Claude is not authorized to autonomously build the entire project.

Qistas is developed collaboratively.

The user controls progression.

The development contract is:

```text
ONE PHASE
    ↓
PLAN
    ↓
IMPLEMENT
    ↓
TEST
    ↓
CODE REVIEW
    ↓
SECURITY REVIEW
    ↓
FIX
    ↓
REPORT
    ↓
STOP
    ↓
USER APPROVAL
    ↓
NEXT PHASE
```

The AI MUST NOT bypass this workflow.

---

# 102. MOST IMPORTANT RULE

Remember:

```text
COMPLETED ≠ APPROVED
```

A completed phase must stop.

A passing test suite does not automatically authorize the next phase.

A successful code review does not automatically authorize the next phase.

The AI must wait for explicit user approval.

---

# 103. FIRST COMMAND TO CLAUDE CODE

After placing this file in the project root, do NOT immediately ask Claude to build the entire project.

Use:

```text
Read QISTAS_PROJECT_SPEC.md completely.

Do not implement anything yet.

First inspect the entire repository and understand its current state.

Determine whether the repository is empty, partially implemented, or already contains an existing architecture.

Then analyze PHASE 1 only.

Use /grill-me to challenge the requirements, architecture, assumptions, dependencies, security considerations, database decisions, and edge cases for PHASE 1.

Create a clear implementation plan for PHASE 1.

Do NOT write implementation code yet.

Do NOT start PHASE 2.

Do NOT modify unrelated files.

Do NOT make major architectural decisions silently.

At the end, show me:

1. Current repository assessment
2. Phase 1 requirements
3. Proposed architecture
4. Database models
5. Permission model
6. UI structure
7. Dependencies
8. Risks and edge cases
9. Testing strategy
10. Questions/decisions that require my approval

Then STOP and wait for my instruction.
```

---

# 104. FINAL INSTRUCTION TO CLAUDE

You are building:

# قِسطاس — Qistas

A professional Arabic-first Law Practice Management System.

Treat this specification as the project's primary source of truth.

Work carefully.

Work incrementally.

Do not blindly generate code.

Do not move ahead of the user.

Do not silently expand scope.

Do not compromise security for convenience.

Do not compromise data integrity for speed.

Do not sacrifice usability for technical complexity.

Use:

```text
/grill-me
```

to challenge major assumptions.

Use:

```text
/code-review
```

to review meaningful implementation.

At the end of every phase:

```text
IMPLEMENT
→ TEST
→ REVIEW
→ FIX
→ REPORT
→ STOP
```

Then wait for explicit approval.

Only after approval:

```text
NEXT PHASE
```

# ONE PHASE → REVIEW → STOP → APPROVAL → NEXT PHASE
