ALTER TABLE call_reservations ADD CONSTRAINT ck_call_reservation_bounds CHECK (upper_bound > 0 AND remaining >= 0 AND remaining <= upper_bound);
ALTER TABLE cost_events ADD CONSTRAINT ck_cost_event_amount CHECK (amount >= 0);
