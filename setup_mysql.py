import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash

def setup_mysql():
    try:
        # MySQL bağlantısı
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password='hazal1805',
            database='school_db'  # Bu veritabanı phpMyAdmin'de veya MySQL CLI'de önceden oluşturulmuş olmalı
        )

        if conn.is_connected():
            print("MySQL bağlantısı başarılı.")
            cursor = conn.cursor()

            # Öğrenci tablosu
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                number VARCHAR(50) NOT NULL
            )
            ''')

            # Öğretmen tablosu
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS teachers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                branch VARCHAR(255) NOT NULL
            )
            ''')

            # Kullanıcı tablosu
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role ENUM('admin', 'teacher') NOT NULL
            )
            ''')

            # Yoklama tablosu
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                date DATE NOT NULL,
                status ENUM('present', 'absent') NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
            ''')

            # Varsayılan kullanıcılar
            users = [
                ('admin', generate_password_hash('1234'), 'admin'),
                ('ogretmen1', generate_password_hash('4567'), 'teacher')
            ]

            for username, password, role in users:
                try:
                    cursor.execute(
                        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                        (username, password, role)
                    )
                    print(f"Kullanıcı eklendi: {username}")
                except mysql.connector.errors.IntegrityError:
                    print(f"Kullanıcı zaten var: {username}")

            conn.commit()
            print("Tüm tablolar oluşturuldu ve kullanıcılar eklendi.")

    except Error as e:
        print("Hata oluştu:", e)

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
            print("MySQL bağlantısı kapatıldı.")

# Script çalıştırıldığında otomatik kurulum
if __name__ == "__main__":
    setup_mysql()
