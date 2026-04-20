#!/usr/bin/env python3
"""Reset OpenMetadata admin password to Admin@1234"""
import bcrypt
import psycopg2

new_hash = bcrypt.hashpw(b"Admin@1234", bcrypt.gensalt(rounds=12)).decode()
print(f"New bcrypt hash: {new_hash}")

conn = psycopg2.connect(
    host="postgres",
    dbname="openmetadata_db",
    user="postgres",
    password="postgres_secret_2024",
)
cur = conn.cursor()
cur.execute(
    """
    UPDATE user_entity
    SET json = jsonb_set(
        json,
        '{authenticationMechanism,config,password}',
        to_jsonb(%s::text)
    )
    WHERE email = 'admin@open-metadata.org'
    RETURNING email, json->>'name'
    """,
    (new_hash,),
)
row = cur.fetchone()
conn.commit()
cur.close()
conn.close()
print(f"Password updated for: {row}")
