from flask import Flask, render_template, redirect, url_for, session, request, flash, Response, jsonify
from authlib.integrations.flask_client import OAuth
import sqlite3
import os
import requests
import base64
import secrets
import cv2
from simple_facerec import SimpleFacerec
from werkzeug.utils import secure_filename
from PIL import Image
import io
# Load model directly
from transformers import AutoImageProcessor, AutoModelForImageClassification

processor = AutoImageProcessor.from_pretrained("imfarzanansari/skintelligent-acne")
model = AutoModelForImageClassification.from_pretrained("imfarzanansari/skintelligent-acne")

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

        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

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

            try:
                image_data = base64.b64decode(user_image_data.split(',')[1])
                filename = secure_filename(dUN + ".png")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                print(f"Saving image to {filepath}")
                with open(filepath, 'wb') as f:
                    f.write(image_data)
            except Exception as e:
                flash(f"Error saving image: {str(e)}")
                return redirect("/register")

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
            print("Error: Failed to read frame.")
            break

        face_locations, face_names = sfr.detect_known_faces(frame)
        for face_loc, name in zip(face_locations, face_names):
            y1, x2, y2, x1 = face_loc[0], face_loc[1], face_loc[2], face_loc[3]
            cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 0, 200), 2)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 200), 2)

        # Request acne classification for the first detected face
        if face_locations:
            try:
                # Crop the first detected face
                x1, y1, x2, y2 = face_locations[0]
                face_image = frame[y1:y2, x1:x2]

                # Convert the cropped face to a PIL image and preprocess it
                face_pil = Image.fromarray(face_image).convert('RGB')
                inputs = processor(images=face_pil, return_tensors="pt")
                
                # Run the model to get predictions
                outputs = model(**inputs)
                predictions = outputs.logits.argmax(-1).item()
                
                # Assuming the model's labels are ['No Acne', 'Acne']
                labels = ['No Acne', 'Acne']
                result = labels[predictions]

                # Display the result on the video frame
                cv2.putText(frame, f'Acne: {result}', (10, 50), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 255, 0), 2)
            except Exception as e:
                print(f"Error during acne classification: {e}")
                cv2.putText(frame, 'Acne: Error', (10, 50), cv2.FONT_HERSHEY_DUPLEX, 1, (0, 0, 255), 2)

        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            print("Error: Failed to encode frame.")
            continue
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    try:
        return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
    except Exception as e:
        print(f"Error in video feed: {e}")
        return "Error: Video feed is unavailable."


@app.route('/loggedin')
def loggedin():
    if 'profile' in session:
        return render_template('LoggedIn.html', user=session['profile'])
    return redirect(url_for('homepage'))

@app.route('/classify_face_acne', methods=['GET'])
def classify_face_acne():
    # Logic to process the video frame and classify acne
    result = 'No Acne Detected'  # Replace with actual result
    return jsonify({'result': result})

@app.route('/classify_acne', methods=['POST'])
def classify_acne():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)

    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)

    if file and allowed_file(file.filename):
        try:
            image = Image.open(file.stream).convert('RGB')  # Ensure image is in RGB format
            inputs = processor(images=image, return_tensors="pt")
            outputs = model(**inputs)
            predictions = outputs.logits.argmax(-1).item()

            # Assuming the model's labels are ['No Acne', 'Acne']
            labels = ['No Acne', 'Acne']
            result = labels[predictions]

            return jsonify({'result': result})
        except Exception as e:
            flash(f"Error processing image: {str(e)}")
            return redirect(request.url)

    flash('Invalid file format')
    return redirect(request.url)

if __name__ == '__main__':
    app.run(debug=True)
