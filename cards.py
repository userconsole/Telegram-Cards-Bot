import sqlite3

con = sqlite3.connect('dataBase.db')

db = con.cursor()


db.execute('''
DELETE FROM cards
WHERE id NOT IN (
    SELECT MIN(id)
    FROM cards
    GROUP BY name
)
''')

# Сохраняем изменения

# Закрываем соединение

db.execute("SELECT * FROM cards")

row = db.fetchall()

for i in row:
    print(i)
  
