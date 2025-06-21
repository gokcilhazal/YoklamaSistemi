import cv2
import os
import numpy as np
from datetime import datetime
import mysql.connector

# LBPH yüz tanıyıcı oluştur
recognizer = cv2.face.LBPHFaceRecognizer_create()
# Haar cascade yükle
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
faces_dir = "faces"


def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='hazal1805',
        database='school_db'
    )


def prepare_training_data():
    faces = []
    labels = []
    label_map = {}
    label_id = 0

    for name in os.listdir(faces_dir):
        person_dir = os.path.join(faces_dir, name)
        if not os.path.isdir(person_dir):
            continue

        for filename in os.listdir(person_dir):
            img_path = os.path.join(person_dir, filename)
            img = cv2.imread(img_path)
            if img is None:
                print(f"Resim okunamadı: {img_path}")
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            detected = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

            for (x, y, w, h) in detected:
                face = gray[y:y+h, x:x+w]
                face = cv2.resize(face, (200, 200))
                faces.append(face)
                labels.append(label_id)

        label_map[label_id] = name
        label_id += 1

    return faces, labels, label_map


def main():
    print("Eğitim verisi hazırlanıyor...")
    faces, labels, label_map = prepare_training_data()

    if len(faces) == 0:
        print("Yüz resmi bulunamadı, eğitim yapılamadı!")
        return

    print(f"{len(faces)} yüz bulundu, eğitim başlıyor...")
    recognizer.train(faces, np.array(labels))
    print("Eğitim tamamlandı, kameradan yüz tanıma başlıyor...")

    # Kamera açılırken DirectShow API kullanılıyor (Windows için)
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print("Kamera açılamadı!")
        return

    recorded = set()
    show_unknown_message = True  # Bilinmeyen yüz mesajı için kontrol

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Kare okunamadı, döngü sonlandırılıyor.")
            break

        frame = cv2.flip(frame, 1)  # Aynalama efekti

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detected = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

        unknown_shown = False

        for (x, y, w, h) in detected:
            face = gray[y:y+h, x:x+w]
            face = cv2.resize(face, (200, 200))

            try:
                label, confidence = recognizer.predict(face)
                predicted_name = label_map.get(label, "Bilinmiyor")
            except Exception as e:
                print(f"Prediction hatası: {e}")
                continue

            if confidence < 60:
                if predicted_name not in recorded:
                    recorded.add(predicted_name)
                    print(f"{predicted_name} tanındı, yoklama kaydediliyor...")

                    now = datetime.now()
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO attendance (username, timestamp) VALUES (%s, %s)",
                            (predicted_name, now)
                        )
                        conn.commit()
                    except mysql.connector.Error as err:
                        print(f"Veritabanı hatası: {err}")
                    finally:
                        cursor.close()
                        conn.close()

                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(frame, f"{predicted_name} ({int(confidence)})", (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                print(f"Tahmin: {predicted_name}, Confidence: {confidence:.2f}")
                show_unknown_message = True  # Sonraki bilinmeyen için mesaj aktif
            else:
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 2)
                cv2.putText(frame, "Bilinmiyor", (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                if show_unknown_message and not unknown_shown:
                    print("Yüz tanınamadı veya emin değil.")
                    show_unknown_message = False
                    unknown_shown = True

        cv2.imshow('Yoklama Kamerası', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Çıkış yapılıyor...")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
