from werkzeug.security import generate_password_hash

hashed = generate_password_hash('admin1', method='pbkdf2:sha256')
print(hashed)
