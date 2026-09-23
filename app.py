import os
import sqlite3
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'anu_space_private_secret_key_998877')

DATABASE = os.path.join('/tmp', 'anu_space.db')

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with get_db() as db:
        # Diary security config
        db.execute('''
            CREATE TABLE IF NOT EXISTS diary_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Diary entries table
        db.execute('''
            CREATE TABLE IF NOT EXISTS diary_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                entry_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Daily coding focus goals table
        db.execute('''
            CREATE TABLE IF NOT EXISTS focus_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_date DATE UNIQUE NOT NULL,
                platform TEXT DEFAULT 'NeetCode',
                target_count INTEGER DEFAULT 2,
                completed_count INTEGER DEFAULT 0
            )
        ''')
        # Individual problem logs
        db.execute('''
            CREATE TABLE IF NOT EXISTS focus_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date DATE NOT NULL,
                platform TEXT NOT NULL,
                problem_title TEXT NOT NULL,
                difficulty TEXT DEFAULT 'Medium',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Coding practice reminders
        db.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT DEFAULT 'NeetCode',
                target_count INTEGER DEFAULT 2,
                time_str TEXT DEFAULT '7:30 PM',
                frequency TEXT DEFAULT 'Every day',
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # Insert default reminder if none exists
        cursor = db.execute('SELECT COUNT(*) FROM reminders')
        if cursor.fetchone()[0] == 0:
            db.execute('''
                INSERT INTO reminders (platform, target_count, time_str, frequency, is_active)
                VALUES ('NeetCode', 2, '7:30 PM', 'Every day', 1)
            ''')
            
        db.commit()

init_db()

def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')

def get_today_formatted():
    return datetime.now().strftime('%A, %B %d, %Y')

def get_today_focus():
    today = get_today_str()
    with get_db() as db:
        row = db.execute('SELECT * FROM focus_goals WHERE goal_date = ?', (today,)).fetchone()
        if not row:
            # Fetch last setting or default
            last = db.execute('SELECT platform, target_count FROM focus_goals ORDER BY id DESC LIMIT 1').fetchone()
            platform = last['platform'] if last else 'NeetCode'
            target = last['target_count'] if last else 2
            db.execute('''
                INSERT INTO focus_goals (goal_date, platform, target_count, completed_count)
                VALUES (?, ?, ?, 0)
            ''', (today, platform, target))
            db.commit()
            row = db.execute('SELECT * FROM focus_goals WHERE goal_date = ?', (today,)).fetchone()
        return dict(row)

def get_active_reminder():
    with get_db() as db:
        row = db.execute('SELECT * FROM reminders WHERE is_active = 1 ORDER BY id ASC LIMIT 1').fetchone()
        if row:
            return dict(row)
        return {'platform': 'NeetCode', 'target_count': 2, 'time_str': '7:30 PM', 'frequency': 'Every day'}

@app.context_processor
def inject_global_data():
    return {
        'today_date_str': get_today_formatted(),
        'is_diary_unlocked': session.get('diary_unlocked', False)
    }

# ================= PAGE ROUTES =================

@app.route('/')
def home():
    focus = get_today_focus()
    reminder = get_active_reminder()
    
    target = focus.get('target_count', 2)
    completed = focus.get('completed_count', 0)
    percent = int((completed / target * 100)) if target > 0 else 0
    if percent > 100:
        percent = 100
        
    return render_template('index.html',
                           page='home',
                           focus=focus,
                           reminder=reminder,
                           completed=completed,
                           target=target,
                           percent=percent)

# ---------- DIARY ROUTES ----------

@app.route('/diary/login', methods=['GET', 'POST'])
def diary_login():
    with get_db() as db:
        config = db.execute('SELECT * FROM diary_config LIMIT 1').fetchone()
        
    is_first_time = config is None
    error = None
    
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        if is_first_time:
            confirm = request.form.get('confirm_password', '').strip()
            if not password:
                error = "Password cannot be empty."
            elif password != confirm:
                error = "Passwords do not match."
            else:
                pw_hash = generate_password_hash(password)
                with get_db() as db:
                    db.execute('INSERT INTO diary_config (password_hash) VALUES (?)', (pw_hash,))
                    db.commit()
                session['diary_unlocked'] = True
                return redirect(url_for('diary_list'))
        else:
            if check_password_hash(config['password_hash'], password):
                session['diary_unlocked'] = True
                return redirect(url_for('diary_list'))
            else:
                error = "Incorrect password. Please try again."
                
    return render_template('diary-login.html', page='diary', is_first_time=is_first_time, error=error)

@app.route('/diary')
def diary_list():
    if not session.get('diary_unlocked'):
        return redirect(url_for('diary_login'))
        
    search_q = request.args.get('q', '').strip()
    with get_db() as db:
        if search_q:
            query = '%{}%'.format(search_q)
            entries = db.execute('''
                SELECT * FROM diary_entries 
                WHERE title LIKE ? OR content LIKE ? 
                ORDER BY entry_date DESC, id DESC
            ''', (query, query)).fetchall()
        else:
            entries = db.execute('''
                SELECT * FROM diary_entries ORDER BY entry_date DESC, id DESC
            ''').fetchall()
            
    return render_template('diary.html', page='diary', entries=[dict(e) for e in entries], search_q=search_q)

@app.route('/diary/entry/new', methods=['GET', 'POST'])
def diary_new():
    if not session.get('diary_unlocked'):
        return redirect(url_for('diary_login'))
        
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        entry_date = request.form.get('entry_date', '').strip() or get_today_str()
        
        if title and content:
            with get_db() as db:
                db.execute('''
                    INSERT INTO diary_entries (title, content, entry_date)
                    VALUES (?, ?, ?)
                ''', (title, content, entry_date))
                db.commit()
            return redirect(url_for('diary_list'))
            
    return render_template('diary-entry.html', page='diary', entry=None, today_str=get_today_str())

@app.route('/diary/entry/<int:entry_id>/edit', methods=['GET', 'POST'])
def diary_edit(entry_id):
    if not session.get('diary_unlocked'):
        return redirect(url_for('diary_login'))
        
    with get_db() as db:
        entry = db.execute('SELECT * FROM diary_entries WHERE id = ?', (entry_id,)).fetchone()
        if not entry:
            return redirect(url_for('diary_list'))
            
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            entry_date = request.form.get('entry_date', '').strip() or entry['entry_date']
            
            if title and content:
                db.execute('''
                    UPDATE diary_entries
                    SET title = ?, content = ?, entry_date = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (title, content, entry_date, entry_id))
                db.commit()
                return redirect(url_for('diary_list'))
                
    return render_template('diary-entry.html', page='diary', entry=dict(entry), today_str=get_today_str())

@app.route('/diary/entry/<int:entry_id>/delete', methods=['POST'])
def diary_delete(entry_id):
    if not session.get('diary_unlocked'):
        return redirect(url_for('diary_login'))
        
    with get_db() as db:
        db.execute('DELETE FROM diary_entries WHERE id = ?', (entry_id,))
        db.commit()
    return redirect(url_for('diary_list'))

@app.route('/diary/lock')
def diary_lock():
    session.pop('diary_unlocked', None)
    return redirect(url_for('home'))

# ---------- FOCUS / CODING ROUTES ----------

@app.route('/focus', methods=['GET', 'POST'])
def focus_page():
    today = get_today_str()
    focus = get_today_focus()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_goal':
            platform = request.form.get('platform', 'NeetCode')
            target = int(request.form.get('target_count', 2))
            with get_db() as db:
                db.execute('''
                    UPDATE focus_goals 
                    SET platform = ?, target_count = ?
                    WHERE goal_date = ?
                ''', (platform, target, today))
                db.commit()
            return redirect(url_for('focus_page'))
            
        elif action == 'log_problem':
            title = request.form.get('problem_title', '').strip()
            difficulty = request.form.get('difficulty', 'Medium')
            notes = request.form.get('notes', '').strip()
            platform = focus.get('platform', 'NeetCode')
            
            if title:
                with get_db() as db:
                    db.execute('''
                        INSERT INTO focus_logs (log_date, platform, problem_title, difficulty, notes)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (today, platform, title, difficulty, notes))
                    
                    db.execute('''
                        UPDATE focus_goals
                        SET completed_count = completed_count + 1
                        WHERE goal_date = ?
                    ''', (today,))
                    db.commit()
            return redirect(url_for('focus_page'))
            
    with get_db() as db:
        logs = db.execute('''
            SELECT * FROM focus_logs WHERE log_date = ? ORDER BY id DESC
        ''', (today,)).fetchall()
        
    focus = get_today_focus()
    target = focus.get('target_count', 2)
    completed = focus.get('completed_count', 0)
    percent = int((completed / target * 100)) if target > 0 else 0
    if percent > 100:
        percent = 100
        
    return render_template('focus.html',
                           page='coding',
                           focus=focus,
                           completed=completed,
                           target=target,
                           percent=percent,
                           logs=[dict(l) for l in logs])

# ---------- REMINDERS ROUTES ----------

@app.route('/reminders', methods=['GET', 'POST'])
def reminders_page():
    if request.method == 'POST':
        platform = request.form.get('platform', 'NeetCode')
        target_count = int(request.form.get('target_count', 2))
        time_str = request.form.get('time_str', '7:30 PM').strip()
        frequency = request.form.get('frequency', 'Every day').strip()
        
        with get_db() as db:
            db.execute('''
                INSERT INTO reminders (platform, target_count, time_str, frequency, is_active)
                VALUES (?, ?, ?, ?, 1)
            ''', (platform, target_count, time_str, frequency))
            db.commit()
        return redirect(url_for('reminders_page'))
        
    with get_db() as db:
        reminders = db.execute('SELECT * FROM reminders ORDER BY id DESC').fetchall()
        
    return render_template('reminders.html', page='reminders', reminders=[dict(r) for r in reminders])

@app.route('/reminders/<int:rem_id>/toggle', methods=['POST'])
def reminder_toggle(rem_id):
    with get_db() as db:
        rem = db.execute('SELECT is_active FROM reminders WHERE id = ?', (rem_id,)).fetchone()
        if rem:
            new_status = 0 if rem['is_active'] == 1 else 1
            db.execute('UPDATE reminders SET is_active = ? WHERE id = ?', (new_status, rem_id))
            db.commit()
    return redirect(url_for('reminders_page'))

@app.route('/reminders/<int:rem_id>/delete', methods=['POST'])
def reminder_delete(rem_id):
    with get_db() as db:
        db.execute('DELETE FROM reminders WHERE id = ?', (rem_id,))
        db.commit()
    return redirect(url_for('reminders_page'))

# ---------- SETTINGS ROUTE ----------

@app.route('/settings', methods=['GET', 'POST'])
def settings_page():
    msg = None
    msg_type = 'success'
    
    with get_db() as db:
        config = db.execute('SELECT * FROM diary_config LIMIT 1').fetchone()
        
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'change_password':
            curr_pw = request.form.get('current_password', '').strip()
            new_pw = request.form.get('new_password', '').strip()
            confirm_pw = request.form.get('confirm_password', '').strip()
            
            if not config:
                msg = "Diary password has not been set yet."
                msg_type = 'danger'
            elif not check_password_hash(config['password_hash'], curr_pw):
                msg = "Current password is incorrect."
                msg_type = 'danger'
            elif not new_pw or new_pw != confirm_pw:
                msg = "New passwords do not match or are empty."
                msg_type = 'danger'
            else:
                new_hash = generate_password_hash(new_pw)
                with get_db() as db:
                    db.execute('UPDATE diary_config SET password_hash = ? WHERE id = ?', (new_hash, config['id']))
                    db.commit()
                msg = "Diary password updated successfully!"
                msg_type = 'success'
                
        elif action == 'reset_data':
            with get_db() as db:
                db.execute('DELETE FROM focus_logs')
                db.execute('DELETE FROM focus_goals')
                db.execute('DELETE FROM diary_entries')
                db.commit()
            session.pop('diary_unlocked', None)
            msg = "Application data reset successfully."
            msg_type = 'info'
            
    return render_template('settings.html', page='settings', has_password=config is not None, msg=msg, msg_type=msg_type)

# ---------- JSON API ENDPOINTS ----------

@app.route('/api/progress')
def api_progress():
    focus = get_today_focus()
    reminder = get_active_reminder()
    target = focus.get('target_count', 2)
    completed = focus.get('completed_count', 0)
    percent = int((completed / target * 100)) if target > 0 else 0
    if percent > 100:
        percent = 100
        
    return jsonify({
        'today_date': get_today_formatted(),
        'platform': focus.get('platform', 'NeetCode'),
        'completed': completed,
        'target': target,
        'percent': percent,
        'reminder_time': reminder.get('time_str', '7:30 PM')
    })

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
