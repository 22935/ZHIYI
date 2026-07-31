DO $$
DECLARE
    actual_type text;
    actual_length integer;
BEGIN
    SELECT data_type, character_maximum_length
      INTO actual_type, actual_length
      FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'password_hash';

    IF actual_type IS NULL THEN
        ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);
    ELSIF actual_type <> 'character varying' OR actual_length <> 255 THEN
        RAISE EXCEPTION 'users.password_hash schema drift: type=%, length=%', actual_type, actual_length;
    END IF;
END $$;
