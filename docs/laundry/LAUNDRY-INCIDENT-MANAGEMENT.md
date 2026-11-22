# Laundry incident management

An operator can report a missing garment, damage, a wrong tag, a wrong customer, processing damage, a stain that remains, the wrong service, a count discrepancy, or a machine failure.

The report stores the order, garment, stage, location, operator, time, description, photos, and related batch. `MISSING`, `DAMAGED`, and `PROCESSING_DAMAGE` open a claim and set the garment hold. A held garment cannot become ready.

A supervisor can investigate, assign follow-up, approve rework, resolve, and close. Resolving an incident uses `laundry:incidents:resolve`. It does not post a refund or a credit note. Compensation uses the existing finance permissions and a separate financial action.

Packing rejects a garment with a blocking incident, a failed QC result, or a tag that belongs to another order. A duplicate packing scan for the same rework count is rejected.
