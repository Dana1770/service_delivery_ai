# Migration: add 4-metric score columns to smart.delivery
def migrate(cr, version):
    cr.execute("""
        ALTER TABLE smart_delivery
        ADD COLUMN IF NOT EXISTS score_pixel   DOUBLE PRECISION DEFAULT 0,
        ADD COLUMN IF NOT EXISTS score_jaccard DOUBLE PRECISION DEFAULT 0,
        ADD COLUMN IF NOT EXISTS score_zone    DOUBLE PRECISION DEFAULT 0,
        ADD COLUMN IF NOT EXISTS score_edge    DOUBLE PRECISION DEFAULT 0;
    """)
