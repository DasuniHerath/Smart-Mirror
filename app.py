from flask import Flask, render_template, redirect, url_for, session, request, flash, Response
from authlib.integrations.flask_client import OAuth
import sqlite3
import os
import base64
import secrets
import cv2
from simple_facerec import SimpleFacerec
from werkzeug.utils import secure_filename

currentlocation = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(currentlocation, 'images')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.secret_key = os.urandom(24)

# OAuth configuration
app.config['GOOGLE_CLIENT_ID'] = '59540794108-p72it3u6i84uujld0gt1beam600vevp4.apps.googleusercontent.com'
app.config['GOOGLE_CLIENT_SECRET'] = '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'
app.config['GOOGLE_DISCOVERY_URL'] = (
    "https://accounts.google.com/.well-known/openid-configuration"
)

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url=app.config['GOOGLE_DISCOVERY_URL'],
    client_kwargs={
        'scope': 'openid email profile'
    }
)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route("/")
def homepage():
    if 'profile' in session:
        return redirect(url_for('loggedin'))
    return render_template("homepage.html")

@app.route("/login", methods=[ "POST"])
def login():
    if request.form.get('login_method') == 'manual':
        return checklogin()
    else:
        redirect_uri = url_for("authorize", _external=True)
        nonce = secrets.token_urlsafe(16)  # Generate a nonce
        session['nonce'] = nonce
        return google.authorize_redirect(redirect_uri, nonce=nonce)

@app.route("/authorize")
def authorize():
      try:
        token = google.authorize_access_token()
        nonce = session.pop('nonce', None)  # Retrieve and remove nonce from session
        if not nonce:
            flash("Nonce not found in session. Please try logging in again.")
            return redirect(url_for("homepage"))

        user_info = google.parse_id_token(token, nonce=nonce)
        session['profile'] = user_info
        return redirect(url_for("loggedin"))
      except Exception as e:
        flash(f"Authorization failed: {str(e)}")
        return redirect(url_for("homepage"))
      
@app.route("/logout")
def logout():
    session.pop('profile', None)
    return redirect("/")

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
        session['profile'] = {'username': UN}  # Mock profile info
        return redirect(url_for("loggedin"))
    else:
        flash("Invalid username or password")
        return redirect(url_for("homepage"))

@app.route("/register", methods=["GET", "POST"])
def registerpage():
    if request.method == "POST":
        dUN = request.form['DUsername']
        dPW = request.form['Dpassword']
        Uemail = request.form['EmailUser']
        user_image_data = request.form['user_image']

        with sqlite3.connect(os.path.join(currentlocation, "Login.db")) as sqlconnection:
            cursor = sqlconnection.cursor()
            cursor.execute("SELECT username FROM Users WHERE username = ?", (dUN,))
            existing_user = cursor.fetchone()

            if existing_user:
                flash("Username already exists. Please choose a different one.")
                return redirect("/register")

            if not user_image_data:
                flash("No image captured")
                return redirect("/register")

            image_data = base64.b64decode(user_image_data.split(',')[1])
            filename = secure_filename(dUN + ".png")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(image_data)

            query = "INSERT INTO Users (username, password, email) VALUES (?, ?, ?)"
            cursor.execute(query, (dUN, dPW, Uemail))
            sqlconnection.commit()
            
            return redirect("/")
    return render_template("register.html")

# Load Camera
camera_index = 0
cap = cv2.VideoCapture(camera_index)

sfr = SimpleFacerec()
sfr.load_encoding_images("images/")
if not cap.isOpened():
    print("Error: Could not open video source.")
    
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
            if not ret:
                print("Error: Could not encode frame.")
                continue
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/loggedin')
def loggedin():
    if 'profile' in session:
        return render_template('LoggedIn.html', user=session['profile'])
    return redirect(url_for('homepage'))

if __name__ == '__main__':
    app.run(debug=True)
