from flask import Flask, render_template, Response, request, redirect
import cv2
import os
import sqlite3
from simple_facerec import SimpleFacerec
from werkzeug.utils import secure_filename

currentlocation = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(currentlocation, 'images')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.secret_key = 'your_secret_key'

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route("/")
def homepage():
    return render_template("homepage.html")

@app.route("/", methods=["POST"])
def checklogin():
    try:
        UN = request.form['username']
        PW = request.form['password']
    except KeyError as e:
        return f"KeyError: {str(e)} - form data: {request.form}", 400

    sqlconnection = sqlite3.Connection(os.path.join(currentlocation, "Login.db"))
    cursor = sqlconnection.cursor()
    query = "SELECT username, password FROM Users WHERE username = ? AND password = ?"
    cursor.execute(query, (UN, PW))
    rows = cursor.fetchall()
    if len(rows) == 1:
        return render_template("LoggedIn.html")
    else:
        return redirect("/register")

@app.route("/register", methods=["GET", "POST"])
def registerpage():
    if request.method == "POST":
        dUN = request.form['DUsername']
        dPW = request.form['Dpassword']
        Uemail = request.form['EmailUser']

        # Check if the post request has the file part
        if 'user_image' not in request.files:
            return "No file part"
        file = request.files['user_image']
        # If the user does not select a file, the browser submits an empty file without a filename
        if file.filename == '':
            return "No selected file"
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Save the user information in the database
            sqlconnection = sqlite3.Connection(os.path.join(currentlocation, "Login.db"))
            cursor = sqlconnection.cursor()
            query = "INSERT INTO Users (username, password, email) VALUES (?, ?, ?)"
            cursor.execute(query, (dUN, dPW, Uemail))
            sqlconnection.commit()
            
            return redirect("/")
    return render_template("register.html")

# Encode faces from a folder
sfr = SimpleFacerec()
sfr.load_encoding_images("images/")

# Load Camera
camera_index = 0
cap = cv2.VideoCapture(camera_index)

def gen_frames():
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        else:
            face_locations, face_names = sfr.detect_known_faces(frame)
            for face_loc, name in zip(face_locations, face_names):
                y1, x2, y2, x1 = face_loc[0], face_loc[1], face_loc[2], face_loc[3]
                cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 0, 200), 2)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 200), 2)
            
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(debug=True)
