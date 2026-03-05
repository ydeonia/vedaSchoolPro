-- ═══════════════════════════════════════════════════════════
-- VedaFlow: Add missing enum values to PostgreSQL
-- Run this ONCE on your database to add values that exist
-- in Python code but not yet in the DB enum types.
-- ═══════════════════════════════════════════════════════════

-- AdmissionStatus (student.py) — add TC_ISSUED and LEFT
ALTER TYPE admissionstatus ADD VALUE IF NOT EXISTS 'TC_ISSUED';
ALTER TYPE admissionstatus ADD VALUE IF NOT EXISTS 'LEFT';

-- AdmissionStatus (admission.py) — add extra workflow stages
ALTER TYPE admissionstatus ADD VALUE IF NOT EXISTS 'DOCUMENT_PENDING';
ALTER TYPE admissionstatus ADD VALUE IF NOT EXISTS 'INTERVIEW';
ALTER TYPE admissionstatus ADD VALUE IF NOT EXISTS 'ENROLLED';

-- UserRole — ensure CHAIRMAN exists (DB dump showed it but let's be safe)
ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'CHAIRMAN';

-- CertificateType — DB has short names (TRANSFER), but Python .name matches now
-- No changes needed.

-- NOTE: These ALTER TYPE commands cannot run inside a transaction in PG < 12.
-- If you get an error, run each line separately.
