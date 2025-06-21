# database.py
import mysql.connector

def get_db():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='hazal1805',
        database='school_db'
    )
