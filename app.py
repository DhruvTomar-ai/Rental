from flask import Flask, request, render_template, session, redirect, flash, url_for
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime
import razorpay

from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image as keras_image
from tensorflow.keras.applications.vgg16 import preprocess_input
import numpy as np


app = Flask(__name__)
app.secret_key = 'your_secret_key'

app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

conn = sqlite3.connect('Rental_Database.db', check_same_thread=False)
curr = conn.cursor()

curr.execute("DROP TABLE IF EXISTS Payment")
model = load_model(r'C:\Users\Victus\Downloads\bedroom_model (1).h5')
razorpay_client = razorpay.Client(auth=("rzp_test_AeaHX4ErfaS1TZ", "BzyJyjvCraGtsjnM6oXCprMw"))


curr.execute('DROP TABLE IF EXISTS bookings')
# Recreate the rooms table with the correct schema
curr.execute('''
  CREATE TABLE IF NOT EXISTS userdata (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL,
      password TEXT NOT NULL
  )
''')

curr.execute('''
    CREATE TABLE IF NOT EXISTS rooms (
        room_id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_email TEXT NOT NULL,
        location TEXT NOT NULL,
        description TEXT,
        rent INTEGER NOT NULL,
        room_image TEXT
    )
''')


curr.execute('''
   CREATE TABLE IF NOT EXISTS  OwnedRooms(
     id INTEGER PRIMARY KEY AUTOINCREMENT,
       room_id INTEGER,
       renter_email TEXT,
       owner_email TEXT,
       date TEXT
   
   )
''')

curr.execute('''
    CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id INTEGER,
        renter_email TEXT,
        owner_email TEXT,
        date TEXT,
        status TEXT
    )
''')

#curr.execute("ALTER TABLE userdata ADD COLUMN role TEXT")

conn.commit()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

from flask import flash, get_flashed_messages

@app.route('/signup', methods=['GET', 'POST'])
def SignUp():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        curr.execute("SELECT * FROM userdata WHERE email = ?", (email,))
        existing_user = curr.fetchone()

        if existing_user:
            flash("Email already registered. Please log in.", "error")
            return redirect(url_for('SignUp')) 

        curr.execute(
            "INSERT INTO userdata (email, password) VALUES (?, ?)", (email, password)
        )
        conn.commit()

        session['user'] = email
        return redirect(url_for('Role'))

    return render_template('signup.html')



@app.route('/login', methods=['GET', 'POST'])
def Login():
    if request.method == 'POST':
        email = request.form['username']
        password = request.form['password']

        curr.execute("SELECT * FROM userdata WHERE email = ?", (email,))

        user = curr.fetchone()

        if user:
            db_password = user[2]
            if password == db_password:
                session['user'] = user[1]
                flash('Login Successful')
                return redirect(url_for('Role'))
            else:
                flash('Incorrect password.')
                return redirect(url_for('Login')) 
        else:
            flash('Email not found.')
            return redirect(url_for('Login'))  

    return render_template('login.html')

@app.route('/setrole', methods=['GET', 'POST'])
def Role():
    if request.method == 'POST':
        role = request.form['role']
        session['role'] = role  # Save role in session
        
        # Redirect to respective dashboard
        if role == 'owner':
            return render_template('owner_dashboard.html')  # Ensure you have a route named 'owner_dashboard'
        else:
            return redirect(url_for('renter_dashboard'))  # Ensure you have a route named 'renter_dashboard'

    return render_template('role.html')


def is_valid_bedroom_image(image_path):
    img = keras_image.load_img(image_path, target_size=(224, 224))
    img_array = keras_image.img_to_array(img)
    img_array = np.expand_dims(img_array, axis=0)
    img_array = preprocess_input(img_array)

    prediction = model.predict(img_array)
    return prediction[0][0] > 0.5  # returns True if 'bedroom interior'

@app.route('/upload_room', methods=['GET', 'POST'])
def UploadRooms():
    if request.method == 'POST':
        owner_email = session['user']
        location = request.form['location']
        description = request.form['description']
        rent = request.form['rent']
        image = request.files['room_image']

        if image and allowed_file(image.filename):
            filename = secure_filename(image.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)

            # Model Check (spam image filter)
            if not is_valid_bedroom_image(image_path):
                os.remove(image_path)  # Delete invalid image
                flash('Image does not appear to be a valid bedroom photo. Upload denied.')
                return redirect(url_for('UploadRooms'))
        else:
            flash('Invalid file format.')
            return redirect(url_for('UploadRooms'))

        # Save room details
        conn = sqlite3.connect('Rental_Database.db')
        curr = conn.cursor()
        curr.execute('''
            INSERT INTO rooms (owner_email, location, description, rent, room_image)
            VALUES (?, ?, ?, ?, ?)
        ''', (owner_email, location, description, rent, image_path))
        conn.commit()
        conn.close()

        flash('Room details uploaded successfully.')
        return redirect(url_for('UploadRooms'))

    return render_template('upload_room.html')

@app.route('/my_rooms')
def my_rooms():
    if 'user' not in session:
        flash("You must be logged in to view your rooms.")
        return redirect(url_for('Login'))

    owner_email = session['user']
    conn = sqlite3.connect('Rental_Database.db')
    curr = conn.cursor()
    curr.execute("SELECT * FROM rooms WHERE owner_email = ?", (owner_email,))
    rooms = curr.fetchall()
    conn.close()

    return render_template('my_rooms.html', rooms=rooms)

@app.route('/delete_room/<int:room_id>', methods=['POST'])
def DeleteRoom(room_id):
    if 'user' not in session:
        flash("You must be logged in to delete a room.")
        return redirect(url_for('Login'))

    conn = sqlite3.connect('Rental_Database.db')
    curr = conn.cursor()
    curr.execute("DELETE FROM rooms WHERE room_id = ?", (room_id,))
    conn.commit()
    conn.close()

    flash('Room deleted successfully.')
    return redirect(url_for('my_rooms'))

@app.route('/deleteOwnedroom/<int:room_id>', methods=['POST'])
def DeleteOwnedRoom(room_id):
    if 'user' not in session:
        flash('Please login first')
        return redirect(url_for('Login'))

    conn = sqlite3.connect('Rental_Database.db')
    curr = conn.cursor()
    curr.execute("DELETE FROM OwnedRooms WHERE room_id = ?", (room_id,))
    conn.commit()
    conn.close()

    flash('Room deleted successfully.')
    return redirect(url_for('owned_rooms'))  # Redirect back to the dashboard

@app.route('/renter_dashboard')
def renter_dashboard():
    conn = sqlite3.connect('Rental_Database.db')
    curr = conn.cursor()
    curr.execute("SELECT * FROM rooms")
    rooms = curr.fetchall()
    conn.close()
    
    return render_template('renter_dashboard.html', rooms=rooms)

@app.route('/owner_dashboard')
def ownerdashboard():
    return render_template('owner_dashboard.html')



@app.route('/room_detail/<int:room_id>')
def room_detail(room_id):
    conn = sqlite3.connect('Rental_Database.db')
    curr = conn.cursor()


    curr.execute("SELECT * FROM rooms WHERE room_id = ?", (room_id,))
    room = curr.fetchone()
    conn.close()


    if room is None:
        return "Room not found", 404

    return render_template('room_detail.html', room=room)


from datetime import datetime
import sqlite3
from flask import session, flash, redirect, url_for, request


@app.route('/book_room/<int:room_id>', methods=['POST'])
def book_room(room_id):
    if 'user' not in session or session.get('role') != 'renter':
        flash("Only renters can book rooms.")
        return redirect(url_for('Login'))

    renter_email = session['user']
    date = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect('Rental_Database.db')
    curr = conn.cursor()

    # Get owner email from room_id
    curr.execute("SELECT owner_email FROM rooms WHERE room_id = ?", (room_id,))
    result = curr.fetchone()

    if result:
        owner_email = result[0]

        # Insert booking into bookings table
        curr.execute('''
            INSERT INTO bookings (room_id, renter_email, owner_email, date)
            VALUES (?, ?, ?, ?)
        ''', (room_id, renter_email, owner_email, date))

        # Insert into OwnedRooms table
        curr.execute('''
            INSERT INTO OwnedRooms (room_id, renter_email, owner_email, date)
            VALUES (?, ?, ?, ?)
        ''', (room_id, renter_email, owner_email, date))

        conn.commit()
        flash("Room booked successfully.")
    else:
        flash("Room not found.")

    conn.close()
    return redirect(url_for('renter_dashboard'))

@app.route('/view_bookings')
def view_bookings():
    if 'user' not in session or session.get('role') != 'owner':
        flash("Only owners can view this page.")
        return redirect(url_for('Login'))

    owner_email = session['user']

    conn = sqlite3.connect('Rental_Database.db')
    curr = conn.cursor()

    curr.execute('''
        SELECT b.id, r.location, b.renter_email, b.date
        FROM bookings b
        JOIN rooms r ON b.room_id = r.room_id
        WHERE b.owner_email = ?
    ''', (owner_email,))
    
    bookings = curr.fetchall()
    conn.close()
    
    return render_template('view_bookings.html', bookings=bookings)

@app.route('/filter_rooms', methods=['POST'])
def filter_rooms():
    city_input = request.form['city']
    max_price = request.form['max_price']

    # Extract the actual city name (assuming it's the last word)
    city = city_input.strip().split()[-1]  # Gets 'Gwalior' from 'abc street Gwalior'

    conn = sqlite3.connect('Rental_Database.db')
    curr = conn.cursor()

    # Use LIKE to match locations that contain the city name
    if max_price:
        curr.execute("SELECT * FROM rooms WHERE location LIKE ? AND rent <= ?", (f"%{city}%", max_price))
    else:
        curr.execute("SELECT * FROM rooms WHERE location LIKE ?", (f"%{city}%",))

    rooms = curr.fetchall()
    conn.close()

    return render_template('renter_dashboard.html', rooms=rooms)





@app.route('/payRent/<int:room_id>')
def payRent(room_id):

    amount = 500 * 100

    order = razorpay_client.order.create(dict(
        amount=amount,
        currency='INR',
        payment_capture='1'
    ))

    return render_template('pay.html', order=order, room_id=room_id)






@app.route('/owned_rooms')
def owned_rooms():
    if 'user' not in session or session.get('role') != 'renter':
        flash("You must be logged in as a renter to view your rooms.")
        return redirect(url_for('Login'))

    renter_email = session['user']

    conn = sqlite3.connect('Rental_Database.db')
    curr = conn.cursor()
     

    curr.execute('''
        SELECT r.room_id, r.location, r.description, r.rent, o.owner_email, r.room_image
        FROM OwnedRooms o
        JOIN rooms r ON o.room_id = r.room_id
        WHERE o.renter_email = ?
    ''', (renter_email,))
    

    rooms = curr.fetchall()
    conn.close()

    return render_template('owned_rooms.html', rooms=rooms)

@app.route('/switch_to_renter')
def switch_to_renter():
    if 'user' not in session:
        return redirect(url_for('Login'))

    session['role'] = 'renter'
    return redirect(url_for('renter_dashboard'))


@app.route('/switch_to_owner')
def switch_to_owner():
    if 'user' not in session:
        return redirect(url_for('Login'))
    session['role'] = 'owner'
    return redirect(url_for('ownerdashboard'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


