import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash

try:
    # Veritabanı bağlantısı
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='hazal1805',
        database='school_db'  # Veritabanı daha önce oluşturulmuş olmalı
    )

    if conn.is_connected():
        cursor = conn.cursor()

        # Öğrenciler tablosu
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            number VARCHAR(50) NOT NULL
        )
        ''')

        # Öğretmenler tablosu
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            branch VARCHAR(255) NOT NULL
        )
        ''')

        # Kullanıcılar tablosu
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role ENUM('admin', 'teacher') NOT NULL
        )
        ''')

        # Yoklama tablosu (isteğe bağlı olarak ekledim)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            date DATE NOT NULL,
            status ENUM('present', 'absent') NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        )
        ''')

        # Admin ve öğretmen kullanıcılarını ekle
        users = [
            ('admin', generate_password_hash('admin1'), 'admin'),
            ('ogretmen1', generate_password_hash('4567'), 'teacher')
        ]

        for username, password, role in users:
            try:
                cursor.execute(
                    "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                    (username, password, role)
                )
                print(f"{username} eklendi.")
            except mysql.connector.errors.IntegrityError:
                print(f"{username} zaten var.")

        conn.commit()
        print("Veritabanı ve tüm tablolar başarıyla oluşturuldu.")

except Error as e:
    print("Hata oluştu:", e)

finally:
    if conn.is_connected():
        cursor.close()
        conn.close()
