CREATE TABLE billing_receipts (
 id VARCHAR PRIMARY KEY,
 workspace VARCHAR NOT NULL,
 provider VARCHAR NOT NULL,
 provider_account VARCHAR NOT NULL,
 bill_id VARCHAR NOT NULL,
 line_id VARCHAR NOT NULL,
 budget_id VARCHAR NOT NULL REFERENCES budgets(id),
 call_id VARCHAR NOT NULL REFERENCES call_reservations(id),
 request_hash VARCHAR NOT NULL,
 currency VARCHAR NOT NULL,
 amount NUMERIC(14,4) NOT NULL CHECK(amount>=0),
 final BOOLEAN NOT NULL,
 evidence_sha256 VARCHAR NOT NULL,
 evidence_key VARCHAR NOT NULL,
 reviewed_by VARCHAR NOT NULL,
 imported_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT uq_supplier_bill_line UNIQUE(provider,provider_account,bill_id,line_id)
);
CREATE INDEX ix_billing_receipts_workspace ON billing_receipts(workspace);
