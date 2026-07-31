DO $$
DECLARE
    actual_type text;
    actual_length integer;
    stable_key_constraint text;
BEGIN
    SELECT data_type, character_maximum_length INTO actual_type, actual_length
      FROM information_schema.columns
     WHERE table_schema='public' AND table_name='conversations' AND column_name='title';
    IF actual_type IS NULL THEN
        ALTER TABLE conversations ADD COLUMN title VARCHAR(200);
    ELSIF actual_type <> 'character varying' OR actual_length <> 200 THEN
        RAISE EXCEPTION 'conversations.title schema drift: type=%, length=%', actual_type, actual_length;
    END IF;

    actual_type := NULL; actual_length := NULL;
    SELECT data_type, character_maximum_length INTO actual_type, actual_length
      FROM information_schema.columns
     WHERE table_schema='public' AND table_name='messages' AND column_name='file_url';
    IF actual_type IS NULL THEN
        ALTER TABLE messages ADD COLUMN file_url VARCHAR(255);
    ELSIF actual_type <> 'character varying' OR actual_length <> 255 THEN
        RAISE EXCEPTION 'messages.file_url schema drift: type=%, length=%', actual_type, actual_length;
    END IF;

    actual_type := NULL; actual_length := NULL;
    SELECT data_type, character_maximum_length INTO actual_type, actual_length
      FROM information_schema.columns
     WHERE table_schema='public' AND table_name='roles' AND column_name='stable_key';
    IF actual_type IS NULL THEN
        ALTER TABLE roles ADD COLUMN stable_key VARCHAR(100);
    ELSIF actual_type <> 'character varying' OR actual_length <> 100 THEN
        RAISE EXCEPTION 'roles.stable_key schema drift: type=%, length=%', actual_type, actual_length;
    END IF;

    IF EXISTS (
        SELECT 1 FROM roles
         WHERE role_type='BUILTIN' AND name IN ('律师','教师','程序员','作家')
         GROUP BY name HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'duplicate builtin roles prevent deterministic stable-key migration';
    END IF;

    SELECT pg_get_constraintdef(oid) INTO stable_key_constraint
      FROM pg_constraint
     WHERE conrelid = 'roles'::regclass
       AND conname = 'uk_roles_stable_key';
    IF stable_key_constraint IS NULL THEN
        ALTER TABLE roles ADD CONSTRAINT uk_roles_stable_key UNIQUE (stable_key);
    ELSIF regexp_replace(lower(stable_key_constraint), '\s+', '', 'g') <> 'unique(stable_key)' THEN
        RAISE EXCEPTION 'uk_roles_stable_key constraint drift: %', stable_key_constraint;
    END IF;
END $$;
