from flask import render_template, request, redirect, url_for, flash, jsonify, abort, session
from flask_login import login_user, login_required, logout_user, current_user
from app import db, login_manager
from app.models import User, Admin, Subject, Chapter, Quiz, Question, Score
from datetime import datetime, timedelta
from functools import wraps
from flask import current_app as app

@login_manager.user_loader
def load_user(user_id):
    # Check if it's an admin ID (prefixed with 'admin_')
    if user_id.startswith('admin_'):
        return Admin.query.get(int(user_id[6:]))  # Remove 'admin_' prefix
    else:
        return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Access denied. Admin privileges required.')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.is_admin():
            flash('Access denied. Student account required.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('user_dashboard'))
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        logout_user()  # Logout regular user if trying to access admin login
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and admin.check_password(password):
            login_user(admin)
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials')
    return render_template('admin_login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        qualification = request.form.get('qualification')
        dob = datetime.strptime(request.form.get('dob'), '%Y-%m-%d')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))
            
        user = User(email=email, full_name=full_name, 
                   qualification=qualification, dob=dob)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    subjects = Subject.query.all()
    chapters = Chapter.query.all()
    quizzes = Quiz.query.all()
    
    # Get all students
    students = User.query.all()
    
    # Overall statistics
    overall_stats = {
        'total_students': len(students),
        'total_quizzes': len(quizzes),
        'total_attempts': Score.query.count(),
        'avg_score': db.session.query(db.func.avg(Score.total_scored * 100.0 / Score.total_questions)).scalar() or 0,
        'avg_time_taken': db.session.query(db.func.avg(Score.time_taken)).scalar() or 0
    }
    
    # Get hourly attempt distribution
    hourly_attempts = db.session.query(
        db.func.extract('hour', Score.time_stamp_of_attempt).label('hour'),
        db.func.count().label('count')
    ).group_by('hour').all()
    
    # Get daily attempt distribution for last 7 days
    seven_days_ago = datetime.now() - timedelta(days=7)
    daily_attempts = db.session.query(
        db.func.date(Score.time_stamp_of_attempt).label('date'),
        db.func.count().label('count')
    ).filter(Score.time_stamp_of_attempt >= seven_days_ago)\
     .group_by('date').all()
    
    # Get quiz-wise average time taken
    quiz_time_stats = db.session.query(
        Quiz.id,
        Quiz.chapter_id,
        db.func.avg(Score.time_taken).label('avg_time')
    ).join(Score).group_by(Quiz.id).all()
    
    # Add time-based metrics to overall_stats
    overall_stats.update({
        'hourly_attempts': {str(hour): count for hour, count in hourly_attempts},
        'daily_attempts': {str(date): count for date, count in daily_attempts},
        'quiz_time_stats': {quiz_id: {'chapter_id': chapter_id, 'avg_time': float(avg_time)} 
                           for quiz_id, chapter_id, avg_time in quiz_time_stats}
    })
    
    # Student rankings
    student_rankings = []
    for student in students:
        scores = Score.query.filter_by(user_id=student.id).all()
        if scores:
            avg_score = sum(s.total_scored * 100.0 / s.total_questions for s in scores) / len(scores)
            total_attempts = len(scores)
            # Calculate subject-wise performance
            subject_performance = {}
            for subject in subjects:
                subject_quizzes = Quiz.query.join(Chapter).filter(Chapter.subject_id == subject.id).all()
                if subject_quizzes:
                    quiz_ids = [q.id for q in subject_quizzes]
                    subject_scores = [s for s in scores if s.quiz_id in quiz_ids]
                    if subject_scores:
                        subject_avg = sum(s.total_scored * 100.0 / s.total_questions for s in subject_scores) / len(subject_scores)
                        subject_performance[subject.name] = subject_avg
            
            student_rankings.append({
                'student': student,
                'avg_score': avg_score,
                'total_attempts': total_attempts,
                'subject_performance': subject_performance
            })
    
    # Sort by average score
    student_rankings.sort(key=lambda x: x['avg_score'], reverse=True)
    
    # Add rank to each student
    for i, ranking in enumerate(student_rankings, 1):
        ranking['rank'] = i
    
    # Subject-wise statistics
    subject_stats = []
    for subject in subjects:
        subject_quizzes = Quiz.query.join(Chapter).filter(Chapter.subject_id == subject.id).all()
        if subject_quizzes:
            quiz_ids = [q.id for q in subject_quizzes]
            scores = Score.query.filter(Score.quiz_id.in_(quiz_ids)).all()
            if scores:
                all_scores = [s.total_scored * 100.0 / s.total_questions for s in scores]
                avg_score = sum(all_scores) / len(all_scores)
                # Calculate median
                sorted_scores = sorted(all_scores)
                mid = len(sorted_scores) // 2
                median = sorted_scores[mid] if len(sorted_scores) % 2 else (sorted_scores[mid-1] + sorted_scores[mid]) / 2
                # Calculate mode
                from statistics import mode, multimode
                try:
                    score_mode = mode(all_scores)
                except:
                    score_mode = multimode(all_scores)[0]  # Take first mode if multiple exist
                
                subject_stats.append({
                    'subject': subject,
                    'avg_score': avg_score,
                    'median_score': median,
                    'mode_score': score_mode,
                    'total_attempts': len(scores),
                    'num_quizzes': len(subject_quizzes)
                })
    
    # Chapter-wise statistics
    chapter_stats = []
    for chapter in chapters:
        chapter_quizzes = Quiz.query.filter_by(chapter_id=chapter.id).all()
        if chapter_quizzes:
            quiz_ids = [q.id for q in chapter_quizzes]
            scores = Score.query.filter(Score.quiz_id.in_(quiz_ids)).all()
            if scores:
                all_scores = [s.total_scored * 100.0 / s.total_questions for s in scores]
                avg_score = sum(all_scores) / len(all_scores)
                # Calculate median
                sorted_scores = sorted(all_scores)
                mid = len(sorted_scores) // 2
                median = sorted_scores[mid] if len(sorted_scores) % 2 else (sorted_scores[mid-1] + sorted_scores[mid]) / 2
                
                chapter_stats.append({
                    'chapter': chapter,
                    'avg_score': avg_score,
                    'median_score': median,
                    'total_attempts': len(scores),
                    'num_quizzes': len(chapter_quizzes)
                })
    
    return render_template('admin_dashboard.html',
                         subjects=subjects,
                         chapters=chapters,
                         quizzes=quizzes,
                         overall_stats=overall_stats,
                         student_rankings=student_rankings,
                         subject_stats=subject_stats,
                         chapter_stats=chapter_stats)

@app.route('/user/dashboard')
@login_required
@student_required
def user_dashboard():
    # Get available quizzes (future quizzes)
    available_quizzes = Quiz.query.filter(Quiz.date_of_quiz > datetime.now()).all()
    
    # Get user's quiz attempts
    user_scores = Score.query.filter_by(user_id=current_user.id).order_by(Score.time_stamp_of_attempt.desc()).all()
    
    # Calculate overall statistics
    total_attempts = len(user_scores)
    if total_attempts > 0:
        avg_score = sum(s.total_scored * 100.0 / s.total_questions for s in user_scores) / total_attempts
        personal_best = max((s.total_scored * 100.0 / s.total_questions) for s in user_scores)
        recent_avg = sum(s.total_scored * 100.0 / s.total_questions for s in user_scores[:5]) / min(5, total_attempts)
    else:
        avg_score = personal_best = recent_avg = 0
    
    overall_stats = {
        'total_attempts': total_attempts,
        'avg_score': avg_score,
        'personal_best': personal_best,
        'recent_avg': recent_avg
    }
    
    # Calculate user's ranking
    all_students = User.query.all()
    rankings = []
    for student in all_students:
        student_scores = Score.query.filter_by(user_id=student.id).all()
        if student_scores:
            student_avg = sum(s.total_scored * 100.0 / s.total_questions for s in student_scores) / len(student_scores)
            rankings.append((student.id, student_avg))
    
    # Sort by average score
    rankings.sort(key=lambda x: x[1], reverse=True)

    # Check if the user is in the rankings
    user_rank = next((i for i, (student_id, _) in enumerate(rankings, 1) if student_id == current_user.id), None)
    total_students = len(rankings)
    
    ranking_info = {
        'rank': user_rank if user_rank is not None else 'N/A',
        'total_students': total_students,
        'percentile': ((total_students - user_rank + 1) / total_students) * 100 if user_rank is not None and total_students > 0 else 0
    }
    
    # Calculate subject-wise performance
    subjects = Subject.query.all()
    subject_performance = []
    
    for subject in subjects:
        # Get all quizzes for this subject
        subject_quizzes = Quiz.query.join(Chapter).filter(Chapter.subject_id == subject.id).all()
        if subject_quizzes:
            quiz_ids = [q.id for q in subject_quizzes]
            subject_scores = [s for s in user_scores if s.quiz_id in quiz_ids]
            
            if subject_scores:
                total_subject_attempts = len(subject_scores)
                subject_avg = sum(s.total_scored * 100.0 / s.total_questions for s in subject_scores) / total_subject_attempts
                subject_best = max(s.total_scored * 100.0 / s.total_questions for s in subject_scores)
                
                # Get chapter breakdown
                chapters = Chapter.query.filter_by(subject_id=subject.id).all()
                chapter_stats = []
                
                for chapter in chapters:
                    chapter_quizzes = [q for q in subject_quizzes if q.chapter_id == chapter.id]
                    if chapter_quizzes:
                        chapter_scores = [s for s in subject_scores if s.quiz_id in [q.id for q in chapter_quizzes]]
                        if chapter_scores:
                            chapter_avg = sum(s.total_scored * 100.0 / s.total_questions for s in chapter_scores) / len(chapter_scores)
                            chapter_stats.append({
                                'chapter': chapter,
                                'avg_score': chapter_avg,
                                'attempts': len(chapter_scores)
                            })
                
                subject_performance.append({
                    'subject': subject,
                    'avg_score': subject_avg,
                    'best_score': subject_best,
                    'total_attempts': total_subject_attempts,
                    'chapters': chapter_stats
                })
    
    return render_template('user_dashboard.html',
                         available_quizzes=available_quizzes,
                         user_scores=user_scores,
                         overall_stats=overall_stats,
                         subject_performance=subject_performance,
                         ranking_info=ranking_info)

# Admin routes for managing subjects, chapters, and quizzes
@app.route('/admin/subject/add', methods=['POST'])
@login_required
@admin_required
def add_subject():
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Subject name is required')
        return redirect(url_for('admin_dashboard'))
        
    subject = Subject(name=name, description=description)
    db.session.add(subject)
    db.session.commit()
    
    flash('Subject added successfully')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/subject/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_subject(id):
    subject = Subject.query.get_or_404(id)
    db.session.delete(subject)
    db.session.commit()
    flash('Subject deleted successfully')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/chapter/add', methods=['POST'])
@login_required
@admin_required
def add_chapter():
    subject_id = request.form.get('subject_id')
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not all([subject_id, name]):
        flash('Subject and chapter name are required')
        return redirect(url_for('admin_dashboard'))
        
    subject = Subject.query.get_or_404(subject_id)
    chapter = Chapter(subject=subject, name=name, description=description)
    db.session.add(chapter)
    db.session.commit()
    
    flash('Chapter added successfully')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/chapter/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_chapter(id):
    chapter = Chapter.query.get_or_404(id)
    db.session.delete(chapter)
    db.session.commit()
    flash('Chapter deleted successfully')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/quiz/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_quiz():
    if request.method == 'POST':
        chapter_id = request.form.get('chapter_id')
        date_of_quiz = datetime.strptime(request.form.get('date_of_quiz'), '%Y-%m-%dT%H:%M')
        time_duration = int(request.form.get('time_duration'))
        remarks = request.form.get('remarks')
        
        if not all([chapter_id, date_of_quiz, time_duration]):
            flash('All fields are required')
            return redirect(url_for('create_quiz'))
            
        # Validate quiz date is in the future
        if date_of_quiz <= datetime.now():
            flash('Quiz date must be in the future')
            return redirect(url_for('create_quiz'))
            
        quiz = Quiz(
            chapter_id=chapter_id,
            date_of_quiz=date_of_quiz,
            time_duration=time_duration,
            remarks=remarks
        )
        db.session.add(quiz)
        db.session.commit()
        
        questions_data = parse_questions_from_form(request.form)
        if not questions_data:
            flash('At least one question is required')
            db.session.delete(quiz)
            db.session.commit()
            return redirect(url_for('create_quiz'))
            
        for q_data in questions_data:
            # Validate all question fields are present
            if not all([
                q_data['statement'],
                q_data['option1'],
                q_data['option2'],
                q_data['option3'],
                q_data['option4'],
                q_data['correct_option']
            ]):
                flash('All question fields are required')
                db.session.delete(quiz)
                db.session.commit()
                return redirect(url_for('create_quiz'))
                
            question = Question(
                quiz_id=quiz.id,
                question_statement=q_data['statement'].strip(),
                option1=q_data['option1'].strip(),
                option2=q_data['option2'].strip(),
                option3=q_data['option3'].strip(),
                option4=q_data['option4'].strip(),
                correct_option=int(q_data['correct_option'])
            )
            db.session.add(question)
        
        try:
            db.session.commit()
            flash('Quiz created successfully')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating quiz. Please try again.')
            return redirect(url_for('create_quiz'))
        
    chapters = Chapter.query.join(Subject).order_by(Subject.name, Chapter.name).all()
    return render_template('quiz_form.html', chapters=chapters)

@app.route('/admin/quiz/<int:quiz_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if quiz has been attempted
    if Score.query.filter_by(quiz_id=quiz_id).first():
        flash('Cannot edit quiz that has been attempted')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        chapter_id = request.form.get('chapter_id')
        date_of_quiz = datetime.strptime(request.form.get('date_of_quiz'), '%Y-%m-%dT%H:%M')
        time_duration = int(request.form.get('time_duration'))
        remarks = request.form.get('remarks')
        
        if not all([chapter_id, date_of_quiz, time_duration]):
            flash('All fields are required')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))
            
        # Validate quiz date is in the future
        if date_of_quiz <= datetime.now():
            flash('Quiz date must be in the future')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))
            
        quiz.chapter_id = chapter_id
        quiz.date_of_quiz = date_of_quiz
        quiz.time_duration = time_duration
        quiz.remarks = remarks
        
        # Delete existing questions
        Question.query.filter_by(quiz_id=quiz.id).delete()
        
        # Add new questions
        questions_data = parse_questions_from_form(request.form)
        if not questions_data:
            flash('At least one question is required')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))
            
        for q_data in questions_data:
            # Validate all question fields are present
            if not all([
                q_data['statement'],
                q_data['option1'],
                q_data['option2'],
                q_data['option3'],
                q_data['option4'],
                q_data['correct_option']
            ]):
                flash('All question fields are required')
                return redirect(url_for('edit_quiz', quiz_id=quiz_id))
                
            question = Question(
                quiz_id=quiz.id,
                question_statement=q_data['statement'].strip(),
                option1=q_data['option1'].strip(),
                option2=q_data['option2'].strip(),
                option3=q_data['option3'].strip(),
                option4=q_data['option4'].strip(),
                correct_option=int(q_data['correct_option'])
            )
            db.session.add(question)
        
        try:
            db.session.commit()
            flash('Quiz updated successfully')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating quiz. Please try again.')
            return redirect(url_for('edit_quiz', quiz_id=quiz_id))
        
    chapters = Chapter.query.join(Subject).order_by(Subject.name, Chapter.name).all()
    return render_template('quiz_form.html', quiz=quiz, chapters=chapters)

@app.route('/admin/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Check if quiz has been attempted
    if Score.query.filter_by(quiz_id=quiz_id).first():
        flash('Cannot delete quiz that has been attempted')
        return redirect(url_for('admin_dashboard'))
    
    try:
        # Delete all questions first
        Question.query.filter_by(quiz_id=quiz_id).delete()
        db.session.delete(quiz)
        db.session.commit()
        flash('Quiz deleted successfully')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting quiz. Please try again.')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/quiz/<int:quiz_id>/questions')
@login_required
@admin_required
def view_quiz_questions(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    return render_template('view_questions.html', quiz=quiz)

@app.route('/admin/quiz/<int:quiz_id>/question/add', methods=['POST'])
@login_required
@admin_required
def add_question(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    
    statement = request.form.get('statement')
    option1 = request.form.get('option1')
    option2 = request.form.get('option2')
    option3 = request.form.get('option3')
    option4 = request.form.get('option4')
    correct_option = request.form.get('correct_option')
    
    if not all([statement, option1, option2, option3, option4, correct_option]):
        flash('All fields are required')
        return redirect(url_for('view_quiz_questions', quiz_id=quiz_id))
    
    question = Question(
        quiz_id=quiz_id,
        question_statement=statement.strip(),
        option1=option1.strip(),
        option2=option2.strip(),
        option3=option3.strip(),
        option4=option4.strip(),
        correct_option=int(correct_option)
    )
    db.session.add(question)
    db.session.commit()
    
    flash('Question added successfully')
    return redirect(url_for('view_quiz_questions', quiz_id=quiz_id))

@app.route('/admin/question/<int:question_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    
    question.question_statement = request.form.get('statement').strip()
    question.option1 = request.form.get('option1').strip()
    question.option2 = request.form.get('option2').strip()
    question.option3 = request.form.get('option3').strip()
    question.option4 = request.form.get('option4').strip()
    question.correct_option = int(request.form.get('correct_option'))
    
    db.session.commit()
    flash('Question updated successfully')
    return redirect(url_for('view_quiz_questions', quiz_id=question.quiz_id))

@app.route('/admin/question/<int:question_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    quiz_id = question.quiz_id
    db.session.delete(question)
    db.session.commit()
    flash('Question deleted successfully')
    return redirect(url_for('view_quiz_questions', quiz_id=quiz_id))

@app.route('/quiz/<int:quiz_id>/start')
@login_required
@student_required
def start_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    now = datetime.now()
    
    # Check if quiz has ended
    quiz_end_time = quiz.date_of_quiz + timedelta(minutes=quiz.time_duration)
    if now > quiz_end_time:
        flash('This quiz has ended')
        return redirect(url_for('user_dashboard'))
    
    # Check if user has already attempted
    if Score.query.filter_by(quiz_id=quiz_id, user_id=current_user.id).first():
        flash('You have already attempted this quiz')
        return redirect(url_for('user_dashboard'))
    
    # Check if quiz has questions
    if not quiz.questions:
        flash('This quiz has no questions')
        return redirect(url_for('user_dashboard'))
    
    # Calculate quiz duration based on time remaining until quiz end
    remaining_time = min(
        quiz.time_duration,
        int((quiz_end_time - now).total_seconds() / 60)
    )
    
    if remaining_time <= 0:
        flash('This quiz has ended')
        return redirect(url_for('user_dashboard'))
    
    # Store quiz timing in session
    quiz_start = now
    quiz_end = quiz_start + timedelta(minutes=remaining_time)
    
    session['quiz_start_time'] = quiz_start.timestamp()
    session['quiz_end_time'] = quiz_end.timestamp()
    session['quiz_id'] = quiz_id  # Store quiz ID to prevent session reuse
    
    return render_template('take_quiz.html',
                         quiz=quiz,
                         remaining_time=remaining_time,
                         now=now,
                         quiz_end_time=quiz_end)

@app.route('/quiz/<int:quiz_id>/submit', methods=['POST'])
@login_required
@student_required
def submit_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    now = datetime.now()
    
    # Verify quiz session
    session_quiz_id = session.get('quiz_id')
    quiz_start_time = session.get('quiz_start_time')
    quiz_end_time = session.get('quiz_end_time')
    
    if not all([session_quiz_id, quiz_start_time, quiz_end_time]) or session_quiz_id != quiz_id:
        flash('Invalid quiz session')
        return redirect(url_for('user_dashboard'))
    
    quiz_start_time = datetime.fromtimestamp(quiz_start_time)
    quiz_end_time = datetime.fromtimestamp(quiz_end_time)
    
    # Check if quiz time has expired
    if now > quiz_end_time:
        flash('Quiz time has expired')
        # Continue to process answers even if time expired
    
    # Check if user has already attempted
    if Score.query.filter_by(quiz_id=quiz_id, user_id=current_user.id).first():
        flash('You have already attempted this quiz')
        return redirect(url_for('user_dashboard'))
    
    total_questions = len(quiz.questions)
    if total_questions == 0:
        flash('This quiz has no questions')
        return redirect(url_for('user_dashboard'))
    
    correct_answers = 0
    for question in quiz.questions:
        user_answer = request.form.get(f'answer_{question.id}')
        if user_answer and int(user_answer) == question.correct_option:
            correct_answers += 1
    
    # Calculate time taken in minutes
    time_taken = int((now - quiz_start_time).total_seconds() / 60)
    
    score = Score(
        quiz_id=quiz_id,
        user_id=current_user.id,
        total_scored=correct_answers,
        total_questions=total_questions,
        time_stamp_of_attempt=now,
        time_taken=time_taken
    )
    db.session.add(score)
    db.session.commit()
    
    # Clear quiz session
    session.pop('quiz_start_time', None)
    session.pop('quiz_end_time', None)
    
    flash(f'Quiz submitted successfully. You scored {correct_answers} out of {total_questions}')
    return redirect(url_for('user_dashboard'))

@app.route('/attempt/<int:attempt_id>')
@login_required
def view_attempt(attempt_id):
    score = Score.query.get_or_404(attempt_id)
    
    # Only allow the user who took the quiz or an admin to view the attempt
    if score.user_id != current_user.id and not current_user.is_admin():
        flash('Access denied')
        return redirect(url_for('user_dashboard'))
    
    return render_template('view_attempt.html', score=score)

def parse_questions_from_form(form):
    questions = []
    i = 0
    while True:
        statement = form.get(f'questions[{i}][statement]')
        if not statement:
            break
            
        questions.append({
            'statement': statement,
            'option1': form.get(f'questions[{i}][option1]'),
            'option2': form.get(f'questions[{i}][option2]'),
            'option3': form.get(f'questions[{i}][option3]'),
            'option4': form.get(f'questions[{i}][option4]'),
            'correct_option': form.get(f'questions[{i}][correct_option]')
        })
        i += 1
    return questions
