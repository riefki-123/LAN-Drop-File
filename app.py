import os
import json
import socket
import qrcode
from queue import Queue
from flask import Flask, render_template, request, send_from_directory, jsonify, Response

# --- PENGGANTI Flask-SSE: Sistem Notifikasi Sederhana ---
class MessageAnnouncer:
    def __init__(self):
        self.listeners = []

    def listen(self):
        q = Queue(maxsize=5)
        self.listeners.append(q)
        return q

    def announce(self, msg):
        for i in reversed(range(len(self.listeners))):
            try:
                self.listeners[i].put_nowait(msg)
            except Queue.Full:
                del self.listeners[i]

def format_sse(data: str, event=None) -> str:
    msg = f'data: {data}\n\n'
    if event is not None:
        msg = f'event: {event}\n{msg}'
    return msg

# --- KONFIGURASI APLIKASI ---
# Menentukan folder 'static' untuk file seperti CSS, JS, dan gambar QR code
app = Flask(__name__, static_folder='static')
UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

announcer = MessageAnnouncer()

# Membuat folder yang diperlukan jika belum ada
for folder in [UPLOAD_FOLDER, STATIC_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# --- FUNGSI BANTUAN ---
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def generate_qr_code_image(ip, port):
    """Membuat QR code dan menyimpannya sebagai file gambar."""
    url = f"http://{ip}:{port}"
    qr_img_path = os.path.join(STATIC_FOLDER, 'qr_code.png')
    if not os.path.exists(qr_img_path): # Hanya generate jika belum ada
        print("Membuat QR Code...")
        qr = qrcode.make(url)
        qr.save(qr_img_path)

# --- RUTE APLIKASI ---
@app.route('/')
def index():
    files = sorted(os.listdir(app.config['UPLOAD_FOLDER']), reverse=True)
    files = [f for f in files if not f.startswith('.')]
    local_ip = get_local_ip()
    return render_template('index.html', files=files, local_ip=local_ip)

@app.route('/upload', methods=['POST'])
def upload_file():
    uploaded_files = request.files.getlist('file')
    if not uploaded_files:
        return jsonify({"status": "error", "message": "Tidak ada file yang dipilih"}), 400

    for file in uploaded_files:
        if file and file.filename != '':
            filename = file.filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            msg = format_sse(data=json.dumps({"filename": filename}), event="new_file")
            announcer.announce(msg=msg)

    return jsonify({"status": "success", "message": f"{len(uploaded_files)} file berhasil di-upload!"})

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# --- [BARU] Rute untuk menghapus file ---
@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            # Kirim notifikasi ke semua client bahwa file telah dihapus
            msg = format_sse(data=json.dumps({"filename": filename}), event="delete_file")
            announcer.announce(msg=msg)
            return jsonify({"status": "success", "message": f"File {filename} telah dihapus."})
        else:
            return jsonify({"status": "error", "message": "File tidak ditemukan."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/stream')
def stream():
    def generate():
        messages = announcer.listen()
        while True:
            msg = messages.get()
            yield msg
    return Response(generate(), mimetype='text/event-stream')

# --- MENJALANKAN SERVER ---
if __name__ == '__main__':
    HOST_IP = get_local_ip()
    PORT = 5000
    
    # Generate QR code sebagai file gambar saat server dimulai
    generate_qr_code_image(HOST_IP, PORT)

    print("======================================================")
    print("🚀 Server File Sharing Ditingkatkan!")
    print(f"Buka di browser Anda: http://{HOST_IP}:{PORT}")
    print(f"Atau di komputer ini: http://127.0.0.1:{PORT}")
    print("======================================================")
    
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)