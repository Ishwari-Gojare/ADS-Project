from flask import Flask, render_template, request, redirect, session, url_for
import MySQLdb
from datetime import datetime
from config import DB_CONFIG

app = Flask(__name__)
app.secret_key = 'asdcare@2025_secure_key'

def get_db_connection():
    return MySQLdb.connect(**DB_CONFIG)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@app.route('/')
def welcome():
    return render_template('welcome.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        role = request.form['role']
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            error = "User already exists with this email."
            conn.close()
            return render_template('register.html', error=error)

        cursor.execute("INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
                       (name, email, password, role))
        user_id = cursor.lastrowid

        if role == 'guardian':
            child_name = request.form['child_name']
            child_age = request.form['child_age']
            diagnosis = request.form['diagnosis']
            cursor.execute("INSERT INTO guardians (user_id, child_name, child_age, diagnosis) VALUES (%s, %s, %s, %s)",
                           (user_id, child_name, child_age, diagnosis))
        elif role == 'doctor':
            specialization = request.form['specialization']
            hospital = request.form['hospital']
            cursor.execute("INSERT INTO doctors (user_id, specialization, hospital) VALUES (%s, %s, %s)",
                           (user_id, specialization, hospital))

        conn.commit()
        conn.close()
        return redirect(url_for('login'))

    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        conn = get_db_connection()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s AND role = %s", (email, password, role))
        user = cursor.fetchone()

        if user:
            session['user_id'] = user['id']
            session['role'] = role

            if role == 'doctor':
                cursor.execute("SELECT id FROM doctors WHERE user_id = %s", (user['id'],))
                doctor = cursor.fetchone()
                if doctor:
                    session['doctor_id'] = doctor['id']

            conn.close()
            if role == 'guardian':
                return redirect(url_for('guardian_dashboard'))
            else:
                return redirect(url_for('doctor_dashboard'))
        else:
            conn.close()
            error = "Invalid email, password, or role."
    return render_template('login.html', error=error)

@app.route('/guardian_dashboard')
def guardian_dashboard():
    if 'user_id' not in session or session.get('role') != 'guardian':
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute("SELECT child_name AS name, child_age AS age, diagnosis FROM guardians WHERE user_id = %s", (user_id,))
    child = cursor.fetchone()

    activity_status = 'completed'
    schedule = ["Therapy session at 10AM", "Reading activity at 2PM"]
    recommendations = ["Try adding more sensory play", "Follow-up in 2 weeks"]

    conn.close()

    return render_template("guardian_dashboard.html", child=child,
                           activity_status=activity_status,
                           schedule=schedule,
                           recommendations=recommendations)

@app.route('/doctor_dashboard')
def doctor_dashboard():
    if 'doctor_id' not in session:
        return redirect(url_for('login'))

    doctor_id = session['doctor_id']
    conn = get_db_connection()
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute("""
        SELECT 
            children.id AS child_id, 
            children.name AS child_name, 
            children.age AS child_age,
            children.diagnosis,
            guardians.user_id AS guardian_id
        FROM children
        JOIN doctors_children ON children.id = doctors_children.child_id
        JOIN guardians ON children.guardian_id = guardians.user_id
        WHERE doctors_children.doctor_id = %s
    """, (doctor_id,))

    children = cursor.fetchall()
    conn.close()
    return render_template('doctor_dashboard.html', children=children)


@app.route('/add-child', methods=['GET', 'POST'])
def add_child():
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        diagnosis = request.form['diagnosis']
        routine = request.form['routine']
        guardian_email = request.args.get('email')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO children (guardian_email, name, age, diagnosis, routine) VALUES (%s, %s, %s, %s, %s)",
                       (guardian_email, name, age, diagnosis, routine))
        conn.commit()
        conn.close()

        return redirect(url_for('guardian_dashboard'))

    return render_template('add_child.html')

@app.route('/progress/<int:child_id>')
def progress(child_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN status='missed' THEN 1 ELSE 0 END) AS missed
        FROM activities WHERE child_id = %s
    """, (child_id,))
    stats = cursor.fetchone()

    cursor.execute("""
        SELECT comment, DATE_FORMAT(date, '%%b %%d, %%Y') as date 
        FROM recommendations 
        WHERE child_id = %s ORDER BY date DESC
    """, (child_id,))
    recommendations = cursor.fetchall()

    cursor.execute("SELECT guardian_id FROM children WHERE id = %s", (child_id,))
    guardian_info = cursor.fetchone()

    conn.close()

    return render_template(
        'progress.html',
        child_id=child_id,
        completed=stats['completed'] or 0,
        missed=stats['missed'] or 0,
        recommendations=recommendations,
        guardian_id=guardian_info['guardian_id']
    )

@app.route('/messaging', methods=['GET', 'POST'])
def messaging():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    role = session['role']

    conn = get_db_connection()
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)

    if role == 'guardian':
        cursor.execute("SELECT id FROM doctors LIMIT 1")
        recipient = cursor.fetchone()
        recipient_id = recipient['id'] if recipient else None
        recipient_role = 'doctor'
    else:
        cursor.execute("SELECT id FROM guardians LIMIT 1")
        recipient = cursor.fetchone()
        recipient_id = recipient['id'] if recipient else None
        recipient_role = 'guardian'

    if request.method == 'POST':
        message_text = request.form['message']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            INSERT INTO messages (sender_id, sender_role, receiver_id, receiver_role, content, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, role, recipient_id, recipient_role, message_text, timestamp))
        conn.commit()

    cursor.execute("""
        SELECT sender_role, content, timestamp FROM messages
        WHERE (sender_id = %s AND receiver_id = %s)
           OR (sender_id = %s AND receiver_id = %s)
        ORDER BY timestamp ASC
    """, (user_id, recipient_id, recipient_id, user_id))
    messages = cursor.fetchall()
    conn.close()

    return render_template('messaging.html', messages=messages)

@app.route('/activity')
def activity_page():
    if 'user_id' not in session or session.get('role') != 'guardian':
        return redirect(url_for('login'))
    return render_template('activity.html')

@app.route('/game/<game_type>')
def game(game_type):
    return redirect(url_for('guardian_dashboard'))

@app.route('/rewards')
def rewards():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute("""
        SELECT COUNT(*) AS completed_tasks FROM activities
        WHERE child_id IN (SELECT id FROM children WHERE guardian_id = %s)
          AND status = 'completed'
    """, (user_id,))
    completed_count = cursor.fetchone()['completed_tasks'] or 0

    cursor.execute("""
        SELECT g.child_name AS name, COUNT(a.id) AS points
        FROM activities a
        JOIN children c ON a.child_id = c.id
        JOIN guardians g ON c.guardian_id = g.user_id
        WHERE a.status = 'completed'
        GROUP BY c.id ORDER BY points DESC LIMIT 5
    """)
    leaderboard = cursor.fetchall()

    conn.close()
    return render_template('rewards.html', completed_count=completed_count, leaderboard=leaderboard)

@app.route('/notifications')
def notifications():
    if 'user_id' not in session or session.get('role') != 'guardian':
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute("SELECT id FROM children WHERE guardian_id = %s", (user_id,))
    child_ids = [row['id'] for row in cursor.fetchall()]

    missed_tasks, doctor_notes = [], []

    if child_ids:
        cursor.execute("""
            SELECT id, child_id, activity_name, DATE_FORMAT(date, '%%b %%d, %%Y') AS date
            FROM activities
            WHERE child_id IN %s AND status = 'missed'
            ORDER BY date DESC
        """, (tuple(child_ids),))
        missed_tasks = cursor.fetchall()

        cursor.execute("""
            SELECT child_id, comment, DATE_FORMAT(date, '%%b %%d, %%Y') AS date
            FROM recommendations
            WHERE child_id IN %s
            ORDER BY date DESC
        """, (tuple(child_ids),))
        doctor_notes = cursor.fetchall()

    conn.close()
    return render_template('notifications.html', missed_tasks=missed_tasks, doctor_notes=doctor_notes)

@app.route('/download_report/<int:child_id>')
def download_report(child_id):
    return f"PDF Report for Child ID: {child_id} (Coming Soon)"

@app.route('/view_progress')
def view_progress():
    if 'user_id' not in session or session.get('role') != 'guardian':
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute("""
        SELECT c.id, c.name, c.age, c.diagnosis,
               SUM(CASE WHEN a.status='completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN a.status='missed' THEN 1 ELSE 0 END) AS missed
        FROM children c
        LEFT JOIN activities a ON c.id = a.child_id
        WHERE c.guardian_id = %s
        GROUP BY c.id
    """, (user_id,))
    progress_data = cursor.fetchall()
    conn.close()

    return render_template('view_progress.html', progress_data=progress_data)

@app.route('/consult_doctor', methods=['GET', 'POST'])
def consult_doctor():
    if 'user_id' not in session or session.get('role') != 'guardian':
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(MySQLdb.cursors.DictCursor)

    # Fetch doctors for dropdown
    cursor.execute("SELECT id, name FROM users WHERE role = 'doctor'")
    doctors = cursor.fetchall()

    if request.method == 'POST':
        doctor_id = request.form['doctor_id']
        message = request.form['message']
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Insert into messages table
        cursor.execute("""
            INSERT INTO messages (sender_id, sender_role, receiver_id, receiver_role, content, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, 'guardian', doctor_id, 'doctor', message, timestamp))
        conn.commit()
        success = True
    else:
        success = False

    conn.close()
    return render_template('consult_doctor.html', doctors=doctors, success=success)


if __name__ == '__main__':
    app.run(debug=True)
