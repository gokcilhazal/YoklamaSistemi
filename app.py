from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import uygulama 
from flask import Response
from threading import Thread
import cv2
import os
import face_recognition
from datetime import datetime
import time
import uuid 
from flask import send_file
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import io
from datetime import datetime, timedelta
from database import get_db  # eğer veritabanı bağlantısını ayrı tanımladıysan buna göre ayarla

app = Flask(__name__)
app.secret_key = 'supersecretkey'

def load_known_faces(course_id):
    known_faces = {}  # student_id -> encoding

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT s.id, s.name 
        FROM students s
        JOIN student_courses sc ON s.username = sc.student_username
        WHERE sc.course_id = %s
    """, (course_id,))
    students = cursor.fetchall()

    cursor.close()
    conn.close()

    for student in students:
        student_id = student['id']
        filename_jpg = f"students/{student_id}.jpg"
        filename_png = f"students/{student_id}.png"
        path = filename_jpg if os.path.exists(filename_jpg) else filename_png

        if os.path.exists(path):
            image = face_recognition.load_image_file(path)
            encoding = face_recognition.face_encodings(image)
            if encoding:
                known_faces[student_id] = encoding[0]  # ✅ artık ID key
            else:
                print(f"[UYARI] Yüz bulunamadı: {student_id}")
        else:
            print(f"[UYARI] Fotoğraf bulunamadı: {path}")

    return known_faces


@app.route('/absentee_summary')
def absentee_summary():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT s.name, s.number, s.class_level, COUNT(*) as absence_count
    FROM students s
    JOIN attendance a ON a.student_username = s.username
    WHERE a.status = 'YOK'
    GROUP BY s.username
""")

    
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('absentee_summary.html', data=rows)

def get_student_name_from_id(student_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT name FROM students WHERE id = %s", (student_id,))
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    if result:
        return result[0]  # name
    return f"Öğrenci_{student_id}"


def recognize_and_mark_attendance(known_faces, course_id=None):
    cap = cv2.VideoCapture(1)
    recognized_ids = set()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        for face_encoding in face_encodings:
            for student_id, known_encoding in known_faces.items():
                matches = face_recognition.compare_faces([known_encoding], face_encoding)
                if matches[0] and student_id not in recognized_ids:
                    recognized_ids.add(student_id)

                    # 🔻 Şimdi veritabanından öğrenci adını al ve yoklamaya ekle
                    connection = get_db_connection()
                    cursor = connection.cursor()
                    cursor.execute("SELECT name FROM students WHERE id = %s", (student_id,))
                    result = cursor.fetchone()

                    if result:
                        student_name = result[0]
                        save_attendance_to_db(student_name, course_id)

                    cursor.close()
                    connection.close()

        # Eğer sadece 1 defa taransın istersen:
        if len(recognized_ids) > 0:
            break

    cap.release()


attendance_folder = 'attendance'
attendance_log = os.path.join(attendance_folder, 'attendance_log.txt')

if not os.path.exists(attendance_folder):
    os.makedirs(attendance_folder)

if not os.path.exists(attendance_log):
    with open(attendance_log, 'w') as f:
        pass  # Boş dosya oluştur



def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='hazal1805',
        database='school_db'
    )
    


            
@app.route('/start_attendance', methods=['POST'])
def start_attendance():
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('login'))

    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    import uuid

    course_id = request.form.get('course_id')
    print(f"[DEBUG] Formdan gelen course_id: {course_id}")

    known_faces = load_known_faces(course_id)  # ✅ student_id -> encoding
    print(f"[DEBUG] Yüklenen yüz sayısı: {len(known_faces)}")

    recognized_ids = []
    image_filenames = []

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        flash('Kamera açılamadı.', 'danger')
        return redirect(url_for('teacher_dashboard'))

    start_time = time.time()
    timeout_duration = 30  # 15 dakika
    os.makedirs('static/attendance_faces', exist_ok=True)

    while time.time() - start_time < timeout_duration:
        ret, frame = cap.read()
        if not ret:
            print("[HATA] Kamera görüntüsü alınamadı.")
            break

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        if not face_locations:
            continue

        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        known_ids = list(known_faces.keys())
        known_encodings = list(known_faces.values())

        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            face_distances = face_recognition.face_distance(known_encodings, face_encoding)
            best_match_index = np.argmin(face_distances)

            if face_distances[best_match_index] < 0.45:
                matched_id = known_ids[best_match_index]
                name = get_student_name_from_id(matched_id)
                print(f"✅ Tanıma: {name} | ID: {matched_id} | Skor: {face_distances[best_match_index]:.4f}")
            else:
                matched_id = None
                name = "Bilinmiyor"
                print(f"❌ Tanınmadı | En düşük skor: {face_distances[best_match_index]:.4f}")

            if matched_id and matched_id not in recognized_ids:
                recognized_ids.append(matched_id)
                save_attendance_to_db(matched_id, course_id)

                face_image = frame[top:bottom, left:right]
                image_filename = f"static/attendance_faces/{matched_id}_{uuid.uuid4().hex}.jpg"
                cv2.imwrite(image_filename, face_image)
                image_filenames.append(image_filename)
                color = (0, 255, 0)
            else:
                color = (0, 0, 255)

            # Görsel üzerine isim yaz
            frame_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(frame_pil)
            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except:
                font = ImageFont.load_default()
            draw.text((left, top - 30), name, font=font, fill=color)
            frame = cv2.cvtColor(np.array(frame_pil), cv2.COLOR_RGB2BGR)
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

        cv2.imshow('Kamera', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    # ✅ Devamsız olanları işaretle (ID listesi veriyoruz artık)
    mark_absent_students(course_id, recognized_ids)

    attendance_faces = session.get('attendance_faces', [])
    attendance_faces.extend(image_filenames)
    session['attendance_faces'] = attendance_faces

    flash('Yoklama tamamlandı.', 'success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user['password'], password):
            session['username'] = user['username']
            session['role'] = user['role']

            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))

            elif user['role'] == 'teacher':
                return redirect(url_for('teacher_dashboard'))

            elif user['role'] == 'student':
                # Öğrenci bilgilerini students tablosundan al
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT id, name FROM students WHERE username = %s", (username,))
                student_data = cursor.fetchone()
                cursor.close()
                conn.close()

                if student_data:
                    session['id'] = student_data['id']
                    session['name'] = student_data['name']
                else:
                    flash('Öğrenci bilgisi bulunamadı.', 'danger')
                    return redirect(url_for('login'))

                return redirect(url_for('student_dashboard'))

            else:
                flash('Bilinmeyen kullanıcı rolü.', 'danger')
                return redirect(url_for('login'))

        else:
            flash('Geçersiz kullanıcı adı veya parola.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/attendance_list', methods=['GET', 'POST'])
def attendance_list():
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('login'))

    teacher_username = session['username']
    selected_date = request.form.get('selected_date')  # formdan gelen tarih
    records = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Hoca hangi dersleri veriyor → ders id’leri
        cursor.execute("SELECT id FROM courses WHERE teacher_username = %s", (teacher_username,))
        course_ids = [row['id'] for row in cursor.fetchall()]

        if course_ids:
            format_strings = ','.join(['%s'] * len(course_ids))

            if selected_date:
                query = f"""
                   SELECT ar.id, ar.student_name, c.name AS course_name, ar.timestamp
                   FROM attendance_records ar
                   LEFT JOIN courses c ON ar.course_id = c.id
                   WHERE ar.course_id IN (%s, %s, ...) AND DATE(ar.timestamp) = %s

                    ORDER BY ar.timestamp DESC
                """
                cursor.execute(query, (*course_ids, selected_date))
            else:
                query = f"""
                    SELECT ar.id, ar.student_name, c.name AS course_name, ar.timestamp
                    FROM attendance_records ar
                    LEFT JOIN courses c ON ar.course_id = c.id
                    WHERE ar.course_id IN ({format_strings})
                    ORDER BY ar.timestamp DESC
                """
                cursor.execute(query, tuple(course_ids))

            records = cursor.fetchall()

    except mysql.connector.Error as err:
        print(f"DB error: {err}")

    finally:
        cursor.close()
        conn.close()

    return render_template(
        'attendance_list.html',
        records=records,
        selected_date=selected_date,
        now=datetime.now()  # ✅ Bunu ekle
    )
@app.route('/student_dashboard')
def student_dashboard():
    if 'username' not in session or session.get('role') != 'student':
        flash('Lütfen önce giriş yapın.', 'danger')
        return redirect(url_for('login'))

    username = session['username']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ✅ class_level alanı için alias ekleniyor
    cursor.execute("""
        SELECT 
            id, 
            name, 
            number AS school_number, 
            class_level AS class_level, 
            birth_date, 
            username 
        FROM students 
        WHERE username = %s
    """, (username,))
    student = cursor.fetchone()

    if not student:
        flash("Öğrenci bilgisi bulunamadı.", "danger")
        return redirect(url_for('login'))

    student_id = student['id']

    # Tüm dersleri al (seçim ekranı için)
    cursor.execute("""
        SELECT c.id, c.name, t.name AS teacher_name 
        FROM courses c
        JOIN teachers t ON c.teacher_username = t.username
    """)
    all_courses = cursor.fetchall()

    # Öğrencinin seçtiği dersler
    cursor.execute("""
        SELECT c.id, c.name 
        FROM student_courses sc
        JOIN courses c ON sc.course_id = c.id 
        WHERE sc.student_username = %s
    """, (username,))
    selected_courses = cursor.fetchall()
    selected_course_ids = [c['id'] for c in selected_courses]

    # Devamsızlık verileri
    cursor.execute("""
        SELECT c.name AS course_name, a.total_classes, a.absences
        FROM attendance a
        JOIN courses c ON a.course_id = c.id
        WHERE a.student_username = %s
    """, (student_id,))
    attendance = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'student_dashboard.html',
        student=student,
        all_courses=all_courses,
        courses=selected_courses,
        selected_course_ids=selected_course_ids,
        attendance=attendance,
        attendance_faces=session.get('attendance_faces', [])
    )

@app.route('/attendance_pdf')
def attendance_pdf():
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('login'))

    teacher_username = session['username']
    one_week_ago = datetime.now() - timedelta(days=7)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id FROM courses WHERE teacher_username = %s", (teacher_username,))
    courses = cursor.fetchall()
    course_ids = [course['id'] for course in courses]

    if not course_ids:
        return "Ders bulunamadı."

    placeholders = ','.join(['%s'] * len(course_ids))
    query = f"""
        SELECT ar.student_name, ar.timestamp, c.name AS course_name
        FROM attendance_records ar
        JOIN courses c ON ar.course_id = c.id
        WHERE ar.course_id IN ({placeholders}) AND ar.timestamp >= %s
        ORDER BY ar.timestamp DESC
    """
    cursor.execute(query, (*course_ids, one_week_ago))
    records = cursor.fetchall()

    cursor.close()
    conn.close()

    # PDF oluşturma
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setFont("Helvetica", 12)
    y = height - 40

    pdf.drawString(200, y, "Haftalık Yoklama Listesi")
    y -= 30
    pdf.line(40, y, width - 40, y)
    y -= 20

    for i, record in enumerate(records, 1):
        if y < 60:
            pdf.showPage()
            y = height - 40
            pdf.setFont("Helvetica", 12)
        text = f"{i}) {record['student_name']} | {record['course_name']} | {record['timestamp'].strftime('%Y-%m-%d %H:%M')}"
        pdf.drawString(50, y, text)
        y -= 20

    pdf.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="yoklama_haftalik.pdf", mimetype='application/pdf')

@app.route('/student_attendance')
def student_attendance():
    if 'username' not in session or session.get('role') != 'student':
        return redirect(url_for('login'))

    username = session.get('username')  # Öğrenci kullanıcı adı

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Öğrenci adını kullanıcı adına göre al
        cursor.execute("SELECT id, name FROM students WHERE username = %s", (username,))
        student = cursor.fetchone()

        if not student:
            return "Öğrenci bulunamadı."

        student_name = student['name']

        query = """
            SELECT ar.id, ar.student_name, c.name AS course_name, ar.timestamp
            FROM attendance_records ar
            LEFT JOIN courses c ON ar.course_id = c.id
            WHERE ar.student_name = %s
            ORDER BY ar.timestamp DESC
        """
        cursor.execute(query, (student_name,))
        records = cursor.fetchall()

        return render_template('student_attendance.html', attendance_records=records)

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
        return "Veritabanı hatası."

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
            
            

@app.route('/admin')
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT name, number, class_level, username FROM students")
    students = cursor.fetchall()

    cursor.execute("SELECT name, branch, username FROM teachers")
    teachers = cursor.fetchall()

    cursor.execute("SELECT name AS course_name, teacher_username FROM courses")
    courses = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin_dashboard.html', students=students, teachers=teachers, courses=courses)

@app.route('/admin/add-student', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        number = request.form['number']
        registration_year = request.form['registration_year']
        birth_date = request.form['birth_date']
        student_class = request.form['class']
        username = request.form['username']
        password = request.form['password']
        class_level = request.form['class_level']

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO students (name, number, registration_year, birth_date, class_level, username) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, number, registration_year, birth_date, student_class, username))
            cursor.execute("""
                INSERT INTO users (username, password, role) VALUES (%s, %s, 'student')
            """, (username, hashed_password))

            conn.commit()
            flash('Öğrenci başarıyla eklendi.', 'success')
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Hata: {err}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_dashboard'))
    return render_template('add_student.html')

@app.route('/admin/delete-student', methods=['GET', 'POST'])
def delete_student():
    if request.method == 'POST':
        username = request.form['username']
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM students WHERE username = %s", (username,))
            cursor.execute("DELETE FROM users WHERE username = %s AND role = 'student'", (username,))
            conn.commit()
            flash('Öğrenci başarıyla silindi.', 'success')
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Hata: {err}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_dashboard'))
    return render_template('delete_student.html')
@app.route('/admin/assign-multiple', methods=['GET', 'POST'])
def assign_multiple():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Tüm öğrencileri ve dersleri çek
    cursor.execute("SELECT username, name FROM students")
    students = cursor.fetchall()

    cursor.execute("SELECT id, name FROM courses")
    courses = cursor.fetchall()

    if request.method == 'POST':
        selected_students = request.form.getlist('student_usernames')
        selected_courses = request.form.getlist('course_ids')

        try:
            for username in selected_students:
                # Önce bu öğrencinin eski kayıtlarını silelim
                cursor.execute("DELETE FROM student_courses WHERE student_username = %s", (username,))
                for course_id in selected_courses:
                    cursor.execute("""
                        INSERT INTO student_courses (student_username, course_id)
                        VALUES (%s, %s)
                    """, (username, course_id))
            conn.commit()
            flash("✅ Seçilen öğrencilere ders(ler) başarıyla atandı.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"❌ Hata oluştu: {e}", "danger")

    cursor.close()
    conn.close()
    return render_template("assign_multiple.html", students=students, courses=courses)

@app.route('/admin/assignments', methods=['GET', 'POST'])
def view_assignments():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Dropdown için tüm dersleri al
    cursor.execute("""
        SELECT c.id, c.name AS course_name, t.name AS teacher_name
        FROM courses c
        JOIN teachers t ON c.teacher_username = t.username
    """)
    courses = cursor.fetchall()

    # Başlangıçta boş değerler
    selected_course_id = None
    selected_course_name = None
    students_in_course = []

    if request.method == 'POST':
        selected_course_id = request.form.get('course_id')

        # Seçilen dersin adı
        cursor.execute("SELECT name FROM courses WHERE id = %s", (selected_course_id,))
        result = cursor.fetchone()
        selected_course_name = result['name'] if result else ""

        # Bu derse kayıtlı öğrencileri getir
        cursor.execute("""
            SELECT s.name AS student_name, s.username
            FROM student_courses sc
            JOIN students s ON s.username = sc.student_username
            WHERE sc.course_id = %s
            ORDER BY s.name
        """, (selected_course_id,))
        students_in_course = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'assignments_filtered.html',
        courses=courses,
        selected_course_id=selected_course_id,
        selected_course_name=selected_course_name,
        assignments=students_in_course
    )
import mysql.connector

def get_student_by_id(user_id):
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="hazal1805",
        database="school_db"
    )
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM students WHERE id = %s", (user_id,))
    student = cur.fetchone()
    cur.close()
    conn.close()
    return student

def get_student_by_username(username):
    cur = mysql.connection.cursor(dictionary=True)
    cur.execute("SELECT * FROM students WHERE username = %s", (username,))
    student = cur.fetchone()
    cur.close()
    return student

@app.route('/admin/add-teacher', methods=['GET', 'POST'])
def add_teacher():
    if request.method == 'POST':
        name = request.form['name']
        branch = request.form.get('branch', '')  # HATA BURADA DÜZELTİLDİ
        username = request.form['username']
        password = request.form['password']

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("INSERT INTO teachers (name, branch, username) VALUES (%s, %s, %s)", (name, branch, username))
            cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, 'teacher')", (username, hashed_password))
            conn.commit()
            flash('Öğretmen başarıyla eklendi.', 'success')
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Hata: {err}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_dashboard'))
    return render_template('add_teacher.html')

@app.route('/admin/delete-teacher', methods=['GET', 'POST'])
def delete_teacher():
    if request.method == 'POST':
        username = request.form['username']
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM teachers WHERE username = %s", (username,))
            cursor.execute("DELETE FROM users WHERE username = %s AND role = 'teacher'", (username,))
            conn.commit()
            flash('Öğretmen başarıyla silindi.', 'success')
        except mysql.connector.Error as err:
            conn.rollback()
            flash(f'Hata: {err}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_dashboard'))
    return render_template('delete_teacher.html')

@app.route('/teacher', methods=['GET'])
def teacher_dashboard():
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT name FROM teachers WHERE username = %s", (session['username'],))
    teacher = cursor.fetchone()

    cursor.execute("SELECT id, name FROM courses WHERE teacher_username = %s", (session['username'],))
    courses = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('teacher_dashboard.html', teacher_name=teacher['name'], courses=courses)

known_faces_dir = 'dataset'
attendance_log = 'attendance/attendance.txt'




@app.route('/teacher/take-attendance')
def take_attendance():
    if 'username' not in session or session.get('role') != 'teacher':
        flash('Giriş yapmalısınız.', 'warning')
        return redirect(url_for('login'))

    selected_course = session.get('selected_course')
    if not selected_course:
        return redirect(url_for('select_course'))
    return render_template('take_attendance.html', course=selected_course)
camera = cv2.VideoCapture(0)  # 0: varsayılan kamera

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            # Görüntüyü jpeg formatına çevir
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            # Multipart response ile gönder
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
@app.route("/teacher/attendance")
def teacher_attendance():
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('login'))

    teacher_username = session['username']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Öğretmenin verdiği derslerin id'lerini al (teacher_username sütununa göre)
    cursor.execute("SELECT id FROM courses WHERE teacher_username = %s", (teacher_username,))
    courses = cursor.fetchall()
    course_ids = [course['id'] for course in courses]

    if not course_ids:
        attendance_data = []
    else:
        format_strings = ','.join(['%s'] * len(course_ids))
        query = f"""
            SELECT a.student_username, a.total_classes, a.absences,
                   s.name AS student_name, s.number,
                   c.name AS course_name
            FROM attendance a
            JOIN students s ON a.student_username = s.username
            JOIN courses c ON a.course_id = c.id
            WHERE a.course_id IN ({format_strings})
        """
        cursor.execute(query, tuple(course_ids))
        attendance_data = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("attendance_list.html", attendance_data=attendance_data)

@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    if request.method == 'POST':
        name = request.form['name']
        teacher_username = request.form['teacher']
        class_name = request.form['class']

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO courses (course_name, teacher_username, class) VALUES (%s, %s, %s)",
                           (name, teacher_username, class_name))
            conn.commit()
            flash("Ders başarıyla eklendi.", "success")
        except Exception as e:
            flash(f"Hata: {e}", "danger")
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('admin_dashboard'))

    return render_template('add_course.html')

# Koduna öğrencinin sadece kendi sınıfına ait dersleri görebilmesi için gerekli bölümü ekliyorum.

@app.route('/student/select-course', methods=['GET', 'POST'])
def select_course():
    if 'username' not in session or session.get('role') != 'student':
        flash('Giriş yapmanız gerekiyor.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Öğrenci bilgisi
    cursor.execute("SELECT id, name, class_level, username FROM students WHERE username = %s", (session['username'],))
    student = cursor.fetchone()

    if not student:
        flash('Bilgi bulunamadı.', 'danger')
        return redirect(url_for('student_dashboard'))

    # Öğrencinin sınıfına ait dersleri getir
    cursor.execute("SELECT class_level FROM students WHERE username = %s", (student['username'],))
    student_class = cursor.fetchone()['class_level']

    cursor.execute("""
        SELECT c.id, c.course_name, t.name AS teacher_name
        FROM courses c
        JOIN teachers t ON c.teacher_username = t.username
        WHERE c.class = %s
    """, (student_class,))
    all_courses = cursor.fetchall()

    # Öğrencinin daha önce seçtiği dersleri getir
    cursor.execute("SELECT course_id FROM student_courses WHERE student_username = %s", (student['username'],))
    selected_courses = [row['course_id'] for row in cursor.fetchall()]

    if request.method == 'POST':
        selected_ids = request.form.getlist('course_ids')

        cursor.execute("DELETE FROM student_courses WHERE student_username = %s", (student['username'],))
        for course_id in selected_ids:
            cursor.execute("INSERT INTO student_courses (student_username, course_id) VALUES (%s, %s)",
                           (student['username'], course_id))
        conn.commit()
        flash('Dersler kaydedildi.', 'success')
        return redirect(url_for('student_dashboard'))

    cursor.close()
    conn.close()
    return render_template('select_course.html', courses=all_courses, selected_courses=selected_courses)

@app.route('/delete-course', methods=['GET', 'POST'])
def delete_course():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        course_id = request.form['course_id']
        cursor.execute("DELETE FROM courses WHERE id = %s", (course_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Ders başarıyla silindi.', 'success')
        return redirect(url_for('admin_dashboard'))

    cursor.execute("SELECT id, name AS course_name, teacher_username FROM courses")
    courses = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('delete_course.html', courses=courses)



from datetime import datetime

def save_attendance_to_db(student_id, course_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ID → isim çöz
        cursor.execute("SELECT name FROM students WHERE id = %s", (student_id,))
        result = cursor.fetchone()
        if not result:
            print(f"🚫 Öğrenci ID bulunamadı: {student_id}")
            return

        student_name = result[0]

        # Aynı gün ve ders için zaten kayıtlı mı?
        cursor.execute("""
            SELECT COUNT(*) FROM attendance_records
            WHERE student_name = %s AND course_id = %s AND DATE(timestamp) = CURDATE()
        """, (student_name, course_id))
        count = cursor.fetchone()[0]

        if count == 0:
            cursor.execute("""
                INSERT INTO attendance_records (student_name, course_id, timestamp)
                VALUES (%s, %s, NOW())
            """, (student_name, course_id))
            conn.commit()
            print(f"✅ KAYDEDİLDİ: {student_name}")
        else:
            print(f"🟡 Zaten kayıt var: {student_name}")

    except mysql.connector.Error as err:
        print("❌ DB hatası:", err)

    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/update_info', methods=['GET', 'POST'])
def update_info():
    if request.method == 'POST':
        # örnek veri güncelleme işlemi (dilediğin gibi özelleştir)
        name = request.form.get("name")
        birth_date = request.form.get("birth_date")
        # Veritabanı güncelleme işlemi buraya yazılmalı
        flash("Bilgileriniz güncellendi.", "success")
        return redirect(url_for("student_dashboard"))

    # mevcut kullanıcıyı çekip forma gönder
    user_id = session.get("user_id")
    student = get_student_by_id(user_id)  # kendi fonksiyonuna göre çek
    return render_template("update_info.html", student=student)

@app.route('/register_student', methods=['POST'])
def register_student():
    number = request.form.get('number')
    name = request.form.get('name')
    username = request.form.get('username')
    password = request.form.get('password')
    class_level = request.form.get('class_level')
    registration_year = request.form.get('registration_year')
    birth_date = request.form.get('birth_date')

    hashed_password = generate_password_hash(password)  # ✅ Şifreyi hashle

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        # 1️⃣ students tablosuna ekle (hashed şifre)
        cursor.execute("""
            INSERT INTO students (number, name, username, password, class_level, registration_year, birth_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (number, name, username, hashed_password, class_level, registration_year, birth_date))

        # 2️⃣ users tablosuna da ekle
        cursor.execute("""
            INSERT INTO users (username, password, role)
            VALUES (%s, %s, %s)
        """, (username, hashed_password, 'student'))

        connection.commit()

    except mysql.connector.Error as err:
        print(f"Veritabanı hatası: {err}")
        flash("Kayıt sırasında bir hata oluştu!", "danger")

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    flash("Öğrenci başarıyla eklendi.", "success")
    return redirect('/admin/add-student')
from datetime import datetime

import mysql.connector  # dosyanın başına eklenmeli

def mark_absent_students(course_id, present_names):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT s.name
            FROM students s
            JOIN student_courses sc ON sc.student_id = s.id
            WHERE sc.course_id = %s
        """, (course_id,))
        all_students = [row[0] for row in cursor.fetchall()]

        for student_name in all_students:
            if student_name not in present_names:
                # Bugün zaten işaretlenmiş mi kontrol et
                cursor.execute("""
                    SELECT id FROM attendance_records
                    WHERE student_name = %s AND course_id = %s AND DATE(timestamp) = CURDATE()
                """, (student_name, course_id))
                already = cursor.fetchone()

                if not already:
                    cursor.execute("""
                        INSERT INTO attendance_records (student_name, course_id, timestamp)
                        VALUES (%s, %s, NOW())
                    """, (student_name, course_id))
                    print(f"🚫 Devamsız olarak eklendi: {student_name}")

        conn.commit()

    except mysql.connector.Error as err:
        print("❌ mark_absent_students DB hatası:", err)

    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/logout')
def logout():
    session.clear()  # oturum bilgisini temizle
    return redirect(url_for('login'))  # login sayfasına yönlendir

if __name__ == '__main__':
    app.run(debug=True)