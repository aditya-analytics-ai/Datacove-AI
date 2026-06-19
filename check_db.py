import mysql.connector

try:
    conn = mysql.connector.connect(
        host='localhost', port=3306,
        user='root', password='newpassword',
        database='datacove'
    )
    cur = conn.cursor()

    # Show tables
    cur.execute('SHOW TABLES')
    tables = [t[0] for t in cur.fetchall()]
    print(f"Connected to 'datacove' DB")
    print(f"Tables ({len(tables)}):")

    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
        count = cur.fetchone()[0]
        print(f"  {table}: {count} rows")

    # Check DB size
    cur.execute("""
        SELECT table_schema AS db,
               ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS size_mb
        FROM information_schema.tables
        WHERE table_schema = 'datacove'
        GROUP BY table_schema
    """)
    row = cur.fetchone()
    if row:
        print(f"\nDB size: {row[1]} MB")

    conn.close()
    print("\nDatabase OK")

except Exception as e:
    print(f"Error: {e}")
