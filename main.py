from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
from psycopg2 import sql
import uuid
import pickle
import numpy as np
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a random secret key

# Load the prediction model
try:
    with open('model.pickle', 'rb') as f:
        model = pickle.load(f)
    print("Model loaded successfully")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

# Database connection function
def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        port="5432",
        database="heart_dwh",
        user="postgres",
        password="A1s2d3f4"
    )
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signin', methods=['POST'])
def signin():
    username = request.form['username']
    password = request.form['password']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if username exists
        cursor.execute("SELECT Patient_ID, Name, Age, Pass, Sex, Phone_no FROM PATIENT WHERE Patient_ID = %s", (username,))
        user = cursor.fetchone()
        
        if not user:
            flash('Username incorrect')
            return redirect(url_for('index'))
        
        # Check password (Pass is at index 3)
        stored_password = user[3].strip() if user[3] else ""
        if stored_password != password:
            flash('Password incorrect')
            return redirect(url_for('index'))
        
        # Login successful
        session['user_id'] = username
        flash('Sign in successful!')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        flash(f'Error: {str(e)}')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

@app.route('/signup_page')
def signup_page():
    return render_template('signup.html')

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form['username']
    name = request.form['name']
    phone = request.form['phone']
    age = request.form['age']
    sex = request.form['sex']
    password = request.form['password']
    
    # Validate required fields
    if not all([username, name, phone, age, sex, password]):
        flash('All fields are mandatory!')
        return redirect(url_for('signup_page'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if username already exists
        cursor.execute("SELECT * FROM PATIENT WHERE Patient_ID = %s", (username,))
        if cursor.fetchone():
            flash('Username already exists!')
            return redirect(url_for('signup_page'))
        
        # Insert new user
        cursor.execute("""
            INSERT INTO PATIENT (Patient_ID, Name, Age, Pass, Sex, Phone_no, Disease_History, Surgery_History, Country)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (username, name, int(age), password, sex, phone, '', '', ''))
        
        conn.commit()
        flash('Signup successful! Please sign in.')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'Error: {str(e)}')
        return redirect(url_for('signup_page'))
    finally:
        if conn:
            conn.close()

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please sign in first')
        return redirect(url_for('index'))
    
    # Get user details
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Patient_ID, Name, Age, Sex, Phone_no FROM PATIENT WHERE Patient_ID = %s", (session['user_id'],))
        user = cursor.fetchone()
        
        # Get prediction history
        cursor.execute("""
            SELECT tr.Test_ID, tr.Chest_Pain_Type, tr.Resting_Blood_Pressure, tr.Cholesterol, 
                   tr.Fasting_Blood_Sugar, tr.Resting_ECG, tr.Max_Heart_Rate, tr.Exercise_Induced_Angina,
                   tr.ST_Depression, tr.Slope, tr.Major_Vessels, tr.Thallium,
                   p.Prediction_Result, p.Prediction_Probability
            FROM TEST_RESULT tr
            JOIN PREDICTION p ON tr.Patient_ID = p.Patient_ID
            WHERE tr.Patient_ID = %s
            ORDER BY tr.Test_ID DESC
        """, (session['user_id'],))
        history = cursor.fetchall()
        
        return render_template('dashboard.html', user=user, history=history)
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

@app.route('/predict', methods=['POST'])
def predict():
    if 'user_id' not in session:
        flash('Please sign in first')
        return redirect(url_for('index'))
    
    if model is None:
        flash('Prediction model not available')
        return redirect(url_for('dashboard'))
    
    try:
        # Get form data
        chest_pain = int(request.form['chest_pain'])
        resting_bp = int(request.form['resting_bp'])
        cholesterol = int(request.form['cholesterol'])
        fasting_bs = int(request.form['fasting_bs'])
        resting_ecg = int(request.form['resting_ecg'])
        max_hr = int(request.form['max_hr'])
        exercise_angina = int(request.form['exercise_angina'])
        st_depression = float(request.form['st_depression'])
        slope = int(request.form['slope'])
        major_vessels = int(request.form['major_vessels'])
        thallium = int(request.form['thallium'])
        
        # Get user details for prediction
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT Age, Sex FROM PATIENT WHERE Patient_ID = %s", (session['user_id'],))
        user_data = cursor.fetchone()
        
        age = user_data[0]
        sex = 1 if user_data[1] == 'Male' else 0
        
        # Prepare data for prediction (age, sex, chest_pain to thallium)
        prediction_data = [age, sex, chest_pain, resting_bp, cholesterol, fasting_bs, 
                          resting_ecg, max_hr, exercise_angina, st_depression, slope, major_vessels, thallium]
        
        # Make prediction
        prediction_array = np.array(prediction_data).reshape(1, -1)
        prediction = model.predict(prediction_array)[0]
        prediction_proba = model.predict_proba(prediction_array)[0]
        
        # Generate unique IDs
        test_id = str(uuid.uuid4())[:8]
        prediction_id = str(uuid.uuid4())[:8]
        
        # Save to TEST_RESULT table
        cursor.execute("""
            INSERT INTO TEST_RESULT (Test_ID, Patient_ID, Chest_Pain_Type, Resting_Blood_Pressure, 
                                   Cholesterol, Fasting_Blood_Sugar, Resting_ECG, Max_Heart_Rate, 
                                   Exercise_Induced_Angina, ST_Depression, Slope, Major_Vessels, Thallium)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (test_id, session['user_id'], chest_pain, resting_bp, cholesterol, fasting_bs, 
              resting_ecg, max_hr, exercise_angina, st_depression, slope, major_vessels, thallium))
        
        # Save to PREDICTION table
        result_text = "1" if prediction == 1 else "0"
        probability = float(max(prediction_proba))
        
        cursor.execute("""
            INSERT INTO PREDICTION (Prediction_ID, Patient_ID, Prediction_Result, Prediction_Probability)
            VALUES (%s, %s, %s, %s)
        """, (prediction_id, session['user_id'], result_text, probability))
        
        conn.commit()
        
        # Flash result message
        if prediction == 1:
            flash('Prediction Result: You should go for checkup. Please consult a doctor.')
        else:
            flash('Prediction Result: No immediate concern, but if you feel something unusual, consider a checkup.')
        
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        flash(f'Prediction error: {str(e)}')
        return redirect(url_for('dashboard'))
    finally:
        if conn:
            conn.close()

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)