import sqlite3
import os

currentlocation = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(currentlocation, "Login.db")

# Connect to the SQLite database (it will create the database if it doesn't exist)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create the Users table
cursor.execute('''
CREATE TABLE IF NOT EXISTS Users (
    username TEXT PRIMARY KEY,
    password TEXT NOT NULL,
    email TEXT NOT NULL
)
''')

# Insert a test user
test_user = ('testuser', 'password', 'testuser@example.com')
cursor.execute('INSERT INTO Users (username, password, email) VALUES (?, ?, ?)', test_user)

# Commit changes and close the connection
conn.commit()
conn.close()

print(f"Database created and test user added at {db_path}")
