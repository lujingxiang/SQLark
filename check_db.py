import sqlite3
conn = sqlite3.connect('data/DB/SQLark.db')
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT Name FROM StockData")
print('Stock Names:')
names = [row[0] for row in cursor.fetchall()]
for name in names:
    print(f"  - {name}")
cursor.execute("SELECT COUNT(*) FROM StockData")
print(f'\nTotal records: {cursor.fetchone()[0]}')
cursor.execute("SELECT MIN(TradeTime), MAX(TradeTime) FROM StockData")
result = cursor.fetchone()
print(f'Date range: {result[0]} to {result[1]}')
conn.close()
